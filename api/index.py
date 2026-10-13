from http.server import BaseHTTPRequestHandler
import json
import os
from urllib.parse import urlparse, parse_qs

# Ubicación de archivos
CURRENT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname(CURRENT_DIR)
REPO_DATA_DIR = os.path.join(ROOT_DIR, "data")
# Vercel solo permite escribir en /tmp, y se borra cuando la instancia se recicla.
# Para producción real hace falta una base de datos.
DATA_DIR = "/tmp/galilea-data" if os.environ.get("VERCEL") else REPO_DATA_DIR
SECRET_SETTINGS = ("mercadopago_access_token",)

import sys
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Lógica compartida con server.py (pagos, sesiones, imágenes)
import auth
import catalog
import payments
import uploads

# Carga del motor de IA especializada
try:
    from ai_advisor import process_chat_message
except Exception:
    try:
        from api.ai_advisor import process_chat_message
    except Exception:
        process_chat_message = None


def load_data(filename, default_val=None):
    if default_val is None:
        default_val = []
    for folder in (DATA_DIR, REPO_DATA_DIR):
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return default_val

def save_data(filename, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, filename), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_products(): return load_data("products.json", [])
def save_products(products): save_data("products.json", products)

def load_orders(): return load_data("orders.json", [])
def save_orders(orders): save_data("orders.json", orders)

def add_order(order):
    orders = load_orders()
    orders.insert(0, order)
    save_orders(orders)
    return order

def public_settings(settings):
    safe = {k: v for k, v in settings.items() if k not in SECRET_SETTINGS}
    safe["mercadopago_configured"] = bool(payments.token())
    return safe

SHIPPING_LABELS = {
    "in_workshop": "En Taller (Ajuste de Medidas)",
    "in_transit": "En Tránsito con Andreani",
    "delivered": "Entregado a Domicilio",
    "pending": "Aguardando Cobro"
}

