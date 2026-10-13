"""Imágenes de joyas: se validan por su contenido real (no por la extensión)."""
import base64, binascii, re

MAX_BYTES = 6 * 1024 * 1024
_URL_RE = re.compile(r"^https?://[^\s\"'<>]+$")
_UPLOAD_RE = re.compile(r"^/uploads/[\w.-]+$")

def detect(data):
    """Devuelve (extensión, mime) si los bytes son JPG/PNG/WebP/GIF; si no, None."""
    if data.startswith(b"\xff\xd8\xff"): return ".jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"): return ".png", "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"): return ".gif", "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP": return ".webp", "image/webp"
    return None

def decode_base64(value):
    """Acepta base64 puro o data URL; devuelve los bytes o lanza ValueError."""
    value = (value or "").strip()
    if value.startswith("data:"):
        value = value.split(",", 1)[1] if "," in value else ""
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("La imagen no es válida")

def check_image(data):
    """Valida tamaño y formato; devuelve (extensión, mime) o lanza ValueError."""
    if not data: raise ValueError("No se recibió ninguna imagen")
    if len(data) > MAX_BYTES: raise ValueError("La imagen supera los 6 MB")
    kind = detect(data)
    if not kind: raise ValueError("Formato no admitido: usá JPG, PNG, WebP o GIF")
    return kind

def safe_image_url(url):
    """Solo links http(s), archivos de /uploads/ o data:image válidas. Si no, None."""
    url = (url or "").strip()
    if _URL_RE.match(url) or _UPLOAD_RE.match(url): return url
    if url.startswith("data:image/"):
        try:
            check_image(decode_base64(url))
            return url
        except ValueError:
            return None
    return None
