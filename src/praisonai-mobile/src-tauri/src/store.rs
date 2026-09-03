//! Durable, atomic storage for the webview.
//!
//! WHY THIS CRATE HAS TO OWN IT. Until now `StoragePort` had exactly one
//! implementation, `adapters/src/web/storage.ts`, over `localStorage` — and
//! `platform.ts` handed it to the Tauri build too. In WKWebView `localStorage`
//! lives in a WebKit data store the system is free to EVICT under storage
//! pressure: the user does nothing wrong, opens the app, and their history is
//! gone with no error anywhere. Android's WebView is better but is still
//! emptied by ordinary "clear cache" flows. Meanwhile `ui/src/i18n/strings.ts`
//! tells the user after a crash that "Your conversations are saved". This
//! module is what makes that sentence true.
//!
//! WHY NOT `tauri-plugin-store`. It was the obvious candidate and it fails the
//! one clause that matters. Its `save()` serialises the WHOLE store and writes
//! it with a plain `fs::write` — truncate, then write — so a process killed
//! mid-write leaves a truncated JSON file, and the next launch loses not one
//! chat but ALL of them. It is also a single in-memory map per file, so one
//! chat write rewrites every chat. `StoragePort` is a key/value store of
//! opaque strings with an explicit atomicity clause; one file per key plus
//! write-temp-then-rename satisfies it in about a hundred lines, with no new
//! dependency and no ACL surface.
//!
//! THE ATOMICITY RULE, spelled out because it is the whole point:
//!
//!   write(tmp) -> fsync(tmp) -> rename(tmp, final) -> fsync(dir)
//!
//! `rename(2)` within a directory is atomic: a concurrent reader opening the
//! final path sees either the complete old file or the complete new one, never
//! a prefix. The `fsync` before the rename is what stops the rename from being
//! ordered ahead of the data on a crash, which would leave a file that exists,
//! has the right name, and contains zeroes. iOS kills suspended apps with no
//! further callback, so "interrupted halfway" is a normal Tuesday rather than a
//! crash scenario — `core/src/ports/storage.ts` says so in as many words.

use std::collections::HashSet;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

/// The command names the webview invokes. `adapters/src/tauri/storage.ts`
/// names the same five strings, and `tools/storage-seam.test.mjs` compares the
/// two files — a rename on one side alone is otherwise SILENT, and silent here
/// means every chat write fails and the app carries on looking fine.
pub const CMD_READ: &str = "storage_read";
pub const CMD_WRITE: &str = "storage_write";
pub const CMD_REMOVE: &str = "storage_remove";
pub const CMD_LIST_IDS: &str = "storage_list_ids";
pub const CMD_CLEAR: &str = "storage_clear";

/// The directory under the app's data dir that everything below lives in.
pub const STORE_DIR: &str = "store";

/// The namespaces `core/src/ports/storage.ts` declares, and no others.
///
/// This list is the path-traversal defence, not a nicety: the namespace is a
/// directory name, so accepting an arbitrary string would let `..` out of the
/// app's data directory entirely. An allowlist cannot be talked around by a
/// cleverer escape sequence.
pub const NAMESPACES: [&str; 4] = ["chats", "settings", "drafts", "cache"];

/// The longest encoded file name we will create.
///
/// Refused with a NAME rather than passed to the OS, which would fail with
/// ENAMETOOLONG on one filesystem and silently truncate — and therefore
/// collide two chats into one file — on another.
const MAX_ENCODED_LEN: usize = 200;

/// Distinguishes concurrent temp files within one process. The pid alone is
/// not enough: two threads writing the same key at once would otherwise pick
/// the same temp name and interleave into it, which is exactly the torn write
/// this module exists to prevent.
static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Bytes that may appear literally in a file name.
///
/// LOWERCASE ONLY, deliberately. iOS ships APFS case-INSENSITIVE by default
/// and macOS has for two decades, so `chat-A` and `chat-a` would be one file
/// on a phone and two files in every test written on a case-sensitive box.
/// Encoding uppercase means the mapping is injective on every filesystem.
/// `.` is excluded too, so no encoded id can ever look like a temp file.
fn is_literal(byte: u8) -> bool {
    byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-' || byte == b'_'
}

