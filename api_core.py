"""API de GALILEA: una sola implementación para server.py (local) y api/index.py (Vercel).
dispatch(method, path, query, body, headers) -> (status, payload)."""
import os, re, json, uuid
from datetime import datetime

import auth, catalog, notify, payments, uploads
from store import get_store, REPO_DATA_DIR

try:
    from ai_advisor import process_chat_message
except Exception:
    process_chat_message = None

PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
UPLOADS_DIR = os.path.join(PUBLIC_DIR, "uploads")
SECRET_SETTINGS = ("mercadopago_access_token",)
SETTINGS_KEYS = ["ticker_text", "hero_tag", "hero_title", "hero_desc", "transfer_discount_pct",
                 "atelier_address", "contact_phone", "mercadopago_access_token", "mercadopago_public_key"]
SHIPPING_LABELS = {
    "in_workshop": "En Taller (Ajuste de Medidas)",
    "in_transit": "En Tránsito con Andreani",
    "delivered": "Entregado a Domicilio",
    "pending": "Aguardando Cobro"
}


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Request:
    def __init__(self, method, path, query, body, headers, params):
        self.method, self.path, self.query, self.body = method, path, query, body
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.params = params

    @property
    def user(self):
        return auth.user_from_header(self.headers.get("authorization", ""))

    def require(self, *roles):
        user = self.user
        if not user or user.get("role") not in roles:
            raise ApiError(401, "Iniciá sesión en el panel")
        return user


def ok(**payload):
    return 200, {"success": True, **payload}


# --- DATOS ---

def load_products():
    return get_store().get("products", [])

def load_settings():
    return get_store().get("settings", {})

def load_users():
    """Cuentas del repo (data/users.json, con hash) + las creadas desde el panel."""
    try:
        with open(os.path.join(REPO_DATA_DIR, "users.json"), encoding="utf-8") as f:
            base = json.load(f)
    except (OSError, ValueError):
        base = []
    ids = {u.get("id") for u in base}
    return base + [u for u in get_store().get("users_extra", []) if u.get("id") not in ids]

def public_settings(settings):
    safe = {k: v for k, v in settings.items() if k not in SECRET_SETTINGS}
    safe["mercadopago_configured"] = bool(payments.token())
    return safe

def on_order_approved(order):
    """Una sola vez por pedido aprobado: descuenta stock y avisa al cliente por email."""
    store = get_store()
    if not store.claim(f"approved:{order['id']}"):
        return
    products = load_products()
    before = json.dumps(products, sort_keys=True)
    shortages = catalog.apply_sale(products, order)
    if json.dumps(products, sort_keys=True) != before:
        store.put("products", products)
    if shortages:
        order["notes"] = (order.get("notes", "") + " Stock insuficiente al aprobar: " + "; ".join(shortages)).strip()
    notify.notify_order(order, "payment_approved")


# --- CATÁLOGO PÚBLICO ---

def list_products(req):
    products = load_products()
    category = req.query.get("category", "todos").lower()
    metal = req.query.get("metal", "todos").lower()
    sort = req.query.get("sort", "featured")
    q = req.query.get("q", "").strip().lower()
    if category != "todos":
        products = [p for p in products if catalog.in_category(p, category)]
    if metal != "todos":
        products = [p for p in products if p.get("metal_group") == metal]
    if q:
        products = [p for p in products if any(q in str(p.get(k, "")).lower()
                                               for k in ("name", "description", "category_label", "metal"))]
    if sort == "price-asc":
        products.sort(key=lambda x: x.get("price", 0))
    elif sort == "price-desc":
        products.sort(key=lambda x: x.get("price", 0), reverse=True)
    elif sort == "featured":
        products.sort(key=lambda x: (not x.get("featured", False), x.get("name", "")))
    return ok(total=len(products), products=products)

def get_product(req):
    product = next((p for p in load_products() if p.get("id") == req.params["id"]), None)
    if not product:
        raise ApiError(404, "Producto no encontrado")
    return ok(product=product)

def get_categories(req):
    products, settings = load_products(), load_settings()
    return ok(categories=catalog.categories_with_counts(products, settings),
              materials=catalog.materials_with_counts(products, settings))

def get_settings(req):
    return ok(settings=public_settings(load_settings()))

def image_storage():
    if uploads.blob_token():
        return "blob"
    return "dentro del producto" if os.environ.get("VERCEL") else "archivos"

