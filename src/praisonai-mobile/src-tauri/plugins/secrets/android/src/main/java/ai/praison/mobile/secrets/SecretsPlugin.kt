package ai.praison.mobile.secrets

import android.app.Activity
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys
import app.tauri.annotation.Command
import app.tauri.annotation.InvokeArg
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin

/**
 * The Android half of tauri-plugin-secrets: the Keystore-backed secret store.
 *
 * WHAT IS ACTUALLY GUARANTEED, because "encrypted" on its own is not a claim
 * anyone can check:
 *
 *  - `MasterKeys.getOrCreate(AES256_GCM_SPEC)` generates an AES key INSIDE the
 *    AndroidKeyStore. On every device this app supports that key material is
 *    held by the TEE (or StrongBox), is not extractable, and never exists as
 *    bytes in this process. Rooting the device does not hand it over; a backup
 *    of /data does not contain it.
 *  - `EncryptedSharedPreferences` encrypts KEYS with AES256-SIV and VALUES with
 *    AES256-GCM under keys wrapped by that master key. So the file that lands
 *    in /data/data/ai.praison.mobile/shared_prefs contains neither the API key
 *    nor the name of the slot it belongs to. The device check for this change
 *    greps that whole tree for the plaintext key and must find nothing.
 *
 * WHY NOT plain SharedPreferences plus a hand-rolled Cipher. It is the same
 * Keystore call underneath and about the same amount of code, and it is also
 * where the mistakes live: a reused GCM nonce, a key that is not rotated, an
 * IV stored next to the ciphertext in a format nobody versioned. This class is
 * the seam, not the cryptography.
 *
 * WHY THE PREFS FILE IS CREATED LAZILY. `EncryptedSharedPreferences.create`
 * talks to the Keystore, which on a cold start can take tens of milliseconds.
 * Doing it in `load()` would put that on the path to first paint for every
 * launch, including the launches where nobody opens Settings at all.
 */
@InvokeArg
class EntryArgs {
  lateinit var slot: String
  lateinit var account: String
}

@InvokeArg
class WriteArgs {
  lateinit var slot: String
  lateinit var account: String
  lateinit var value: String
}

@TauriPlugin
class SecretsPlugin(private val activity: Activity) : Plugin(activity) {
  private var prefs: android.content.SharedPreferences? = null

  /**
   * One store, opened once.
   *
   * `@Synchronized` is not decoration: Tauri dispatches plugin commands off the
   * UI thread, so two settings rows checking presence at once would otherwise
   * race to build two EncryptedSharedPreferences over the same file.
   */
  @Synchronized
  private fun store(): android.content.SharedPreferences {
    prefs?.let { return it }
    val context = activity.applicationContext
    val opened = try {
      open(context)
    } catch (e: Exception) {
      // The store is on disk but this device cannot open it. The one way that
      // happens in practice is a restore: Android Auto Backup copies the
      // shared_prefs file to a new or wiped device, but the AndroidKeyStore
      // master key that wraps the Tink keysets is device-local and does NOT
      // travel with it, so `create` throws trying to unwrap them.
      //
      // Left unhandled this is permanent: every read, write, presence check
      // AND delete goes through here, so the user cannot even CLEAR the key to
      // recover -- the settings screen is bricked until app data is wiped by
      // hand. A restored ciphertext we can never decrypt is indistinguishable
      // from no secret, so discard the unreadable file and start clean. The
      // user re-enters the key once, which is exactly the state a fresh install
      // is in. `back-gesture`'s precedent: recover from underneath rather than
      // surface a failure the caller cannot act on.
      discard(context)
      open(context)
    }
    prefs = opened
    return opened
  }

