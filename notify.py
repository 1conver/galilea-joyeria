"""Avisos por email al cliente sobre su pedido (SMTP de la casilla de Hostinger, sin dependencias).

Variables de entorno: SMTP_USER (ej. pedidos@galilea.online) y SMTP_PASSWORD; opcionales
SMTP_HOST (smtp.hostinger.com), SMTP_PORT (465) y MAIL_FROM_NAME (GALILEA Atelier).
Sin SMTP_USER/SMTP_PASSWORD no se envía nada y la tienda funciona igual.
Cada evento se envía una sola vez por pedido (queda anotado en order["emails_sent"])."""
import os, smtplib, ssl
from html import escape
from email.message import EmailMessage
from email.utils import formataddr

import payments

ANDREANI_URL = "https://www.andreani.com/envio/{}"


def configured():
    return bool(os.environ.get("SMTP_USER", "").strip() and os.environ.get("SMTP_PASSWORD", "").strip())


def send(to, subject, text, html):
    user = os.environ.get("SMTP_USER", "").strip()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((os.environ.get("MAIL_FROM_NAME", "GALILEA Atelier"), user))
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    host = os.environ.get("SMTP_HOST", "smtp.hostinger.com").strip()
    port = int(os.environ.get("SMTP_PORT", "465"))
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=12, context=ssl.create_default_context()) as s:
            s.login(user, os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=12) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)


def tracking_page(order):
    return f"{payments.site_url()}/?pedido={order['id']}"


def andreani_link(order):
    tn = str(order.get("tracking_number") or "").strip()
    return ANDREANI_URL.format(tn) if tn else ""


def _items_text(order):
    return "\n".join(f"  {it.get('quantity', 1)} x {it.get('name', '')} ({it.get('size', '')})" for it in order.get("items", []))


def _items_html(order):
    return "".join(f"<li>{escape(str(it.get('quantity', 1)))} × {escape(it.get('name', ''))} "
                   f"<span style='color:#8E2F48'>({escape(str(it.get('size', '')))})</span></li>"
                   for it in order.get("items", []))


def _money(value):
    return "$" + f"{float(value or 0):,.0f}".replace(",", ".")


def build(order, event):
    """Devuelve (asunto, texto, html) del aviso, o None si el evento no tiene email."""
    name = (order.get("customer") or {}).get("name") or "¡Hola"
    oid, total = order["id"], _money(order.get("total_amount"))
    follow = tracking_page(order)
    if event == "payment_approved":
        subject = f"Pago confirmado: pedido {oid}"
        intro = "Recibimos tu pago. Ya estamos preparando tu pieza en el taller."
        extra_text, extra_html = "", ""
    elif event == "transfer_created":
        b = payments.BANK_DETAILS
        subject = f"Recibimos tu pedido {oid}: datos para transferir"
        intro = f"Reservamos tu pedido. Para confirmarlo, transferí {total} y respondé este email con el comprobante."
        extra_text = (f"\nAlias: {b['alias']}\nCBU: {b['cbu']}\nTitular: {b['titular']}\nCUIT: {b['cuit']}\n"
                      f"Referencia: {oid}\n")
        extra_html = (f"<p style='background:#FDF4F5;padding:12px 16px;border-radius:8px'>"
                      f"<b>Alias:</b> {escape(b['alias'])}<br><b>CBU:</b> {escape(b['cbu'])}<br>"
                      f"<b>Titular:</b> {escape(b['titular'])}<br><b>CUIT:</b> {escape(b['cuit'])}<br>"
                      f"<b>Referencia:</b> {escape(oid)}</p>")
    elif event == "shipped":
        link = andreani_link(order)
        subject = f"Tu pedido {oid} está en camino"
        intro = f"Despachamos tu pedido con {order.get('shipping_carrier') or 'Andreani'}."
        extra_text = f"\nNúmero de envío: {order.get('tracking_number', '')}\nSeguilo en Andreani: {link}\n" if link else ""
        extra_html = (f"<p><b>Número de envío:</b> {escape(order.get('tracking_number', ''))}<br>"
                      f"<a href='{escape(link)}' style='color:#C4506B'>Seguir el envío en Andreani</a></p>") if link else ""
    elif event == "delivered":
        subject = f"Tu pedido {oid} fue entregado"
        intro = "Tu pedido figura como entregado. ¡Gracias por elegir GALILEA! Que la disfrutes."
        extra_text, extra_html = "", ""
    else:
        return None
    text = (f"{name}:\n\n{intro}\n{extra_text}\nPedido {oid} - Total {total}\n{_items_text(order)}\n\n"
            f"Seguí tu pedido: {follow}\n\nGALILEA Atelier")
    html = (f"<div style='font-family:Arial,sans-serif;color:#3A1822;max-width:560px;margin:auto'>"
            f"<h2 style='font-family:Georgia,serif;font-weight:normal;color:#8E2F48'>GALILEA Atelier</h2>"
            f"<p>{escape(name)}:</p><p>{escape(intro)}</p>{extra_html}"
            f"<p><b>Pedido {escape(oid)}</b> · Total {escape(total)}</p><ul>{_items_html(order)}</ul>"
            f"<p><a href='{escape(follow)}' style='display:inline-block;background:#C4506B;color:#fff;"
            f"padding:10px 18px;border-radius:999px;text-decoration:none'>Seguí tu pedido</a></p>"
            f"<p style='font-size:12px;color:#A5808B'>Si tenés dudas, respondé este email.</p></div>")
    return subject, text, html


def notify_order(order, event):
    """Envía el aviso del evento si corresponde. Modifica order (emails_sent); el que llama lo guarda."""
    sent = order.setdefault("emails_sent", [])
    to = str((order.get("customer") or {}).get("email") or "").strip()
    if event in sent or "@" not in to or not configured():
        return False
    content = build(order, event)
    if not content:
        return False
    try:
        send(to, *content)
    except Exception as e:  # un email que falla nunca frena el pedido
        print(f"Email '{event}' de {order['id']} no enviado:", e)
        return False
    sent.append(event)
    return True