def health(req):
    """Estado público de las conexiones (sin claves): base de datos, fotos, emails y Mercado Pago."""
    store = get_store()
    try:
        storage_ok = bool(store.ping())
    except Exception as e:
        print("Health: la base no responde:", e)
        storage_ok = False
    return ok(storage=store.kind, storage_ok=storage_ok, images=image_storage(),
              emails=notify.configured(), mercadopago=bool(payments.token()))


# --- COBROS ---

def checkout_preference(req):
    try:
        return 200, payments.create_preference(req.body, load_products(), get_store().put_order)
    except RuntimeError as e:
        print("MP error:", e)
        raise ApiError(502, "No pudimos iniciar el pago")

def process_card(req):
    raise ApiError(410, "Pagá con tarjeta desde Mercado Pago (hasta 6 cuotas).")

def webhook(req):
    store = get_store()
    try:
        return payments.process_webhook(req.query, req.body, req.headers, store.get_order, store.put_order, on_order_approved)
    except Exception as e:
        print("Webhook error:", e)
        return 500, {"error": "reintentar"}

def confirm(req):
    store = get_store()
    try:
        return 200, payments.confirm_payment(req.body, store.get_order, store.put_order, on_order_approved)
    except (ValueError, LookupError):
        raise
    except Exception as e:
        print("MP confirm error:", e)
        raise ApiError(502, "No pudimos verificar el pago")

def bank_transfer(req):
    discount = load_settings().get("transfer_discount_pct", 15)
    response, order = payments.create_transfer_order(req.body, load_products(), discount, get_store().put_order)
    if notify.notify_order(order, "transfer_created"):
        get_store().put_order(order)
    return 200, response

def track_order(req):
    """Página "Seguí tu pedido": código + email del pedido, sin cuentas."""
    order_id = str(req.body.get("order_id", "")).strip().upper()
    email = str(req.body.get("email", "")).strip().lower()
    order = get_store().get_order(order_id) if order_id and email else None
    if not order or str((order.get("customer") or {}).get("email", "")).strip().lower() != email:
        raise ApiError(404, "No encontramos un pedido con ese código y email")
    return ok(order={
        "id": order["id"], "date": order.get("date"), "total_amount": order.get("total_amount"),
        "items": [{k: it.get(k) for k in ("name", "size", "quantity", "price", "image")} for it in order.get("items", [])],
        "payment_method_label": order.get("payment_method_label"),
        "payment_status": order.get("payment_status"), "payment_status_label": order.get("payment_status_label"),
        "shipping_status": order.get("shipping_status"), "shipping_status_label": order.get("shipping_status_label"),
        "shipping_carrier": order.get("shipping_carrier"), "tracking_number": order.get("tracking_number"),
        "tracking_url": notify.andreani_link(order), "history": order.get("history", [])})


# --- CHAT ---

def chat(req):
    message = str(req.body.get("message", "")).strip()
    products = load_products()
    if process_chat_message:
        return 200, process_chat_message(message, req.body.get("history", []), products)
    return 200, {"success": True, "reply": "Bienvenido/a a <strong>GALILEA Atelier</strong>. ¿En qué pieza puedo orientarte hoy?",
                 "products": products[:2], "provider": "galilea-fallback"}


# --- SESIÓN ---

def login(req):
    login_id = req.body.get("email") or req.body.get("username") or req.body.get("user") or ""
    user = auth.find_user(load_users(), login_id, str(req.body.get("password", "")).strip())
    if not user:
        raise ApiError(401, "Usuario o contraseña incorrectos")
    return ok(token=auth.issue_token(user), user=auth.session_user(user))

def me(req):
    user = req.user
    if not user:
        raise ApiError(401, "No autenticado")
    return ok(user=user)


# --- PEDIDOS (PERSONAL) ---

def admin_orders(req):
    req.require("admin", "operario")
    orders = get_store().list_orders()
    for key, field in (("status", "payment_status"), ("shipping", "shipping_status"), ("method", "payment_method")):
        value = req.query.get(key, "all")
        if value != "all":
            orders = [o for o in orders if o.get(field) == value]
    q = req.query.get("q", "").strip().lower()
    if q:
        orders = [o for o in orders if q in o.get("id", "").lower() or q in o.get("tracking_number", "").lower()
                  or any(q in str(o.get("customer", {}).get(k, "")).lower() for k in ("name", "dni", "email"))]
    return ok(total=len(orders), orders=orders)

