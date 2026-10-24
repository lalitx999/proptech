// ==============================================================================
// PropTech Service Worker (PWA)
// Security Policy: Strict Zero-Sensitive-Cache Policy & Same-Origin Only
// ==============================================================================

const CACHE_VERSION = 'proptech-v1.0.3';
const STATIC_CACHE_NAME = `static-${CACHE_VERSION}`;
const DYNAMIC_CACHE_NAME = `dynamic-${CACHE_VERSION}`;

// Pre-cached assets (Static UI shell only)
const STATIC_ASSETS = [
    '/',
    '/static/manifest.json',
    '/static/images/logo.png',
];

// STRICT SECURITY EXCLUSION LIST: Never cache sensitive or authenticated endpoints
const SENSITIVE_URL_PATTERNS = [
    /^\/accounts\//,
    /^\/admin\//,
    /^\/dev-admin-only\//,
    /^\/properties\//,
    /^\/internal-media\//,
    /^\/contracts\//,
    /^\/api\/private\//,
];

function isSensitiveRequest(url, request) {
    if (request.method !== 'GET') {
        return true;
    }
    return SENSITIVE_URL_PATTERNS.some(pattern => pattern.test(url.pathname));
}

// Install Event: Pre-cache static shell & skip waiting
self.addEventListener('install', event => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(STATIC_CACHE_NAME).then(cache => {
            return cache.addAll(STATIC_ASSETS);
        }).catch(err => console.log('SW install cache error:', err))
    );
});

// Activate Event: Clear obsolete cache versions and take immediate control
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== STATIC_CACHE_NAME && cacheName !== DYNAMIC_CACHE_NAME) {
                        console.log('Purging legacy cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Fetch Event: ONLY handle same-origin requests. Never interfere with external CDNs!
self.addEventListener('fetch', event => {
    const request = event.request;

    // 1. Only handle GET requests
    if (request.method !== 'GET') {
        return;
    }

    const url = new URL(request.url);

    // 2. CRITICAL: NEVER intercept cross-origin CDNs (Tailwind, Fonts, Unpkg)
    // Intercepting external CDNs causes CSS/script corruption upon page refresh!
    if (url.origin !== location.origin) {
        return;
    }

    // 3. Sensitive / Auth routes: strictly bypass cache and fetch from network
    if (isSensitiveRequest(url, request)) {
        return;
    }

    // 4. Same-origin Static Assets (/static/): Cache First, fallback to Network
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(request).then(cachedResponse => {
                if (cachedResponse) return cachedResponse;
                return fetch(request).then(networkResponse => {
                    if (networkResponse && networkResponse.status === 200) {
                        const responseToCache = networkResponse.clone();
                        caches.open(STATIC_CACHE_NAME).then(cache => {
                            cache.put(request, responseToCache);
                        });
                    }
                    return networkResponse;
                });
            })
        );
        return;
    }

    // 5. HTML Navigation Requests ONLY: Network First, fallback to cached home page
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request).then(networkResponse => {
                if (networkResponse && networkResponse.status === 200) {
                    const responseToCache = networkResponse.clone();
                    caches.open(DYNAMIC_CACHE_NAME).then(cache => {
                        cache.put(request, responseToCache);
                    });
                }
                return networkResponse;
            }).catch(() => {
                return caches.match(request).then(cachedResponse => {
                    return cachedResponse || caches.match('/');
                });
            })
        );
        return;
    }
});
