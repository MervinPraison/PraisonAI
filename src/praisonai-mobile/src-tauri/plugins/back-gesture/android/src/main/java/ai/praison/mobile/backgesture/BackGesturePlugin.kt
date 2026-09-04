package ai.praison.mobile.backgesture

import android.app.Activity
import android.webkit.WebView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import app.tauri.annotation.Command
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin

/**
 * The Kotlin half of tauri-plugin-back-gesture.
 *
 * Owns one OnBackPressedCallback. While Rust has registered a listener (it
 * does so during plugin setup), every press is handed to Rust and NOT acted
 * on here; Rust decides, and calls `fallBack` if the app declined it. With no
 * listener -- Rust setup failed, or the channel is gone -- the press falls
 * through immediately, so a broken bridge degrades to a normal back button
 * rather than a dead one.
 *
 * What "falling through" means depends on where the app is: see `defer` -- at
 * the task root the app is BACKGROUNDED, and anywhere else the press is
 * re-dispatched to whatever is beneath this callback.
 */
@TauriPlugin
class BackGesturePlugin(private val activity: Activity) : Plugin(activity) {
  private val callback = object : OnBackPressedCallback(true) {
    override fun handleOnBackPressed() {
      if (hasListener(EVENT)) {
        trigger(EVENT, JSObject())
      } else {
        defer()
      }
    }
  }

  /**
   * Registered in `load`, not `init`, and that is load-bearing.
   *
   * OnBackPressedDispatcher consults the MOST RECENTLY ADDED enabled callback
   * first. Tauri's AppPlugin adds its own in `init`, at plugin registration;
   * plugin registration order between it and this class is whatever the Rust
   * plugin store happens to produce. `load` runs once the WebView exists,
   * which is after every plugin's `init`, so this callback is always the
   * newer one and always wins. Registered in `init` it would win only when
   * the store initialised this plugin after Tauri's.
   */
  override fun load(webView: WebView) {
    val host = activity as AppCompatActivity
    host.runOnUiThread { host.onBackPressedDispatcher.addCallback(host, callback) }
  }

  /** Rust declined the press (or timed out waiting for the webview). */
  @Command
  fun fallBack(invoke: Invoke) {
    activity.runOnUiThread { defer() }
    invoke.resolve()
  }

  /**
   * Let something else have the press.
   *
   * Two paths, because the "system default" is not one thing.
   *
   * Above the task root -- a second activity, or webview history -- the press
   * is RE-DISPATCHED with this callback disabled, so whatever sits beneath it
   * runs: Tauri's AppPlugin, then the platform.
   *
   * At the task root it is not re-dispatched, and that difference is the whole
   * point of this function. Android 12+ backgrounds a root activity instead of
   * finishing it, but only on the press the SYSTEM dispatches; calling
   * `onBackPressedDispatcher.onBackPressed()` ourselves walks the app-level
   * path, which ends in `Activity.onBackPressed` -> `finishAfterTransition()`.
   * Measured on an Android 15 emulator: back on the root chat produced
   * `WIN DEATH` for MainActivity and `pidof` came back empty -- the process was
   * gone, so returning to the app was a cold start with the transcript and the
   * live run lost. `moveTaskToBack(true)` is the behaviour the comment above
   * used to claim: the task goes behind the launcher, the process stays warm,
   * and the app is one tap away in Recents.
   *
   * `finish()` would destroy the activity and `exitProcess` would kill the
   * process; both are worse than either path here.
   */
  private fun defer() {
    val host = activity as AppCompatActivity
    if (host.isTaskRoot) {
      // Ignore the return: `false` means the task was not moved (it is not the
      // one in front any more), and there is nothing better to do about that
      // than leave the app where it is.
      host.moveTaskToBack(true)
      return
    }
    callback.isEnabled = false
    try {
      host.onBackPressedDispatcher.onBackPressed()
    } finally {
      callback.isEnabled = true
    }
  }

  companion object {
    /** Must match `EVT_PRESSED` in src/lib.rs. */
    private const val EVENT = "pressed"
  }
}
