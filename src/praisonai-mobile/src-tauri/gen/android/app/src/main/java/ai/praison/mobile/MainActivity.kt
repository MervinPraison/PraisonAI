package ai.praison.mobile

import android.os.Bundle
import android.webkit.WebView
import androidx.activity.enableEdgeToEdge
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsAnimationCompat
import androidx.core.view.WindowInsetsCompat

/**
 * The Android host, and the only place the real window insets exist.
 *
 * `enableEdgeToEdge()` sets `decorFitsSystemWindows = false`, which is what
 * lets the webview paint behind the status and navigation bars. The cost is
 * that the window is then never resized -- not by the system bars and not by
 * the IME -- so no web API can see either of them:
 *
 *   - `env(safe-area-inset-*)` in Chromium on Android reports the DISPLAY
 *     CUTOUT alone. Measured on an Android 15 emulator running this app: with a
 *     cutout configured, `--safe-area-inset-top` was 49px (the 128px cutout at
 *     dpr 2.625) while the 63px status bar contributed nothing, and rotated to
 *     landscape that same 49px moved to `--safe-area-inset-left` and top read
 *     0px with the status bar still along the top edge. On the same emulator
 *     with no cutout, every edge read 0px and the topbar's title was painted
 *     straight through the status-bar clock.
 *   - the keyboard is not merely under-reported but absent. With the IME shown
 *     (`dumpsys input_method` reporting `mInputShown=true`) and the composer
 *     focused, `window.innerHeight`, `visualViewport.height` and
 *     `navigator.virtualKeyboard.boundingRect` all still reported the full
 *     915px viewport, so the composer was laid out at the bottom of a viewport
 *     the keyboard was covering and vanished underneath it.
 *
 * `WindowInsetsCompat` has all of it, so this reads it and hands it to the page
 * through the one global `adapters/src/tauri/shell.ts` installs. `bottom` is
 * the system bars, NOT the keyboard: the page composes the two with `max`, not
 * `+` (ui/src/layout/insets.ts), and sending the keyboard on both channels
 * would be that sum by another route.
 *
 * The animation callback is not decoration. `setOnApplyWindowInsetsListener`
 * fires once at each END of the IME transition, so on its own the composer
 * teleports the full height of the keyboard; `onProgress` runs every frame in
 * between, which is what makes it slide with the keyboard instead.
 */
class MainActivity : TauriActivity() {
  /** True once the page has answered a push. Until then the global does not
   *  exist yet and every push is silently dropped -- see `retryUntilAcked`. */
  private var acknowledged = false

  override fun onCreate(savedInstanceState: Bundle?) {
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)
  }

  override fun onWebViewCreate(webView: WebView) {
    ViewCompat.setOnApplyWindowInsetsListener(webView) { view, insets ->
      push(view as WebView, insets)
      // Returned, not consumed: the webview is not the only view in the tree
      // and swallowing the insets here would stop anything below it seeing a
      // rotation.
      insets
    }

    ViewCompat.setWindowInsetsAnimationCallback(
      webView,
      object : WindowInsetsAnimationCompat.Callback(DISPATCH_MODE_CONTINUE_ON_SUBTREE) {
        override fun onProgress(
          insets: WindowInsetsCompat,
          runningAnimations: MutableList<WindowInsetsAnimationCompat>,
        ): WindowInsetsCompat {
          push(webView, insets)
          return insets
        }
      },
    )

    ViewCompat.requestApplyInsets(webView)
    retryUntilAcked(webView, 0)
  }

  /**
   * Push the current insets until the page has actually taken one.
   *
   * This exists because of an ordering that produced a fix that worked on
   * every later dispatch and did nothing at all on the one that matters.
   * `onWebViewCreate` runs before the page has loaded, so the first
   * `requestApplyInsets` evaluates `window.<global> && window.<global>(...)`
   * against a document that has no global yet -- a legal no-op with no error
   * anywhere. Android then has no reason to dispatch insets again, so the app
   * sat at zero insets until the user rotated the phone or opened the keyboard:
   * measured on the emulator as `#root` still carrying `--inset-top: 0px` with
   * the OS reporting 48px, and the topbar title over the clock exactly as
   * before the fix.
   *
   * Polling rather than a `@JavascriptInterface` handshake because the webview
   * is Tauri's, created and navigated by Rust, and an interface added here is
   * only injected into documents loaded AFTER the call -- which is the same
   * race in a different place. This stops the moment the page answers.
   */
  private fun retryUntilAcked(webView: WebView, attempt: Int) {
    if (acknowledged || attempt > MAX_PUSH_ATTEMPTS) return
    ViewCompat.getRootWindowInsets(webView)?.let { push(webView, it) }
    webView.postDelayed({ retryUntilAcked(webView, attempt + 1) }, PUSH_RETRY_MS)
  }

  private fun push(webView: WebView, insets: WindowInsetsCompat) {
    val density = webView.resources.displayMetrics.density
    // Guard the divide: a density of 0 is not something Android reports, but a
    // NaN reaching a CSS length silently drops the whole declaration and drops
    // the composer under the keyboard with nothing in any log.
    if (density <= 0f) return
    // A cutout is folded in with the system bars rather than sent separately:
    // the page wants one "do not paint here" number per edge, and on a device
    // whose cutout is deeper than its status bar (every emulator AVD with a
    // punch hole, and such a phone in landscape) the bars alone are too small.
    val bars = insets.getInsets(
      WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout(),
    )
    val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
    fun css(value: Int): Int = (value / density).toInt().coerceAtLeast(0)
    // Returns a boolean so the page's readiness is observable rather than
    // assumed; `retryUntilAcked` is the only reader.
    val js = "(function(){if(!window.$INSETS_GLOBAL)return false;window.$INSETS_GLOBAL({" +
      "top:${css(bars.top)}," +
      "right:${css(bars.right)}," +
      "bottom:${css(bars.bottom)}," +
      "left:${css(bars.left)}," +
      "keyboard:${css(ime.bottom)}});return true;})()"
    webView.evaluateJavascript(js) { result ->
      if (result == "true") acknowledged = true
    }
  }

  private companion object {
    /** Must match NATIVE_INSETS_GLOBAL in adapters/src/tauri/shell.ts.
     *  tools/shell-seam.test.mjs pins the two together. */
    const val INSETS_GLOBAL = "__praisonaiNativeInsets"
    const val PUSH_RETRY_MS = 120L
    /** ~15s of retries. A page that has not booted by then has a worse problem
     *  than its insets, and a retry loop with no bound is a battery bug. */
    const val MAX_PUSH_ATTEMPTS = 125
  }
}
