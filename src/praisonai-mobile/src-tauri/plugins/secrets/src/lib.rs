//! The platform secret store: iOS/macOS Keychain, Android Keystore.
//!
//! WHY THIS EXISTS. `core/src/ports/secrets.ts` says in its first line that the
//! port IS "the keychain (iOS) and keystore (Android)". Until now the only
//! implementation was `adapters/src/web/secrets.ts` -- a module-scoped `Map` --
//! and `app/src/platform.ts` handed it to the Tauri build as well, next to a
//! `storage:` line that had already been given a native implementation. So on a
//! phone the user typed their API key in, it worked, and it was gone the next
//! time the app started. Not lost on a crash, not evicted under pressure:
//! gone on every single launch, because it was never written down anywhere.
//!
//! WHAT WAS CONSIDERED AND WHY IT IS NOT USED.
//!
//!  * `tauri-plugin-stronghold`, the official one, is not a keychain. It is an
//!    IOTA Stronghold snapshot: an encrypted FILE whose key is derived from a
//!    password the app must supply on every open. There is no hardware store
//!    involved, so `isHardwareBacked` could not honestly become true, and the
//!    password has to be kept somewhere -- which is the problem again, one
//!    indirection down. The README calls it "secure storage"; what it does is
//!    write a file.
//!  * `keyring` (the crate every Rust CLI reaches for) has macOS, Windows and
//!    Linux/secret-service backends and NO Android backend at all. Half of the
//!    two platforms this app ships to.
//!  * Writing the value into `src-tauri/src/store.rs` with some encryption on
//!    top would break rule 1 of the port ("a secret never passes through
//!    StoragePort") and, more importantly, would put the decryption key in the
//!    same place as the ciphertext. That is an obfuscation, not a keychain.
//!
//! WHAT IS ACTUALLY DONE, per platform, because "secure storage" is a claim and
//! not a design:
//!
//!  * Apple (iOS, macOS): `SecItemAdd` / `SecItemCopyMatching` / `SecItemDelete`
//!    with `kSecClassGenericPassword`, through the `security-framework` crate --
//!    the identical C calls a Swift helper would make. The value is held by the
//!    OS keychain daemon, encrypted with a key in the Secure Enclave on every
//!    device this app supports, and is not in the app sandbox at all. No Swift
//!    package: which is why this half is exercised by `cargo test` on any macOS
//!    box, against the real Keychain, rather than only on a device.
//!  * Android: `EncryptedSharedPreferences` (androidx.security-crypto) in
//!    `android/.../SecretsPlugin.kt`. Keys AES256-SIV, values AES256-GCM, and
//!    the master key that wraps both is a `KeyGenParameterSpec` key generated
//!    IN the AndroidKeyStore -- so it lives in the TEE/StrongBox and never
//!    exists as bytes in the app's address space. What lands on disk under
//!    /data/data is ciphertext; `tools/`'s device check greps for the plaintext
//!    and must find none.
//!  * Anything else -- a Linux or Windows desktop dev build -- has NO hardware
//!    store here, and every call REFUSES with [`Error::Unsupported`].
//!
//! That last line is the one that makes `isHardwareBacked: true` honest on the
//! Tauri adapter without an async probe. The adapter cannot ask "am I on iOS?"
//! synchronously, and `ShellPort.insets` forbids making the platform decision a
//! promise. So the invariant is enforced from underneath instead: *if a secret
//! was stored through this plugin at all, it is in a hardware-backed store*,
//! because on a platform without one nothing is stored. A silent fallback to a
//! file is precisely the "downgrade [that] is how a user comes to believe a key
//! is protected when it is not" the port warns about, and it is available here
//! in about four lines. It is not taken.

use std::fmt;

use tauri::{
    plugin::{Builder, TauriPlugin},
    Manager, Runtime,
};

/// The plugin name, as `tauri::plugin::Builder` and the ACL know it.
pub const PLUGIN_NAME: &str = "secrets";

/// The keychain service namespace. One service per slot, so a bug that
/// produced a slot the port never declared would still be confined to a name
/// under this prefix -- and `src-tauri/src/secrets.rs` refuses such a slot
/// before it ever gets here.
pub const SERVICE_PREFIX: &str = "ai.praison.mobile.secrets";

/// Java package of the Kotlin half. Must match `package` in
/// `android/src/main/java/ai/praison/mobile/secrets/SecretsPlugin.kt`; a
/// mismatch is a `ClassNotFoundException` at startup, not a build error.
#[cfg(target_os = "android")]
const PLUGIN_IDENTIFIER: &str = "ai.praison.mobile.secrets";

