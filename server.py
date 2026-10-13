import os
import json
import uuid
import secrets
from datetime import datetime
from aiohttp import web
import aiohttp_cors

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

import auth
import catalog
import payments
import uploads

try:
    from ai_advisor import process_chat_message
except ImportError:
    process_chat_message = None

PORT = int(os.environ.get("PORT", 3000))
SECRET_SETTINGS = ("mercadopago_access_token",)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "public")
UPLOADS_DIR = os.path.join(PUBLIC_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

PRODUCTS_FILE = os.path.join(DATA_DIR, "products.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# --- ACCESO A DATOS (PERSISTENCIA JSON) ---

def load_json(filepath, default_value=None):
    if default_value is None:
        default_value = []
    try:
        if not os.path.exists(filepath):
            return default_value
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error leyendo {filepath}: {e}")
        return default_value

def save_json(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error escribiendo {filepath}: {e}")
        return False

# Helpers específicos
def load_products(): return load_json(PRODUCTS_FILE, [])
def save_products(data): return save_json(PRODUCTS_FILE, data)

def load_orders(): return load_json(ORDERS_FILE, [])
def save_orders(data): return save_json(ORDERS_FILE, data)

def load_users(): return load_json(USERS_FILE, [])
def save_users(data): return save_json(USERS_FILE, data)

def load_settings(): return load_json(SETTINGS_FILE, {})
def save_settings(data): return save_json(SETTINGS_FILE, data)

def add_order(order_data):
    orders = load_orders()
    orders.insert(0, order_data)
    save_orders(orders)
    return order_data

# --- MIDDLEWARE / HELPER DE AUTENTICACIÓN ---

def get_current_user(request):
    return auth.user_from_header(request.headers.get("Authorization", ""))

def staff_required(request):
    """Pedidos y KPIs: cualquier cuenta del personal (admin u operario)."""
    user = get_current_user(request)
    if not user or user.get("role") not in ("admin", "operario"):
        return web.json_response({"success": False, "error": "Iniciá sesión en el panel"}, status=401)
    return None

def public_settings(settings):
    safe = {k: v for k, v in settings.items() if k not in SECRET_SETTINGS}
    safe["mercadopago_configured"] = bool(payments.token())
    return safe

# --- API DE AUTENTICACIÓN ---

async def handle_login(request):
    """POST /api/auth/login - Autenticación de Operarios y Administradores"""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Credenciales inválidas"}, status=400)

    login_id = data.get("email") or data.get("username") or data.get("user") or ""
    user = auth.find_user(load_users(), login_id, str(data.get("password", "")).strip())
    if not user:
        return web.json_response({"success": False, "error": "Usuario o contraseña incorrectos"}, status=401)

    return web.json_response({
        "success": True,
        "token": auth.issue_token(user),
        "user": auth.session_user(user)
    })

async def handle_me(request):
    """GET /api/auth/me - Verificación del usuario actual"""
    user = get_current_user(request)
    if not user:
        return web.json_response({"success": False, "error": "No autenticado"}, status=401)
    return web.json_response({"success": True, "user": user})

# --- API DE CONFIGURACIÓN DE LA TIENDA & OFERTAS ---

async def handle_get_settings(request):
    """GET /api/settings - Ajustes públicos (banners, textos de portada y descuentos)"""
    return web.json_response({"success": True, "settings": public_settings(load_settings())})

async def handle_update_settings(request):
    """PUT /api/admin/settings - Actualizar ofertas, textos de portada y descuentos (Solo Admin)"""
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return web.json_response({"success": False, "error": "Acceso restringido a administradores"}, status=403)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Datos inválidos"}, status=400)

    settings = load_settings()
    try:
        catalog.apply_option_settings(settings, data)  # categorías y materiales
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)}, status=400)
    for key in ["ticker_text", "hero_tag", "hero_title", "hero_desc", "transfer_discount_pct", "atelier_address", "contact_phone", "mercadopago_access_token", "mercadopago_public_key"]:
        if key in data:
            if key in SECRET_SETTINGS and not str(data[key]).strip():
                continue  # vacío = conservar el token guardado (el panel nunca lo muestra)
            settings[key] = data[key]

    save_settings(settings)
    return web.json_response({"success": True, "message": "Configuración de la tienda actualizada", "settings": public_settings(settings)})

# --- API DE GESTIÓN DE PERSONAL & OPERARIOS ---

