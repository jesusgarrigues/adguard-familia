// Authenticated content is never cached. All operations require the server.
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{if(event.request.mode==='navigate')event.respondWith(fetch(event.request).catch(()=>new Response('<html lang="es"><meta name="viewport" content="width=device-width"><h1>Sin conexión</h1><p>Conecta con tu servidor para consultar solicitudes y permisos.</p></html>',{headers:{'Content-Type':'text/html; charset=utf-8'}})))});
