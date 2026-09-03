//! The four commands the webview reaches the platform secret store through.
//!
//! The store itself is `plugins/secrets` -- the Keychain on Apple, the
//! Keystore-backed `EncryptedSharedPreferences` on Android, and a refusal
//! anywhere else. This module is the boundary in front of it, and it exists for
//! one reason the store cannot supply: **the slot is a closed union**.
//!
//! `core/src/ports/secrets.ts` rule 3 spells out why. `SecretSlot` is five
//! names, not a string, because "a free-form name lets a bug write an
//! attacker-influenced string into the keychain service namespace" -- and the
//! slot becomes the keychain SERVICE (`service_for` in the plugin) and part of
//! the Android preferences key. TypeScript's union is erased at runtime; the
//! webview is where a compromised page would be; so the union has to exist a
//! second time, in Rust, as an allowlist that cannot be talked around. Exactly
//! the argument `store.rs`'s `NAMESPACES` makes for a directory name, one
//! sensitive namespace over.
//!
//! The command names are duplicated in `adapters/src/tauri/secrets.ts` and
//! compared by `tools/secrets-seam.test.mjs`: a rename on one side alone is
//! silent, and silent here means the settings screen reports "Not set" forever
//! while the user's key sits in the keychain.

use tauri::{AppHandle, Runtime};
use tauri_plugin_secrets::SecretsExt;

/// The command names the webview invokes. `adapters/src/tauri/secrets.ts`
/// names the same four strings.
pub const CMD_READ: &str = "secret_read";
pub const CMD_WRITE: &str = "secret_write";
pub const CMD_REMOVE: &str = "secret_remove";
pub const CMD_HAS: &str = "secret_has";

/// The slots `core/src/ports/secrets.ts` declares, and no others.
///
/// Not a nicety: the slot is the keychain service name. An arbitrary string
/// here would let the webview name a service belonging to something else, and
/// on Android would let it write outside the entry namespace this app owns.
pub const SLOTS: [&str; 5] = ["openai", "anthropic", "google", "openrouter", "custom"];

/// The longest account name that will be stored.
///
/// Refused with a NAME rather than handed to the platform, which answers a
/// too-long keychain attribute with `errSecParam` -- a number that tells the
/// user nothing and points at no cause.
pub const MAX_ACCOUNT_LEN: usize = 200;

/// A slot, or an error naming the one that was refused.
pub fn checked_slot(slot: &str) -> Result<&str, String> {
    SLOTS
        .iter()
        .find(|known| **known == slot)
        .copied()
        .ok_or_else(|| format!("unknown secret slot {slot:?}"))
}

/// An account name, or an error saying why not.
pub fn checked_account(account: &str) -> Result<&str, String> {
    if account.is_empty() {
        return Err("a secret account may not be empty".to_string());
    }
    if account.len() > MAX_ACCOUNT_LEN {
        return Err(format!(
            "secret account is too long ({} bytes, limit {MAX_ACCOUNT_LEN})",
            account.len()
        ));
    }
    Ok(account)
}