/// A storage id as a file name. Injective, reversible, and incapable of
/// naming a parent directory.
pub fn encode_id(id: &str) -> String {
    let mut out = String::with_capacity(id.len());
    for byte in id.as_bytes() {
        if is_literal(*byte) {
            out.push(*byte as char);
        } else {
            // `~` is itself encoded (as `~7e`), so the escape can never be
            // confused with a literal and decoding is unambiguous.
            out.push('~');
            out.push_str(&format!("{byte:02x}"));
        }
    }
    out
}

/// The inverse. `None` for anything this module did not write — a temp file, a
/// `.DS_Store`, a file dropped in by a backup tool — so `list_ids` reports
/// only real ids rather than inventing one.
pub fn decode_id(name: &str) -> Option<String> {
    let bytes = name.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'~' {
            let hex = name.get(i + 1..i + 3)?;
            out.push(u8::from_str_radix(hex, 16).ok()?);
            i += 3;
        } else {
            if !is_literal(bytes[i]) {
                return None;
            }
            out.push(bytes[i]);
            i += 1;
        }
    }
    String::from_utf8(out).ok()
}

/// A namespace, or an error naming the one that was refused.
fn checked_namespace(namespace: &str) -> Result<&str, String> {
    NAMESPACES
        .iter()
        .find(|known| **known == namespace)
        .copied()
        .ok_or_else(|| format!("unknown storage namespace {namespace:?}"))
}

/// Files under the app's data directory, one per key.
#[derive(Debug, Clone)]
pub struct FileStore {
    root: PathBuf,
}

impl FileStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    fn namespace_dir(&self, namespace: &str) -> Result<PathBuf, String> {
        Ok(self.root.join(checked_namespace(namespace)?))
    }

    fn path_for(&self, namespace: &str, id: &str) -> Result<PathBuf, String> {
        let encoded = encode_id(id);
        if encoded.is_empty() {
            return Err("a storage id may not be empty".to_string());
        }
        if encoded.len() > MAX_ENCODED_LEN {
            return Err(format!(
                "storage id is too long to store ({} bytes encoded, limit {MAX_ENCODED_LEN})",
                encoded.len()
            ));
        }
        Ok(self.namespace_dir(namespace)?.join(encoded))
    }

    /// `Ok(None)` for a missing key. Absence is not an error; only I/O is —
    /// which is the difference between "no such chat" and "the disk is
    /// failing", and the caller treats those very differently.
    pub fn read(&self, namespace: &str, id: &str) -> Result<Option<String>, String> {
        let path = self.path_for(namespace, id)?;
        match fs::read(&path) {
            Ok(bytes) => String::from_utf8(bytes)
                .map(Some)
                // Not `from_utf8_lossy`: replacing bytes with U+FFFD would
                // hand the repository a JSON document that parses to the wrong
                // text, and it would then be saved back that way.
                .map_err(|error| format!("{} is not valid UTF-8: {error}", path.display())),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
            Err(error) => Err(format!("could not read {}: {error}", path.display())),
        }
    }

    /// Atomic. See the module header: temp, fsync, rename, fsync the directory.
    pub fn write(&self, namespace: &str, id: &str, value: &str) -> Result<(), String> {
        let path = self.path_for(namespace, id)?;
        let dir = path
            .parent()
            .ok_or_else(|| format!("{} has no parent directory", path.display()))?
            .to_path_buf();
        fs::create_dir_all(&dir).map_err(|e| format!("could not create {}: {e}", dir.display()))?;

        let temp = dir.join(format!(
            ".tmp.{}.{}",
            std::process::id(),
            TEMP_COUNTER.fetch_add(1, Ordering::Relaxed)
        ));

        // Scoped, so the handle is closed before the rename. Windows refuses to
        // rename over an open file, and this crate builds for desktop too.
        let written = (|| -> io::Result<()> {
            let mut file = fs::File::create(&temp)?;
            file.write_all(value.as_bytes())?;
            // The one line that makes the rename meaningful. Without it the
            // metadata operation can reach the disk before the data, and a
            // power loss leaves a correctly-named file full of zeroes.
            file.sync_all()?;
            Ok(())
        })();

        if let Err(error) = written {
            // Best effort: a leftover temp is invisible to `list_ids` (it
            // does not decode) but there is no reason to leave it.
            let _ = fs::remove_file(&temp);
            return Err(format!("could not write {}: {error}", temp.display()));
        }

        if let Err(error) = fs::rename(&temp, &path) {
            let _ = fs::remove_file(&temp);
            return Err(format!(
                "could not replace {}: {error}",
                path.display()
            ));
        }

        // The rename itself is a directory operation and needs its own flush to
        // survive a power loss. Best effort: a filesystem that refuses to open
        // a directory for sync (Windows) is not a reason to report the write
        // as failed, because the data is already durable and in place.
        sync_dir(&dir);
        Ok(())
    }

    /// Removing an absent key succeeds — the caller wanted it gone and it is.
    pub fn remove(&self, namespace: &str, id: &str) -> Result<(), String> {
        let path = self.path_for(namespace, id)?;
        match fs::remove_file(&path) {
            Ok(()) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
            Err(error) => return Err(format!("could not remove {}: {error}", path.display())),
        }
        if let Some(dir) = path.parent() {
            sync_dir(dir);
        }
        Ok(())
    }

    /// Ids in one namespace. An untouched namespace has no directory yet and
    /// lists empty rather than failing.
    pub fn list_ids(&self, namespace: &str) -> Result<Vec<String>, String> {
        let dir = self.namespace_dir(namespace)?;
        let entries = match fs::read_dir(&dir) {
            Ok(entries) => entries,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(Vec::new()),
            Err(error) => return Err(format!("could not list {}: {error}", dir.display())),
        };

        let mut ids = Vec::new();
        // A `HashSet` because a case-insensitive filesystem can hand back the
        // same name twice under some sync tools, and a duplicated chat id
        // renders as two identical rows that both open the same conversation.
        let mut seen = HashSet::new();
        for entry in entries {
            let entry = entry.map_err(|e| format!("could not list {}: {e}", dir.display()))?;
            let Some(name) = entry.file_name().to_str().map(str::to_owned) else {
                continue;
            };
            // Anything this module did not write — a temp file mid-rename, a
            // .DS_Store, a backup tool's droppings — decodes to None and is
            // skipped rather than reported as a chat that cannot be read.
            let Some(id) = decode_id(&name) else { continue };
            if seen.insert(id.clone()) {
                ids.push(id);
            }
        }
        Ok(ids)
    }

    /// Empties one namespace and leaves the others.
    pub fn clear(&self, namespace: &str) -> Result<(), String> {
        let dir = self.namespace_dir(namespace)?;
        for id in self.list_ids(namespace)? {
            self.remove(namespace, &id)?;
        }
        sync_dir(&dir);
        Ok(())
    }
}

