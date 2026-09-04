/* sw-push.js — Service Worker Web Push CV. Dewi Aditya ERP.
 *
 * Sengaja MINIMAL & tanpa caching: satu-satunya tugasnya menerima event `push`
 * lalu membuka halaman yang tepat saat notifikasi diklik. Tidak ada precache
 * supaya SW ini tidak pernah menyajikan bundle React yang kedaluwarsa
 * (sumber bug klasik "aplikasi tidak berubah setelah deploy").
 *
 * Didaftarkan oleh src/components/erp/PushNotificationToggle.jsx
 * (`navigator.serviceWorker.register('/sw-push.js')`).
 *
 * FASE 19 / AUDIT-2: berkas ini SEBELUMNYA TIDAK ADA sama sekali, padahal
 * PushNotificationToggle sudah memanggilnya — jadi tombol "Aktifkan Notifikasi"
 * selalu gagal di langkah pertama, bahkan jika VAPID sudah dikonfigurasi.
 */
/* eslint-env serviceworker */

self.addEventListener('install', () => {
  // Aktif segera — jangan menunggu tab lama ditutup.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (e) {
    payload = { title: 'CV. Dewi Aditya ERP', body: event.data ? event.data.text() : '' };
  }

  const title = payload.title || 'CV. Dewi Aditya ERP';
  const options = {
    body: payload.body || '',
    icon: payload.icon || '/logo192.png',
    badge: payload.badge || '/favicon-32x32.png',
    tag: payload.tag || 'da-erp',
    renotify: true,
    requireInteraction: false,
    data: { url: (payload.data && payload.data.url) || payload.url || '/' },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Fokuskan tab ERP yang sudah terbuka daripada membuka tab baru.
      for (const client of clientList) {
        if ('focus' in client && client.url.includes(target)) return client.focus();
      }
      for (const client of clientList) {
        if ('navigate' in client && 'focus' in client) {
          return client.navigate(target).then((c) => (c ? c.focus() : null));
        }
      }
      return self.clients.openWindow ? self.clients.openWindow(target) : null;
    })
  );
});

self.addEventListener('pushsubscriptionchange', (event) => {
  // Browser memutar ulang subscription: beri tahu semua tab agar re-subscribe.
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      clientList.forEach((c) => c.postMessage({ type: 'PUSH_SUBSCRIPTION_CHANGED' }));
    })
  );
});
