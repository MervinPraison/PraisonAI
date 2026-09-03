// The web build's service worker. tools/build-webview.mjs writes the two
// tokens below at build time: the precache list is exactly the files the
// build emitted, and the cache name carries a hash of their bytes, so a new
// build is a new cache and an old one is deleted on activate.
//
// Strategy:
//   navigation  -- network-first, falling back to the precached index.html.
//                  A user with a network gets the current page; one without
//                  gets the last one that loaded, instead of the dinosaur.
//   precached   -- cache-first. These bytes are the ones the cache name was
//                  derived from; the network cannot have a different answer
//                  without the worker itself having changed.
//   anything else same-origin -- straight to the network. Cross-origin (the
//                  engine at 127.0.0.1:8765, an https engine) is never touched.
const CACHE = "praisonai-mobile-__BUILD_ID__";
const CACHE_PREFIX = "praisonai-mobile-";
const PRECACHE = __PRECACHE__;

const INDEX = new URL("./index.html", self.location.href).href;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            event.waitUntil(caches.open(CACHE).then((cache) => cache.put(INDEX, copy)));
          }
          return response;
        })
        .catch(() => caches.match(INDEX)),
    );
    return;
  }

  event.respondWith(
    caches.match(request, { ignoreSearch: true }).then((hit) => {
      if (hit) return hit;
      // A same-origin file that is not precached is a LAZY chunk: the build
      // leaves those out on purpose (see tools/build-webview.mjs) so a browser
      // does not download 1.4MB it may never use. Cache each one as it is
      // actually fetched, and a feature that has been used once still works
      // offline. It goes into the SAME versioned cache, so a new build drops
      // these along with everything else rather than leaving a chunk from an
      // older app behind to be paired with a newer one.
      return fetch(request).then((response) => {
        if (response.ok && response.type === "basic") {
          const copy = response.clone();
          event.waitUntil(caches.open(CACHE).then((cache) => cache.put(request, copy)));
        }
        return response;
      });
    }),
  );
});
