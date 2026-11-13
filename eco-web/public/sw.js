// New Age AI service worker. Deliberately minimal: it only shows a friendly offline screen when a page can't load.
// It never caches pages, API responses or files, so no account data is ever stored on the device.
const CACHE = "nai-shell-v1";
const SHELL = ["/offline", "/icons/icon-192.png", "/favicon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.mode !== "navigate" || new URL(req.url).origin !== self.location.origin) return; // everything else: untouched
  e.respondWith(fetch(req).catch(() => caches.match("/offline")));
});
