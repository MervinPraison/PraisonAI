// Registers the service worker for the WEB build only.
//
// An external file rather than an inline <script>, because index.html ships a
// `script-src 'self'` CSP and an inline script would be blocked with nothing
// but a console line to say so.
//
// Two guards, both deliberate:
//   - `serviceWorker in navigator`: a browser without the API (or a page on an
//     insecure origin, where the property is simply absent) boots normally
//     without one.
//   - `__TAURI_INTERNALS__`: inside the Tauri shell the page is served by a
//     custom-protocol handler, and a worker caching those responses would put
//     a second copy of the app between the shell and its own assets. The web
//     platform is the only one that needs offline precaching; the app IS the
//     offline copy everywhere else.
(function () {
  if (!("serviceWorker" in navigator)) return;
  if ("__TAURI_INTERNALS__" in window) return;
  if (!/^https?:$/.test(location.protocol)) return;
  navigator.serviceWorker.register("./sw.js").catch(function (error) {
    // Registration failing is a degraded page, not a broken one: the app still
    // boots from the network. Say so rather than throwing into nowhere.
    console.warn("praisonai: service worker not registered:", error);
  });
})();
