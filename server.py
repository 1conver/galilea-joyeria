import os
import json
import uuid
import secrets
from datetime import datetime
from aiohttp import web
import aiohttp_cors
import payments

try:
    from ai_advisor import process_chat_message
except ImportError:
    process_chat_message = None

PORT = int(os.environ.get("PORT", 3000))
MP_ACCESS_TOKEN = os.environ.get("MERCADOPAGO_ACCESS_TOKEN", "").strip()

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "public")

PRODUCTS_FILE = os.path.join(DATA_DIR, "products.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# Almacenamiento en memoria de tokens de sesión activos
ACTIVE_SESSIONS = {}

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
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        user = ACTIVE_SESSIONS.get(token)
        if user:
            return user
    return None

# --- API DE AUTENTICACIÓN ---

async def handle_login(request):
    """POST /api/auth/login - Autenticación de Operarios y Administradores"""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Credenciales inválidas"}, status=400)

    login_id = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    users = load_users()
    user = next((u for u in users if (u.get("email", "").lower() == login_id or u.get("username", "").lower() == login_id) and u.get("password") == password), None)

    if not user:
        if login_id in ("bren", "bren@galilea-joyeria.com") and password == "brenpea":
            user = {"id": "USR-001", "name": "Bren", "email": "bren@galilea-joyeria.com", "role": "admin", "role_label": "Administradora General & Dirección"}
        elif login_id in ("taller", "taller@galilea-joyeria.com") and password == "taller123":
            user = {"id": "USR-002", "name": "Martín Benítez", "email": "taller@galilea-joyeria.com", "role": "operario", "role_label": "Maestro Orfebre & Logística"}

    if not user:
        return web.json_response({"success": False, "error": "Usuario o contraseña incorrectos"}, status=401)

    # Generar token de sesión seguro
    token = f"gal_{secrets.token_hex(24)}"
    user_session = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "role_label": user.get("role_label", "Personal de Atelier")
    }
    ACTIVE_SESSIONS[token] = user_session

    return web.json_response({
        "success": True,
        "token": token,
        "user": user_session
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
    settings = load_settings()
    return web.json_response({"success": True, "settings": settings})

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
    for key in ["ticker_text", "hero_tag", "hero_title", "hero_desc", "transfer_discount_pct", "atelier_address", "contact_phone"]:
        if key in data:
            settings[key] = data[key]

    save_settings(settings)
    return web.json_response({"success": True, "message": "Configuración de la tienda actualizada", "settings": settings})

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

    new_user = {
        "id": f"USR-{uuid.uuid4().hex[:4].upper()}",
        "name": name,
        "email": email,
        "password": password,
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

    name = data.get("name", "").strip()
    price = float(data.get("price", 0))
    category = data.get("category", "anillos")
    metal = data.get("metal", "Oro 18K")
    description = data.get("description", "")
    primary_image = data.get("primary_image", "")

    if not name or price <= 0:
        return web.json_response({"success": False, "error": "Nombre y precio válidos obligatorios"}, status=400)

    products = load_products()
    new_prod = {
        "id": f"galilea-{len(products) + 1:02d}",
        "name": name,
        "category": category,
        "category_label": category.capitalize(),
        "metal": metal,
        "metal_group": "oro" if "oro" in metal.lower() and "blanco" not in metal.lower() else ("oro-blanco" if "blanco" in metal.lower() else "plata"),
        "price": price,
        "badge": data.get("badge", "Nuevo"),
        "featured": data.get("featured", False),
        "primary_image": primary_image if primary_image else "https://images.unsplash.com/photo-1605100804763-247f67b3557e?auto=format&fit=crop&w=900&q=85",
        "secondary_image": data.get("secondary_image", "https://images.unsplash.com/photo-1603561591411-07134e71a2a9?auto=format&fit=crop&w=900&q=85"),
        "description": description,
        "specs": {
            "metal": metal,
            "acabado": data.get("acabado", "Orfebrería artesanal pulida"),
            "origen": "Buenos Aires, Argentina"
        },
        "sizes": data.get("sizes", ["14", "16", "18"]),
        "in_stock": True
    }
    products.insert(0, new_prod)
    save_products(products)

    return web.json_response({"success": True, "message": "Joya creada en el catálogo", "product": new_prod})

async def handle_admin_update_product(request):
    """PUT /api/admin/products/{id} - Modificar precio, stock o datos de una joya"""
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return web.json_response({"success": False, "error": "Acceso restringido"}, status=403)

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
    if "price" in data:
        prod["price"] = float(data["price"])
    if "in_stock" in data:
        prod["in_stock"] = bool(data["in_stock"])
    if "name" in data:
        prod["name"] = data["name"].strip()
    if "badge" in data:
        prod["badge"] = data["badge"].strip()
    if "description" in data:
        prod["description"] = data["description"].strip()

    products[target_idx] = prod
    save_products(products)

    return web.json_response({"success": True, "message": "Joya actualizada", "product": prod})

# --- API CATÁLOGO PÚBLICO ---

async def handle_get_products(request):
    """GET /api/products - Catálogo filtrable y ordenable"""
    products = load_products()
    
    category = request.query.get("category", "todos").lower()
    metal = request.query.get("metal", "todos").lower()
    sort = request.query.get("sort", "featured")
    query = request.query.get("q", "").strip().lower()
    
    if category != "todos":
        if category in ("alta-joyeria", "diamantes"):
            products = [p for p in products if p.get("category") == "diamantes" or p.get("badge") == "Alta Joyería" or "diamante" in p.get("name", "").lower() or p.get("price", 0) >= 400000]
        elif category == "limitada":
            products = [p for p in products if p.get("category") == "limitada" or p.get("badge") == "Edición Limitada"]
        else:
            products = [p for p in products if p.get("category") == category]
            
    if metal != "todos":
        products = [p for p in products if p.get("metal_group") == metal]
        
    if query:
        products = [
            p for p in products
            if query in p.get("name", "").lower() 
            or query in p.get("description", "").lower()
            or query in p.get("category_label", "").lower()
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
    products = load_products()
    categories = [
        {"id": "todos", "label": "Colección Completa", "count": len(products)},
        {"id": "anillos", "label": "Anillos", "count": len([p for p in products if p.get("category") == "anillos"])},
        {"id": "collares", "label": "Collares", "count": len([p for p in products if p.get("category") == "collares"])},
        {"id": "aros", "label": "Aros", "count": len([p for p in products if p.get("category") == "aros"])},
        {"id": "pulseras", "label": "Pulseras", "count": len([p for p in products if p.get("category") == "pulseras"])},
        {"id": "diamantes", "label": "Alta Joyería & Diamantes", "count": len([p for p in products if p.get("category") == "diamantes" or "diamante" in p.get("name", "").lower() or p.get("badge") == "Alta Joyería"])},
        {"id": "limitada", "label": "Edición Limitada", "count": len([p for p in products if p.get("category") == "limitada" or p.get("badge") == "Edición Limitada"])}
    ]
    return web.json_response({"success": True, "categories": categories})

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

async def handle_bank_transfer(request):
    """POST /api/checkout/bank-transfer - Transferencia bancaria (Requiere validación de acreditación)"""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Datos inválidos"}, status=400)

    settings = load_settings()
    discount_pct = float(settings.get("transfer_discount_pct", 15)) / 100.0

    total_amount = float(data.get("total_amount", 0))
    final_amount = round(total_amount * (1 - discount_pct), 2)
    order_id = f"GAL-TRF-{uuid.uuid4().hex[:8].upper()}"

    customer_name = data.get("customer_name", "Cliente")
    email = data.get("email", "cliente@galilea-joyeria.com")
    phone = data.get("phone", "+54 9 11 4000-0000")
    dni = str(data.get("dni", ""))
    address = data.get("address", "A convenir")
    province = data.get("province", "CABA")
    items = data.get("items", [])

    order_record = {
        "id": order_id,
        "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "customer": {
            "name": customer_name,
            "email": email,
            "phone": phone,
            "dni": dni,
            "address": address,
            "province": province,
            "zip": data.get("zip", "")
        },
        "items": items if items else [
            {
                "id": "galilea-custom",
                "name": "Selección de Joyería GALILEA",
                "metal": "Oro 18K",
                "size": "A medida",
                "quantity": 1,
                "price": final_amount,
                "image": "https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?auto=format&fit=crop&w=900&q=85"
            }
        ],
        "total_amount": final_amount,
        "payment_method": "bank_transfer",
        "payment_method_label": f"Transferencia ({int(discount_pct*100)}% OFF)",
        "installments": 1,
        "installment_amount": final_amount,
        "payment_status": "pending_verification",
        "payment_status_label": "Pendiente Acreditación CBU",
        "shipping_status": "pending",
        "shipping_status_label": "Aguardando Cobro",
        "shipping_carrier": "Andreani Asegurado",
        "tracking_number": "",
        "notes": f"Total regular: ${total_amount:,.2f} ARS. Descuento aplicado: {int(discount_pct*100)}%."
    }
    add_order(order_record)

    return web.json_response({
        "success": True,
        "order_id": order_id,
        "original_amount": total_amount,
        "discount_applied": f"{int(discount_pct*100)}% OFF por transferencia bancaria",
        "final_amount": final_amount,
        "currency": "ARS",
        "bank_details": {
            "banco": "Banco Santander Río / Banco Galicia",
            "titular": "GALILEA ATELIER JOYERÍA S.A.",
            "cuit": "30-71829341-8",
            "cbu": "0720194820000001284910",
            "alias": "GALILEA.JOYAS.ARG",
            "tipo_cuenta": "Cuenta Corriente Especial en Pesos"
        },
        "instructions": (
            f"Transferí el importe de ${final_amount:,.2f} ARS a nuestro Alias: GALILEA.JOYAS.ARG. "
            f"Referencia: {order_id}."
        )
    })

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
    app = web.Application()
    
    # Rutas Públicas
    app.router.add_get("/api/products", handle_get_products)
    app.router.add_get("/api/products/{id}", handle_get_product_by_id)
    app.router.add_get("/api/categories", handle_get_categories)
    app.router.add_get("/api/settings", handle_get_settings)
    app.router.add_post("/api/checkout/preference", handle_create_mp_preference)
    app.router.add_post("/api/checkout/process-card", handle_process_card)
    app.router.add_post("/api/checkout/webhook", handle_mp_webhook)
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
    print(f"   Autenticación de pagos: AUTOMÁTICA")
    print(f"==================================================")
    web.run_app(app, host="127.0.0.1", port=PORT)
