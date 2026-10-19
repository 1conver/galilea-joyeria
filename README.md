# GALILEA — Joyería contemporánea

Tienda + panel `/admin` + backend Python. Local: `python server.py` y abrí http://localhost:3000
(lee `.env` automáticamente; copiá `.env.example` a `.env`). En Vercel corre `api/index.py`.

## Cómo está armado
- `api_core.py`: toda la API, una sola vez. `server.py` (local, aiohttp) y `api/index.py` (Vercel) solo la conectan.
- `store.py`: dónde se guardan los datos. Local: archivos en `data/`. Vercel con Upstash Redis: en Redis
  (no se pierde nada). Vercel sin Redis: temporal en `/tmp` (se borra cada tanto). El panel muestra cuál está activo.
- `payments.py` (Mercado Pago y transferencia), `catalog.py` (categorías, materiales, talles y stock),
  `notify.py` (emails), `uploads.py` (fotos), `auth.py` (contraseñas y sesiones).

## Vercel: qué hay que conectar
1. **Storage → Upstash Redis** (Marketplace) conectado al proyecto: guarda pedidos, stock, joyas y ajustes.
   La primera vez copia el catálogo de `data/`; después el catálogo se maneja desde el panel.
2. **Storage → Blob** (acceso público) conectado al proyecto: guarda las fotos que se suben desde el panel.
3. Variables de entorno: `MERCADOPAGO_ACCESS_TOKEN`, `SITE_URL=https://www.galilea.online`, `SESSION_SECRET`,
   `MERCADOPAGO_WEBHOOK_SECRET`, y para emails `SMTP_USER` + `SMTP_PASSWORD` (casilla de Hostinger).
4. Después de cada cambio de variables o de Storage: **Redeploy**.

## Mercado Pago (Checkout Pro)
- La orden se crea **pendiente** con precios y stock del catálogo (nunca del cliente) y pasa a *approved* solo
  cuando la API de MP lo confirma: webhook (`/api/checkout/webhook`) o vuelta a la tienda (`/api/checkout/confirm`).
  Si el monto no coincide queda *en revisión*.
- Al aprobarse: se descuenta el stock y se avisa al cliente por email (una sola vez, aunque lleguen webhook y vuelta juntos).
- Sin `MERCADOPAGO_ACCESS_TOKEN` funciona en modo prueba (orden pendiente, no cobra).
- Prueba: usuario comprador de prueba + tarjeta de prueba con titular `APRO` (aprobado), `OTHE` (rechazado), `CONT` (pendiente).

## Pedidos y avisos al cliente
- Emails automáticos: transferencia (con datos bancarios), pago confirmado, despachado (con link de Andreani) y entregado.
- En el panel, cada pedido tiene un botón de **WhatsApp** con el mensaje armado según su estado.
- **Seguí tu pedido**: el cliente pone código + email y ve el estado, el historial y el link de Andreani
  (también se abre desde `/?pedido=CODIGO`, el link que va en los emails). No hay cuentas de cliente.

## Portada y cuenta para transferencias
- La foto de portada se cambia en `/admin` → **Ajustes** (subir, arrastrar o pegar link; "Volver a la foto original").
  Ahí mismo, **Fotos de categorías** cambia las 6 tarjetas de "Explorá por categoría".
- La cuenta donde transfieren los clientes (banco, titular, CUIT/CUIL, CBU/CVU, alias) también va en **Ajustes**.
  Mientras no se cargue, la tienda muestra la cuenta de ejemplo de `payments.py` y el panel lo avisa.
  Cada pedido guarda la cuenta vigente al comprar, que es la que sale en su email.
- Cambiar la cuenta pide la **contraseña** de quien está en el panel. Con emails activos (SMTP) pide además un
  **código de 6 números** que llega a `BANK_CONFIRM_EMAIL` (o, si no está, a `SMTP_USER`); esa casilla se define
  en Vercel y no se puede cambiar desde el panel. El código vale 10 minutos, una sola vez y solo para esos datos.
  Queda registrado quién y cuándo cambió la cuenta (se ve en Ajustes).

## Contacto e Instagram
- WhatsApp e Instagram se editan en `/admin` → **Ajustes** → Contacto y redes. Los usan los botones de la
  tienda (encabezado, pie, chat) y las respuestas del chat. Por defecto: +54 9 11 5419-7890 y @galileaacc.
- Feed de publicaciones (opcional): cargá `INSTAGRAM_ACCESS_TOKEN` en Vercel (token de larga duración de la
  "API de Instagram con inicio de sesión de Instagram", cuenta profesional). Se renueva solo cada 7 días y las
  publicaciones se guardan 1 hora. Sin token, la sección muestra el perfil con el botón para seguirlo.
  Instagram no ofrece webhook para las publicaciones propias, por eso se consulta así (`instagram.py`).

## Catálogo
- Tipos de joya y materiales configurables desde `/admin` → Catálogo → **Categorías y materiales**.
- Stock por unidades (vacío = sin control). Al llegar a 0 la joya queda **Agotada** y no se puede comprar.
- Talles o medidas por joya. Las fotos se achican en el navegador antes de subir.

## Seguridad
- Contraseñas con hash en `data/users.json`; cambiar una: `python auth.py <usuario>`. Las cuentas creadas desde
  el panel van a la base (local: `data/users_extra.json`, ignorado por git).
- Sesiones firmadas con `SESSION_SECRET` (12 h). Pedidos y KPIs requieren login; la API pública no expone el token de MP.
