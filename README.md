# GALILEA — Joyería contemporánea

Tienda + panel `/admin` + backend Python (aiohttp). `python server.py` y abrí http://localhost:3000.

## Mercado Pago (lo que te falta vincular)
1. Copiá `.env.example` a `.env` y completá `MERCADOPAGO_ACCESS_TOKEN` (empezá con el de prueba), `SITE_URL` y `MERCADOPAGO_WEBHOOK_SECRET`.
2. En el panel de MP, configurá el webhook (evento *Pagos*) a `SITE_URL/api/checkout/webhook`.
3. Flujo: `POST /api/checkout/preference` crea la orden **pendiente** con precios del catálogo (nunca del cliente) y devuelve `init_point` (redirigir ahí). La orden pasa a *approved* solo cuando MP lo confirma por webhook. Sin token funciona en modo prueba y no aprueba nada.
4. Tarjeta directa deshabilitada (`/api/checkout/process-card` → 410): se paga con Checkout Pro.

Lógica en `payments.py`. Credenciales de admin: definilas vos en `data/users.json` (ver pendientes de seguridad).