/// Flush a directory entry, so a rename survives a power loss.
#[cfg(unix)]
fn sync_dir(dir: &Path) {
    if let Ok(handle) = fs::File::open(dir) {
        let _ = handle.sync_all();
    }
}

/// Windows cannot open a directory as a file, and has no equivalent call.
/// The data is already durable; only the ordering guarantee is weaker.
#[cfg(not(unix))]
fn sync_dir(_dir: &Path) {}

// ---------------------------------------------------------------------------
// the Tauri commands
// ---------------------------------------------------------------------------

/// Where the store lives, resolved once at startup and held in Tauri state.
///
/// Resolved ONCE rather than per call, because `app_data_dir()` can fail and a
/// failure that surfaces on the fiftieth write is a failure nobody can
/// reproduce.
pub struct StoreState(pub FileStore);

/// Every argument is a single lowercase word on purpose: Tauri 2 maps JS
/// `camelCase` onto Rust `snake_case` parameters, and a two-word name is the
/// standing way to get a command that rejects every call with a deserialisation
/// error the webview reports as "storage failed".
#[tauri::command]
pub fn storage_read(
    state: tauri::State<'_, StoreState>,
    namespace: String,
    id: String,
) -> Result<Option<String>, String> {
    state.0.read(&namespace, &id)
}

#[tauri::command]
pub fn storage_write(
    state: tauri::State<'_, StoreState>,
    namespace: String,
    id: String,
    value: String,
) -> Result<(), String> {
    state.0.write(&namespace, &id, &value)
}

#[tauri::command]
pub fn storage_remove(
    state: tauri::State<'_, StoreState>,
    namespace: String,
    id: String,
) -> Result<(), String> {
    state.0.remove(&namespace, &id)
}