async def handle_admin_get_users(request):
    """GET /api/admin/users - Listar cuentas de personal (Solo Admin)"""
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return web.json_response({"success": False, "error": "Acceso restringido"}, status=403)

    users = load_users()
    # Omitir contraseñas en la respuesta
    safe_users = [
        {
            "id": u["id"],
            "name": u["name"],
            "email": u["email"],
            "role": u["role"],
            "role_label": u.get("role_label", ""),
            "created_at": u.get("created_at", "")
        }
        for u in users
    ]
    return web.json_response({"success": True, "users": safe_users})

async def handle_admin_create_user(request):
    """POST /api/admin/users - Crear nueva cuenta de operario o administrador"""
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return web.json_response({"success": False, "error": "Acceso restringido"}, status=403)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Datos inválidos"}, status=400)

    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    role = data.get("role", "operario")

    if not name or not email or not password:
        return web.json_response({"success": False, "error": "Nombre, correo y contraseña requeridos"}, status=400)

    users = load_users()
    if any(u.get("email", "").lower() == email for u in users):
        return web.json_response({"success": False, "error": "Ese correo ya está registrado"}, status=400)

    if len(password) < 8:
        return web.json_response({"success": False, "error": "La contraseña debe tener al menos 8 caracteres"}, status=400)

    new_user = {
        "id": f"USR-{uuid.uuid4().hex[:4].upper()}",
        "name": name,
        "email": email,
        "password_hash": auth.hash_password(password),
        "role": role,
        "role_label": "Maestro Orfebre & Logística" if role == "operario" else "Administrador de Atelier",
        "created_at": datetime.now().strftime("%d/%m/%Y")
    }
    users.append(new_user)
    save_users(users)

    return web.json_response({
        "success": True,
        "message": f"Cuenta de {role} creada exitosamente",
        "user": {
            "id": new_user["id"],
            "name": new_user["name"],
            "email": new_user["email"],
            "role": new_user["role"],
            "role_label": new_user["role_label"]
        }
    })

# --- API DE CATÁLOGO EDITABLE (ADMIN) ---

async def handle_admin_create_product(request):
    """POST /api/admin/products - Dar de alta una nueva joya en el catálogo"""
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return web.json_response({"success": False, "error": "Acceso restringido"}, status=403)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Datos inválidos"}, status=400)

    products = load_products()
    try:
        new_prod = catalog.new_product(data, products, load_settings())
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)}, status=400)
    products.insert(0, new_prod)
    save_products(products)

    return web.json_response({"success": True, "message": "Joya creada en el catálogo", "product": new_prod})

async def handle_admin_update_product(request):
    """PUT /api/admin/products/{id} - Modificar precio, stock, imágenes o datos de una joya"""
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return web.json_response({"success": False, "error": "Acceso restringido a administradores"}, status=403)

    product_id = request.match_info.get("id")
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Datos inválidos"}, status=400)

    products = load_products()
    target_idx = next((i for i, p in enumerate(products) if p.get("id") == product_id), None)
    if target_idx is None:
        return web.json_response({"success": False, "error": "Producto no encontrado"}, status=404)

    prod = products[target_idx]
    try:
        catalog.update_product(prod, data, load_settings())
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)}, status=400)

    products[target_idx] = prod
    save_products(products)

    return web.json_response({"success": True, "message": "Joya actualizada correctamente", "product": prod})

async def handle_admin_delete_product(request):
    """DELETE /api/admin/products/{id} - Dar de baja una joya del catálogo"""
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return web.json_response({"success": False, "error": "Acceso restringido a administradores"}, status=403)

    product_id = request.match_info.get("id")
    products = load_products()
    filtered = [p for p in products if p.get("id") != product_id]

    if len(filtered) == len(products):
        return web.json_response({"success": False, "error": "Producto no encontrado"}, status=404)

    save_products(filtered)
    return web.json_response({"success": True, "message": f"Joya {product_id} eliminada del catálogo"})