  private fun open(context: android.content.Context): android.content.SharedPreferences {
    val masterKeyAlias = MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC)
    return EncryptedSharedPreferences.create(
      PREFS_FILE,
      masterKeyAlias,
      context,
      EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
      EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )
  }

  /**
   * Drop the on-disk store so the next `open` rebuilds it empty.
   *
   * `deleteSharedPreferences`, NOT `getSharedPreferences(...).edit().clear()`.
   * Opening the file with `getSharedPreferences` would be opening it as PLAIN
   * preferences -- the one call this plugin must never make, because it is
   * exactly the two-word edit that writes the API key as plaintext XML, and the
   * seam test forbids the string for that reason. `deleteSharedPreferences`
   * removes the file (and its Tink keysets) without ever holding a plaintext
   * handle to it. It is API 24, which is this plugin's `minSdk`.
   */
  private fun discard(context: android.content.Context) {
    try {
      context.deleteSharedPreferences(PREFS_FILE)
    } catch (_: Exception) {
      // Best effort. If the delete fails, `open` below throws and the command
      // rejects -- the same honest failure as before, never a silent fallback
      // to an unprotected store.
    }
  }

  /**
   * The slot is part of the key, not a separate file.
   *
   * A colon is safe as the separator only because the slot is a closed union
   * with no colon in any member -- `core/src/ports/secrets.ts` rule 3, enforced
   * on the Rust side in `src-tauri/src/secrets.rs` before a call ever reaches
   * here. Without that, slot "a" + account "b:c" and slot "a:b" + account "c"
   * would be one entry.
   */
  private fun keyFor(slot: String, account: String): String = "$slot:$account"

  @Command
  fun readSecret(invoke: Invoke) {
    val args = invoke.parseArgs(EntryArgs::class.java)
    try {
      // `null` as the default, so a stored EMPTY string is still an empty
      // string and not an absence. `getString(key, "")` would make the two
      // indistinguishable, and a deliberately blank credential would read back
      // as "not configured" forever.
      val value = store().getString(keyFor(args.slot, args.account), null)
      // JSObject.put(String, String?) with null REMOVES the key, so an absent
      // secret arrives in Rust as `{}` -- which ReadReply's #[serde(default)]
      // reads as None. Deliberate on both sides.
      invoke.resolve(JSObject().put("value", value))
    } catch (e: Exception) {
      invoke.reject("could not read from the keystore-backed store", e)
    }
  }

  /**
   * Presence WITHOUT the value.
   *
   * `contains` compares the AES256-SIV encryption of the key against what is on
   * disk; it never decrypts the value. That is rule 2 of the port -- "has()
   * must not fault the value into memory" -- kept at the only layer that can
   * keep it. Rewriting this as `readSecret(...) != null` passes every
   * behavioural test and pulls the user's API key into process memory on every
   * repaint of the settings screen.
   */
  @Command
  fun hasSecret(invoke: Invoke) {
    val args = invoke.parseArgs(EntryArgs::class.java)
    try {
      invoke.resolve(JSObject().put("present", store().contains(keyFor(args.slot, args.account))))
    } catch (e: Exception) {
      invoke.reject("could not check the keystore-backed store", e)
    }
  }

  @Command
  fun writeSecret(invoke: Invoke) {
    val args = invoke.parseArgs(WriteArgs::class.java)
    try {
      // `commit`, not `apply`. `apply` returns immediately and writes on a
      // background thread; on Android a process killed in that window loses the
      // write, and the user's key is gone with the app reporting it saved.
      // This is the one write in the app where that matters and it happens
      // once per key, so the blocking call costs nothing worth having.
      val ok = store().edit().putString(keyFor(args.slot, args.account), args.value).commit()
      if (ok) invoke.resolve() else invoke.reject("the keystore-backed store refused the write")
    } catch (e: Exception) {
      invoke.reject("could not write to the keystore-backed store", e)
    }
  }

  @Command
  fun removeSecret(invoke: Invoke) {
    val args = invoke.parseArgs(EntryArgs::class.java)
    try {
      // Removing something absent is a success: the caller wanted it gone and
      // it is gone. `remove` on a missing key is already a no-op here.
      store().edit().remove(keyFor(args.slot, args.account)).commit()
      invoke.resolve()
    } catch (e: Exception) {
      invoke.reject("could not remove from the keystore-backed store", e)
    }
  }

  companion object {
    /**
     * The file under shared_prefs/. Renaming it orphans every key already
     * stored: they stay on the device, the app reports "Not set", and the user
     * is asked for a credential they already gave.
     */
    private const val PREFS_FILE = "ai.praison.mobile.secrets"
  }
}
