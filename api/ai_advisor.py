"""
ai_advisor.py - Motor de Inteligencia Artificial para GALILEA Atelier Joyería
Soporta proveedores de terceros (Google Gemini, OpenAI) y motor experto local especializado.
Entrenado y adaptado para responder con rigor, calidez y precisión sobre todas las áreas del Atelier.
"""

import os
import json
import re
import urllib.request
import urllib.error

# Prompt de Sistema para modelos LLM de terceros (Gemini / OpenAI)
JEWELRY_SYSTEM_PROMPT = """Eres 'Galilea Concierge IA', la asesora virtual oficial de alta joyería y gemología de GALILEA Atelier (Av. Alvear 1850, Ciudad Autónoma de Buenos Aires, Argentina).

MISIÓN:
Guiar al cliente con máxima elegancia, empatía y conocimiento orfebre en su experiencia de compra, respondiendo con precisión a cualquier inquietud sobre la tienda, joyas, gemas, precios, formas de pago, envíos y visitas al taller.

DOMINIOS DE ASESORÍA:
1. Joyas y colecciones: Anillos de autor, solitarios, alianzas de boda, collares, gargantillas, aros criollos y pulseras rivières.
2. Metales nobles de ley: Oro 18K macizo (amarillo, blanco aleado con paladio, rosa) y Plata 925 de ley con acabado espejo antialérgico. Sin baños ni enchapados superficiales.
3. Gemología ética: Diamantes cultivados (lab-grown) carbono neutro certificados IGI/GIA de pureza VVS1/VVS2 y color incoloro F-G; zafiros, esmeraldas y perlas.
4. Medidas y Talles en Argentina: Sistema métrico de diámetro interno en milímetros (16.5 mm = Talle 12/13; 17.2 mm = Talle 14/15; 18.0 mm = Talle 17/18; 19.0 mm = Talle 20/21). Primer ajuste de talle 100% bonificado sin cargo.
5. Beneficios comerciales: 3 y 6 cuotas fijas sin interés con todas las tarjetas bancarias mediante Mercado Pago; 15% de descuento directo por Transferencia Bancaria (Alias: GALILEA.JOYAS.ARG).
6. Envíos y Packaging: Envío gratis asegurado a toda la Argentina por Andreani Custodia Express (24-48h CABA/GBA, 3-5 días interior). Packaging de gala en caja rígida de lino, lazo de satén y certificado de autenticidad.
7. Atención personalizada y taller: Atelier en Av. Alvear 1850, Buenos Aires. Visitas con cita previa y contacto humano por WhatsApp al +54 9 11 4050-9988.
8. Garantía y cuidado: Garantía perpetua sobre la ley de los metales; servicio de pulido y revisión anual sin cargo de por vida.

GUARDRAIL ESTRICTO:
Si el usuario consulta sobre temas completamente ajenos a la joyería (fútbol, programación, política, cocina, matemática, religión, etc.):
Responde con cortesía y elegancia:
'Disculpas, como asesora de GALILEA Atelier estoy capacitada para orientarte sobre nuestras piezas de joyería fina, metales nobles, gemología, talles y compras en el atelier. ¿En qué joya o momento especial puedo ayudarte?'

Tono: Distinguido, empático, conocedor de la orfebrería. Utiliza castellano rioplatense elegante ('podés', 'contamos', 'te ofrecemos'). Usa formato Markdown (**negritas**, viñetas •) para una lectura ágil.
"""

OFF_TOPIC_PATTERNS = [
    r'\b(python|javascript|typescript|react|html|css|php|java|c\+\+|sql|codigo|código|programar|programacion|programación|script|bug|api|backend|frontend)\b',
    r'\b(futbol|fútbol|messi|maradona|river|boca|partido|mundial|champions|gol|copa libertadores|deporte|tenis|nba)\b',
    r'\b(politica|política|presidente|elecciones|diputado|senador|partido politico|gobierno|milei|cristina|macri)\b',
    r'\b(receta|cocinar|torta|brownie|pasta|asado|ingredientes|horno|sarten|sartén)\b',
    r'\b(matematica|matemática|ecuacion|ecuación|raiz cuadrada|raíz cuadrada|derivada|integral|algebra|álgebra|calcular|cuanto es \d+)\b',
    r'\b(clima hoy|pronostico|pronóstico|temperatura manana|va a llover)\b',
    r'\b(chiste|contame un chiste|broma|cuento)\b',
    r'\b(pelicula|película|serie|netflix|spotify|cancion|canción|cantante|trailer)\b'
]