/// Both checks, in the one order every command uses them.
fn checked(slot: &str, account: &str) -> Result<(), String> {
    checked_slot(slot)?;
    checked_account(account)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// the Tauri commands
// ---------------------------------------------------------------------------
//
// Every argument is a single lowercase word on purpose, exactly as in
// `store.rs`: Tauri 2 maps JS `camelCase` onto Rust `snake_case` parameters,
// and a two-word name is the standing way to get a command that rejects every
// call with a deserialisation error the webview reports as "could not save".

/// `Ok(None)` for a secret that was never set. Absence is not an error.
#[tauri::command]
pub fn secret_read<R: Runtime>(
    app: AppHandle<R>,
    slot: String,
    account: String,
) -> Result<Option<String>, String> {
    checked(&slot, &account)?;
    app.secrets()
        .read(&slot, &account)
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn secret_write<R: Runtime>(
    app: AppHandle<R>,
    slot: String,
    account: String,
    value: String,
) -> Result<(), String> {
    checked(&slot, &account)?;
    app.secrets()
        .write(&slot, &account, &value)
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn secret_remove<R: Runtime>(
    app: AppHandle<R>,
    slot: String,
    account: String,
) -> Result<(), String> {
    checked(&slot, &account)?;
    app.secrets()
        .remove(&slot, &account)
        .map_err(|error| error.to_string())
}

/// Presence only. See rule 2 of `core/src/ports/secrets.ts`: this must not
/// bring the value into memory, which is why it is a command of its own rather
/// than `secret_read(..).is_some()` in the adapter.
#[tauri::command]
pub fn secret_has<R: Runtime>(
    app: AppHandle<R>,
    slot: String,
    account: String,
) -> Result<bool, String> {
    checked(&slot, &account)?;
    app.secrets()
        .has(&slot, &account)
        .map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_command_names_are_the_ones_the_webview_invokes() {
        // Literals on purpose, exactly as store.rs does for its five. A rename
        // here is silent on a device: every secret call rejects and the app
        // keeps running, reporting "Not set" for a key that is stored.
        assert_eq!(CMD_READ, "secret_read");
        assert_eq!(CMD_WRITE, "secret_write");
        assert_eq!(CMD_REMOVE, "secret_remove");
        assert_eq!(CMD_HAS, "secret_has");
    }

    #[test]
    fn the_slots_are_the_five_the_port_declares() {
        assert_eq!(
            SLOTS,
            ["openai", "anthropic", "google", "openrouter", "custom"]
        );
    }

    #[test]
    fn a_slot_outside_the_union_is_refused_rather_than_named() {
        // Rule 3. Each of these, accepted, becomes a keychain service name or
        // an Android preferences namespace of the caller's choosing.
        for bad in [
            "",
            "OpenAI",
            "openai ",
            "../../etc",
            "ai.praison.mobile.secrets.openai",
            "com.apple.account",
            "openai:extra",
        ] {
            let refused = checked_slot(bad);
            assert!(refused.is_err(), "{bad:?} was accepted as a slot");
            assert!(
                refused.unwrap_err().contains("unknown secret slot"),
                "{bad:?} was refused without saying why"
            );
        }
    }

    #[test]
    fn every_declared_slot_is_accepted() {
        // The control. A checker that refused everything would satisfy the case
        // above while making the app unable to store anything at all.
        for slot in SLOTS {
            assert_eq!(checked_slot(slot).unwrap(), slot);
        }
    }

    #[test]
    fn no_slot_contains_the_separator_the_android_key_is_built_with() {
        // `SecretsPlugin.kt` composes its preferences key as "$slot:$account".
        // That is injective ONLY while no slot contains a colon: with one,
        // slot "a:b" + account "c" and slot "a" + account "b:c" would be a
        // single entry, and adding one profile's key would overwrite another's.
        for slot in SLOTS {
            assert!(!slot.contains(':'), "{slot:?} would collide two entries");
        }
    }

    #[test]
    fn an_empty_or_over_long_account_is_refused_by_name() {
        assert!(checked_account("").unwrap_err().contains("may not be empty"));
        let long = "a".repeat(MAX_ACCOUNT_LEN + 1);
        assert!(checked_account(&long).unwrap_err().contains("too long"));
        assert_eq!(checked_account("default").unwrap(), "default");
        assert_eq!(
            checked_account(&"a".repeat(MAX_ACCOUNT_LEN)).unwrap(),
            "a".repeat(MAX_ACCOUNT_LEN)
        );
    }

    #[test]
    fn the_pair_is_checked_before_anything_reaches_the_platform() {
        // Both halves, in one call, because a command that checked only the
        // slot would still hand an unbounded account to the keychain.
        assert!(checked("openai", "default").is_ok());
        assert!(checked("nope", "default").is_err());
        assert!(checked("openai", "").is_err());
    }
}
