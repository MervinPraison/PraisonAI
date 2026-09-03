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
   * Re-dispatch with this callback disabled, so the next one runs: Tauri's
   * AppPlugin (webview history, if any), then the system default. On Android
   * 12+ the default moves the task to the back rather than destroying the
   * activity, which preserves warm start. `finish()` would destroy it and
   * `exitProcess` would kill the process; both are worse.
   */
  private fun defer() {
    callback.isEnabled = false
    try {
      (activity as AppCompatActivity).onBackPressedDispatcher.onBackPressed()
    } finally {
      callback.isEnabled = true
    }
  }

  companion object {
    /** Must match `EVT_PRESSED` in src/lib.rs. */
    private const val EVENT = "pressed"
  }
}