/// The four Kotlin `@Command` names. Must match `SecretsPlugin.kt`.
#[cfg(target_os = "android")]
mod android_commands {
    pub const READ: &str = "readSecret";
    pub const WRITE: &str = "writeSecret";
    pub const REMOVE: &str = "removeSecret";
    pub const HAS: &str = "hasSecret";
}

/// Why a secret could not be stored, read or removed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Error {
    /// The platform store said no.
    Platform(String),
    /// This build has no hardware-backed store. Deliberately NOT a fallback.
    Unsupported(&'static str),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Platform(message) => write!(f, "the platform secret store failed: {message}"),
            Error::Unsupported(platform) => write!(
                f,
                "{platform} has no hardware-backed secret store in this build, \
                 and a secret is not written to a file instead"
            ),
        }
    }
}

impl std::error::Error for Error {}

/// The keychain service for one slot.
///
/// Exported so `src-tauri/src/secrets.rs`'s tests can pin it: the service name
/// is what a user sees in Keychain Access, and renaming it silently orphans
/// every key already stored under the old one -- the user's key is still there
/// and the app reports "Not set".
#[must_use]
pub fn service_for(slot: &str) -> String {
    format!("{SERVICE_PREFIX}.{slot}")
}

// ---------------------------------------------------------------------------
// Apple: the real Keychain, via the Security framework
// ---------------------------------------------------------------------------

#[cfg(target_vendor = "apple")]
mod apple {
    use super::Error;
    use security_framework::item::{ItemClass, ItemSearchOptions, Limit};
    use security_framework::passwords::{
        delete_generic_password, get_generic_password, set_generic_password,
    };
    use security_framework_sys::base::errSecItemNotFound;

    /// `Ok(None)` for a key that is not there. Absence is not an error, and
    /// conflating the two would make a failing keychain look like a user who
    /// never configured anything -- so the app would quietly ask for the key
    /// again instead of reporting that it could not be read.
    pub fn read(service: &str, account: &str) -> Result<Option<String>, Error> {
        match get_generic_password(service, account) {
            Ok(bytes) => String::from_utf8(bytes)
                .map(Some)
                // Not `from_utf8_lossy`: a credential with U+FFFD substituted
                // into it is a credential that fails authentication with no
                // explanation at all.
                .map_err(|e| Error::Platform(format!("the stored secret is not UTF-8: {e}"))),
            Err(error) if error.code() == errSecItemNotFound => Ok(None),
            Err(error) => Err(Error::Platform(error.to_string())),
        }
    }

    /// Presence WITHOUT the value.
    ///
    /// Rule 2 of `core/src/ports/secrets.ts`: `has()` "must not fault the value
    /// into memory". `get_generic_password` always sets `kSecReturnData`, so
    /// this cannot be `read().is_some()` -- it builds its own query with no
    /// `load_*` at all, which makes `SecItemCopyMatching` answer with a status
    /// and nothing else. The key never leaves the keychain daemon.
    pub fn has(service: &str, account: &str) -> Result<bool, Error> {
        let mut query = ItemSearchOptions::new();
        query
            .class(ItemClass::generic_password())
            .service(service)
            .account(account)
            .limit(Limit::Max(1));
        match query.search() {
            Ok(_) => Ok(true),
            Err(error) if error.code() == errSecItemNotFound => Ok(false),
            Err(error) => Err(Error::Platform(error.to_string())),
        }
    }

    /// Creates or replaces. `set_generic_password` falls back to `SecItemUpdate`
    /// on `errSecDuplicateItem`, so a second write is a replacement rather than
    /// a duplicate item the next read picks arbitrarily between.
    pub fn write(service: &str, account: &str, value: &str) -> Result<(), Error> {
        set_generic_password(service, account, value.as_bytes())
            .map_err(|e| Error::Platform(e.to_string()))
    }

    /// Removing an absent secret SUCCEEDS. The caller wanted it gone and it is;
    /// throwing would force every "clear key" path to wrap itself in a try.
    pub fn remove(service: &str, account: &str) -> Result<(), Error> {
        match delete_generic_password(service, account) {
            Ok(()) => Ok(()),
            Err(error) if error.code() == errSecItemNotFound => Ok(()),
            Err(error) => Err(Error::Platform(error.to_string())),
        }
    }
}

// ---------------------------------------------------------------------------
// the handle
// ---------------------------------------------------------------------------

