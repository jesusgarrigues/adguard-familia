// Only allowlisted public assets are cached. Accounts, API responses and HTML are never cached.
const CACHE = 'parental-static-v1';
const PUBLIC = new Set([
  '/manifest.webmanifest', '/icon-192.png', '/icon-512.png', '/apple-touch-icon.png', '/favicon.png', '/icon.svg',
  '/assets/app.css', '/assets/parental.css', '/assets/app-shell.js', '/assets/client-settings.js', '/assets/fonts/InterVariable.woff2',
  ...['monitor','laptop','smartphone','tablet','gamepad-2','tv','router','printer','speaker','headphones','watch','server'].map(id => '/assets/icons/' + id + '.svg')
]);
const OFFLINE = '<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#ffffff"><title>Parental · Sin conexión</title><style>body{font-family:system-ui,sans-serif;padding:56px 24px;max-width:440px;margin:auto;color:#111}img{width:64px;border-radius:16px}h1{font-size:30px;letter-spacing:-1px}p{color:#62666d;line-height:1.6}button{background:#111;color:#fff;border:0;border-radius:99px;padding:14px 24px;font:inherit}</style><img src="/apple-touch-icon.png" alt=""><h1>Sin conexión</h1><p>Conecta con tu servidor para consultar tus clientes, solicitudes y permisos.</p><button onclick="location.reload()">Volver a intentar</button></html>';
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await Promise.allSettled([...PUBLIC].map(async path => {
      const response = await fetch(path, {cache: 'reload', credentials: 'omit'});
      if (response.ok && !response.redirected) await cache.put(path, response);
    }));
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', event => event.waitUntil((async () => {
  for (const name of await caches.keys()) if (name.startsWith('parental-static-') && name !== CACHE) await caches.delete(name);
  await self.clients.claim();
})()));
self.addEventListener('fetch', event => {
  const request = event.request, url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => new Response(OFFLINE, {headers: {'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store'}})));
    return;
  }
  if (!PUBLIC.has(url.pathname)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const response = await fetch(request);
      if (response.ok && !response.redirected) await cache.put(url.pathname, response.clone());
      return response;
    } catch {
      return await cache.match(url.pathname) || Response.error();
    }
  })());
});
