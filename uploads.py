"""Imágenes de joyas: se validan por su contenido real (no por la extensión) y se guardan en
Vercel Blob (si BLOB_READ_WRITE_TOKEN está cargado), en public/uploads/ (local) o, como
último recurso, dentro del producto como data URL."""
import base64, binascii, json, os, re, secrets, urllib.parse, urllib.request

BLOB_API = "https://vercel.com/api/blob/"
BLOB_API_VERSION = "12"  # el mismo que usa @vercel/blob 2.8

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

def upload_to_blob(data, ext, mime, token, store_id):
    """Sube a Vercel Blob (acceso público) y devuelve la URL definitiva."""
    pathname = f"joyas/joya-{secrets.token_hex(6)}{ext}"
    base = os.environ.get("VERCEL_BLOB_API_URL", BLOB_API).rstrip("/") + "/"  # igual que el SDK
    req = urllib.request.Request(base + "?" + urllib.parse.urlencode({"pathname": pathname}), method="PUT", data=data,
                                 headers={"authorization": f"Bearer {token}", "x-api-version": BLOB_API_VERSION,
                                          "x-vercel-blob-store-id": store_id, "x-vercel-blob-access": "public",
                                          "x-content-type": mime, "x-add-random-suffix": "1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        url = json.loads(r.read()).get("url", "")
    if not url.startswith("https://"):
        raise RuntimeError("Vercel Blob no devolvió una URL")
    return url

def blob_store_id():
    """BLOB_STORE_ID (o con el prefijo elegido al conectar), sin el "store_" inicial, como el SDK."""
    value = os.environ.get("BLOB_STORE_ID", "").strip() or next(
        (v.strip() for k, v in sorted(os.environ.items()) if k.endswith("STORE_ID") and v.strip().startswith("store_")), "")
    return value[len("store_"):] if value.startswith("store_") else value

def oidc_token(header_token=""):
    """Token temporal que Vercel manda a la función en cada pedido (encabezado x-vercel-oidc-token)."""
    token = (header_token or os.environ.get("VERCEL_OIDC_TOKEN", "")).strip()
    token_file = os.environ.get("VERCEL_OIDC_TOKEN_FILE", "")
    if not token and token_file and os.path.exists(token_file):
        with open(token_file, encoding="utf-8") as f:
            token = f.read().strip()
    return token

def blob_auth(header_token=""):
    """(token, store_id) para Vercel Blob, en el mismo orden que @vercel/blob:
    1) OIDC (conexión actual desde Storage: BLOB_STORE_ID + token temporal),
    2) clave fija BLOB_READ_WRITE_TOKEN (conexiones viejas). Si no hay ninguna: (None, None)."""
    store_id, token = blob_store_id(), oidc_token(header_token)
    if store_id and token:
        return token, store_id
    rw = blob_token()
    if rw:
        parts = rw.split("_")
        return rw, parts[3] if len(parts) > 3 else ""
    return None, None

def blob_token():
    """BLOB_READ_WRITE_TOKEN, o la misma clave con el prefijo elegido al conectar el Blob en Vercel."""
    token = os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip()
    if token:
        return token
    return next((v.strip() for k, v in sorted(os.environ.items())
                 if k.endswith("READ_WRITE_TOKEN") and v.strip().startswith("vercel_blob_rw_")), "")

def save_image(data, local_dir=None, header_token=""):
    """Valida y guarda la imagen. Devuelve (url, aviso). El aviso explica si quedó en un lugar provisorio."""
    ext, mime = check_image(data)
    token, store_id = blob_auth(header_token)
    if token:
        try:
            return upload_to_blob(data, ext, mime, token, store_id), ""
        except Exception as e:
            print("Vercel Blob falló:", e)
            warning = "No se pudo guardar en Vercel Blob; la foto quedó dentro del producto."
            return f"data:{mime};base64,{base64.b64encode(data).decode()}", warning
    if local_dir and not os.environ.get("VERCEL"):
        os.makedirs(local_dir, exist_ok=True)
        name = f"joya_{secrets.token_hex(8)}{ext}"
        with open(os.path.join(local_dir, name), "wb") as f:
            f.write(data)
        return f"/uploads/{name}", ""
    return (f"data:{mime};base64,{base64.b64encode(data).decode()}",
            "Conectá Vercel Blob para que las fotos no queden dentro del producto.")