/// What the Kotlin commands take and return. `camelCase` because Tauri's
/// Kotlin deserialiser is Jackson with the field names as written.
#[cfg(target_os = "android")]
#[derive(serde::Serialize)]
struct EntryArgs<'a> {
    slot: &'a str,
    account: &'a str,
}

#[cfg(target_os = "android")]
#[derive(serde::Serialize)]
struct WriteArgs<'a> {
    slot: &'a str,
    account: &'a str,
    value: &'a str,
}

/// `{"value": ...}`. `default` matters: `JSObject.put(key, null as String?)`
/// REMOVES the key rather than writing a JSON null, so an absent secret comes
/// back as `{}` and without this the deserialise would fail and an ordinary
/// "not configured" would surface as a store error.
#[cfg(target_os = "android")]
#[derive(serde::Deserialize)]
struct ReadReply {
    #[serde(default)]
    value: Option<String>,
}

#[cfg(target_os = "android")]
#[derive(serde::Deserialize)]
struct HasReply {
    present: bool,
}

/// The handle to the platform store, managed as Tauri state. Reach it with
/// [`SecretsExt::secrets`].
pub struct SecretStore<R: Runtime> {
    #[cfg(target_os = "android")]
    handle: tauri::plugin::PluginHandle<R>,
    #[cfg(not(target_os = "android"))]
    _runtime: std::marker::PhantomData<fn() -> R>,
}

impl<R: Runtime> SecretStore<R> {
    /// `Ok(None)` for a slot/account that was never set.
    pub fn read(&self, slot: &str, account: &str) -> Result<Option<String>, Error> {
        #[cfg(target_os = "android")]
        {
            let reply: ReadReply = self
                .handle
                .run_mobile_plugin(android_commands::READ, EntryArgs { slot, account })
                .map_err(|e| Error::Platform(e.to_string()))?;
            Ok(reply.value)
        }
        #[cfg(all(target_vendor = "apple", not(target_os = "android")))]
        {
            apple::read(&service_for(slot), account)
        }
        #[cfg(not(any(target_os = "android", target_vendor = "apple")))]
        {
            let _ = (slot, account);
            Err(Error::Unsupported(UNSUPPORTED_PLATFORM))
        }
    }

    /// Presence only. Must not read the value; see rule 2 of the port.
    pub fn has(&self, slot: &str, account: &str) -> Result<bool, Error> {
        #[cfg(target_os = "android")]
        {
            let reply: HasReply = self
                .handle
                .run_mobile_plugin(android_commands::HAS, EntryArgs { slot, account })
                .map_err(|e| Error::Platform(e.to_string()))?;
            Ok(reply.present)
        }
        #[cfg(all(target_vendor = "apple", not(target_os = "android")))]
        {
            apple::has(&service_for(slot), account)
        }
        #[cfg(not(any(target_os = "android", target_vendor = "apple")))]
        {
            let _ = (slot, account);
            Err(Error::Unsupported(UNSUPPORTED_PLATFORM))
        }
    }

    /// Creates or replaces.
    pub fn write(&self, slot: &str, account: &str, value: &str) -> Result<(), Error> {
        #[cfg(target_os = "android")]
        {
            self.handle
                .run_mobile_plugin::<serde_json::Value>(
                    android_commands::WRITE,
                    WriteArgs {
                        slot,
                        account,
                        value,
                    },
                )
                .map_err(|e| Error::Platform(e.to_string()))?;
            Ok(())
        }
        #[cfg(all(target_vendor = "apple", not(target_os = "android")))]
        {
            apple::write(&service_for(slot), account, value)
        }
        #[cfg(not(any(target_os = "android", target_vendor = "apple")))]
        {
            let _ = (slot, account, value);
            Err(Error::Unsupported(UNSUPPORTED_PLATFORM))
        }
    }

    /// Removing an absent secret succeeds.
    pub fn remove(&self, slot: &str, account: &str) -> Result<(), Error> {
        #[cfg(target_os = "android")]
        {
            self.handle
                .run_mobile_plugin::<serde_json::Value>(
                    android_commands::REMOVE,
                    EntryArgs { slot, account },
                )
                .map_err(|e| Error::Platform(e.to_string()))?;
            Ok(())
        }
        #[cfg(all(target_vendor = "apple", not(target_os = "android")))]
        {
            apple::remove(&service_for(slot), account)
        }
        #[cfg(not(any(target_os = "android", target_vendor = "apple")))]
        {
            let _ = (slot, account);
            Err(Error::Unsupported(UNSUPPORTED_PLATFORM))
        }
    }
}

