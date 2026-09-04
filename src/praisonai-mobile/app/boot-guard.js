// The boot indicator's failure path.
//
// index.html paints a wordmark and "Starting…" on the first frame so a cold
// start does not look like a broken install. That message is true right up
// until the moment the app can no longer start at all -- and the ONE failure
// that leaves nobody to say so is app.js not loading or throwing on its way
// in. app/src/crash.ts is installed by `mount()`, which is inside the module
// that just failed; a static indicator with no cover would then sit there
// claiming progress forever, which is worse than the blank page it replaced.
//
// An external file rather than an inline <script>, for the reason
// register-sw.js gives: index.html ships a `script-src 'self'` CSP and an
// inline script -- or an `onerror=` attribute, which is the same thing to CSP
// -- would be blocked with nothing but a console line to say so.
//
// It is loaded BEFORE app.js and without `defer` on purpose, and that ordering
// is the whole guarantee. `<script type=module>` is implicitly deferred: it is
// FETCHED while the document parses and EXECUTED afterwards, and its `error`
// fires whenever that fetch settles. A listener installed after it -- or
// deferred alongside it -- may not exist yet at that moment. Over a real
// connection the fetch always loses the race to the parser, so the wrong order
// looks fine every time and fails the day a service worker or a memory cache
// answers instantly; app/src/boot-screen.test.ts pins the order rather than
// trusting the race. The cost is a parser pause on a same-origin file of a few
// hundred bytes that the service worker precaches, and the boot markup is above
// it, so nothing that has to be painted is waiting on this.
//
// ES5, by hand. tools/bundle.mjs holds the app to the Chrome that the declared
// `minSdkVersion` ships (chrome58 today) and scans every chunk it emits -- but
// this file is copied verbatim, so esbuild never sees it and no gate would
// catch an arrow function here. A syntax error in this script is a parse error
// in the one file whose job is to report parse errors.
(function () {
  // ONE invariant, and every rule below follows from it: this file speaks only
  // while the boot indicator is still on screen. The app's first paint removes
  // it (`root.textContent = ""` in app/src/main.ts), and so does the crash
  // screen -- so once either has run, `fail()` finds nothing and says nothing.
  // That is what keeps this from double-reporting over app/src/crash.ts, which
  // owns every error from `mount()` onwards.
  function fail() {
    var boot = document.querySelector("[data-boot]");
    if (boot === null) return;
    var note = boot.querySelector("[data-boot-note]");
    var failed = boot.querySelector("[data-boot-failed]");
    if (note !== null) note.hidden = true;
    // Swapped rather than added: "Starting…" and "could not start" on screen
    // together is the app contradicting itself.
    if (failed !== null) failed.hidden = false;
  }

  window.addEventListener(
    "error",
    function (event) {
      // Capture, because a resource's `error` event does not bubble -- a
      // bubble-phase listener on window hears a thrown exception and never
      // hears a script that failed to download, which is the case this exists
      // for. It is also why the listener can be installed before the <script>
      // element it is about has even been parsed.
      var target = event.target;
      // A SCRIPT that would not load, or a throw (whose target is the window).
      // A stylesheet or an icon that 404s is a degraded page, not an app that
      // cannot start, and claiming otherwise would be its own lie.
      if (target && target !== window && target.tagName !== "SCRIPT") return;
      fail();
    },
    true,
  );
})();
