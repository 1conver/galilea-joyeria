"""Servidor local de GALILEA (aiohttp): sirve la tienda y el panel, y pasa /api/* a api_core.
En Vercel la misma API corre desde api/index.py."""
import os
import asyncio
from aiohttp import web


def load_env_file(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    """Carga .env en os.environ (sin pisar variables ya definidas)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env_file()

import api_core
import notify
import payments
from store import get_store

PORT = int(os.environ.get("PORT", 3000))
PUBLIC_DIR = api_core.PUBLIC_DIR
UPLOADS_DIR = api_core.UPLOADS_DIR
os.makedirs(UPLOADS_DIR, exist_ok=True)


async def api_handler(request):
    body = {}
    if request.can_read_body:
        try:
            body = await request.json()
        except Exception:
            body = {}
    # api_core hace llamadas bloqueantes (Mercado Pago, email): van en un hilo aparte
    status, payload = await asyncio.to_thread(api_core.dispatch, request.method, request.path,
                                              dict(request.query), body, dict(request.headers))
    return web.json_response(payload, status=status)


def create_app():
    app = web.Application(client_max_size=10 * 1024 * 1024)

    async def no_cache_pages(request, response):
        # HTML/JS/CSS se revalidan en cada carga: después de un cambio nadie queda con una versión vieja
        if not request.path.startswith(("/api/", "/uploads/")):
            response.headers["Cache-Control"] = "no-cache"
    app.on_response_prepare.append(no_cache_pages)

    app.router.add_route("*", "/api/{tail:.*}", api_handler)

    # Archivos estáticos
    app.router.add_static("/css/", path=os.path.join(PUBLIC_DIR, "css"), name="css")
    app.router.add_static("/js/", path=os.path.join(PUBLIC_DIR, "js"), name="js")
    app.router.add_static("/uploads/", path=UPLOADS_DIR, name="uploads")
    app.router.add_static("/brand/", path=os.path.join(PUBLIC_DIR, "brand"), name="brand")

    async def admin_handler(request):
        return web.FileResponse(os.path.join(PUBLIC_DIR, "admin.html"))

    async def index_handler(request):
        return web.FileResponse(os.path.join(PUBLIC_DIR, "index.html"))

    app.router.add_get("/admin", admin_handler)
    app.router.add_get("/admin/", admin_handler)
    app.router.add_get("/", index_handler)
    return app


if __name__ == "__main__":
    print("==================================================")
    print("   GALILEA Atelier Joyería - Servidor Activo")
    print(f"   Tienda: http://localhost:{PORT}")
    print(f"   Panel:  http://localhost:{PORT}/admin")
    print(f"   Mercado Pago: {'CONFIGURADO' if payments.token() else 'SIN TOKEN (modo prueba, no aprueba pagos)'}")
    print(f"   Datos: {get_store().kind} | Emails: {'activos' if notify.configured() else 'sin configurar'}")
    print("==================================================")
    web.run_app(create_app(), host="127.0.0.1", port=PORT)
