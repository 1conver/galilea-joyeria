"""Catálogo GALILEA: categorías, materiales y talles que el admin configura desde el panel.
Las listas se guardan en data/settings.json ("categories" y "materials"); si no están,
se usan las sugeridas de abajo. Lo usan server.py (local) y api/index.py (Vercel)."""
import re, unicodedata
import uploads

DEFAULT_CATEGORIES = [
    {"id": "anillos", "label": "Anillos"},
    {"id": "collares", "label": "Collares"},
    {"id": "aros", "label": "Aros"},
    {"id": "pulseras", "label": "Pulseras"},
    {"id": "dijes", "label": "Dijes"},
    {"id": "cadenas", "label": "Cadenas"},
    {"id": "tobilleras", "label": "Tobilleras"},
    {"id": "piercings", "label": "Piercings"},
    {"id": "conjuntos", "label": "Conjuntos"},
    {"id": "relojes", "label": "Relojes"},
    {"id": "diamantes", "label": "Alta Joyería & Diamantes"},
    {"id": "limitada", "label": "Edición Limitada"},
]
DEFAULT_MATERIALS = [
    {"id": "oro", "label": "Oro 18K"},
    {"id": "oro-blanco", "label": "Oro blanco 18K"},
    {"id": "oro-rosa", "label": "Oro rosa 18K"},
    {"id": "plata", "label": "Plata 925"},
    {"id": "plata-banada", "label": "Plata 925 bañada en oro"},
    {"id": "acero-quirurgico", "label": "Acero quirúrgico"},
    {"id": "acero-dorado", "label": "Acero quirúrgico dorado"},
    {"id": "bronce-platinado", "label": "Bronce platinado"},
    {"id": "bronce-banado-plata", "label": "Bronce bañado en plata"},
    {"id": "bronce-banado", "label": "Bronce bañado en oro"},
    {"id": "enchapado", "label": "Enchapado en oro (plaqué)"},
    {"id": "alpaca", "label": "Alpaca"},
    {"id": "titanio", "label": "Titanio"},
    {"id": "fantasia-fina", "label": "Fantasía fina"},
    {"id": "fantasia", "label": "Fantasía"},
    {"id": "cuero-hilo", "label": "Cuero / hilo encerado"},
]
OPTION_KEYS = ("categories", "materials")

def slugify(text):
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40]

def get_options(settings, key):
    opts = (settings or {}).get(key)
    if isinstance(opts, list) and opts:
        return opts
    return [dict(o) for o in (DEFAULT_CATEGORIES if key == "categories" else DEFAULT_MATERIALS)]

def clean_options(raw):
    """Lista que manda el panel -> [{id, label}] sin repetidos. Las nuevas toman el id del nombre."""
    out, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        item = item if isinstance(item, dict) else {"label": item}
        label = re.sub(r"\s+", " ", re.sub(r"[<>\"]", "", str(item.get("label") or ""))).strip()[:60]
        oid = slugify(item.get("id") or label)
        if label and oid and oid != "todos" and oid not in seen:
            seen.add(oid)
            out.append({"id": oid, "label": label})
    if not out:
        raise ValueError("Tiene que quedar al menos una opción")
    if len(out) > 60:
        raise ValueError("Máximo 60 opciones por lista")
    return out

def apply_option_settings(settings, data):
    """Copia a settings las listas de categorías/materiales que vengan en data (validadas)."""
    for key in OPTION_KEYS:
        if key in data:
            settings[key] = clean_options(data[key])

def in_category(product, cat):
    if cat in ("alta-joyeria", "diamantes"):
        return (product.get("category") == "diamantes" or product.get("badge") == "Alta Joyería"
                or "diamante" in product.get("name", "").lower() or product.get("price", 0) >= 400000)
    if cat == "limitada":
        return product.get("category") == "limitada" or product.get("badge") == "Edición Limitada"
    return product.get("category") == cat

def categories_with_counts(products, settings):
    cats = [{"id": "todos", "label": "Colección Completa", "count": len(products)}]
    return cats + [dict(c, count=sum(1 for p in products if in_category(p, c["id"])))
                   for c in get_options(settings, "categories")]

def materials_with_counts(products, settings):
    mats = [dict(m, count=sum(1 for p in products if p.get("metal_group") == m["id"]))
            for m in get_options(settings, "materials")]
    known = {m["id"] for m in mats}
    for p in products:  # joyas con un material que ya no está en la lista
        group = p.get("metal_group")
        if group and group not in known:
            known.add(group)
            mats.append({"id": group, "label": p.get("metal") or group,
                         "count": sum(1 for q in products if q.get("metal_group") == group)})
    return mats

def resolve_category(value, settings):
    cid = slugify(value)
    for c in get_options(settings, "categories"):
        if cid == c["id"]:
            return c["id"], c["label"]
    raise ValueError("Elegí una categoría de la lista")

def resolve_material(value, settings):
    value = str(value or "").strip()
    if not value:
        raise ValueError("Elegí un material")
    for m in get_options(settings, "materials"):
        if value == m["id"] or value.lower() == m["label"].lower():
            return m["label"], m["id"]
    return value[:60], slugify(value)  # material escrito a mano (joyas viejas)

