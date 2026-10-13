"""Pagos GALILEA: Mercado Pago Checkout Pro + transferencia (sin dependencias externas).
Reglas: el precio SIEMPRE se calcula en el servidor; una orden solo pasa a
'approved' cuando Mercado Pago lo confirma (webhook o retorno), consultando su API.
Lo usan server.py (local) y api/index.py (Vercel)."""
import os, json, hmac, hashlib, uuid, urllib.request, urllib.error
from datetime import datetime

MP_API = "https://api.mercadopago.com"
STATUS = {"approved": "Pago aprobado", "pending": "Pago pendiente", "in_process": "Pago en revisión",
          "rejected": "Pago rechazado", "cancelled": "Pago cancelado", "refunded": "Pago reembolsado",
          "charged_back": "Contracargo"}
CUSTOMER_FIELDS = ("name", "email", "phone", "dni", "address", "province", "zip")
BANK_DETAILS = {
    "banco": "Banco Santander Río / Banco Galicia",
    "titular": "GALILEA ATELIER JOYERÍA S.A.",
    "cuit": "30-71829341-8",
    "cbu": "0720194820000001284910",
    "alias": "GALILEA.JOYAS.ARG",
    "tipo_cuenta": "Cuenta Corriente Especial en Pesos"
}

def token():
    # 1. Variable de entorno en producción (Vercel o local)
    t = os.environ.get("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if t:
        return t
    # 2. Respaldo en data/settings.json (cargado desde el panel /admin)
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
        if p.get("in_stock") is False: raise ValueError(f"{p.get('name', 'La pieza')} está agotada")
        price = float(p["price"]); total += price * qty
        lines.append({"id": str(p["id"]), "name": p.get("name", ""), "size": str(it.get("size") or "Estándar")[:30],
                      "quantity": qty, "price": price, "image": p.get("primary_image", "")})
    if not lines: raise ValueError("La bolsa está vacía")
    return lines, round(total, 2)

def _customer(payer):
    return {k: str(payer.get(k, "") or "").strip()[:160] for k in CUSTOMER_FIELDS}

def _new_order(order_id, customer, lines, total, **extra):
    order = {
        "id": order_id, "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "customer": customer, "items": lines, "total_amount": total,
        "payment_method": "mercadopago", "payment_method_label": "Mercado Pago",
        "payment_status": "pending", "payment_status_label": STATUS["pending"],
        "shipping_status": "awaiting_payment", "shipping_status_label": "Esperando pago",
        "shipping_carrier": "Andreani Asegurado", "tracking_number": "", "notes": ""}
    order.update(extra)
    return order

def create_preference(data, products, add_order):
    customer = _customer(data.get("payer") or {})
    lines, total = price_cart(data.get("items"), products)
    order_id = f"GAL-{uuid.uuid4().hex[:8].upper()}"
    add_order(_new_order(order_id, customer, lines, total))
    if not token():  # modo prueba: NO aprueba nada, la orden queda pendiente
        return {"success": True, "mode": "sandbox", "order_id": order_id, "total_ars": total,
                "init_point": f"/?checkout=sandbox&order={order_id}",
                "message": "Sin MERCADOPAGO_ACCESS_TOKEN: orden creada como pendiente."}
    s = site_url()
    items = []
    for l in lines:
        item = {"id": l["id"], "title": f"GALILEA - {l['name']}", "quantity": l["quantity"],
                "unit_price": l["price"], "currency_id": "ARS"}
        if str(l["image"]).startswith("https://"): item["picture_url"] = l["image"]
        items.append(item)
    pref_payload = {
        "items": items,
        "payer": {"name": customer["name"] or "Cliente Galilea"},
        "external_reference": order_id,
        # Copia de la orden dentro de Mercado Pago: si el servidor perdió el JSON
        # (Vercel no tiene disco persistente) el webhook la puede reconstruir.
        "metadata": {"order_id": order_id, "customer": customer, "total": total,
                     "items": [{k: l[k] for k in ("id", "name", "size", "quantity", "price")} for l in lines]},
        "statement_descriptor": "GALILEA",
        "back_urls": {k: f"{s}/?checkout={k}&order={order_id}" for k in ("success", "pending", "failure")},
        "payment_methods": {"installments": 6}
    }
    if s.startswith("https://"):  # MP rechaza auto_return y no puede notificar a http://localhost
        pref_payload["auto_return"] = "approved"
        pref_payload["notification_url"] = f"{s}/api/checkout/webhook"

    pref = _mp("POST", "/checkout/preferences", pref_payload)
    return {"success": True, "mode": "live", "order_id": order_id, "total_ars": total,
            "preference_id": pref["id"], "init_point": pref["init_point"]}

def create_transfer_order(data, products, discount_pct, add_order):
    """Orden por transferencia: total con descuento calculado en el servidor; queda
    'pending_verification' hasta que el admin confirme la acreditación."""
    lines, total = price_cart(data.get("items"), products)
    pct = max(0.0, min(float(discount_pct or 0), 50.0))
    final = round(total * (1 - pct / 100), 2)
    order_id = f"GAL-TRF-{uuid.uuid4().hex[:8].upper()}"
    add_order(_new_order(order_id, _customer(data.get("payer") or data), lines, final,
        payment_method="bank_transfer", payment_method_label=f"Transferencia ({pct:g}% OFF)",
        installments=1, installment_amount=final,
        payment_status="pending_verification", payment_status_label="Pendiente Acreditación CBU",
        shipping_status="pending", shipping_status_label="Aguardando Cobro",
        notes=f"Total regular: ${total:,.2f} ARS. Descuento aplicado: {pct:g}%."))
    return {"success": True, "order_id": order_id, "original_amount": total,
            "discount_applied": f"{pct:g}% OFF por transferencia bancaria",
            "final_amount": final, "currency": "ARS", "bank_details": BANK_DETAILS,
            "instructions": (f"Transferí el importe de ${final:,.2f} ARS a nuestro Alias: {BANK_DETAILS['alias']}. "
                             f"Referencia: {order_id}.")}

def _order_from_metadata(pay):
    md = pay.get("metadata") or {}
    if not md.get("order_id") or md.get("order_id") != pay.get("external_reference"): return None
    customer = {k: str((md.get("customer") or {}).get(k, "")) for k in CUSTOMER_FIELDS}
    lines = [{"id": str(i.get("id", "")), "name": i.get("name", ""), "size": i.get("size", ""),
              "quantity": int(i.get("quantity", 1)), "price": float(i.get("price", 0)), "image": ""}
             for i in md.get("items") or []]
    return _new_order(md["order_id"], customer, lines, float(md.get("total", 0)))

def apply_payment(pay, load_orders, save_orders):
    """Aplica a la orden el estado de un pago tal como lo informa la API de Mercado Pago."""
    orders = load_orders()
    order = next((o for o in orders if o.get("id") == pay.get("external_reference")), None)
    if not order:
        order = _order_from_metadata(pay)
        if not order: return None
        orders.insert(0, order)
    pid, status = str(pay.get("id", "")), pay.get("status", "pending")
    if order.get("payment_status") == "approved" and status != "approved" and order.get("mp_payment_id") not in (None, "", pid):
        return order  # un intento fallido de otro pago no pisa uno ya aprobado
    if status == "approved" and (pay.get("currency_id", "ARS") != "ARS" or
                                 abs(float(pay.get("transaction_amount", 0)) - float(order["total_amount"])) > 0.01):
        status = "in_process"; order["notes"] = "Monto del pago no coincide: revisar manualmente."
    order.update(payment_status=status, payment_status_label=STATUS.get(status, status), mp_payment_id=pid)
    if pay.get("installments"): order["installments"] = pay["installments"]
    if pay.get("payment_method_id"): order["payment_method_label"] = f"Mercado Pago ({pay['payment_method_id']})"
    if status == "approved" and order.get("shipping_status") == "awaiting_payment":
        order.update(shipping_status="in_workshop", shipping_status_label="En taller (preparación)")
    save_orders(orders)
    return order

def _signature_ok(query, headers, data_id):
    secret = os.environ.get("MERCADOPAGO_WEBHOOK_SECRET", "").strip()
    if not secret: return True  # configurarlo en producción
    h = {k.lower(): v for k, v in headers.items()}
    parts = dict(p.strip().split("=", 1) for p in h.get("x-signature", "").split(",") if "=" in p)
    manifest = f"id:{str(data_id).lower()};request-id:{h.get('x-request-id', '')};ts:{parts.get('ts', '')};"
    mac = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, parts.get("v1", ""))

