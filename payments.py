"""Pagos GALILEA: Mercado Pago Checkout Pro (sin dependencias externas).
Reglas: el precio SIEMPRE se calcula en el servidor; una orden solo pasa a
'approved' cuando Mercado Pago lo confirma por webhook (consultando su API)."""
import os, json, hmac, hashlib, uuid, urllib.request, urllib.error
from datetime import datetime

MP_API = "https://api.mercadopago.com"
STATUS = {"approved": "Pago aprobado", "pending": "Pago pendiente", "in_process": "Pago en revisión",
          "rejected": "Pago rechazado", "cancelled": "Pago cancelado", "refunded": "Pago reembolsado",
          "charged_back": "Contracargo"}

def token():
    # 1. Variable de entorno en producción (Vercel o local)
    t = os.environ.get("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if t:
        return t
    # 2. Respaldo en data/settings.json
    try:
        settings_path = os.path.join(os.path.dirname(__file__), "data", "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                s = json.load(f)
                return str(s.get("mercadopago_access_token", "")).strip()
    except Exception:
        pass
    return ""

def site_url():
    if os.environ.get("SITE_URL"):
        return os.environ.get("SITE_URL").rstrip("/")
    if os.environ.get("VERCEL_URL"):
        return f"https://{os.environ.get('VERCEL_URL')}".rstrip("/")
    return "https://galilea-joyeria.vercel.app"

def _mp(method, path, body=None):
    req = urllib.request.Request(MP_API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json",
                 "X-Idempotency-Key": uuid.uuid4().hex})
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Mercado Pago {e.code}: {e.read().decode()[:300]}")

def price_cart(items, products):
    """Devuelve (líneas, total) usando los precios del catálogo, nunca los del cliente."""
    by_id = {str(p.get("id")): p for p in products}
    lines, total = [], 0.0
    for it in items or []:
        p = by_id.get(str(it.get("id")))
        qty = int(it.get("quantity", 1) or 1)
        if not p or not 1 <= qty <= 10: raise ValueError("Producto o cantidad inválidos")
        price = float(p["price"]); total += price * qty
        lines.append({"id": str(p["id"]), "name": p.get("name", ""), "size": it.get("size", "Estándar"),
                      "quantity": qty, "price": price, "image": p.get("primary_image", "")})
    if not lines: raise ValueError("La bolsa está vacía")
    return lines, round(total, 2)

def create_preference(data, products, add_order):
    payer = data.get("payer", {})
    lines, total = price_cart(data.get("items"), products)
    order_id = f"GAL-{uuid.uuid4().hex[:8].upper()}"
    add_order({
        "id": order_id, "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "customer": {k: str(payer.get(k, "")) for k in ("name", "email", "phone", "dni", "address", "province", "zip")},
        "items": lines, "total_amount": total, "payment_method": "mercadopago",
        "payment_method_label": "Mercado Pago", "payment_status": "pending",
        "payment_status_label": STATUS["pending"], "shipping_status": "awaiting_payment",
        "shipping_status_label": "Esperando pago", "shipping_carrier": "Andreani Asegurado",
        "tracking_number": "", "notes": ""})
    if not token():  # modo prueba: NO aprueba nada, la orden queda pendiente
        return {"success": True, "mode": "sandbox", "order_id": order_id, "total_ars": total,
                "init_point": f"/?checkout=sandbox&order={order_id}",
                "message": "Sin MERCADOPAGO_ACCESS_TOKEN: orden creada como pendiente."}
    s = site_url()
    pref_payload = {
        "items": [{
            "id": str(l["id"]),
            "title": f"GALILEA - {l['name']}",
            "quantity": int(l["quantity"]),
            "unit_price": float(l["price"]),
            "currency_id": "ARS"
        } for l in lines],
        "payer": {
            "name": str(payer.get("name", "")).strip() or "Cliente Galilea",
            "email": str(payer.get("email", "")).strip() or "cliente@galilea-joyeria.com"
        },
        "external_reference": order_id,
        "statement_descriptor": "GALILEA",
        "back_urls": {k: f"{s}/?checkout={k}&order={order_id}" for k in ("success", "pending", "failure")},
        "auto_return": "approved",
        "payment_methods": {"installments": 6}
    }
    if s.startswith("https://"):
        pref_payload["notification_url"] = f"{s}/api/checkout/webhook"

    pref = _mp("POST", "/checkout/preferences", pref_payload)
    return {"success": True, "mode": "live", "order_id": order_id, "total_ars": total,
            "preference_id": pref["id"], "init_point": pref["init_point"]}

def _signature_ok(query, headers, data_id):
    secret = os.environ.get("MERCADOPAGO_WEBHOOK_SECRET", "").strip()
    if not secret: return True  # configurarlo en producción
    h = {k.lower(): v for k, v in headers.items()}
    parts = dict(p.split("=", 1) for p in h.get("x-signature", "").split(",") if "=" in p)
    manifest = f"id:{str(data_id).lower()};request-id:{h.get('x-request-id', '')};ts:{parts.get('ts', '')};"
    mac = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, parts.get("v1", ""))

def process_webhook(query, body, headers, load_orders, save_orders):
    data_id = (body.get("data") or {}).get("id") or query.get("data.id") or query.get("id")
    if (body.get("type") or query.get("type") or query.get("topic")) != "payment" or not data_id:
        return 200, {"ignored": True}
    if not _signature_ok(query, headers, data_id): return 401, {"error": "firma inválida"}
    pay = _mp("GET", f"/v1/payments/{data_id}")  # se confirma contra la API, no contra el body
    orders = load_orders()
    order = next((o for o in orders if o["id"] == pay.get("external_reference")), None)
    if not order: return 200, {"ignored": "orden desconocida"}
    status = pay.get("status", "pending")
    if status == "approved" and abs(float(pay.get("transaction_amount", 0)) - order["total_amount"]) > 0.01:
        status = "in_process"; order["notes"] = "Monto del pago no coincide: revisar manualmente."
    order.update(payment_status=status, payment_status_label=STATUS.get(status, status),
                 mp_payment_id=str(data_id))
    if status == "approved" and order.get("shipping_status") == "awaiting_payment":
        order.update(shipping_status="in_workshop", shipping_status_label="En taller (preparación)")
    save_orders(orders)
    return 200, {"ok": True}