def parse_sizes(value):
    if isinstance(value, str):
        value = value.split(",")
    sizes = [re.sub(r"\s+", " ", str(s)).strip()[:30] for s in (value or [])]
    return [s for s in sizes if s][:20] or ["Único"]

def parse_stock(value):
    """Unidades disponibles. Vacío = sin control de stock (se maneja con el interruptor En stock/Agotado)."""
    if value is None or str(value).strip() == "":
        return None
    try:
        stock = int(float(value))
    except (TypeError, ValueError):
        raise ValueError("El stock tiene que ser un número de unidades")
    if stock < 0:
        raise ValueError("El stock no puede ser negativo")
    return stock

def available(product):
    """Unidades que se pueden vender (None = sin límite)."""
    if product.get("in_stock") is False:
        return 0
    stock = product.get("stock")
    return stock if isinstance(stock, int) else None

def apply_sale(products, order):
    """Descuenta del stock las piezas de un pedido aprobado (una sola vez por pedido).
    Devuelve avisos si alguna pieza no alcanzaba (para revisar a mano)."""
    if order.get("stock_applied"):
        return []
    by_id = {str(p.get("id")): p for p in products}
    shortages = []
    for it in order.get("items", []):
        p = by_id.get(str(it.get("id")))
        if not p or not isinstance(p.get("stock"), int):
            continue
        qty = int(it.get("quantity", 1))
        if qty > p["stock"]:
            shortages.append(f"{p.get('name')}: se vendieron {qty} y había {p['stock']}")
        p["stock"] = max(0, p["stock"] - qty)
        p["in_stock"] = p["stock"] > 0
    order["stock_applied"] = True
    return shortages

def _price(value):
    try:
        price = float(value)
    except (TypeError, ValueError):
        raise ValueError("Precio inválido")
    if price <= 0:
        raise ValueError("El precio tiene que ser mayor a cero")
    return round(price, 2)

def _image(data, key):
    if not data.get(key):
        return ""
    url = uploads.safe_image_url(data[key])
    if not url:
        raise ValueError("Imagen inválida: usá un link http(s) o subí JPG, PNG, WebP o GIF")
    return url

def new_product(data, products, settings):
    name = str(data.get("name", "")).strip()[:120]
    if not name:
        raise ValueError("El nombre es obligatorio")
    price = _price(data.get("price"))
    category, category_label = resolve_category(data.get("category") or "anillos", settings)
    metal, metal_group = resolve_material(data.get("material") or data.get("metal"), settings)
    stock = parse_stock(data.get("stock"))
    primary = _image(data, "primary_image")
    if not primary:
        raise ValueError("Falta la foto principal")
    existing = {p.get("id") for p in products}
    n = len(products) + 1
    while f"galilea-{n:02d}" in existing:
        n += 1
    return {
        "id": f"galilea-{n:02d}",
        "name": name,
        "category": category,
        "category_label": category_label,
        "metal": metal,
        "metal_group": metal_group,
        "price": price,
        "badge": str(data.get("badge", "Nuevo")).strip()[:40],
        "featured": bool(data.get("featured", False)),
        "primary_image": primary,
        # sin foto de detalle la tienda muestra la principal (antes ponía una foto de stock de otra joya)
        "secondary_image": _image(data, "secondary_image"),
        "description": str(data.get("description", "")).strip(),
        "specs": {"material": metal, "acabado": str(data.get("acabado") or "Terminación artesanal").strip()[:80]},
        "sizes": parse_sizes(data.get("sizes")),
        "stock": stock,
        "in_stock": stock is None or stock > 0
    }

def update_product(prod, data, settings):
    """Aplica los cambios del panel a la joya (modifica prod). ValueError si algo es inválido."""
    if "price" in data:
        prod["price"] = _price(data["price"])
    if "stock" in data:
        prod["stock"] = parse_stock(data["stock"])
    if isinstance(prod.get("stock"), int):
        prod["in_stock"] = prod["stock"] > 0  # con cantidad, la disponibilidad sale del número
    elif "in_stock" in data:
        prod["in_stock"] = bool(data["in_stock"])
    if "name" in data and str(data["name"]).strip():
        prod["name"] = str(data["name"]).strip()[:120]
    if data.get("category"):
        prod["category"], prod["category_label"] = resolve_category(data["category"], settings)
    if data.get("material") or data.get("metal"):
        prod["metal"], prod["metal_group"] = resolve_material(data.get("material") or data.get("metal"), settings)
        if isinstance(prod.get("specs"), dict):
            prod["specs"]["metal" if "metal" in prod["specs"] else "material"] = prod["metal"]
    if "badge" in data:
        prod["badge"] = str(data["badge"]).strip()[:40]
    if "description" in data:
        prod["description"] = str(data["description"]).strip()
    if "sizes" in data:
        prod["sizes"] = parse_sizes(data["sizes"])
    for key in ("primary_image", "secondary_image"):
        url = _image(data, key)
        if url:
            prod[key] = url
    return prod