class handler(BaseHTTPRequestHandler):

    def _set_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _json(self, status, payload):
        self._set_headers(status)
        self.wfile.write(json.dumps(payload).encode('utf-8'))

    def do_OPTIONS(self):
        self._set_headers(200)

    def _get_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 0:
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                return json.loads(body)
            except Exception:
                return {}
        return {}

    def _get_user(self):
        return auth.user_from_header(self.headers.get("Authorization", ""))

    def _require(self, *roles):
        """Devuelve el usuario si tiene uno de los roles; si no, responde 401 y devuelve None."""
        user = self._get_user()
        if user and user.get("role") in roles:
            return user
        self._json(401, {"success": False, "error": "Iniciá sesión en el panel"})
        return None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        # GET /api/products
        if path == "/api/products":
            products = load_products()
            category = qs.get("category", ["todos"])[0].lower()
            metal = qs.get("metal", ["todos"])[0].lower()
            sort = qs.get("sort", ["featured"])[0]
            q = qs.get("q", [""])[0].lower()

            if category != "todos":
                products = [p for p in products if catalog.in_category(p, category)]

            if metal != "todos":
                products = [p for p in products if p.get("metal_group") == metal]

            if q:
                products = [p for p in products if q in p.get("name", "").lower() or q in p.get("description", "").lower() or q in p.get("metal", "").lower()]

            if sort == "price-asc":
                products.sort(key=lambda x: x.get("price", 0))
            elif sort == "price-desc":
                products.sort(key=lambda x: x.get("price", 0), reverse=True)

            self._json(200, {"success": True, "total": len(products), "products": products})
            return

        # GET /api/categories (categorías y materiales configurables, con cantidad de joyas)
        if path == "/api/categories":
            products, settings = load_products(), load_data("settings.json", {})
            self._json(200, {"success": True,
                             "categories": catalog.categories_with_counts(products, settings),
                             "materials": catalog.materials_with_counts(products, settings)})
            return

        # GET /api/settings
        if path == "/api/settings":
            self._json(200, {"success": True, "settings": public_settings(load_data("settings.json", {}))})
            return

        # GET /api/auth/me
        if path == "/api/auth/me":
            user = self._get_user()
            if not user:
                self._json(401, {"success": False, "error": "No autenticado"})
                return
            self._json(200, {"success": True, "user": user})
            return

        # GET /api/admin/orders
        if path == "/api/admin/orders":
            if not self._require("admin", "operario"):
                return
            orders = load_orders()
            status = qs.get("status", ["all"])[0]
            shipping = qs.get("shipping", ["all"])[0]
            method = qs.get("method", ["all"])[0]
            q = qs.get("q", [""])[0].lower()

            if status != "all":
                orders = [o for o in orders if o.get("payment_status") == status]
            if shipping != "all":
                orders = [o for o in orders if o.get("shipping_status") == shipping]
            if method != "all":
                orders = [o for o in orders if o.get("payment_method") == method]
            if q:
                orders = [o for o in orders if q in o.get("id", "").lower() or q in o.get("customer", {}).get("name", "").lower()]

            self._json(200, {"success": True, "total": len(orders), "orders": orders})
            return

        # GET /api/admin/stats
        if path == "/api/admin/stats":
            if not self._require("admin", "operario"):
                return
            orders = load_orders()
            total_rev = sum(o.get("total_amount", 0) for o in orders if o.get("payment_status") == "approved")
            self._json(200, {
                "success": True,
                "stats": {
                    "total_revenue_ars": total_rev,
                    "total_orders": len(orders),
                    "pending_transfers": len([o for o in orders if o.get("payment_status") == "pending_verification"]),
                    "in_workshop": len([o for o in orders if o.get("shipping_status") == "in_workshop"]),
                    "in_transit": len([o for o in orders if o.get("shipping_status") == "in_transit"]),
                    "delivered": len([o for o in orders if o.get("shipping_status") == "delivered"])
                }
            })
            return

        # GET /api/admin/users
        if path == "/api/admin/users":
            if not self._require("admin"):
                return
            users = load_data("users.json", [])
            safe = [{"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"], "role_label": u.get("role_label", ""), "created_at": u.get("created_at", "")} for u in users]
            self._json(200, {"success": True, "users": safe})
            return

        self._json(404, {"success": False, "error": "Ruta no encontrada"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        body = self._get_body()

        # POST /api/auth/login
        if path == "/api/auth/login":
            login_id = body.get("email") or body.get("username") or body.get("user") or ""
            user = auth.find_user(load_data("users.json", []), login_id, str(body.get("password", "")).strip())
            if not user:
                self._json(401, {"success": False, "error": "Usuario o contraseña incorrectos"})
                return
            self._json(200, {"success": True, "token": auth.issue_token(user), "user": auth.session_user(user)})
            return

        # POST /api/checkout/process-card: deshabilitado, las tarjetas se cobran en Mercado Pago
        if path == "/api/checkout/process-card":
            self._json(410, {"success": False, "error": "Pagá con tarjeta desde Mercado Pago (hasta 6 cuotas)."})
            return

        # POST /api/checkout/preference
        if path == "/api/checkout/preference":
            try:
                self._json(200, payments.create_preference(body, load_products(), add_order))
            except ValueError as ve:
                self._json(400, {"success": False, "error": str(ve)})
            except Exception as e:
                print("MP error:", e)
                self._json(502, {"success": False, "error": "No pudimos iniciar el pago"})
            return

        # POST /api/checkout/confirm (retorno desde Mercado Pago)
        if path == "/api/checkout/confirm":
            try:
                self._json(200, payments.confirm_payment(body, load_orders, save_orders))
            except ValueError as ve:
                self._json(400, {"success": False, "error": str(ve)})
            except LookupError as le:
                self._json(404, {"success": False, "error": str(le)})
            except Exception as e:
                print("MP confirm error:", e)
                self._json(502, {"success": False, "error": "No pudimos verificar el pago"})
            return

        # POST /api/checkout/webhook
        if path == "/api/checkout/webhook":
            try:
                query_dict = {k: v[0] for k, v in qs.items()}
                code, out = payments.process_webhook(query_dict, body, dict(self.headers.items()), load_orders, save_orders)
            except Exception as e:
                print("Webhook error:", e)
                code, out = 500, {"error": "reintentar"}
            self._json(code, out)
            return

        # POST /api/checkout/bank-transfer
        if path == "/api/checkout/bank-transfer":
            try:
                discount = load_data("settings.json", {}).get("transfer_discount_pct", 15)
                self._json(200, payments.create_transfer_order(body, load_products(), discount, add_order))
            except (ValueError, TypeError) as e:
                self._json(400, {"success": False, "error": str(e) or "Datos inválidos"})
            return

        # POST /api/chat (Asesoría Virtual con IA y Guardrail de Joyería)
        if path == "/api/chat":
            message = str(body.get("message", "")).strip()
            history = body.get("history", [])
            products = load_products()
            if process_chat_message:
                result = process_chat_message(message, history, products)
            else:
                result = {
                    "success": True,
                    "reply": "Bienvenido/a a <strong>GALILEA Atelier</strong>. Como asesora de joyería fina, ¿en qué pieza puedo orientarte hoy?",
                    "products": products[:2],
                    "provider": "galilea-fallback"
                }
            self._json(200, result)
            return

        # POST /api/admin/products (alta de joya)
        if path == "/api/admin/products":
            if not self._require("admin"):
                return
            products = load_products()
            try:
                new_prod = catalog.new_product(body, products, load_data("settings.json", {}))
            except ValueError as ve:
                self._json(400, {"success": False, "error": str(ve)})
                return
            products.insert(0, new_prod)
            save_products(products)
            self._json(200, {"success": True, "message": "Joya creada en el catálogo", "product": new_prod})
            return

        # POST /api/admin/upload
        if path == "/api/admin/upload":
            if not self._require("admin"):
                return
            # En Vercel no hay disco persistente: la imagen validada vuelve como data URL
            try:
                raw = body.get("data") or body.get("image") or ""
                image_bytes = uploads.decode_base64(raw)
                _, mime = uploads.check_image(image_bytes)
            except ValueError as ve:
                self._json(400, {"success": False, "error": str(ve)})
                return
            b64 = raw.split(",", 1)[1] if raw.startswith("data:") else raw
            self._json(200, {"success": True, "url": f"data:{mime};base64,{b64.strip()}", "filename": body.get("filename", "joya.jpg")})
            return

        self._json(404, {"success": False, "error": "Ruta no encontrada"})

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._get_body()

        # PUT /api/admin/orders/<id>/status
        if path.startswith("/api/admin/orders/") and path.endswith("/status"):
            if not self._require("admin", "operario"):
                return
            parts = path.split("/")
            order_id = parts[4] if len(parts) > 4 else ""
            orders = load_orders()
            order = next((o for o in orders if o.get("id") == order_id), None)
            if not order:
                self._json(404, {"success": False, "error": "Pedido no encontrado"})
                return
            if "payment_status" in body:
                order["payment_status"] = body["payment_status"]
                if body["payment_status"] == "approved":
                    order["payment_status_label"] = "Aprobado (Acreditación Confirmada)"
                elif body["payment_status"] == "rejected":
                    order["payment_status_label"] = "Rechazado / Anulado"
            if "shipping_status" in body:
                order["shipping_status"] = body["shipping_status"]
                order["shipping_status_label"] = SHIPPING_LABELS.get(body["shipping_status"], order.get("shipping_status_label", ""))
            if "tracking_number" in body:
                order["tracking_number"] = str(body["tracking_number"]).strip()
            if "notes" in body:
                order["notes"] = body["notes"]
            save_orders(orders)
            self._json(200, {"success": True, "message": f"Pedido {order_id} actualizado", "order": order})
            return

        # PUT /api/admin/settings
        if path == "/api/admin/settings":
            if not self._require("admin"):
                return
            settings = load_data("settings.json", {})
            try:
                catalog.apply_option_settings(settings, body)  # categorías y materiales
            except ValueError as ve:
                self._json(400, {"success": False, "error": str(ve)})
                return
            for key in ["ticker_text", "hero_tag", "hero_title", "hero_desc", "transfer_discount_pct", "atelier_address", "contact_phone", "mercadopago_public_key"]:
                if key in body:
                    settings[key] = body[key]
            save_data("settings.json", settings)
            message = "Ajustes actualizados"
            if str(body.get("mercadopago_access_token", "")).strip():
                message += ". En Vercel el Access Token se carga como variable de entorno MERCADOPAGO_ACCESS_TOKEN"
            self._json(200, {"success": True, "message": message, "settings": public_settings(settings)})
            return

        # PUT /api/admin/products/<id>
        if path.startswith("/api/admin/products/"):
            if not self._require("admin"):
                return
            prod_id = path.split("/")[4] if len(path.split("/")) > 4 else ""
            products = load_products()
            prod = next((p for p in products if p.get("id") == prod_id), None)
            if not prod:
                self._json(404, {"success": False, "error": "Producto no encontrado"})
                return
            try:
                catalog.update_product(prod, body, load_data("settings.json", {}))
            except ValueError as ve:
                self._json(400, {"success": False, "error": str(ve)})
                return
            save_products(products)
            self._json(200, {"success": True, "message": "Joya actualizada correctamente", "product": prod})
            return

        self._json(404, {"success": False, "error": "Ruta no encontrada"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/admin/products/"):
            if not self._require("admin"):
                return
            prod_id = path.split("/")[4] if len(path.split("/")) > 4 else ""
            products = load_products()
            remaining = [p for p in products if p.get("id") != prod_id]
            if len(remaining) == len(products):
                self._json(404, {"success": False, "error": "Producto no encontrado"})
                return
            save_products(remaining)
            self._json(200, {"success": True, "message": f"Joya {prod_id} eliminada del catálogo"})
            return

        self._json(404, {"success": False, "error": "Ruta no encontrada"})
