// Iveri AI Customer Support Assistant - Progressive Web App Service Worker
const CACHE_NAME = 'iveri-pwa-v1';
const STATIC_ASSETS = [
  '/',
  '/dashboard',
  '/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/iveri-avatar.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('PWA Asset pre-cache partial warning:', err);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Network-first strategy for dynamic API calls, cache-fallback for static shell
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip caching for backend APIs and SSE streaming
  if (url.pathname.startsWith('/api/') || event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
        }
        return networkResponse;
      })
      .catch(() => {
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) return cachedResponse;
          if (event.request.mode === 'navigate') {
            return caches.match('/dashboard');
          }
        });
      })
  );
});

// Web Push Notification Handler (Native Phone Vibration, App Icon Badging & Ringing)
self.addEventListener('push', (event) => {
  let payload = {
    title: '🔔 Iveri Customer Notification',
    body: 'A new customer request or ticket requires your attention.',
    url: '/dashboard#tickets',
    tag: 'iveri-alert',
    unread_count: 1
  };

  if (event.data) {
    try {
      payload = event.data.json();
    } catch (e) {
      payload.body = event.data.text();
    }
  }

  // 1. Update Native Home Screen App Icon Badge Count (like WhatsApp)
  const unreadCount = parseInt(payload.unread_count || 1, 10);
  if ('setAppBadge' in self.navigator) {
    self.navigator.setAppBadge(unreadCount).catch((err) => {
      console.warn('App badge set error:', err);
    });
  }

  // 2. High-Priority System Notification (wakes closed phone with vibration & sound)
  const notificationOptions = {
    body: payload.body,
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    vibrate: [300, 100, 300, 100, 300],
    data: {
      url: payload.url || '/dashboard#tickets',
      unread_count: unreadCount
    },
    actions: [
      { action: 'open', title: 'Open Dashboard' },
      { action: 'dismiss', title: 'Dismiss' }
    ],
    tag: payload.tag || 'iveri-ticket',
    renotify: true,
    requireInteraction: true
  };

  event.waitUntil(
    self.registration.showNotification(payload.title, notificationOptions)
  );
});

// Notification Tap / Click Action
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  // Clear or reset native app badge on user engagement
  if ('clearAppBadge' in self.navigator) {
    self.navigator.clearAppBadge().catch(() => {});
  }

  if (event.action === 'dismiss') {
    return;
  }

  const targetUrl = (event.notification.data && event.notification.data.url) ? event.notification.data.url : '/dashboard#tickets';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes('/dashboard') && 'focus' in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});

// App Badge Communication Channel with Frontend
self.addEventListener('message', (event) => {
  if (!event.data) return;
  if (event.data.type === 'SET_BADGE') {
    const count = parseInt(event.data.count || 0, 10);
    if ('setAppBadge' in self.navigator) {
      if (count > 0) self.navigator.setAppBadge(count).catch(() => {});
      else if ('clearAppBadge' in self.navigator) self.navigator.clearAppBadge().catch(() => {});
    }
  } else if (event.data.type === 'CLEAR_BADGE') {
    if ('clearAppBadge' in self.navigator) {
      self.navigator.clearAppBadge().catch(() => {});
    }
  }
});