/// Named rather than inlined so the refusal reads the same in all four calls.
#[cfg(not(any(target_os = "android", target_vendor = "apple")))]
const UNSUPPORTED_PLATFORM: &str = "this platform";

/// `app.secrets()` on anything that is a `Manager`.
pub trait SecretsExt<R: Runtime> {
    fn secrets(&self) -> &SecretStore<R>;
}

impl<R: Runtime, T: Manager<R>> SecretsExt<R> for T {
    fn secrets(&self) -> &SecretStore<R> {
        self.state::<SecretStore<R>>().inner()
    }
}

/// Build the plugin.
pub fn init<R: Runtime>() -> TauriPlugin<R> {
    Builder::new(PLUGIN_NAME)
        .setup(|app, api| {
            #[cfg(target_os = "android")]
            let state: SecretStore<R> = SecretStore {
                handle: api.register_android_plugin(PLUGIN_IDENTIFIER, "SecretsPlugin")?,
            };

            #[cfg(not(target_os = "android"))]
            let state: SecretStore<R> = {
                // Apple needs no registration -- the Security framework is just
                // there -- and a platform with no store registers nothing and
                // refuses on use rather than at boot, so a desktop dev build
                // still starts.
                let _ = &api;
                SecretStore {
                    _runtime: std::marker::PhantomData,
                }
            };

            app.manage(state);
            Ok(())
        })
        .build()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_slot_becomes_one_service_under_the_app_prefix() {
        // The name a user sees in Keychain Access, and the thing that must not
        // drift: rename the prefix and every key already stored is orphaned --
        // still on the device, invisible to the app, reported as "Not set".
        assert_eq!(service_for("openai"), "ai.praison.mobile.secrets.openai");
        assert_eq!(SERVICE_PREFIX, "ai.praison.mobile.secrets");
    }

    #[test]
    fn two_slots_never_share_a_service() {
        let names: Vec<String> = ["openai", "anthropic", "google", "openrouter", "custom"]
            .iter()
            .map(|slot| service_for(slot))
            .collect();
        let mut unique = names.clone();
        unique.sort();
        unique.dedup();
        assert_eq!(unique.len(), names.len(), "two slots collided: {names:?}");
    }

    #[test]
    fn an_unsupported_platform_says_so_rather_than_naming_a_file() {
        // The refusal has to be readable in a device log AND must not hint at a
        // fallback that does not exist.
        let message = Error::Unsupported("linux").to_string();
        assert!(message.contains("linux"), "unhelpful error: {message}");
        assert!(
            message.contains("not written to a file"),
            "the refusal must say the secret went nowhere: {message}"
        );
    }

    // ---- the Apple keychain, for real -------------------------------------
    //
    // These run on any macOS box and on CI's macOS runners, against the login
    // keychain, under the app's own service name and a per-run account. That is
    // deliberate: a mock of `SecItemAdd` proves the mock. Each test cleans up
    // through a guard that runs on panic as well as on success.
    #[cfg(target_vendor = "apple")]
    mod keychain {
        use super::*;
        use std::sync::atomic::{AtomicU64, Ordering};

        static COUNTER: AtomicU64 = AtomicU64::new(0);

        /// A unique account in the real "custom" slot, removed on drop.
        struct Scratch {
            slot: &'static str,
            account: String,
        }

        impl Scratch {
            fn new(label: &str) -> Self {
                let account = format!(
                    "test-{label}-{}-{}",
                    std::process::id(),
                    COUNTER.fetch_add(1, Ordering::Relaxed)
                );
                let scratch = Self {
                    slot: "custom",
                    account,
                };
                let _ = apple::remove(&service_for(scratch.slot), &scratch.account);
                scratch
            }
            fn service(&self) -> String {
                service_for(self.slot)
            }
        }

        impl Drop for Scratch {
            fn drop(&mut self) {
                let _ = apple::remove(&self.service(), &self.account);
            }
        }

        #[test]
        fn a_secret_that_was_never_set_reads_as_absent_rather_than_failing() {
            let scratch = Scratch::new("absent");
            assert_eq!(apple::read(&scratch.service(), &scratch.account).unwrap(), None);
            assert!(!apple::has(&scratch.service(), &scratch.account).unwrap());
        }

        #[test]
        fn a_secret_survives_a_relaunch() {
            // THE claim this whole plugin exists to make. There is no second
            // process to start here, but there is something stronger: the
            // keychain is not in this process at all, so a value written by one
            // run is read by the next one. That is what the on-device
            // force-stop check exercises end to end.
            let scratch = Scratch::new("relaunch");
            apple::write(&scratch.service(), &scratch.account, "sk-kept-across-launches").unwrap();
            assert_eq!(
                apple::read(&scratch.service(), &scratch.account).unwrap(),
                Some("sk-kept-across-launches".to_string()),
                "the key did not come back"
            );
        }

        #[test]
        fn a_rewrite_replaces_rather_than_adding_a_second_item() {
            // Without the errSecDuplicateItem -> SecItemUpdate fallback this is
            // an error on the second write, and the user's replacement key
            // silently never takes.
            let scratch = Scratch::new("rewrite");
            apple::write(&scratch.service(), &scratch.account, "first").unwrap();
            apple::write(&scratch.service(), &scratch.account, "second").unwrap();
            assert_eq!(
                apple::read(&scratch.service(), &scratch.account).unwrap(),
                Some("second".to_string())
            );
        }

        #[test]
        fn an_empty_secret_is_a_stored_value_not_an_absence() {
            // `""` is falsy in the language above this one. A store that turned
            // a deliberately blank credential back into "not configured" would
            // make the settings row lie on every read.
            let scratch = Scratch::new("empty");
            apple::write(&scratch.service(), &scratch.account, "").unwrap();
            assert_eq!(
                apple::read(&scratch.service(), &scratch.account).unwrap(),
                Some(String::new())
            );
            assert!(apple::has(&scratch.service(), &scratch.account).unwrap());
        }

        #[test]
        fn two_accounts_in_one_slot_are_two_different_secrets() {
            let a = Scratch::new("acct-a");
            let b = Scratch::new("acct-b");
            apple::write(&a.service(), &a.account, "sk-work").unwrap();
            apple::write(&b.service(), &b.account, "sk-personal").unwrap();
            assert_eq!(
                apple::read(&a.service(), &a.account).unwrap(),
                Some("sk-work".to_string()),
                "the second account overwrote the first"
            );
            assert_eq!(
                apple::read(&b.service(), &b.account).unwrap(),
                Some("sk-personal".to_string())
            );
        }

        #[test]
        fn removing_a_secret_removes_it_and_removing_an_absent_one_succeeds() {
            let scratch = Scratch::new("remove");
            apple::write(&scratch.service(), &scratch.account, "sk-x").unwrap();
            apple::remove(&scratch.service(), &scratch.account).unwrap();
            assert_eq!(apple::read(&scratch.service(), &scratch.account).unwrap(), None);
            assert!(
                apple::remove(&scratch.service(), &scratch.account).is_ok(),
                "removing an absent secret must succeed"
            );
        }

        #[test]
        fn has_answers_without_asking_the_keychain_for_the_value() {
            // Rule 2, at the layer that can actually keep it. The behavioural
            // half -- that `has` agrees with `read` -- is asserted here; the
            // structural half, that the query carries no kSecReturnData, is
            // pinned by `no_return_data_in_the_presence_query` below, because
            // no in-process test can observe which CoreFoundation keys were in
            // the dictionary.
            let scratch = Scratch::new("has");
            assert!(!apple::has(&scratch.service(), &scratch.account).unwrap());
            apple::write(&scratch.service(), &scratch.account, "sk-present").unwrap();
            assert!(apple::has(&scratch.service(), &scratch.account).unwrap());
            apple::remove(&scratch.service(), &scratch.account).unwrap();
            assert!(!apple::has(&scratch.service(), &scratch.account).unwrap());
        }

        #[test]
        fn no_return_data_in_the_presence_query() {
            // `has` reimplemented as `read(..).is_some()` passes every
            // behavioural test above and quietly breaks the port's rule 2 --
            // the value is copied out of the keychain daemon into this
            // process's memory on every settings repaint. The only thing that
            // can catch that is the shape of the call, so it is pinned on the
            // source of this file.
            let source = include_str!("lib.rs");
            let body = source
                .split("pub fn has(service:")
                .nth(1)
                .expect("apple::has not found");
            let body = body.split("\n    pub fn ").next().unwrap_or(body);
            assert!(
                !body.contains("get_generic_password"),
                "has() must not read the value: rule 2 of core/src/ports/secrets.ts"
            );
            assert!(
                !body.contains("load_data"),
                "has() must not request the data at all"
            );
            assert!(
                body.contains("ItemSearchOptions"),
                "has() no longer builds its own no-data query"
            );
        }
    }
}