async def handle_admin_upload(request):
    """POST /api/admin/upload - Subida directa de fotos locales para joyas"""
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return web.json_response({"success": False, "error": "Acceso restringido a administradores"}, status=403)

    os.makedirs(UPLOADS_DIR, exist_ok=True)

    try:
        content_type = request.content_type or ""
        file_bytes = None
        if "multipart" in content_type:
            reader = await request.multipart()
            field = await reader.next()
            while field:
                if field.name in ("file", "image", "foto"):
                    file_bytes = await field.read()
                    break
                field = await reader.next()
        elif "json" in content_type:
            data = await request.json()
            file_bytes = uploads.decode_base64(data.get("data") or data.get("image") or "")
        else:
            return web.json_response({"success": False, "error": "Formato de archivo no soportado"}, status=400)

        # Se valida el contenido real (un script renombrado a .png se rechaza)
        ext, _ = uploads.check_image(file_bytes)
        unique_name = f"joya_{int(datetime.now().timestamp())}_{secrets.token_hex(6)}{ext}"
        with open(os.path.join(UPLOADS_DIR, unique_name), "wb") as f:
            f.write(file_bytes)
        return web.json_response({
            "success": True,
            "url": f"/uploads/{unique_name}",
            "filename": unique_name
        })
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)}, status=400)
    except Exception as e:
        print("Error en upload:", e)
        return web.json_response({"success": False, "error": f"Error al procesar la imagen: {str(e)}"}, status=500)


# --- API CATÁLOGO PÚBLICO ---

async def handle_get_products(request):
    """GET /api/products - Catálogo filtrable y ordenable"""
    products = load_products()
    
    category = request.query.get("category", "todos").lower()
    metal = request.query.get("metal", "todos").lower()
    sort = request.query.get("sort", "featured")
    query = request.query.get("q", "").strip().lower()
    
    if category != "todos":
        products = [p for p in products if catalog.in_category(p, category)]

    if metal != "todos":
        products = [p for p in products if p.get("metal_group") == metal]
        
    if query:
        products = [
            p for p in products
            if query in p.get("name", "").lower() 
            or query in p.get("description", "").lower()
            or query in p.get("category_label", "").lower()
            or query in p.get("metal", "").lower()
        ]
        
    if sort == "price-asc":
        products.sort(key=lambda x: x.get("price", 0))
    elif sort == "price-desc":
        products.sort(key=lambda x: x.get("price", 0), reverse=True)
    elif sort == "featured":
        products.sort(key=lambda x: (not x.get("featured", False), x.get("name", "")))
        
    return web.json_response({
        "success": True,
        "total": len(products),
        "products": products
    })

async def handle_get_product_by_id(request):
    """GET /api/products/{id}"""
    product_id = request.match_info.get("id")
    products = load_products()
    product = next((p for p in products if p.get("id") == product_id), None)
    
    if not product:
        return web.json_response({"success": False, "error": "Producto no encontrado"}, status=404)
        
    return web.json_response({"success": True, "product": product})

async def handle_get_categories(request):
    """GET /api/categories"""
    products, settings = load_products(), load_settings()
    return web.json_response({
        "success": True,
        "categories": catalog.categories_with_counts(products, settings),
        "materials": catalog.materials_with_counts(products, settings)
    })

# --- COBROS CON AUTENTICACIÓN AUTOMÁTICA EN LA API ---

async def handle_process_card(request):
    """Deshabilitado: los datos de tarjeta no deben pasar por este servidor. Se paga con Mercado Pago."""
    return web.json_response({"success": False, "error": "Pagá con tarjeta desde Mercado Pago (hasta 6 cuotas)."}, status=410)

async def handle_create_mp_preference(request):
    """POST /api/checkout/preference - crea orden pendiente + preferencia de Mercado Pago"""
    try:
        data = await request.json()
        return web.json_response(payments.create_preference(data, load_products(), add_order))
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)}, status=400)
    except Exception as e:
        print("MP error:", e)
        return web.json_response({"success": False, "error": "No pudimos iniciar el pago"}, status=502)

async def handle_mp_webhook(request):
    """POST /api/checkout/webhook - notificaciones de Mercado Pago"""
    try: body = await request.json()
    except Exception: body = {}
    try:
        code, out = payments.process_webhook(dict(request.query), body, dict(request.headers), load_orders, save_orders)
    except Exception as e:
        print("Webhook error:", e); code, out = 500, {"error": "reintentar"}
    return web.json_response(out, status=code)

async def handle_mp_confirm(request):
    """POST /api/checkout/confirm - al volver de Mercado Pago, verifica el pago contra su API"""
    try:
        data = await request.json()
        return web.json_response(payments.confirm_payment(data, load_orders, save_orders))
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)}, status=400)
    except LookupError as e:
        return web.json_response({"success": False, "error": str(e)}, status=404)
    except Exception as e:
        print("MP confirm error:", e)
        return web.json_response({"success": False, "error": "No pudimos verificar el pago"}, status=502)

