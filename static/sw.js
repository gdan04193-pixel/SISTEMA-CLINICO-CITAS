// ============================================================
// static/sw.js — Service Worker Principal de HealthVault PWA
// Práctica 2.2: PWA Completa Publicada (App Shell, Offline & Push)
// ============================================================

const CACHE_NAME = 'healthvault-v2.2-prod';
const OFFLINE_URL = '/offline';

// Recursos de App Shell a pre-cachear durante la instalación
const APP_SHELL_ASSETS = [
  '/',
  '/login',
  '/offline',
  '/manifest.json',
  '/static/css/main.css',
  '/static/css/pwa.css',
  '/static/css/chatbot.css',
  '/static/js/main.js',
  '/static/js/pwa.js',
  '/static/logo.png',
  '/static/icons/icon-72x72.png',
  '/static/icons/icon-96x96.png',
  '/static/icons/icon-128x128.png',
  '/static/icons/icon-144x144.png',
  '/static/icons/icon-152x152.png',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-384x384.png',
  '/static/icons/icon-512x512.png',
  '/static/icons/apple-touch-icon.png'
];

// ── 1. Instalación: Pre-caching del App Shell ────────────────────────────────
self.addEventListener('install', event => {
  console.log('[SW v2.2] Instalando Service Worker y pre-cacheando App Shell...');
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      console.log('[SW v2.2] Guardando recursos esenciales en cache...');
      // Usamos map individual con catch para no fallar si algún recurso dinámico cambia
      return Promise.all(
        APP_SHELL_ASSETS.map(url => {
          return cache.add(url).catch(err => {
            console.warn(`[SW v2.2] No se pudo pre-cachear: ${url}`, err);
          });
        })
      );
    }).then(() => self.skipWaiting())
  );
});

// ── 2. Activación: Limpieza de versiones obsoletas y control inmediato ────────
self.addEventListener('activate', event => {
  console.log('[SW v2.2] Activando nuevo Service Worker...');
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => {
          console.log('[SW v2.2] Purgando caché obsoleta:', k);
          return caches.delete(k);
        })
      )
    ).then(() => {
      console.log('[SW v2.2] Reclamando clientes activos.');
      return self.clients.claim();
    })
  );
});

// ── 3. Fetch: Estrategias híbridas (Cache-First para estáticos, Network-First para páginas) ───
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  if (!event.request.url.startsWith(self.location.origin)) return;

  const requestUrl = new URL(event.request.url);

  // A. Recursos estáticos inmutables (CSS, JS, imágenes, fuentes) -> Cache-First
  if (
    requestUrl.pathname.startsWith('/static/') ||
    requestUrl.pathname.startsWith('/manifest.json')
  ) {
    event.respondWith(
      caches.match(event.request).then(cachedResponse => {
        if (cachedResponse) {
          // Revalidar en segundo plano (Stale-While-Revalidate)
          fetch(event.request).then(networkResponse => {
            if (networkResponse && networkResponse.status === 200) {
              caches.open(CACHE_NAME).then(cache => cache.put(event.request, networkResponse));
            }
          }).catch(() => {/* offline silencioso */});
          return cachedResponse;
        }

        return fetch(event.request).then(networkResponse => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return networkResponse;
        });
      })
    );
    return;
  }

  // B. Páginas HTML / Rutas dinámicas -> Network-First con fallback a Caché y luego a /offline
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response && response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(async () => {
        console.log('[SW v2.2] Red no disponible, buscando en caché:', event.request.url);
        const cached = await caches.match(event.request);
        if (cached) return cached;

        // Si es navegación entre páginas, mostrar fallback amigable
        if (event.request.mode === 'navigate') {
          const offlinePage = await caches.match(OFFLINE_URL);
          if (offlinePage) return offlinePage;
          return caches.match('/login');
        }

        return new Response('Recurso no disponible offline', {
          status: 503,
          statusText: 'Service Unavailable',
          headers: new Headers({ 'Content-Type': 'text/plain; charset=utf-8' })
        });
      })
  );
});

// ── 4. Push: Recepción de notificaciones push del servidor VAPID ──────────────
self.addEventListener('push', event => {
  console.log('[SW v2.2] Evento push recibido:', event);

  let data = {
    title: '🏥 HealthVault PWA',
    body: 'Notificación del sistema clínico HealthVault.',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/badge-96x96.png',
    tag: 'healthvault-notif',
    data: { url: '/dashboard' }
  };

  if (event.data) {
    try {
      const pushed = event.data.json();
      data = { ...data, ...pushed };
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: data.icon,
    badge: data.badge,
    tag: data.tag,
    data: data.data,
    vibrate: [200, 100, 200],
    actions: [
      { action: 'open', title: '📂 Abrir HealthVault' },
      { action: 'dismiss', title: '✕ Descartar' }
    ],
    requireInteraction: false
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// ── 5. NotificationClick: Gestión de clic e interacciones ──────────────────────
self.addEventListener('notificationclick', event => {
  console.log('[SW v2.2] Click en notificación:', event.action);
  event.notification.close();

  if (event.action === 'dismiss') return;

  const urlToOpen = (event.notification.data && event.notification.data.url)
    ? event.notification.data.url
    : '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(windowClients => {
        for (const client of windowClients) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            client.navigate(urlToOpen);
            return client.focus();
          }
        }
        if (clients.openWindow) {
          return clients.openWindow(urlToOpen);
        }
      })
  );
});

// ── 6. Background Sync: Sincronización offline en segundo plano ────────────────
self.addEventListener('sync', event => {
  if (event.tag === 'sync-records') {
    console.log('[SW v2.2] Sincronización en segundo plano de expedientes offline...');
    event.waitUntil(
      // Lógica de sincronización diferida
      Promise.resolve()
    );
  }
});

console.log('[SW v2.2] HealthVault Service Worker registrado y activo.');
