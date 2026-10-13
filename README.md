# GALILEA — Joyería contemporánea

Tienda + panel `/admin` + backend Python (aiohttp). `python server.py` y abrí http://localhost:3000.
`server.py` lee el archivo `.env` automáticamente (copiá `.env.example` a `.env`).

## Mercado Pago (Checkout Pro)
- `POST /api/checkout/preference` crea la orden **pendiente** con precios del catálogo (nunca del cliente) y devuelve `init_point` (la tienda redirige ahí). Tarjeta y Mercado Pago usan este mismo flujo: los datos de tarjeta nunca pasan por nuestro servidor (`/api/checkout/process-card` → 410).
- La orden pasa a *approved* solo cuando la API de MP lo confirma: por webhook (`POST /api/checkout/webhook`) o al volver a la tienda (`POST /api/checkout/confirm`, verifica el `payment_id` contra MP). Si el monto no coincide queda *en revisión*.
- Sin `MERCADOPAGO_ACCESS_TOKEN` funciona en modo prueba: crea la orden pendiente y no cobra nada.
- La transferencia también calcula el total en el servidor (con el % de descuento del panel).

### Probar en local (credenciales de prueba)
1. En `.env`: `MERCADOPAGO_ACCESS_TOKEN` de prueba y `SITE_URL=http://localhost:3000`.
2. `python server.py`, agregá una joya a la bolsa y pagá con Mercado Pago o Tarjeta.
3. En MP, en una ventana de incógnito, iniciá sesión con el **usuario comprador de prueba** y pagá con una tarjeta de prueba (titular `APRO` = aprobado, `OTHE` = rechazado, DNI 12345678).
4. En local MP no puede volver solo (`auto_return` exige https) ni mandar el webhook: tocá **"Volver al sitio"** y la tienda verifica el pago. El pedido aparece en `/admin` como aprobado y pasa a taller.

### Producción
1. Credenciales **productivas** de la cuenta real en `MERCADOPAGO_ACCESS_TOKEN` (variable de entorno; en Vercel: Settings → Environment Variables).
2. `SITE_URL=https://tudominio` (con https se activan `auto_return` y `notification_url`).
3. En el panel de MP: Webhooks → evento *Pagos* → `SITE_URL/api/checkout/webhook`, y copiá la clave secreta a `MERCADOPAGO_WEBHOOK_SECRET`.
4. `SESSION_SECRET` con un valor largo y aleatorio (sin él, las sesiones del panel no duran en Vercel).

Lógica de pagos en `payments.py` (la usan `server.py` y `api/index.py`).

## Catálogo: tipos de joya, materiales y talles
- En `/admin` → Catálogo → **Categorías y materiales** se agregan o quitan opciones (anillos, dijes, tobilleras… / oro, plata, acero quirúrgico, bronce platinado, fantasía…). Las que tienen joyas asignadas no se pueden quitar.
- Se guardan en `data/settings.json` (`categories`, `materials`); si no están, se usan las sugeridas de `catalog.py`.
- Cada joya tiene sus talles o medidas (separados por coma; vacío = "Único").
- En la tienda, el filtro de material y la barra de categorías muestran solo lo que tiene joyas.

## Panel /admin y seguridad
- Contraseñas guardadas con hash en `data/users.json`. Para cambiar una: `python auth.py <usuario>`.
- Las sesiones son tokens firmados (`auth.py`), válidos 12 h. Pedidos, KPIs y cambios de estado requieren iniciar sesión.
- El Access Token cargado desde el panel nunca se devuelve por la API pública.
- Imágenes subidas: se valida el contenido real (JPG/PNG/WebP/GIF, máx. 6 MB) en `uploads.py`.

## Pendiente antes de publicar en Vercel
- Vercel no tiene disco persistente: órdenes, ajustes y fotos subidas viven en `/tmp` y se pierden al reciclarse la instancia. Hace falta una base de datos (y un almacenamiento de imágenes) o correr `server.py` en un hosting con disco. Los datos de cada pago con MP igual quedan guardados en Mercado Pago (`metadata` de la preferencia).
- En Vercel, las joyas que se crean, editan o borran desde el panel también viven en `/tmp` (mismo problema).
