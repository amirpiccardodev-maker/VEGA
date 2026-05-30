// Service Worker minimo per rendere Vega una PWA installabile.
// Cache statici (CSS/JS/icone), passa attraverso le API live.
const CACHE_NAME = "vega-v15-orb";
const STATIC_ASSETS = [
  "/",
  "/style.css",
  "/theme.css",
  "/vega.js",
  "/manifest.json",
  "/assets/vega.ico",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((c) => c.addAll(STATIC_ASSETS).catch(() => null))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ===== Web Push notifications =====
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) {}
  const title = data.title || "Vega";
  const opts = {
    body: data.body || "",
    icon: "/assets/vega_preview.png",
    badge: "/assets/vega.ico",
    data: { url: data.url || "/" },
    vibrate: [100, 50, 100],
  };
  event.waitUntil(self.registration.showNotification(title, opts));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/";
  event.waitUntil(
    clients.matchAll({ type: "window" }).then((wins) => {
      for (const w of wins) {
        if (w.url.includes(url) && "focus" in w) return w.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Never cache API or WebSocket
  if (url.pathname.startsWith("/api/") || url.pathname === "/ws" || url.pathname.startsWith("/assets/music/")) {
    return;
  }
  if (e.request.method !== "GET") return;
  // Network-first: always serve the freshest code when the server is reachable,
  // fall back to the cached copy only when offline. This prevents stale JS/CSS
  // from shadowing updates (cache-first did exactly that). Cache stays populated
  // for offline PWA use.
  e.respondWith(
    fetch(e.request).then((resp) => {
      if (resp && resp.ok) {
        const clone = resp.clone();
        caches.open(CACHE_NAME).then((c) => c.put(e.request, clone).catch(() => null));
      }
      return resp;
    }).catch(() => caches.match(e.request))
  );
});
