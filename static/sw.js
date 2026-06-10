/**
 * PorraCarLOL — Service Worker
 * Cache-first para estáticos, red directa para todo lo demás (API siempre fresca).
 */
const CACHE_NAME = 'porracarlol-v1';
const STATIC_ASSETS = [
    '/static/css/styles.css',
    '/static/js/app.js',
    '/static/manifest.json',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Solo gestionamos GET de estáticos propios; API y páginas van siempre a red
    const isStatic = url.origin === self.location.origin && url.pathname.startsWith('/static/');
    if (event.request.method !== 'GET' || !isStatic) return;

    event.respondWith(
        fetch(event.request)
            .then((response) => {
                const copy = response.clone();
                caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});
