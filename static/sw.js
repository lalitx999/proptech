// ==============================================================================
// PropTech Service Worker (PWA)
// Security Policy: Strict Zero-Sensitive-Cache Policy
// ==============================================================================

const CACHE_VERSION = 'proptech-v1.0.0';
const STATIC_CACHE_NAME = `static-${CACHE_VERSION}`;
const DYNAMIC_CACHE_NAME = `dynamic-${CACHE_VERSION}`;

// Pre-cached assets (Static UI shell only)
const STATIC_ASSETS = [
    '/',
    '/static/manifest.json',
];

// ⚠️ STRICT SECURITY EXCLUSION LIST: Never cache sensitive or authenticated endpoints
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
    // 1. Only GET requests may ever be considered for caching
    if (request.method !== 'GET') {
        return true;
    }
    // 2. Check path against sensitive blacklist
    return SENSITIVE_URL_PATTERNS.some(pattern => pattern.test(url.pathname));
}

// Install Event: Pre-cache static shell
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(STATIC_CACHE_NAME).then(cache => {
            return cache.addAll(STATIC_ASSETS);
        }).then(() => self.skipWaiting())
    );
});

// Activate Event: Clear obsolete cache versions
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== STATIC_CACHE_NAME && cacheName !== DYNAMIC_CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Fetch Event: Enforce routing & cache isolation
self.addEventListener('fetch', event => {
    const request = event.request;
    const url = new URL(request.url);

    // If same origin and matches sensitive paths -> strictly fetch directly from network!
    if (url.origin === location.origin && isSensitiveRequest(url, request)) {
        event.respondWith(fetch(request));
        return;
    }

    // Static Assets: Cache First, fallback to Network
    if (url.origin === location.origin && url.pathname.startsWith('/static/')) {
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

    // Public Listings: Network First, fallback to Cache for offline support
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
});