def admin_order_status(req):
    req.require("admin", "operario")
    store, data = get_store(), req.body
    order = store.get_order(req.params["id"])
    if not order:
        raise ApiError(404, "Pedido no encontrado")
    events, emails_before = [], set(order.get("emails_sent", []))
    if "payment_status" in data and data["payment_status"] != order.get("payment_status"):
        order["payment_status"] = data["payment_status"]
        if data["payment_status"] == "approved":
            order["payment_status_label"] = "Aprobado (Acreditación Confirmada)"
            payments.add_history(order, "Pago acreditado: en preparación en el taller")
            on_order_approved(order)
        elif data["payment_status"] == "rejected":
            order["payment_status_label"] = "Rechazado / Anulado"
            payments.add_history(order, "Pedido anulado")
    if "tracking_number" in data:
        order["tracking_number"] = str(data["tracking_number"]).strip()[:60]
    if "shipping_status" in data and data["shipping_status"] != order.get("shipping_status"):
        status = data["shipping_status"]
        order["shipping_status"] = status
        order["shipping_status_label"] = SHIPPING_LABELS.get(status, order.get("shipping_status_label", ""))
        if status == "in_transit":
            guide = f" (guía {order['tracking_number']})" if order.get("tracking_number") else ""
            payments.add_history(order, f"Despachado con Andreani{guide}")
            events.append("shipped")
        elif status == "delivered":
            payments.add_history(order, "Entregado")
            events.append("delivered")
        elif status == "in_workshop" and "preparación" not in (order.get("history") or [{}])[-1].get("label", ""):
            payments.add_history(order, "En preparación en el taller")
    if "notes" in data:
        order["notes"] = str(data["notes"])
    for event in events:
        notify.notify_order(order, event)
    emailed = [e for e in order.get("emails_sent", []) if e not in emails_before]
    store.put_order(order)
    return ok(message=f"Pedido {order['id']} actualizado", order=order, emailed=emailed)

def admin_stats(req):
    req.require("admin", "operario")
    orders = get_store().list_orders()
    count = lambda field, value: len([o for o in orders if o.get(field) == value])
    return ok(stats={
        "total_revenue_ars": sum(o.get("total_amount", 0) for o in orders if o.get("payment_status") == "approved"),
        "total_orders": len(orders),
        "pending_transfers": count("payment_status", "pending_verification"),
        "in_workshop": count("shipping_status", "in_workshop"),
        "in_transit": count("shipping_status", "in_transit"),
        "delivered": count("shipping_status", "delivered"),
        "storage": get_store().kind,
        "images": image_storage(),
        "emails": notify.configured()})


# --- CATÁLOGO (ADMIN) ---

def admin_create_product(req):
    req.require("admin")
    products = load_products()
    product = catalog.new_product(req.body, products, load_settings())
    products.insert(0, product)
    get_store().put("products", products)
    return ok(message="Joya creada en el catálogo", product=product)

def admin_update_product(req):
    req.require("admin")
    products = load_products()
    product = next((p for p in products if p.get("id") == req.params["id"]), None)
    if not product:
        raise ApiError(404, "Producto no encontrado")
    catalog.update_product(product, req.body, load_settings())
    get_store().put("products", products)
    return ok(message="Joya actualizada correctamente", product=product)

def admin_delete_product(req):
    req.require("admin")
    products = load_products()
    remaining = [p for p in products if p.get("id") != req.params["id"]]
    if len(remaining) == len(products):
        raise ApiError(404, "Producto no encontrado")
    get_store().put("products", remaining)
    return ok(message=f"Joya {req.params['id']} eliminada del catálogo")

def admin_upload(req):
    req.require("admin")
    data = uploads.decode_base64(req.body.get("data") or req.body.get("image") or "")
    url, warning = uploads.save_image(data, UPLOADS_DIR)
    return ok(url=url, warning=warning, filename=req.body.get("filename", "joya.jpg"))

def admin_settings(req):
    req.require("admin")
    settings = load_settings()
    catalog.apply_option_settings(settings, req.body)  # categorías y materiales
    message = "Configuración de la tienda actualizada"
    for key in SETTINGS_KEYS:
        if key not in req.body:
            continue
        if key in SECRET_SETTINGS:
            if not str(req.body[key]).strip():
                continue  # vacío = conservar el token guardado (el panel nunca lo muestra)
            if os.environ.get("VERCEL"):
                message += ". En Vercel el Access Token se carga como variable de entorno MERCADOPAGO_ACCESS_TOKEN"
                continue
        settings[key] = req.body[key]
    get_store().put("settings", settings)
    return ok(message=message, settings=public_settings(settings))