async def handle_bank_transfer(request):
    """POST /api/checkout/bank-transfer - Transferencia bancaria (Requiere validación de acreditación)"""
    try:
        data = await request.json()
        discount = load_settings().get("transfer_discount_pct", 15)
        return web.json_response(payments.create_transfer_order(data, load_products(), discount, add_order))
    except (ValueError, TypeError) as e:
        return web.json_response({"success": False, "error": str(e) or "Datos inválidos"}, status=400)
    except Exception:
        return web.json_response({"success": False, "error": "Datos inválidos"}, status=400)

# --- API DE CHAT CON INTELIGENCIA ARTIFICIAL & GUARDRAIL DE JOYERÍA ---

async def handle_ai_chat(request):
    """POST /api/chat - Asesoría Virtual Inteligente con Guardrail Exclusivo de Joyería"""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Datos inválidos"}, status=400)

    message = str(data.get("message", "")).strip()
    history = data.get("history", [])
    products = load_products()

    if process_chat_message:
        result = process_chat_message(message, history, products)
    else:
        result = {
            "success": True,
            "reply": "Bienvenido/a a <strong>GALILEA Atelier</strong>. ¿En qué pieza o consulta de joyería puedo orientarte hoy?",
            "products": products[:2],
            "provider": "galilea-fallback"
        }

    return web.json_response(result)

# --- API DE OPERARIOS: BANDEJA DE PEDIDOS & KPIs ---

async def handle_admin_get_orders(request):
    """GET /api/admin/orders - Bandeja de pedidos"""
    denied = staff_required(request)
    if denied:
        return denied
    orders = load_orders()
    status = request.query.get("status", "all")
    shipping = request.query.get("shipping", "all")
    method = request.query.get("method", "all")
    q = request.query.get("q", "").strip().lower()

    if status != "all":
        orders = [o for o in orders if o.get("payment_status") == status]
    if shipping != "all":
        orders = [o for o in orders if o.get("shipping_status") == shipping]
    if method != "all":
        orders = [o for o in orders if o.get("payment_method") == method]
        
    if q:
        orders = [
            o for o in orders
            if q in o.get("id", "").lower()
            or q in o.get("customer", {}).get("name", "").lower()
            or q in str(o.get("customer", {}).get("dni", "")).lower()
            or q in o.get("customer", {}).get("email", "").lower()
            or q in o.get("tracking_number", "").lower()
        ]

    return web.json_response({"success": True, "total": len(orders), "orders": orders})

async def handle_admin_update_order_status(request):
    """PUT /api/admin/orders/{id}/status - Cambios de estado en taller o despacho Andreani"""
    denied = staff_required(request)
    if denied:
        return denied
    order_id = request.match_info.get("id")
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Cuerpo inválido"}, status=400)

    orders = load_orders()
    target_idx = next((i for i, o in enumerate(orders) if o.get("id") == order_id), None)

    if target_idx is None:
        return web.json_response({"success": False, "error": "Pedido no encontrado"}, status=404)

    order = orders[target_idx]

    if "payment_status" in data:
        order["payment_status"] = data["payment_status"]
        if data["payment_status"] == "approved":
            order["payment_status_label"] = "Aprobado (Acreditación Confirmada)"
        elif data["payment_status"] == "rejected":
            order["payment_status_label"] = "Rechazado / Anulado"

    if "shipping_status" in data:
        order["shipping_status"] = data["shipping_status"]
        if data["shipping_status"] == "in_workshop":
            order["shipping_status_label"] = "En Taller (Ajuste de Medidas)"
        elif data["shipping_status"] == "in_transit":
            order["shipping_status_label"] = "En Tránsito con Andreani"
        elif data["shipping_status"] == "delivered":
            order["shipping_status_label"] = "Entregado a Domicilio"
        elif data["shipping_status"] == "pending":
            order["shipping_status_label"] = "Aguardando Cobro"

    if "tracking_number" in data:
        order["tracking_number"] = data["tracking_number"].strip()
    if "notes" in data:
        order["notes"] = data["notes"]

    orders[target_idx] = order
    save_orders(orders)

    return web.json_response({"success": True, "message": f"Pedido {order_id} actualizado", "order": order})

