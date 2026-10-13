"""Acceso al panel GALILEA: contraseñas con hash (PBKDF2) y sesiones firmadas.
Las sesiones no se guardan en memoria, así que funcionan igual en server.py y en Vercel.

Cambiar o crear la contraseña de un usuario de data/users.json:
    python auth.py bren
"""
import os, json, hmac, hashlib, base64, secrets, time

ITERATIONS = 200_000
SESSION_HOURS = 12
_fallback_secret = secrets.token_bytes(32)

def _secret():
    # Sin SESSION_SECRET las sesiones se invalidan al reiniciar (y en Vercel no duran entre instancias)
    s = os.environ.get("SESSION_SECRET", "").strip()
    return s.encode() if s else _fallback_secret

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${dk}"

def check_password(password, stored):
    try:
        _, iterations, salt, dk = (stored or "").split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    except ValueError:
        return False
    return hmac.compare_digest(calc, dk)

def find_user(users, login_id, password):
    login_id = (login_id or "").strip().lower()
    if not login_id: return None
    user = next((u for u in users if login_id in (u.get("email", "").lower(), u.get("username", "").lower())), None)
    return user if user and check_password(password or "", user.get("password_hash")) else None

def session_user(user):
    return {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"],
            "role_label": user.get("role_label", "Personal de Atelier")}

def _sign(body):
    return hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()

def issue_token(user):
    payload = dict(session_user(user), exp=int(time.time()) + SESSION_HOURS * 3600)
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"gal_{body}.{_sign(body)}"

def read_token(token):
    if not token or not token.startswith("gal_") or "." not in token: return None
    body, sig = token[4:].rsplit(".", 1)
    if not hmac.compare_digest(_sign(body), sig): return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    if payload.pop("exp", 0) < time.time(): return None
    return payload

def user_from_header(auth_header):
    auth_header = auth_header or ""
    return read_token(auth_header[7:].strip()) if auth_header.startswith("Bearer ") else None

if __name__ == "__main__":
    import sys, getpass
    if len(sys.argv) != 2:
        sys.exit("Uso: python auth.py <usuario o email>")
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "users.json")
    with open(path, encoding="utf-8") as f: users = json.load(f)
    login = sys.argv[1].strip().lower()
    user = next((u for u in users if login in (u.get("email", "").lower(), u.get("username", "").lower())), None)
    if not user: sys.exit(f"No existe el usuario {login} en data/users.json")
    pw = getpass.getpass("Nueva contraseña: ")
    if len(pw) < 8 or pw != getpass.getpass("Repetila: "):
        sys.exit("Las contraseñas no coinciden o tienen menos de 8 caracteres")
    user["password_hash"] = hash_password(pw); user.pop("password", None)
    with open(path, "w", encoding="utf-8") as f: json.dump(users, f, indent=2, ensure_ascii=False)
    print(f"Contraseña de {user['name']} actualizada.")