JEWELRY_CONTEXT_WORDS = [
    'joya', 'joyas', 'joyeria', 'anillo', 'anillos', 'solitario', 'solitarios', 'alianza', 'alianzas',
    'collar', 'collares', 'gargantilla', 'gargantillas', 'cadena', 'cadenas', 'dije', 'dijes', 'colgante',
    'aro', 'aros', 'arito', 'aritos', 'argolla', 'argollas', 'criollo', 'criollos',
    'pulsera', 'pulseras', 'brazalete', 'brazaletes', 'riviere', 'esclava',
    'oro', 'plata', 'platino', 'rodio', 'quilate', 'quilates', '18k', '925',
    'diamante', 'diamantes', 'gema', 'gemas', 'piedra', 'piedras', 'brillante', 'brillantes', 'zafiro', 'esmeralda', 'rubi', 'perla', 'perlas',
    'talle', 'talles', 'talla', 'medida', 'medidas', 'medir', 'diametro', 'milimetro', 'mm', 'dedo',
    'precio', 'precios', 'cuanto sale', 'cuanto cuesta', 'costo', 'costos', 'presupuesto', 'barato', 'accesible', 'caro', 'exclusivo',
    'pago', 'pagos', 'cuota', 'cuotas', 'tarjeta', 'tarjetas', 'mercado pago', 'mercadopago', 'transferencia', 'descuento', '15%', 'banco',
    'envio', 'envios', 'andreani', 'tiempo', 'demora', 'entrega', 'despacho', 'retiro',
    'taller', 'atelier', 'alvear', 'galilea', 'direccion', 'donde estan', 'donde queda', 'visitar', 'cita', 'horario', 'local', 'tienda',
    'regalo', 'regalos', 'aniversario', 'compromiso', 'casamiento', 'boda', 'novia', 'mama', 'esposa',
    'limpieza', 'limpiar', 'cuidado', 'mantenimiento', 'garantia', 'certificado', 'autenticidad', 'pulido',
    'personalizado', 'personalizados', 'a medida', 'grabar', 'grabado', 'stock', 'como compro', 'contacto', 'whatsapp',
    'cambio', 'cambios', 'devolucion', 'devoluciones', 'mojar', 'agua', 'circon', 'zirconia', 'catalogo', 'quienes son', 'historia', 'sobre ustedes'
]

def normalize_text(text: str) -> str:
    """Normaliza texto quitando acentos y signos para matching robusto."""
    s = text.lower().strip()
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u',
        'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u',
        '¿': '', '?': '', '¡': '', '!': '', '(': '', ')': '', ':': '', ';': '', '"': '', "'": ''
    }
    for orig, rep in replacements.items():
        s = s.replace(orig, rep)
    return s

def is_off_topic(query: str) -> bool:
    """Verifica si la consulta está fuera del dominio de la joyería y compras en el atelier."""
    norm = normalize_text(query)
    
    # Si contiene alguna palabra del contexto de joyería/tienda, NO es off-topic
    if any(k in norm for k in JEWELRY_CONTEXT_WORDS):
        return False

    # Cortesías habituales tampoco son off-topic
    if any(k in norm for k in ['hola', 'buen dia', 'buenas', 'gracias', 'adios', 'chau', 'que tal', 'como estas']):
        return False

    # Revisar si coincide con patrones expresamente off-topic
    for pattern in OFF_TOPIC_PATTERNS:
        if re.search(pattern, norm, re.IGNORECASE):
            return True

    return False

def extract_budget(query: str):
    """Extrae montos numéricos de presupuesto de la consulta."""
    norm = normalize_text(query).replace('.', '').replace(',', '')
    match_mil = re.search(r'(\d+)\s*(mil|k)', norm)
    if match_mil:
        try:
            return int(match_mil.group(1)) * 1000
        except ValueError:
            pass
    match_num = re.search(r'\$?\s*(\d{4,7})', norm)
    if match_num:
        try:
            return int(match_num.group(1))
        except ValueError:
            pass
    return None

def format_ars(val: int) -> str:
    """Formatea un monto como ARS $ ###.###."""
    return f"${val:,.0f}".replace(",", ".")

def match_products(query: str, products: list) -> list:
    """Busca hasta 3 productos del catálogo relacionados con la consulta."""
    if not products:
        return []
    norm = normalize_text(query)
    budget = extract_budget(query)

    # 1. Filtro por presupuesto
    if budget:
        filtered = [p for p in products if p.get('price', 0) <= budget]
        if filtered:
            filtered.sort(key=lambda x: x.get('price', 0), reverse=True)
            return filtered[:3]

    # 2. Filtro por categorías específicas
    if any(k in norm for k in ['aro', 'aros', 'arito', 'aritos', 'argolla', 'criollo']):
        matched = [p for p in products if p.get('category') == 'aros']
        if matched:
            return matched[:3]

    if any(k in norm for k in ['collar', 'collares', 'gargantilla', 'cadena', 'dije']):
        matched = [p for p in products if p.get('category') == 'collares']
        if matched:
            return matched[:3]

    if any(k in norm for k in ['pulsera', 'pulseras', 'brazalete', 'riviere', 'esclava']):
        matched = [p for p in products if p.get('category') == 'pulseras']
        if matched:
            return matched[:3]

    if any(k in norm for k in ['compromiso', 'casamiento', 'boda', 'alianza', 'solitario']):
        matched = [p for p in products if p.get('category') == 'anillos' or 'solitario' in normalize_text(p.get('name', '')) or p.get('badge') == 'Alta Joyería']
        if matched:
            return matched[:3]

    if any(k in norm for k in ['diamante', 'diamantes', 'brillante', 'vvs', 'gema']):
        matched = [p for p in products if p.get('category') == 'diamantes' or 'diamante' in normalize_text(p.get('name', '')) or p.get('badge') == 'Alta Joyería']
        if matched:
            return matched[:3]

    if any(k in norm for k in ['oro blanco', 'blanco']):
        matched = [p for p in products if 'blanco' in normalize_text(p.get('metal', ''))]
        if matched:
            return matched[:3]

    if any(k in norm for k in ['oro amarillo', 'oro 18k', 'oro']):
        matched = [p for p in products if 'oro' in normalize_text(p.get('metal', ''))]
        if matched:
            return matched[:3]

    if any(k in norm for k in ['plata', '925']):
        matched = [p for p in products if 'plata' in normalize_text(p.get('metal', ''))]
        if matched:
            return matched[:3]

    if any(k in norm for k in ['anillo', 'anillos']):
        matched = [p for p in products if p.get('category') == 'anillos']
        if matched:
            return matched[:3]

    if any(k in norm for k in ['barato', 'economico', 'accesible', 'menor precio']):
        sorted_prods = sorted(products, key=lambda x: x.get('price', 0))
        return sorted_prods[:3]

    if any(k in norm for k in ['exclusivo', 'alta gama', 'alta joyeria', 'mas caro']):
        sorted_prods = sorted(products, key=lambda x: x.get('price', 0), reverse=True)
        return sorted_prods[:3]

    # Por defecto, los destacados
    featured = [p for p in products if p.get('featured')]
    return (featured if featured else products)[:3]

