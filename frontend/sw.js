/* Riot Music — Service Worker.
   Strategie: Network-first für eigene Seiten/Assets (immer aktuell, kein
   Stale-JS nach Deploys), Cache nur als Offline-Fallback. API, Medien
   (Audio/Bilder) und Range-Requests werden NIE gecacht (immer direkt aus dem
   Netz gestreamt). */
const CACHE = "riot-music-v1";
const SHELL = [
  "/", "/index.html",
  "/css/styles.css",
  "/js/app.js",
  "/favicon.svg",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  // Niemals cachen: API, Medien-Streaming, Range-Requests.
  if (url.pathname.startsWith("/api/") ||
      url.pathname.startsWith("/media/") ||
      req.headers.has("range")) return;

  e.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      })
      .catch(() =>
        caches.match(req).then((cached) =>
          cached || (req.mode === "navigate" ? caches.match("/index.html") : undefined)
        )
      )
  );
});