async def handle_admin_stats(request):
    """GET /api/admin/stats - KPIs financieros y logísticos"""
    denied = staff_required(request)
    if denied:
        return denied
    orders = load_orders()
    total_revenue = sum(o.get("total_amount", 0) for o in orders if o.get("payment_status") == "approved")
    pending_transfers = len([o for o in orders if o.get("payment_status") == "pending_verification"])
    in_workshop = len([o for o in orders if o.get("shipping_status") == "in_workshop"])
    in_transit = len([o for o in orders if o.get("shipping_status") == "in_transit"])
    delivered = len([o for o in orders if o.get("shipping_status") == "delivered"])

    return web.json_response({
        "success": True,
        "stats": {
            "total_revenue_ars": total_revenue,
            "total_orders": len(orders),
            "pending_transfers": pending_transfers,
            "in_workshop": in_workshop,
            "in_transit": in_transit,
            "delivered": delivered
        }
    })

# --- CONFIGURACIÓN DE LA APP Y SERVICIO DE ARCHIVOS ESTÁTICOS ---

def create_app():
    app = web.Application(client_max_size=10 * 1024 * 1024)

    async def no_cache_pages(request, response):
        # HTML/JS/CSS se revalidan en cada carga: después de un cambio nadie queda con una versión vieja
        if not request.path.startswith(("/api/", "/uploads/")):
            response.headers["Cache-Control"] = "no-cache"
    app.on_response_prepare.append(no_cache_pages)
    
    # Rutas Públicas
    app.router.add_get("/api/products", handle_get_products)
    app.router.add_get("/api/products/{id}", handle_get_product_by_id)
    app.router.add_get("/api/categories", handle_get_categories)
    app.router.add_get("/api/settings", handle_get_settings)
    app.router.add_post("/api/checkout/preference", handle_create_mp_preference)
    app.router.add_post("/api/checkout/process-card", handle_process_card)
    app.router.add_post("/api/checkout/webhook", handle_mp_webhook)
    app.router.add_post("/api/checkout/confirm", handle_mp_confirm)
    app.router.add_post("/api/checkout/bank-transfer", handle_bank_transfer)
    app.router.add_post("/api/chat", handle_ai_chat)

    # Rutas de Autenticación
    app.router.add_post("/api/auth/login", handle_login)
    app.router.add_get("/api/auth/me", handle_me)

    # Rutas de Operarios & Administración
    app.router.add_get("/api/admin/orders", handle_admin_get_orders)
    app.router.add_put("/api/admin/orders/{id}/status", handle_admin_update_order_status)
    app.router.add_get("/api/admin/stats", handle_admin_stats)
    
    # Rutas de Catálogo, Ofertas y Usuarios (Admin)
    app.router.add_post("/api/admin/products", handle_admin_create_product)
    app.router.add_put("/api/admin/products/{id}", handle_admin_update_product)
    app.router.add_delete("/api/admin/products/{id}", handle_admin_delete_product)
    app.router.add_post("/api/admin/upload", handle_admin_upload)
    app.router.add_put("/api/admin/settings", handle_update_settings)
    app.router.add_get("/api/admin/users", handle_admin_get_users)
    app.router.add_post("/api/admin/users", handle_admin_create_user)

    # CORS
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*"
        )
    })
    for route in list(app.router.routes()):
        cors.add(route)

    # Static assets
    app.router.add_static("/css/", path=os.path.join(PUBLIC_DIR, "css"), name="css")
    app.router.add_static("/js/", path=os.path.join(PUBLIC_DIR, "js"), name="js")
    app.router.add_static("/uploads/", path=UPLOADS_DIR, name="uploads")

    # Panel de Operarios y Administradores
    async def admin_handler(request):
        admin_file = os.path.join(PUBLIC_DIR, "admin.html")
        if os.path.exists(admin_file):
            return web.FileResponse(admin_file)
        return web.Response(text="Admin panel not found", status=404)

    app.router.add_get("/admin", admin_handler)
    app.router.add_get("/admin/", admin_handler)

    # Index
    async def index_handler(request):
        index_file = os.path.join(PUBLIC_DIR, "index.html")
        if os.path.exists(index_file):
            return web.FileResponse(index_file)
        return web.Response(text="GALILEA Atelier is running.", content_type="text/plain")

    app.router.add_get("/", index_handler)

    return app

if __name__ == "__main__":
    app = create_app()
    print(f"==================================================")
    print(f"   GALILEA Atelier Joyería - Servidor Activo")
    print(f"   Tienda: http://localhost:{PORT}")
    print(f"   Panel Modular: http://localhost:{PORT}/admin")
    print(f"   Mercado Pago: {'CONFIGURADO' if payments.token() else 'SIN TOKEN (modo prueba, no aprueba pagos)'}")
    print(f"==================================================")
    web.run_app(app, host="127.0.0.1", port=PORT)
