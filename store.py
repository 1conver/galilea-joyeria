"""Persistencia GALILEA.
- Local (python server.py): archivos JSON en data/.
- Vercel con Upstash Redis conectado (pestaña Storage): todo se guarda en Redis y no se pierde.
- Vercel sin Redis: /tmp de respaldo (se borra cuando la instancia se recicla).

Documentos: "products", "settings", "users_extra" (cuentas creadas desde el panel).
Pedidos: uno por clave, para que dos compras simultáneas no se pisen.
La primera vez que Redis no tiene un documento, se carga desde data/ del repo."""
import os, json, time, threading, urllib.request

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DATA_DIR = os.path.join(ROOT_DIR, "data")
PREFIX = "galilea"


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


class FileStore:
    def __init__(self, data_dir, seed_dir=REPO_DATA_DIR):
        self.data_dir, self.seed_dir = data_dir, seed_dir
        self.kind = "temporal" if data_dir.startswith("/tmp") else "archivos"
        self._lock = threading.Lock()
        self._claims = set()

    def _path(self, name):
        return os.path.join(self.data_dir, f"{name}.json")

    def get(self, name, default):
        path = self._path(name)
        if not os.path.exists(path):
            path = os.path.join(self.seed_dir, f"{name}.json")
        return _read_json(path, default)

    def put(self, name, data):
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self._path(name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def claim(self, key, ttl=30 * 24 * 3600):
        """True solo la primera vez para cada key (evita procesar dos veces lo mismo).
        En memoria alcanza: con archivos corre un solo proceso."""
        with self._lock:
            if key in self._claims:
                return False
            self._claims.add(key)
            return True

    def list_orders(self):
        return self.get("orders", [])

    def get_order(self, order_id):
        return next((o for o in self.list_orders() if o.get("id") == order_id), None)

    def put_order(self, order):
        with self._lock:
            orders = self.list_orders()
            idx = next((i for i, o in enumerate(orders) if o.get("id") == order["id"]), None)
            if idx is None:
                orders.insert(0, order)
            else:
                orders[idx] = order
            self.put("orders", orders)


class RedisStore:
    """Upstash Redis por su API REST (sin dependencias)."""
    kind = "redis"

    def __init__(self, url, token, seed_dir=REPO_DATA_DIR):
        self.url, self.token, self.seed_dir = url.rstrip("/"), token, seed_dir

    def _request(self, path, payload):
        req = urllib.request.Request(self.url + path, method="POST", data=json.dumps(payload).encode(),
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    def _cmd(self, *args):
        out = self._request("", list(args))
        if "error" in out:
            raise RuntimeError(f"Redis: {out['error']}")
        return out.get("result")

    def _pipeline(self, commands):
        out = self._request("/pipeline", commands)
        errors = [o["error"] for o in out if "error" in o]
        if errors:
            raise RuntimeError(f"Redis: {errors[0]}")
        return [o.get("result") for o in out]

    def get(self, name, default):
        key = f"{PREFIX}:doc:{name}"
        raw = self._cmd("GET", key)
        if raw is None:
            seed = _read_json(os.path.join(self.seed_dir, f"{name}.json"), None)
            if seed is None:
                return default
            self._cmd("SET", key, json.dumps(seed, ensure_ascii=False), "NX")
            raw = self._cmd("GET", key)
        return json.loads(raw) if raw else default

    def put(self, name, data):
        self._cmd("SET", f"{PREFIX}:doc:{name}", json.dumps(data, ensure_ascii=False))

    def claim(self, key, ttl=30 * 24 * 3600):
        """True solo la primera vez para cada key, aunque lo pidan dos instancias a la vez."""
        return self._cmd("SET", f"{PREFIX}:claim:{key}", "1", "NX", "EX", ttl) == "OK"

    def list_orders(self):
        ids = self._cmd("ZREVRANGE", f"{PREFIX}:orders", 0, -1) or []
        if not ids:
            return []
        raws = self._cmd("MGET", *[f"{PREFIX}:order:{i}" for i in ids]) or []
        return [json.loads(r) for r in raws if r]

    def get_order(self, order_id):
        raw = self._cmd("GET", f"{PREFIX}:order:{order_id}")
        return json.loads(raw) if raw else None

    def put_order(self, order):
        self._pipeline([
            ["SET", f"{PREFIX}:order:{order['id']}", json.dumps(order, ensure_ascii=False)],
            # NX: al actualizar un pedido no cambia su lugar en la lista
            ["ZADD", f"{PREFIX}:orders", "NX", str(order.get("created_ts") or time.time()), order["id"]],
        ])


def redis_credentials():
    """Vercel puede cargar las variables con el prefijo KV_ o UPSTASH_REDIS_ según la integración."""
    for url_key, token_key in (("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"),
                               ("KV_REST_API_URL", "KV_REST_API_TOKEN")):
        url, token = os.environ.get(url_key, "").strip(), os.environ.get(token_key, "").strip()
        if url and token:
            return url, token
    return None, None


_store = None

def get_store():
    global _store
    if _store is None:
        url, token = redis_credentials()
        if url:
            _store = RedisStore(url, token)
        elif os.environ.get("VERCEL"):
            _store = FileStore("/tmp/galilea-data")
        else:
            _store = FileStore(REPO_DATA_DIR)
    return _store