def process_webhook(query, body, headers, load_orders, save_orders):
    data_id = (body.get("data") or {}).get("id") or query.get("data.id") or query.get("id")
    if (body.get("type") or body.get("topic") or query.get("type") or query.get("topic")) != "payment" or not data_id:
        return 200, {"ignored": True}
    if not _signature_ok(query, headers, data_id): return 401, {"error": "firma inválida"}
    if not token(): return 200, {"ignored": "sin token"}
    pay = _mp("GET", f"/v1/payments/{data_id}")  # se confirma contra la API, no contra el body
    order = apply_payment(pay, load_orders, save_orders)
    return 200, {"ok": True} if order else {"ignored": "orden desconocida"}

def confirm_payment(data, load_orders, save_orders):
    """Retorno desde Checkout Pro (back_url): verifica el pago contra la API de MP.
    Hace falta en local, donde MP no puede mandar el webhook a localhost."""
    order_id = str(data.get("order_id") or "").strip()
    payment_id = str(data.get("payment_id") or "").strip()
    order = next((o for o in load_orders() if o.get("id") == order_id), None)
    if payment_id.isdigit() and token():
        pay = _mp("GET", f"/v1/payments/{payment_id}")
        if pay.get("external_reference") != order_id: raise ValueError("El pago no corresponde a esta orden")
        order = apply_payment(pay, load_orders, save_orders) or order
    if not order: raise LookupError("Orden no encontrada")
    return {"success": True, "order_id": order_id, "payment_status": order.get("payment_status"),
            "payment_status_label": order.get("payment_status_label"), "total_amount": order.get("total_amount")}
