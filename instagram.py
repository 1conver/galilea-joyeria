"""Últimas publicaciones de Instagram para la tienda (Instagram API with Instagram Login, sin dependencias).

Se activa cargando INSTAGRAM_ACCESS_TOKEN (token de larga duración, dura 60 días) en Vercel.
El token se renueva solo cada 7 días y la versión renovada se guarda en la base.
Las publicaciones se guardan 1 hora para no consultar a Instagram en cada visita.
Instagram no avisa por webhook de las publicaciones propias, por eso se consulta así."""
import hashlib, json, os, time, urllib.parse, urllib.request

GRAPH = "https://graph.instagram.com"
# caption no está disponible con Instagram Login (solo con Facebook Login)
FIELDS = "id,media_type,media_url,thumbnail_url,permalink,timestamp"
CACHE_SECONDS = 3600
REFRESH_EVERY = 7 * 24 * 3600


def env_token():
    return os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()


def configured():
    return bool(env_token())


def _get(path, params):
    url = f"{GRAPH}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def current_token(store):
    """Token vigente: el de Vercel, o su versión renovada guardada en la base."""
    env = env_token()
    auth = store.get("instagram_auth", {}) or {}
    source = hashlib.sha256(env.encode()).hexdigest()[:16]
    if auth.get("source") != source:  # se cargó un token nuevo en Vercel
        auth = {"source": source, "token": env, "refreshed_at": 0}
    if time.time() - auth.get("refreshed_at", 0) > REFRESH_EVERY:
        try:
            out = _get("/refresh_access_token", {"grant_type": "ig_refresh_token", "access_token": auth["token"]})
            if out.get("access_token"):
                auth.update(token=out["access_token"], refreshed_at=time.time())
        except Exception as e:  # un token de menos de 24 h todavía no se puede renovar: reintenta en 1 hora
            print("Instagram: no se pudo renovar el token:", e)
            auth["refreshed_at"] = time.time() - REFRESH_EVERY + 3600
        store.put("instagram_auth", auth)
    return auth["token"]


def get_posts(store, limit=8):
    if not configured():
        return {"configured": False, "posts": []}
    cache = store.get("instagram_cache", {}) or {}
    if time.time() - cache.get("at", 0) < CACHE_SECONDS:
        return {"configured": True, "posts": cache.get("posts", [])}
    posts = cache.get("posts", [])
    try:
        data = _get("/me/media", {"fields": FIELDS, "limit": limit, "access_token": current_token(store)})
        posts = []
        for item in data.get("data", []):
            image = item.get("thumbnail_url") if item.get("media_type") == "VIDEO" else item.get("media_url")
            if image and item.get("permalink"):  # media_url no viene en contenido con reclamo de copyright
                posts.append({"id": item.get("id"), "image": image, "url": item["permalink"],
                              "type": item.get("media_type"), "date": item.get("timestamp")})
        store.put("instagram_cache", {"at": time.time(), "posts": posts[:limit]})
    except Exception as e:  # si Instagram falla se muestran las últimas guardadas y reintenta en 10 minutos
        print("Instagram: no se pudieron leer las publicaciones:", e)
        store.put("instagram_cache", {"at": time.time() - CACHE_SECONDS + 600, "posts": posts})
    return {"configured": True, "posts": posts[:limit]}