#[tauri::command]
pub fn storage_list_ids(
    state: tauri::State<'_, StoreState>,
    namespace: String,
) -> Result<Vec<String>, String> {
    state.0.list_ids(&namespace)
}

#[tauri::command]
pub fn storage_clear(
    state: tauri::State<'_, StoreState>,
    namespace: String,
) -> Result<(), String> {
    state.0.clear(&namespace)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A scratch directory under the OS temp dir. No `tempfile` dependency:
    /// adding one to reach an offline CI cache is a worse trade than eight
    /// lines here.
    struct Scratch(PathBuf);

    impl Scratch {
        fn new(label: &str) -> Self {
            let dir = std::env::temp_dir().join(format!(
                "praisonai-store-{label}-{}-{}",
                std::process::id(),
                TEMP_COUNTER.fetch_add(1, Ordering::Relaxed)
            ));
            let _ = fs::remove_dir_all(&dir);
            fs::create_dir_all(&dir).expect("scratch dir");
            Self(dir)
        }
        fn store(&self) -> FileStore {
            FileStore::new(&self.0)
        }
    }

    impl Drop for Scratch {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn a_value_round_trips_through_the_filesystem() {
        let scratch = Scratch::new("round-trip");
        let store = scratch.store();
        let payload = "{\"a\":\"line1\nline2\",\"b\":\"quo\\\"te\",\"c\":\"日本語 🎉\"}";
        store.write("chats", "c1", payload).unwrap();
        assert_eq!(store.read("chats", "c1").unwrap(), Some(payload.to_string()));
    }

    #[test]
    fn a_missing_key_is_absent_rather_than_an_error() {
        let scratch = Scratch::new("missing");
        assert_eq!(scratch.store().read("chats", "nope").unwrap(), None);
    }

    #[test]
    fn an_empty_string_is_a_value_not_an_absence() {
        // `||` instead of `??`, one language down. A deliberately blank
        // setting must not read back as "never configured".
        let scratch = Scratch::new("empty");
        let store = scratch.store();
        store.write("settings", "blank", "").unwrap();
        assert_eq!(store.read("settings", "blank").unwrap(), Some(String::new()));
    }

    #[test]
    fn a_value_survives_a_relaunch() {
        // The crash-recovery claim, at the layer that has to keep it. A second
        // FileStore over the same root is exactly what the next launch builds.
        let scratch = Scratch::new("relaunch");
        scratch.store().write("chats", "c1", "kept").unwrap();
        drop(scratch.store());
        let after_relaunch = FileStore::new(&scratch.0);
        assert_eq!(after_relaunch.read("chats", "c1").unwrap(), Some("kept".into()));
        assert_eq!(after_relaunch.list_ids("chats").unwrap(), vec!["c1".to_string()]);
    }

    #[test]
    fn a_write_interrupted_before_the_rename_leaves_the_old_value_intact() {
        // The iOS case, simulated: the app is killed after the temp file is
        // written and before the rename. `fs::write` straight to the final
        // path would have truncated it by now and the chat would be gone.
        let scratch = Scratch::new("interrupted");
        let store = scratch.store();
        store.write("chats", "c1", "the old conversation").unwrap();

        let dir = scratch.0.join("chats");
        let orphan = dir.join(".tmp.9999.0");
        fs::write(&orphan, "half of the new one").unwrap();

        assert_eq!(
            store.read("chats", "c1").unwrap(),
            Some("the old conversation".to_string()),
            "an unfinished write must not be visible at the real key"
        );
        assert_eq!(
            store.list_ids("chats").unwrap(),
            vec!["c1".to_string()],
            "a temp file must never be reported as a chat"
        );
    }

    #[test]
    fn a_completed_write_leaves_no_temp_file_behind() {
        let scratch = Scratch::new("no-temp");
        let store = scratch.store();
        for n in 0..5 {
            store.write("chats", "c1", &format!("value {n}")).unwrap();
        }
        let leftovers: Vec<String> = fs::read_dir(scratch.0.join("chats"))
            .unwrap()
            .map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
            .filter(|name| name.starts_with(".tmp."))
            .collect();
        assert!(leftovers.is_empty(), "temp files left behind: {leftovers:?}");
    }

    #[test]
    fn a_concurrent_reader_never_sees_a_torn_value() {
        // THE atomicity clause, exercised rather than asserted in prose.
        //
        // Ten threads rewrite one key with ten distinct 256KB payloads while a
        // reader reads it a thousand times. Every observation must be one of
        // the whole payloads or absent — never a prefix, never a mixture.
        // Replace the temp-then-rename with a plain `fs::write` and this test
        // fails within a few iterations; that mutation was run.
        use std::sync::mpsc;
        use std::thread;

        let scratch = Scratch::new("torn");
        let store = scratch.store();

        let payloads: Vec<String> = (0..10)
            .map(|n| char::from(b'a' + n as u8).to_string().repeat(256 * 1024))
            .collect();

        let (stop_tx, stop_rx) = mpsc::channel::<()>();
        let reader_store = store.clone();
        let reader_payloads = payloads.clone();
        let reader = thread::spawn(move || {
            let mut torn: Option<usize> = None;
            let mut reads = 0usize;
            while stop_rx.try_recv().is_err() {
                match reader_store.read("chats", "hot").unwrap() {
                    None => {}
                    Some(seen) => {
                        reads += 1;
                        if !reader_payloads.contains(&seen) {
                            torn = Some(seen.len());
                            break;
                        }
                    }
                }
            }
            (torn, reads)
        });

        let mut writers = Vec::new();
        for payload in payloads.clone() {
            let writer_store = store.clone();
            writers.push(thread::spawn(move || {
                for _ in 0..20 {
                    writer_store.write("chats", "hot", &payload).unwrap();
                }
            }));
        }
        for writer in writers {
            writer.join().unwrap();
        }
        let _ = stop_tx.send(());
        let (torn, reads) = reader.join().unwrap();

        assert_eq!(torn, None, "a reader saw a partial value of {torn:?} bytes");
        // The control. A reader that observed NOTHING would report no tearing
        // while proving nothing at all.
        assert!(reads > 0, "the reader never observed a value; the test proved nothing");
        assert!(payloads.contains(&store.read("chats", "hot").unwrap().unwrap()));
    }

    #[test]
    fn namespaces_are_separate_directories() {
        let scratch = Scratch::new("namespaces");
        let store = scratch.store();
        store.write("chats", "same", "chat value").unwrap();
        store.write("settings", "same", "settings value").unwrap();
        assert_eq!(store.read("chats", "same").unwrap(), Some("chat value".into()));
        assert_eq!(store.read("settings", "same").unwrap(), Some("settings value".into()));
        assert_eq!(store.list_ids("chats").unwrap(), vec!["same".to_string()]);
    }

    #[test]
    fn an_unknown_namespace_is_refused_rather_than_created() {
        // The traversal defence. `..` as a namespace would otherwise write
        // outside the app's data directory entirely.
        let scratch = Scratch::new("unknown-ns");
        let store = scratch.store();
        for bad in ["..", "../../etc", "keychain", ""] {
            assert!(store.write(bad, "x", "y").is_err(), "{bad:?} was accepted");
            assert!(store.read(bad, "x").is_err(), "{bad:?} was accepted");
            assert!(store.list_ids(bad).is_err(), "{bad:?} was accepted");
            assert!(store.clear(bad).is_err(), "{bad:?} was accepted");
            assert!(store.remove(bad, "x").is_err(), "{bad:?} was accepted");
        }
    }

    #[test]
    fn an_id_cannot_escape_its_namespace() {
        // `/` and `.` are encoded, so this is a file called `~2e~2e~2fboot`
        // inside chats/ rather than a write two directories up.
        let scratch = Scratch::new("escape");
        let store = scratch.store();
        store.write("chats", "../../boot", "payload").unwrap();
        assert_eq!(store.read("chats", "../../boot").unwrap(), Some("payload".into()));
        assert_eq!(store.list_ids("chats").unwrap(), vec!["../../boot".to_string()]);
        assert!(
            scratch.0.join("chats").join("~2e~2e~2f~2e~2e~2fboot").exists(),
            "the id was not encoded into a single flat file name"
        );
    }

    #[test]
    fn ids_differing_only_in_case_are_different_chats() {
        // macOS and iOS are case-insensitive by default. Without encoding the
        // uppercase, two chats share one file and one of them is overwritten —
        // on a phone, and never on a Linux CI box.
        let scratch = Scratch::new("case");
        let store = scratch.store();
        store.write("chats", "Chat-A", "upper").unwrap();
        store.write("chats", "chat-a", "lower").unwrap();
        assert_eq!(store.read("chats", "Chat-A").unwrap(), Some("upper".into()));
        assert_eq!(store.read("chats", "chat-a").unwrap(), Some("lower".into()));
        let mut ids = store.list_ids("chats").unwrap();
        ids.sort();
        assert_eq!(ids, vec!["Chat-A".to_string(), "chat-a".to_string()]);
    }

    #[test]
    fn encoding_round_trips_every_id_the_app_can_produce() {
        for id in [
            "c1",
            "0198f2b0-1c2d-7000-8000-a1b2c3d4e5f6",
            "Chat-A",
            "../escape",
            "spaces and 日本語 🎉",
            "~already~escaped",
            ".hidden",
            "UPPER_CASE-99",
        ] {
            let encoded = encode_id(id);
            assert_eq!(decode_id(&encoded).as_deref(), Some(id), "round trip failed for {id:?}");
            assert!(!encoded.contains('/'), "{encoded} can name another directory");
            assert!(!encoded.contains('.'), "{encoded} can be mistaken for a temp file");
        }
    }

    #[test]
    fn a_temp_file_name_never_decodes_to_an_id() {
        // The other half of the filter: if a temp name decoded, an interrupted
        // write would appear in the chat list as an unreadable conversation.
        assert_eq!(decode_id(".tmp.4321.7"), None);
        assert_eq!(decode_id(".DS_Store"), None);
        assert_eq!(decode_id("~zz"), None, "a bad escape is not an id");
        assert_eq!(decode_id("~7"), None, "a truncated escape is not an id");
    }

    #[test]
    fn an_over_long_id_is_refused_by_name_rather_than_by_the_os() {
        let scratch = Scratch::new("long");
        let store = scratch.store();
        let long = "x".repeat(MAX_ENCODED_LEN + 1);
        let error = store.write("chats", &long, "v").unwrap_err();
        assert!(error.contains("too long"), "unhelpful error: {error}");
    }

    #[test]
    fn removing_an_absent_key_succeeds() {
        let scratch = Scratch::new("remove-absent");
        assert!(scratch.store().remove("chats", "ghost").is_ok());
    }

    #[test]
    fn a_removed_key_reads_as_absent_again() {
        let scratch = Scratch::new("removed");
        let store = scratch.store();
        store.write("chats", "c1", "x").unwrap();
        store.remove("chats", "c1").unwrap();
        assert_eq!(store.read("chats", "c1").unwrap(), None);
        assert!(store.list_ids("chats").unwrap().is_empty());
    }

    #[test]
    fn clear_empties_one_namespace_and_leaves_the_others() {
        let scratch = Scratch::new("clear");
        let store = scratch.store();
        for id in ["a", "b", "c", "d", "e"] {
            store.write("chats", id, id).unwrap();
        }
        store.write("settings", "keep", "1").unwrap();

        store.clear("chats").unwrap();
        // Every key, not every other one — the index-shifting bug the web
        // adapter has a named case for.
        assert!(store.list_ids("chats").unwrap().is_empty());
        assert_eq!(store.list_ids("settings").unwrap(), vec!["keep".to_string()]);
    }

    #[test]
    fn an_untouched_namespace_lists_empty_rather_than_failing() {
        let scratch = Scratch::new("untouched");
        assert!(scratch.store().list_ids("drafts").unwrap().is_empty());
    }

    #[test]
    fn the_command_names_are_the_ones_the_webview_invokes() {
        // Literals on purpose, exactly as tests/contract.rs does for the shell
        // seam. A rename here is silent on a device: every chat write rejects
        // and the app keeps running.
        assert_eq!(CMD_READ, "storage_read");
        assert_eq!(CMD_WRITE, "storage_write");
        assert_eq!(CMD_REMOVE, "storage_remove");
        assert_eq!(CMD_LIST_IDS, "storage_list_ids");
        assert_eq!(CMD_CLEAR, "storage_clear");
    }

    #[test]
    fn the_namespaces_are_the_four_the_port_declares() {
        assert_eq!(NAMESPACES, ["chats", "settings", "drafts", "cache"]);
    }
}