def admin_users(req):
    req.require("admin")
    return ok(users=[{k: u.get(k, "") for k in ("id", "name", "email", "role", "role_label", "created_at")} for u in load_users()])

def admin_create_user(req):
    req.require("admin")
    name = str(req.body.get("name", "")).strip()
    email = str(req.body.get("email", "")).strip().lower()
    password = str(req.body.get("password", "")).strip()
    role = "admin" if req.body.get("role") == "admin" else "operario"
    if not name or not email or not password:
        raise ApiError(400, "Nombre, correo y contraseña requeridos")
    if len(password) < 8:
        raise ApiError(400, "La contraseña debe tener al menos 8 caracteres")
    if any(u.get("email", "").lower() == email for u in load_users()):
        raise ApiError(400, "Ese correo ya está registrado")
    user = {"id": f"USR-{uuid.uuid4().hex[:4].upper()}", "name": name, "email": email,
            "password_hash": auth.hash_password(password), "role": role,
            "role_label": "Maestro Orfebre & Logística" if role == "operario" else "Administrador de Atelier",
            "created_at": datetime.now(payments.ARGENTINA).strftime("%d/%m/%Y")}
    extra = get_store().get("users_extra", [])
    extra.append(user)
    get_store().put("users_extra", extra)
    return ok(message=f"Cuenta de {role} creada exitosamente", user=auth.session_user(user))


ROUTES = [
    ("GET", r"/api/products", list_products),
    ("GET", r"/api/products/(?P<id>[^/]+)", get_product),
    ("GET", r"/api/categories", get_categories),
    ("GET", r"/api/settings", get_settings),
    ("GET", r"/api/health", health),
    ("POST", r"/api/checkout/preference", checkout_preference),
    ("POST", r"/api/checkout/process-card", process_card),
    ("POST", r"/api/checkout/webhook", webhook),
    ("POST", r"/api/checkout/confirm", confirm),
    ("POST", r"/api/checkout/bank-transfer", bank_transfer),
    ("POST", r"/api/orders/track", track_order),
    ("POST", r"/api/chat", chat),
    ("POST", r"/api/auth/login", login),
    ("GET", r"/api/auth/me", me),
    ("GET", r"/api/admin/orders", admin_orders),
    ("PUT", r"/api/admin/orders/(?P<id>[^/]+)/status", admin_order_status),
    ("GET", r"/api/admin/stats", admin_stats),
    ("POST", r"/api/admin/products", admin_create_product),
    ("PUT", r"/api/admin/products/(?P<id>[^/]+)", admin_update_product),
    ("DELETE", r"/api/admin/products/(?P<id>[^/]+)", admin_delete_product),
    ("POST", r"/api/admin/upload", admin_upload),
    ("PUT", r"/api/admin/settings", admin_settings),
    ("GET", r"/api/admin/users", admin_users),
    ("POST", r"/api/admin/users", admin_create_user),
]


def dispatch(method, path, query=None, body=None, headers=None):
    path = "/" + path.strip("/")
    path_known = False
    for route_method, pattern, handler in ROUTES:
        match = re.fullmatch(pattern, path)
        if not match:
            continue
        path_known = True
        if route_method != method.upper():
            continue
        req = Request(method.upper(), path, query or {}, body if isinstance(body, dict) else {}, headers, match.groupdict())
        try:
            return handler(req)
        except ApiError as e:
            return e.status, {"success": False, "error": str(e)}
        except KeyError as e:  # error de programación, no "no encontrado"
            print(f"Error en {method} {path}:", repr(e))
            return 500, {"success": False, "error": "Error interno, probá de nuevo"}
        except ValueError as e:
            return 400, {"success": False, "error": str(e) or "Datos inválidos"}
        except LookupError as e:
            return 404, {"success": False, "error": str(e)}
        except Exception as e:
            print(f"Error en {method} {path}:", repr(e))
            return 500, {"success": False, "error": "Error interno, probá de nuevo"}
    if path_known:
        return 405, {"success": False, "error": "Método no permitido"}
    return 404, {"success": False, "error": "Ruta no encontrada"}