def call_gemini_api(api_key: str, message: str, history: list = None) -> str:
    """Llama a Google Gemini API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    contents = []
    if history:
        for item in history[-4:]:
            role = "user" if item.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": item.get("text", "")}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    payload = {
        "system_instruction": {"parts": [{"text": JEWELRY_SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.35, "maxOutputTokens": 600}
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        res_data = json.loads(response.read().decode('utf-8'))
        candidates = res_data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()
    return ""

def call_openai_api(api_key: str, message: str, history: list = None) -> str:
    """Llama a OpenAI API (gpt-4o-mini)."""
    url = "https://api.openai.com/v1/chat/completions"
    messages = [{"role": "system", "content": JEWELRY_SYSTEM_PROMPT}]
    if history:
        for item in history[-4:]:
            role = "user" if item.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": item.get("text", "")})
    messages.append({"role": "user", "content": message})

    payload = {"model": "gpt-4o-mini", "messages": messages, "temperature": 0.35, "max_tokens": 600}
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=10) as response:
        res_data = json.loads(response.read().decode('utf-8'))
        choices = res_data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
    return ""

def generate_local_response(raw_query: str, products: list) -> dict:
    """
    Motor experto especializado con cobertura conversacional profunda.
    Responde con precisión a cada intención específica sin repetir fallbacks genéricos.
    """
    norm = normalize_text(raw_query)
    budget = extract_budget(raw_query)
    matched = match_products(raw_query, products)

    # 1. Guardrail para temas ajenos a joyería
    if is_off_topic(raw_query):
        return {
            "reply": (
                "Disculpas, como asesora de **GALILEA Atelier** me dedico exclusivamente a orientarte sobre nuestras piezas de joyería fina, "
                "metales nobles, gemología, talles y compras en el atelier.<br><br>"
                "Podés consultarme sobre anillos, aros, collares, cómo medir tu talle de anillo o nuestras facilidades de pago en cuotas sin interés."
            ),
            "products": [],
            "suggestions": ["¿Cómo elijo mi talle de anillo?", "Ver joyas en Oro 18K", "Promociones y Cuotas"],
            "guardrail_triggered": True
        }

    # 2. Saludos de cortesía (si es un saludo solo o muy corto)
    if any(k in norm for k in ['hola', 'buen dia', 'buenas tardes', 'buenas noches', 'que tal', 'como estas', 'buenas']) and len(norm.split()) <= 4:
        return {
            "reply": (
                "¡Hola! Qué gusto saludarte. Te doy una cálida bienvenida a **GALILEA Atelier**.<br><br>"
                "Soy tu asesora virtual de alta orfebrería y gemología. Puedo orientarte en la elección de piezas según tu estilo o presupuesto, "
                "ayudarte a medir tu talle de anillo con exactitud o detallarte nuestras facilidades de pago en hasta **6 cuotas fijas sin interés** y envíos asegurados por Andreani.<br><br>"
                "¿Te gustaría explorar alguna colección en particular?"
            ),
            "products": matched,
            "suggestions": ["Ver Anillos y Solitarios", "¿Cómo mido mi talle?", "Joyas en Oro 18K"]
        }

    # 3. Agradecimientos y despedidas
    if any(k in norm for k in ['gracias', 'muchas gracias', 'genial', 'perfecto', 'chau', 'adios', 'hasta luego', 'muy amable', 'de diez', 'excelente']):
        return {
            "reply": (
                "¡Ha sido un verdadero placer asesorarte! Recordá que podés consultarme en cualquier momento "
                "o comunicarte directamente con nuestro atelier por WhatsApp si querés coordinar una visita privada o diseñar una joya personalizada.<br><br>"
                "¡Que tengas una hermosa jornada!"
            ),
            "products": [],
            "suggestions": ["Ver Catálogo Completo", "WhatsApp del Atelier", "Reiniciar Consulta"]
        }

    # 4. Quiénes son / Sobre la marca / Historia
    if any(k in norm for k in ['quienes son', 'quien sos', 'sobre ustedes', 'marca galilea', 'historia', 'que es galilea']):
        return {
            "reply": (
                "**GALILEA Atelier** es una casa argentina de alta joyería y orfebrería de autor ubicada en Av. Alvear 1850, Ciudad Autónoma de Buenos Aires.<br><br>"
                "• **Nobleza Material:** Forjamos alianzas, solitarios, gargantillas y pulseras exclusivamente en metales nobles genuinos (Oro 18K y Plata 925 de ley) sin baños ni enchapados superficiales.<br>"
                "• **Sostenibilidad:** Incorporamos diamantes cultivados en laboratorio (lab-grown) carbono neutro certificados VVS, garantizando la misma pureza y dureza 10 Mohs con impacto ambiental positivo.<br>"
                "• **Atelier:** Contamos con taller propio para ajustes, grabados láser de precisión y mantenimiento perpetuo."
            ),
            "products": matched,
            "suggestions": ["Ver Colección Destacada", "Dónde estamos ubicados", "Hablar con un orfebre"]
        }

    # 5. Ubicación, Atelier Central, Visitas y Horarios
    if any(k in norm for k in ['donde estan', 'donde queda', 'ubicacion', 'direccion', 'local', 'tienda fisica', 'showroom', 'taller', 'visitar', 'cita', 'horario', 'abren', 'puedo ir', 'calle']):
        return {
            "reply": (
                "Nuestro **Atelier Central** se encuentra ubicado en:<br><br>"
                "• **Dirección:** Av. Alvear 1850, Ciudad Autónoma de Buenos Aires.<br>"
                "• **Modalidad:** Atención personalizada con cita previa para garantizarte privacidad y asesoramiento mano a mano con un maestro orfebre.<br>"
                "• **Horarios:** Lunes a Viernes de 10:00 a 19:00 hs | Sábados de 10:00 a 14:00 hs.<br><br>"
                "Si querés coordinar una cita para probarte alianzas o diseñar una joya a medida, podés pulsar el botón de WhatsApp aquí mismo."
            ),
            "products": [],
            "suggestions": ["Coordinar cita por WhatsApp", "Ver piezas en catálogo", "Tiempos de envío"]
        }

    # 6. Garantía, Autenticidad, Calidad y Mantenimiento
    if any(k in norm for k in ['garantia', 'certificado', 'autenticidad', 'original', 'calidad', 'reparar', 'reparacion', 'mantenimiento', 'pulido']):
        return {
            "reply": (
                "En **GALILEA Atelier** respaldamos cada obra con los más altos estándares de orfebrería:<br><br>"
                "• **Garantía Perpetua:** Avalamos de por vida la nobleza y ley de nuestros metales (Oro 18K y Plata 925).<br>"
                "• **Certificado de Autenticidad Foliado:** Cada pieza incluye especificación de aleación, gramaje y graduación de gemas.<br>"
                "• **Primer Ajuste de Talle Bonificado:** Si el anillo no te calza a la perfección, lo ajustamos sin cargo con retiro y entrega asegurada.<br>"
                "• **Mantenimiento Anual Gratuito:** Disponés de pulido y revisión de engastes sin costo anual de por vida en nuestro atelier."
            ),
            "products": matched,
            "suggestions": ["¿Cómo mido mi talle?", "Joyas en Oro 18K", "Consultar por WhatsApp"]
        }

    # 7. Cambios, Devoluciones y Satisfacción
    if any(k in norm for k in ['cambio', 'cambios', 'devolucion', 'devoluciones', 'si no me gusta', 'si no le queda', 'si me equivoque', 'politica de cambio']):
        return {
            "reply": (
                "Comprar en GALILEA es 100% libre de riesgos:<br><br>"
                "• **Plazo de Cambio:** Disponés de **30 días corridos** desde la recepción de tu joya para solicitar un cambio de modelo o medida.<br>"
                "• **Primer Ajuste Bonificado:** Si elegiste un anillo y el talle necesita modificación, el primer ajuste es **100% gratuito** con retiro y entrega asegurada a domicilio.<br>"
                "• **Procedimiento Simple:** Nos contactás por WhatsApp o mail y Andreani retira el paquete asegurado por tu domicilio sin complicaciones."
            ),
            "products": matched,
            "suggestions": ["¿Cómo mido mi talle?", "Iniciar una compra", "Hablar con soporte"]
        }

    # 8. Cómo comprar / Proceso de pedido
    if any(k in norm for k in ['como compro', 'como es el proceso', 'pasos para comprar', 'como pago', 'hacer pedido', 'agregar al carrito', 'como hacer la compra', 'como encargar']):
        return {
            "reply": (
                "Comprar en GALILEA es ágil, seguro y transparente:<br><br>"
                "1. **Elegí tu joya:** Podés verla en detalle con 'Ver' o agregarla directamente a tu compra con **'+ Bolsa'** aquí en el chat.<br>"
                "2. **Seleccioná tu talle:** En tu bolsa hacé clic en 'Iniciar Pago Seguro'.<br>"
                "3. **Elegí tu beneficio de pago:** Hasta **6 cuotas fijas sin interés** con tarjetas vía Mercado Pago o **15% OFF directo** por Transferencia Bancaria.<br>"
                "4. **Envío asegurado:** Lo despachamos gratis a tu domicilio con Andreani y te enviamos el código de seguimiento satelital."
            ),
            "products": matched,
            "suggestions": ["Ver Catálogo Completo", "Medios de pago y cuotas", "Hablar con un orfebre"]
        }

    # 9. Contacto humano y WhatsApp
    if any(k in norm for k in ['contacto', 'telefono', 'mail', 'whatsapp', 'humano', 'persona', 'asesor real', 'hablar con alguien', 'numero']):
        return {
            "reply": (
                "Podés ponerte en contacto directo con nuestro equipo de orfebres y asesores a través de:<br><br>"
                "• **WhatsApp Directo:** [+54 9 11 4050-9988](https://wa.me/5491140509988) (Atención personalizada de lunes a sábados).<br>"
                "• **Correo Institucional:** atelier@galilea-joyeria.com<br>"
                "• **Atelier:** Av. Alvear 1850, Ciudad Autónoma de Buenos Aires.<br><br>"
                "Haciendo clic en el botón de WhatsApp superior podés iniciar una conversación de inmediato con una asesora humana."
            ),
            "products": [],
            "suggestions": ["Abrir WhatsApp Oficial", "Ver catálogo de joyas", "Seguir chateando aquí"]
        }

    # 10. Diseños personalizados y grabados
    if any(k in norm for k in ['personalizado', 'personalizados', 'a medida', 'grabar', 'grabado', 'inscripcion', 'disenar', 'a pedido']):
        return {
            "reply": (
                "Realizamos **piezas exclusivas y alianzas a medida** en nuestro taller:<br><br>"
                "• **Grabado Láser de Alta Precisión:** Bonificado sin costo en todas nuestras alianzas y solitarios (nombres, fechas, iniciales o coordenadas).<br>"
                "• **Orfebrería a Pedido:** Forjamos alianzas en Oro 18K (amarillo o blanco) con acabados pulido espejo, satinado mate o texturado florentino.<br>"
                "• **Engastes a Medida:** Asesoramiento para montar diamantes o gemas heredadas con monturas contemporáneas."
            ),
            "products": match_products('alianzas', products),
            "suggestions": ["Cotizar por WhatsApp", "Ver alianzas en catálogo", "¿Cómo medir el talle?"]
        }

    # 11. Consulta explícita sobre cómo medir el talle de anillo
    if any(k in norm for k in ['talle', 'talla', 'como se mi talle', 'como mido', 'medir', 'medida', 'diametro', 'milimetro', 'tabla de talles', 'numero de anillo', 'medir mi dedo', 'tamano de anillo']):
        return {
            "reply": (
                "Para conocer tu talle exacto en Argentina, el método más preciso es medir con regla milimetrada el "
                "**diámetro interno** de un anillo que te quede cómodo (sin incluir el borde metálico):<br><br>"
                "• **16.5 mm** = Talle 12 / 13<br>"
                "• **17.2 mm** = Talle 14 / 15 *(estándar femenino más frecuente)*<br>"
                "• **18.0 mm** = Talle 17 / 18<br>"
                "• **19.0 mm** = Talle 20 / 21<br><br>"
                "**Tranquilidad Galilea:** Todas nuestras piezas cuentan con el **primer ajuste de talle 100% bonificado sin cargo**, "
                "incluyendo retiro y entrega asegurada en tu domicilio."
            ),
            "products": match_products('anillos', products),
            "suggestions": ["Ver anillos en stock", "¿Y si es para regalo sorpresa?", "Consultar por WhatsApp"]
        }

    # 12. Compromiso, Casamiento, Alianzas y Pedidas
    if any(k in norm for k in ['compromiso', 'casamiento', 'boda', 'alianza', 'alianzas', 'pedida', 'proponer', 'matrimonio']):
        return {
            "reply": (
                "Para una propuesta de compromiso o unión matrimonial inolvidable, nuestras obras de alta orfebrería destacan por su solidez eterna:<br><br>"
                "• **Solitarios de Compromiso:** En Oro 18K macizo con diamantes cultivados lab-grown certificados VVS de brillo excepcional.<br>"
                "• **Alianzas Matrimoniales:** Diseñadas con perfil *comfort-fit* anatómico para uso diario continuo.<br>"
                "• **Beneficios Especiales:** Incluyen grabado láser personalizado sin cargo y cambio de talle garantizado."
            ),
            "products": match_products('compromiso', products),
            "suggestions": ["Ver Solitarios de Compromiso", "¿Cómo saber su talle en secreto?", "Hablar con un orfebre"]
        }

    # 13. Diamantes cultivados vs Circones / Zirconia / Sintéticos
    if any(k in norm for k in ['circon', 'zirconia', 'cubic', 'sintetico', 'moissanita', 'falso', 'trucho', 'es real']):
        return {
            "reply": (
                "Existe una diferencia radical entre un circón y un diamante cultivado:<br><br>"
                "• **Circón o Zirconia:** Es una gema sintética blanda de laboratorio (óxido de circonio) que se desgasta, raya y pierde su brillo o se vuelve lechosa con el roce y el agua en pocos meses.<br>"
                "• **Diamante Cultivado Galilea:** Es un **diamante auténtico** en su física, química y óptica (100% carbono puro cristalizado con dureza 10 Mohs). Brilla eternamente, no se raya y viene con certificación gemológica oficial."
            ),
            "products": match_products('diamantes', products),
            "suggestions": ["Ver joyas con Diamantes", "Certificación VVS", "Consultar por WhatsApp"]
        }

    # 14. ¿Se pueden mojar? / Ducha / Pileta / Mar
    if any(k in norm for k in ['mojar', 'se puede mojar', 'agua', 'ducha', 'pileta', 'mar', 'bano', 'se arruina']):
        return {
            "reply": (
                "¡Sí! Todas nuestras creaciones de **Oro 18K macizo y Plata 925 de ley** son metales nobles macizos y no enchapados, por lo que **no se pelan ni se despintan con el agua cotidiana ni en la ducha**.<br><br>"
                "• **Recomendación orfebre:** Para conservar el lustre de pulido espejo como el primer día, aconsejamos retirar las piezas antes de ingresar a piletas con cloro intenso o aplicar fragancias y cremas directamente sobre ellas.<br>"
                "• **Beneficio perpetuo:** Recordá que tenés **mantenimiento y pulido anual bonificado de por vida** en nuestro atelier."
            ),
            "products": matched,
            "suggestions": ["Consejos de limpieza", "Joyas en Oro 18K", "Mantenimiento gratuito"]
        }

    # 15. Colección de AROS
    if any(k in norm for k in ['aro', 'aros', 'arito', 'aritos', 'argolla', 'argollas', 'criollo', 'criollos']):
        return {
            "reply": (
                "Nuestra colección de **Aros de Autor** combina ligereza escultural y porte refinado:<br><br>"
                "• Criollos y argollas macizas forjadas a mano en **Oro 18K y Plata 925**.<br>"
                "• Cierres de seguridad reforzados antialérgicos para máximo confort.<br>"
                "• Terminaciones pulidas a mano con brillo espejo inalterable.<br><br>"
                "Aquí tenés nuestras piezas más destacadas para ver detalles o agregar a tu bolsa:"
            ),
            "products": match_products('aros', products),
            "suggestions": ["Aros en Oro 18K", "Aros en Plata 925", "Calcular cuotas sin interés"]
        }

    # 16. Colección de COLLARES y GARGANTILLAS
    if any(k in norm for k in ['collar', 'collares', 'gargantilla', 'gargantillas', 'cadena', 'cadenas', 'dije', 'dijes', 'colgante']):
        return {
            "reply": (
                "Nuestras **Gargantillas y Collares** están concebidos para resaltar sobre la piel con delicadeza atemporal:<br><br>"
                "• Cadenas forjadas en Oro 18K y Plata 925 con largo regulable (40 a 45 cm) que se adapta a cualquier escote.<br>"
                "• Solitarios colgantes con diamantes cultivados éticos y engastes a cuatro granos de máxima refracción.<br>"
                "• Broches de seguridad reforzados tipo marinero u oval pulido."
            ),
            "products": match_products('collares', products),
            "suggestions": ["Gargantillas con Diamante", "Collares en Oro 18K", "Opciones para regalo"]
        }

    # 17. Colección de PULSERAS y RIVIÈRES
    if any(k in norm for k in ['pulsera', 'pulseras', 'brazalete', 'brazaletes', 'riviere', 'rivière', 'esclava']):
        return {
            "reply": (
                "Nuestra línea de **Pulseras y Rivières** encarna el equilibrio entre diseño escultórico y ergonomía diaria:<br><br>"
                "• **Pulseras Rivière / Tenis:** Engarzadas a mano con diamantes cultivados de brillo continuo y cierre de doble traba de seguridad.<br>"
                "• **Brazaletes Rígidos & Eslabones:** Forjados en Oro 18K macizo y Plata 925 con acabado satinado o espejo."
            ),
            "products": match_products('pulseras', products),
            "suggestions": ["Pulseras Rivière Diamantes", "Medidas de muñeca", "Pulseras en Oro 18K"]
        }

    # 18. Colección de ANILLOS (cuando preguntan por anillos en general, no talle)
    if any(k in norm for k in ['anillo', 'anillos', 'solitario', 'solitarios']):
        return {
            "reply": (
                "Nuestra selección de **Anillos y Solitarios** abarca desde siluetas contemporáneas hasta piezas de alta orfebrería:<br><br>"
                "• Forjados en **Oro 18K Amarillo Macizo**, **Oro Blanco con rodio** y **Plata 925 de ley**.<br>"
                "• Con gemas éticas, diamantes cultivados VVS o siluetas minimalistas puras.<br>"
                "• Incluyen **primer ajuste de talle sin cargo** para que compres con total tranquilidad."
            ),
            "products": match_products('anillos', products),
            "suggestions": ["¿Cómo mido mi talle?", "Solitarios de Compromiso", "Ver piezas en Oro 18K"]
        }

    # 19. Regalos, Aniversarios y Recomendaciones
    if any(k in norm for k in ['regalo', 'regalos', 'recomendar', 'recomiendame', 'que me recomendas', 'aniversario', 'cumpleanos', 'cumple', 'novia', 'mama', 'esposa', 'especial', 'destacado', 'mas vendido']):
        return {
            "reply": (
                "Para agasajar en una ocasión especial o celebrar un hito trascendental, te recomiendo nuestras piezas de silueta universal:<br><br>"
                "• **Gargantillas con Diamante Solitario:** Una joya atemporal con largo adaptable que no depende de conocer talles de dedo.<br>"
                "• **Aros Criollos Clásicos:** Perfectos para uso cotidiano o de noche, en Oro 18K o Plata 925.<br>"
                "• **Presentación de Obsequio:** Todas nuestras joyas se entregan listas para regalar en un estuche rígido forrado en lino, con lazo de satén y cambio garantizado."
            ),
            "products": matched,
            "suggestions": ["Gargantillas para regalo", "Aros atemporales", "¿Cómo viene el packaging?"]
        }

    # 20. Metales Nobles (Oro 18k, Oro Blanco, Plata 925)
    if any(k in norm for k in ['oro', 'plata', 'metal', 'metales', '18k', '925', 'blanco', 'rosa', 'amarillo', 'despinta', 'enchapado', 'macizo', 'rodio']):
        return {
            "reply": (
                "En **GALILEA Atelier** forjamos nuestras piezas exclusivamente en metales nobles macizos de primera ley:<br><br>"
                "• **Oro 18K Amarillo Macizo (750‰):** Nobleza perpetua. No se despinta, no pierde su brillo ni se desgasta con los años.<br>"
                "• **Oro Blanco 18K:** Aleación de alta orfebrería con paladio y terminación de rodio electrolítico para un brillo níveo inalterable.<br>"
                "• **Plata 925 de Ley:** Plata esterlina maciza forjada y pulida artesanalmente con acabado espejo antialérgico.<br><br>"
                "Prescindimos de baños superficiales perecederos para que cada joya conviva con tu piel de generación en generación."
            ),
            "products": matched,
            "suggestions": ["Joyas en Oro 18K", "Joyas en Plata 925", "Garantía perpetua"]
        }

    # 21. Diamantes Cultivados y Gemología Ética
    if any(k in norm for k in ['diamante', 'diamantes', 'lab grown', 'cultivado', 'cultivados', 'laboratorio', 'vvs', 'brillante', 'gema', 'gemas', 'piedra', 'zafiro', 'esmeralda', 'rubi']):
        return {
            "reply": (
                "Nuestros diamantes son **cultivados en laboratorio con huella de carbono neutra certificada**:<br><br>"
                "• **Identidad Absoluta:** Tienen exactamente la misma composición química (100% carbono puro cristalizado en red cúbica), dureza 10 Mohs y brillo óptico que un diamante de mina.<br>"
                "• **Pureza Superior:** Seleccionamos graduaciones **VVS1 / VVS2** y escala de color **F-G (incoloro excepcional)**.<br>"
                "• **Sostenibilidad:** Libres de conflicto ético y con trazabilidad verificable certificada."
            ),
            "products": match_products('diamantes', products),
            "suggestions": ["Ver Alta Joyería Diamantes", "¿Tienen certificación oficial?", "Cuotas sin interés"]
        }

    # 22. Descuentos, Promociones y Ofertas
    if any(k in norm for k in ['descuento', 'descuentos', 'promocion', 'promociones', 'promo', 'promos', 'oferta', 'ofertas', 'cupon', '15%']):
        return {
            "reply": (
                "En **GALILEA Atelier** disponemos de importantes beneficios comerciales vigentes:<br><br>"
                "• **15% de Descuento Inmediato** abonando mediante Transferencia Bancaria directa (Alias: `GALILEA.JOYAS.ARG`).<br>"
                "• **3 y 6 Cuotas Fijas Sin Interés** con tarjetas de crédito bancarias Visa, Mastercard y American Express por Mercado Pago.<br>"
                "• **Envío Gratis Asegurado** a todo el país a través de Andreani Custodia Express."
            ),
            "products": matched,
            "suggestions": ["Datos de Transferencia 15% OFF", "Calcular cuotas", "Ver catálogo de joyas"]
        }

    # 23. Stock y Disponibilidad Inmediata
    if any(k in norm for k in ['stock', 'disponible', 'disponibilidad', 'inmediata', 'entrega inmediata']):
        return {
            "reply": (
                "Todas las piezas expuestas en nuestro catálogo online cuentan con **stock asegurado para despacho prioritario**:<br><br>"
                "• **CABA y Gran Buenos Aires:** Despacho prioritario en 24 a 48 hs hábiles.<br>"
                "• **Resto del país:** 3 a 5 días hábiles a domicilio o sucursal Andreani con seguimiento satelital.<br>"
                "• **Piezas a Medida / Ajustes especiales:** La calibración orfebre toma entre 48 y 72 hs hábiles adicionales."
            ),
            "products": matched,
            "suggestions": ["Ver joyas en stock", "¿Cómo mido mi talle?", "Tiempos de envío Andreani"]
        }

    # 24. Precios, Presupuesto y Opciones Accesibles / Exclusivas
    if budget or any(k in norm for k in ['precio', 'precios', 'cuanto sale', 'cuanto cuesta', 'costo', 'costos', 'presupuesto', 'barato', 'economico', 'accesible', 'caro', 'exclusivo']):
        budget_str = f" de hasta **{format_ars(budget)}**" if budget else ""
        return {
            "reply": (
                f"Para tu consulta de presupuesto{budget_str}, seleccioné creaciones destacadas forjadas en metales nobles:<br><br>"
                "• **Piezas en Plata 925 de Ley:** Desde $58.000 a $95.000 (o 3 cuotas fijas sin interés de ~$19.000).<br>"
                "• **Orfebrería en Oro 18K Macizo:** Desde $190.000 a $380.000.<br>"
                "• **Alta Joyería en Diamantes Cultivados:** Obras de autor de $390.000 a $780.000.<br><br>"
                "Recordá que abonando por **Transferencia Bancaria tenés un 15% de descuento inmediato**, o podés financiar en **hasta 6 cuotas sin interés**."
            ),
            "products": matched,
            "suggestions": ["Opciones más accesibles", "Joyas en Oro 18K", "Calcular cuotas sin interés"]
        }

    # 25. Medios de Pago, Cuotas y Transferencia
    if any(k in norm for k in ['pago', 'pagos', 'cuota', 'cuotas', 'tarjeta', 'tarjetas', 'mercado pago', 'mercadopago', 'transferencia', 'banco', 'alias', 'cbu']):
        return {
            "reply": (
                "Contamos con los siguientes beneficios comerciales en toda la Argentina:<br><br>"
                "• **3 y 6 Cuotas Fijas Sin Interés** con todas las tarjetas de crédito bancarias (Visa, Mastercard, Amex) procesadas por **Mercado Pago**.<br>"
                "• **15% de Descuento Inmediato** abonando por Transferencia Bancaria directa (Alias: `GALILEA.JOYAS.ARG`).<br>"
                "• Facturación formal automática tipo A o B y protección de cobro bancario SSL de 256 bits."
            ),
            "products": matched,
            "suggestions": ["Datos para Transferencia", "¿Cómo es el envío Andreani?", "Ver catálogo completo"]
        }

    # 26. Envíos y Tiempos de Entrega
    if any(k in norm for k in ['envio', 'envios', 'andreani', 'tiempo', 'demora', 'llega', 'domicilio', 'sucursal', 'interior', 'packaging', 'caja', 'estuche']):
        return {
            "reply": (
                "Brindamos **Envío Gratis Asegurado a toda la República Argentina** a través de **Andreani Custodia Express**:<br><br>"
                "• **CABA y Gran Buenos Aires:** Despacho prioritario en 24 a 48 hs hábiles.<br>"
                "• **Resto del país:** 3 a 5 días hábiles a domicilio o sucursal Andreani con seguimiento satelital en tiempo real.<br>"
                "• **Packaging de Gala:** Cada alhaja viaja en un cofre rígido forrado en lino italiano, lazo de satén, estuche de gamuza y certificado oficial."
            ),
            "products": [],
            "suggestions": ["¿El envío tiene seguro total?", "¿Cómo viene el packaging?", "Ver catálogo de joyas"]
        }

    # 27. Catálogo General y Colecciones
    if any(k in norm for k in ['catalogo', 'coleccion', 'colecciones', 'que tienen', 'productos', 'piezas', 'modelos', 'ver todo']):
        return {
            "reply": (
                "En **GALILEA Atelier** forjamos cuatro grandes colecciones de autor:<br><br>"
                "• **Anillos & Solitarios:** Diseños en Oro 18K y Plata 925 con diamantes cultivados o siluetas puras.<br>"
                "• **Gargantillas & Collares:** Cadenas de eslabón fino y solitarios colgantes regulables.<br>"
                "• **Aros Criollos:** Argollas macizas con cierres antialérgicos reforzados.<br>"
                "• **Pulseras & Rivières:** Brazaletes rígidos y líneas rivière con engaste continuo.<br><br>"
                "Aquí tenés algunas de nuestras piezas más aclamadas para inspeccionar o sumar a tu bolsa:"
            ),
            "products": matched,
            "suggestions": ["Ver Anillos y Solitarios", "Ver Aros Criollos", "Gargantillas y Collares"]
        }

    # 28. Respuesta conversacional amplia y acogedora (evita insistencias rígidas)
    return {
        "reply": (
            "Con mucho gusto te asesoro. En **GALILEA Atelier** nos especializamos en alta orfebrería de autor forjada en Buenos Aires:<br><br>"
            "• **Anillos, Solitarios y Alianzas** en Oro 18K macizo y Plata 925 de ley.<br>"
            "• **Gargantillas, Aros criollos y Pulseras** con diamantes cultivados éticos.<br>"
            "• **Medición y primer ajuste de talle 100% bonificado** en todo el país.<br>"
            "• **Hasta 6 cuotas fijas sin interés** con tarjetas y 15% OFF por transferencia bancaria.<br><br>"
            "Podés elegir alguna de las sugerencias rápidas debajo o consultarme sobre cualquier pieza, metal o detalle de compra."
        ),
        "products": matched,
        "suggestions": ["Ver Anillos y Solitarios", "¿Cómo mido mi talle?", "Joyas en Oro 18K"]
    }

def process_chat_message(message: str, history: list = None, products: list = None) -> dict:
    """
    Punto de entrada principal para el chat de IA.
    1. Verifica si es off-topic para aplicar el guardrail con elegancia.
    2. Si hay claves de API configuradas, invoca el LLM de terceros.
    3. Si no hay claves o falla, utiliza el motor experto integral del Atelier.
    """
    if products is None:
        products = []

    clean_msg = message.strip()
    if not clean_msg:
        return {
            "success": False,
            "error": "Mensaje vacío",
            "reply": "Por favor ingresá tu consulta sobre nuestras joyas.",
            "suggestions": ["Ver anillos de compromiso", "¿Cómo mido mi talle?", "Cuotas y pagos"]
        }

    # Verificación de Guardrail
    if is_off_topic(clean_msg):
        return {
            "success": True,
            "reply": (
                "Disculpas, como asesora de **GALILEA Atelier** me dedico exclusivamente a orientarte sobre nuestras piezas de joyería fina, "
                "metales nobles, gemología, talles y compras en el atelier.<br><br>"
                "Podés consultarme sobre anillos, aros, collares, cómo medir tu talle de anillo o nuestras facilidades de pago en cuotas sin interés."
            ),
            "products": [],
            "suggestions": ["¿Cómo elijo mi talle de anillo?", "Ver joyas en Oro 18K", "Promociones y Cuotas"],
            "provider": "galilea-guardrail",
            "guardrail_triggered": True
        }

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()

    # Si hay API keys de terceros disponibles
    if gemini_key:
        try:
            gemini_reply = call_gemini_api(gemini_key, clean_msg, history)
            if gemini_reply:
                return {
                    "success": True,
                    "reply": gemini_reply,
                    "products": match_products(clean_msg, products),
                    "suggestions": generate_local_response(clean_msg, products).get("suggestions", []),
                    "provider": "google-gemini"
                }
        except Exception as e:
            print(f"Aviso Gemini API: {e}")

    if openai_key:
        try:
            openai_reply = call_openai_api(openai_key, clean_msg, history)
            if openai_reply:
                return {
                    "success": True,
                    "reply": openai_reply,
                    "products": match_products(clean_msg, products),
                    "suggestions": generate_local_response(clean_msg, products).get("suggestions", []),
                    "provider": "openai"
                }
        except Exception as e:
            print(f"Aviso OpenAI API: {e}")

    # Motor experto local de Joyería GALILEA
    local_res = generate_local_response(clean_msg, products)
    return {
        "success": True,
        "reply": local_res["reply"],
        "products": local_res.get("products", match_products(clean_msg, products)),
        "suggestions": local_res.get("suggestions", ["Ver Anillos y Solitarios", "¿Cómo mido mi talle?", "Joyas en Oro 18K"]),
        "provider": "galilea-expert-engine"
    }
