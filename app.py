# app.py - Scraper Electromedicina V15 (Streamlit)
# Enfoque: LinkedIn (pasivo usando snippets de Google) + distribuidores/portales institucionales
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re
import time
from urllib.parse import quote_plus, urlparse, parse_qs

# ------------- CONFIG -------------
st.set_page_config(page_title="Scraper Electromedicina V15", layout="wide")
st.title("🩺 Scraper Electromedicina Argentina — V15 (LinkedIn pasivo + institucionales)")
st.write("Búsqueda intensiva en LinkedIn (posts públicos indexados por Google) usando snippets + sitios de distribuidores/institucionales argentinos. Prioriza calidad: hospital + equipo.")

# ------------- LISTAS Y DICT -------------
# términos ampliados y de contexto
equipos_keywords = [
    "resonador", "resonancia magnética", "resonancia", "rmn",
    "tomógrafo", "tomografía", "tomografo", "tc", "scanner", "escáner",
    "rayos x", "radiografía", "radiografia", "radiología", "radiologia",
    "angiografo", "angiografía", "angiografia", "hemodinamia",
    "ecógrafo", "ecografía", "ecografo", "ecografia", "ultrasonido",
    "mamógrafo", "mamografía", "mamografo", "pet", "spect",
    "instaló", "instalaron", "adquirió", "adquirieron", "donó", "donaron",
    "incorporó", "incorporaron", "estrenó", "sumó", "entregó", "renovó",
    "nueva sala", "nuevo equipo", "modernización", "modernizacion"
]

marcas_keywords = [
    "Philips", "Siemens", "GE", "Canon", "Mindray", "Hitachi", "Fujifilm", "Agfa",
    "Medtronic", "Dräger", "Drager", "Samsung", "Neusoft", "Esaote", "Carestream",
    "Toshiba", "Hologic", "Varian", "Shimadzu"
]

hospital_indicators = [
    "Hospital", "Hospital Provincial", "Hospital Regional", "Hospital Municipal", "Hospital Público",
    "Clínica", "Sanatorio", "Centro de Salud", "Instituto", "Fundación", "Fundacion"
]

modalidad_dict = {
    "CT": ["tomógrafo", "tomografia", "tomografía", "tc", "escáner", "scanner"],
    "DXR": ["rayos x", "radiografía", "radiografia", "radiología", "radiologia"],
    "MR": ["resonador", "resonancia", "rmn", "resonancia magnética"],
    "IGT": ["angiografo", "angiografía", "angiografia", "hemodinamia", "intervencionista"],
    "US": ["ecógrafo", "ecografia", "ecografía", "ultrasonido", "doppler"],
    "MG": ["mamógrafo", "mamografia", "mamografía"]
}

# ------------- FUENTES INSTITUCIONALES / DISTRIBUIDORES -------------
# Agregá o reemplazá URLs locales que conozcas para más eficacia.
institutional_sites = {
    "Philips AR - News": "https://www.philips.com.ar/a-w/about/news.html",
    "Siemens Healthineers AR (global / noticias)": "https://www.siemens-healthineers.com/es-ar",
    "Mindray - News": "https://www.mindray.com/en/news.html",
    # ejemplos locales de distribuidores que suelen publicar instalaciones:
    # "Distribuidor Ejemplo": "https://www.distribuidorejemplo.com.ar/noticias"
}

comprar_search = "https://www.argentina.gob.ar/compras?search="  # heurística

# ------------- PARAMS UI -------------
st.sidebar.header("Opciones V15 - LinkedIn + institucional")
pages_ln = st.sidebar.slider("Páginas de Google Search (LinkedIn) a recorrer", 1, 6, 3)
include_institutional = st.sidebar.checkbox("Incluir sitios institucionales / distribuidores", True)
include_comprar = st.sidebar.checkbox("Incluir COMPR.AR (licitaciones)", False)
max_links_per_site = st.sidebar.slider("Máx. enlaces por sitio institucional", 10, 150, 60, step=10)
custom_keywords = st.sidebar.text_area("Palabras clave adicionales (separadas por coma)", value="resonador,tomógrafo,angiografo,rayos X")
st.sidebar.markdown("---")
st.sidebar.info("Se priorizará LinkedIn (posts públicos indexados por Google). Si conocés páginas de distribuidores/hospitales locales, agregalas al diccionario 'institutional_sites' en el código para mejor cobertura.")

# incorporar keywords custom
if custom_keywords.strip():
    for w in [x.strip() for x in custom_keywords.split(",") if x.strip()]:
        if w.lower() not in [k.lower() for k in equipos_keywords]:
            equipos_keywords.append(w)

# ------------- UTILIDADES -------------
def normalize_link(base_url, link):
    if not link:
        return None
    if link.startswith("//"):
        return "https:" + link
    if link.startswith("/"):
        base = base_url.split("/")[0] + "//" + base_url.split("/")[2]
        return base + link
    if link.startswith("./"):
        return base_url.rstrip("/") + "/" + link.lstrip("./")
    return link

def safe_get_text_from_soup(soup):
    if not soup:
        return ""
    return " ".join(p.get_text(separator=" ", strip=True) for p in soup.find_all("p"))

def find_first_keyword(keywords, texto):
    texto_l = (texto or "").lower()
    for k in keywords:
        if k.lower() in texto_l:
            return k
    return ""

def detect_modalidad(texto):
    texto_l = (texto or "").lower()
    for mod, terms in modalidad_dict.items():
        for t in terms:
            if t.lower() in texto_l:
                return mod
    return ""

def extract_fecha_from_soup(soup):
    if not soup:
        return None
    time_tag = soup.find("time")
    if time_tag:
        dt = time_tag.get("datetime") or time_tag.get_text(strip=True)
        if dt:
            m = re.search(r"\d{4}-\d{2}-\d{2}", dt)
            if m:
                return m.group(0)
            try:
                parsed = pd.to_datetime(dt, dayfirst=True, errors="coerce")
                if not pd.isna(parsed):
                    return parsed.strftime("%Y-%m-%d")
            except:
                return dt.strip()
    meta = soup.find("meta", {"property": "article:published_time"}) or soup.find("meta", {"name": "pubdate"})
    if meta and meta.get("content"):
        content = meta.get("content")
        m = re.search(r"\d{4}-\d{2}-\d{2}", content)
        if m:
            return m.group(0)
        try:
            parsed = pd.to_datetime(content, dayfirst=True, errors="coerce")
            if not pd.isna(parsed):
                return parsed.strftime("%Y-%m-%d")
        except:
            return content
    return None

def extract_hospital_name(texto):
    if not texto:
        return ""
    for h in hospital_indicators:
        m = re.search(rf'({h}\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9\-\s]+(?:de\s+[A-ZÁÉÍÓÚÑ][A-Za-z]+)?)', texto, re.IGNORECASE)
        if m:
            return " ".join(m.group(1).split())
    # intento extra: nombres comunes "San Martín", "Santo Tomás" si aparecen con Hospital en snippet missing
    m2 = re.search(r'([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9\-\s]+ (Hospital|Hospital Regional|Sanatorio|Clínica))', texto)
    if m2:
        return m2.group(0).strip()
    return ""

def extract_modelo_heuristic(texto, marca):
    if not texto:
        return ""
    modelo = ""
    if marca:
        m = re.search(rf'({re.escape(marca)})\s+([A-Za-z0-9\.\-\/]+(?:\s+[A-Za-z0-9\.\-\/]+){{0,3}})', texto, re.IGNORECASE)
        if m:
            modelo = (m.group(1) + " " + m.group(2)).strip()
    if not modelo:
        m2 = re.search(r'([A-Z][A-Za-z0-9\-]{3,}\s+\d{1,2}\.\d[A-Za-z0-9]*)', texto)
        if m2:
            modelo = m2.group(0).strip()
    if not modelo:
        m3 = re.search(r'(?:resonador|tomógrafo|tomografo|ecógrafo|mamógrafo)\s+([A-Z][A-Za-z0-9\-]{2,}(?:\s+[A-Za-z0-9\-]{1,3})?)', texto, re.IGNORECASE)
        if m3:
            modelo = m3.group(1).strip()
    return modelo

def compute_confidence(row):
    score = 0
    if row.get("Ubicación (Hospital)"):
        score += 35
    if row.get("Marca"):
        score += 25
    if row.get("Modelo"):
        score += 20
    fecha = row.get("Fecha instalación", "")
    if fecha and isinstance(fecha, str) and not (fecha.startswith("*") and fecha.endswith("*")):
        score += 20
    return min(100, score)

# ------------- PROCESS ARTICLE (usa snippet si el body falla) -------------
def process_article_from_link(link, source_label, headers, snippet_text=None):
    """
    visita link y extrae información; si el HTML no permite leer contenido (ej LinkedIn),
    usa 'snippet_text' como texto base para extracción.
    """
    result = {
        "Tipo": "",
        "Modelo": "",
        "Modalidad": "",
        "Fecha instalación": "",
        "Ubicación (Hospital)": "",
        "Marca": "",
        "Fuente": source_label,
        "Título": "",
        "Link": link,
        "Confianza": 0
    }

    soup = None
    page_text = ""
    title = ""

    try:
        resp = requests.get(link, headers=headers, timeout=12)
        soup = BeautifulSoup(resp.text, "html.parser")
        # extraer título si existe
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        meta_title = soup.find("meta", {"property": "og:title"}) or soup.find("meta", {"name": "title"})
        if not title and meta_title and meta_title.get("content"):
            title = meta_title.get("content").strip()
        page_text = title + " " + safe_get_text_from_soup(soup)
    except Exception:
        # no pudo descargar, usaremos snippet si existe
        page_text = snippet_text or ""
        title = "" if not title else title

    # si la página devolvió muy poco texto pero tenemos snippet, usar snippet
    if (not page_text or len(page_text) < 80) and snippet_text:
        page_text = (snippet_text or "") + " " + page_text

    # detectar tipo (por snippet o page_text)
    tipo_detectado = find_first_keyword(equipos_keywords, page_text)
    if not tipo_detectado:
        tipo_detectado = find_first_keyword(equipos_keywords, title)
    if tipo_detectado:
        result["Tipo"] = tipo_detectado

    # fecha: preferir extract_fecha_from_soup(soup) si hay soup
    fecha_pub = extract_fecha_from_soup(soup) if soup else None
    if fecha_pub:
        try:
            fecha_dt = pd.to_datetime(fecha_pub, errors="coerce")
            if not pd.isna(fecha_dt):
                result["Fecha instalación"] = fecha_dt.strftime("%Y-%m-%d")
            else:
                result["Fecha instalación"] = fecha_pub
        except:
            result["Fecha instalación"] = fecha_pub
    else:
        # intentar extraer fecha desde snippet (patrón dd/mm/yyyy o yyyy-mm-dd)
        if snippet_text:
            m = re.search(r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})', snippet_text)
            if m:
                try:
                    parsed = pd.to_datetime(m.group(1), dayfirst=True, errors="coerce")
                    if not pd.isna(parsed):
                        result["Fecha instalación"] = parsed.strftime("%Y-%m-%d")
                    else:
                        result["Fecha instalación"] = m.group(1)
                except:
                    result["Fecha instalación"] = m.group(1)
            else:
                result["Fecha instalación"] = f"*{datetime.today().strftime('%Y-%m-%d')}*"
        else:
            result["Fecha instalación"] = f"*{datetime.today().strftime('%Y-%m-%d')}*"

    # marca (por coincidencia en texto)
    marca = find_first_keyword(marcas_keywords, page_text) or ""
    result["Marca"] = marca

    # modelo heurístico
    modelo = extract_modelo_heuristic(page_text, marca)
    result["Modelo"] = modelo

    # hospital (preferir snippet)
    ubic = extract_hospital_name(page_text)
    result["Ubicación (Hospital)"] = ubic

    # modalidad
    result["Modalidad"] = detect_modalidad(page_text)

    result["Título"] = title or (snippet_text[:120] if snippet_text else "")
    result["Link"] = link
    result["Confianza"] = compute_confidence(result)

    return result

# ------------- LINKEDIN: buscar en Google y extraer snippet -------------
def linkedin_search_with_snippets(query_terms, pages_to_check=2, headers=None):
    """
    Busca en Google resultados site:linkedin.com/posts con query_terms (list of strings).
    Retorna lista de tuples (url, snippet_text).
    """
    headers = headers or {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    base = "https://www.google.com/search?q="
    q = f"site:linkedin.com/posts +(Argentina) +({' OR '.join(query_terms)})"
    q_enc = quote_plus(q)
    results = []

    for p in range(pages_to_check):
        start = p * 10
        url = f"{base}{q_enc}&hl=es&start={start}"
        try:
            resp = requests.get(url, headers=headers, timeout=12)
            soup = BeautifulSoup(resp.text, "html.parser")
            # Google muestra resultados en bloques; intentar varias heurísticas para el snippet
            # 1) bloques con class 'BNeawe s3v9rd AP7Wnd' suelen contener snippet (varía)
            snippet_blocks = soup.find_all("div", class_=re.compile(r'BNeawe.*'))
            # también buscar bloques 'div.IsZvec' o 'div.VwiC3b'
            snippets = {}
            for block in soup.find_all("div"):
                # buscar enlace dentro del bloque
                a = block.find("a", href=True)
                if a and "linkedin.com" in a.get("href"):
                    href = a.get("href")
                    # Google wraps redirect in '/url?q=...'
                    m = re.search(r'/url\?q=(https?://[^&]+)&', href)
                    link = m.group(1) if m else href
                    # snippet text: buscar siguiente <div> con texto corto o el propio block text
                    text = block.get_text(" ", strip=True)
                    # Sanitize: evitar largos excesivos
                    snippet = text if text and len(text) < 800 else (block.get_text(" ", strip=True)[:800] if text else "")
                    if link not in [r[0] for r in results]:
                        results.append((link, snippet))
            # fallback: parse 'a' tags and try to get adjacent span/div snippet
            if not results:
                for a in soup.find_all("a", href=True):
                    href = a.get("href")
                    if not href:
                        continue
                    m = re.search(r'/url\?q=(https?://[^&]+)&', href)
                    actual = m.group(1) if m else href
                    if "linkedin.com" in actual:
                        # try to find snippet in parent or sibling
                        parent = a.parent
                        snippet = ""
                        # look for sibling div or span with short text
                        for sib in parent.find_all_next(['div', 'span'], limit=4):
                            txt = sib.get_text(" ", strip=True)
                            if txt and len(txt) < 900:
                                snippet = txt
                                break
                        results.append((actual, snippet))
            time.sleep(0.3)
        except Exception:
            # ignorar página si falla
            continue
    # dedupe preserving order
    dedup = []
    seen = set()
    for u, s in results:
        if u not in seen:
            dedup.append((u, s))
            seen.add(u)
    return dedup

# ------------- RUN (botón) -------------
if st.button("🔍 Iniciar scraping (V15)"):
    st.info("Iniciando scraping enfocado en LinkedIn (snippets) + sitios institucionales. Esto puede tardar varios minutos.")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    collected = []
    seen_links = set()
    progress = st.progress(0)
    status_text = st.empty()

    # preparar query terms para LinkedIn (keywords más contextos)
    query_terms = ["hospital", "clínica", "sanatorio", "instaló", "adquirió", "donó", "incorporó", "nuevo equipo", "tomógrafo", "resonador", "rayos x", "angiografo"]
    # también agregar los equipos_keywords que hayas personalizado
    for w in equipos_keywords:
        if w not in query_terms:
            query_terms.append(w)

    total_expected = pages_ln * 10
    if include_institutional:
        total_expected += len(institutional_sites) * min(max_links_per_site, 40)
    processed = 0
    errors = 0

    # 1) LinkedIn (pasivo) via Google Search snippets
    status_text.text("Buscando posts públicos de LinkedIn vía Google Search (snippets)...")
    ln_results = linkedin_search_with_snippets(query_terms, pages_to_check=pages_ln, headers=headers)
    for link, snippet in ln_results:
        processed += 1
        progress.progress(min(100, int((processed / max(1, total_expected)) * 100)))
        # normalizar redirecciones / quitar parámetros google
        parsed = urlparse(link)
        if parsed.netloc.endswith("google.com") and "q" in parse_qs(parsed.query):
            # try to extract from q param
            try:
                qv = parse_qs(parsed.query).get("q")[0]
                link = qv
            except:
                pass
        if link in seen_links:
            continue
        seen_links.add(link)
        try:
            art = process_article_from_link(link, "LinkedIn", headers, snippet_text=snippet)
            if art and art.get("Ubicación (Hospital)") and art.get("Tipo"):
                collected.append(art)
        except Exception:
            errors += 1
        time.sleep(0.25)

    # 2) institucionales / distribuidores
    if include_institutional:
        for label, url in institutional_sites.items():
            status_text.text(f"Scrapeando institucional: {label}")
            try:
                resp = requests.get(url, headers=headers, timeout=12)
                soup = BeautifulSoup(resp.text, "html.parser")
                anchors = soup.find_all("a", href=True)
                links = []
                for a in anchors:
                    href = a.get("href")
                    txt = a.get_text(strip=True)
                    if not href or not txt:
                        continue
                    full = normalize_link(url, href)
                    if not full or full in seen_links:
                        continue
                    links.append(full)
                    seen_links.add(full)
                    if len(links) >= max_links_per_site:
                        break
                # procesar links
                for link in links:
                    processed += 1
                    progress.progress(min(100, int((processed / max(1, total_expected)) * 100)))
                    try:
                        art = process_article_from_link(link, label, headers)
                        if art and art.get("Ubicación (Hospital)") and art.get("Tipo"):
                            collected.append(art)
                    except Exception:
                        errors += 1
                    time.sleep(0.25)
            except Exception:
                errors += 1
                continue

    # 3) COMPR.AR (opcional heurístico)
    if include_comprar:
        status_text.text("Buscando en COMPR.AR (heurístico)...")
        try:
            url = comprar_search + quote_plus("equipamiento OR tomógrafo OR resonador")
            resp = requests.get(url, headers=headers, timeout=12)
            soup = BeautifulSoup(resp.text, "html.parser")
            anchors = soup.find_all("a", href=True)
            count = 0
            for a in anchors:
                href = a.get("href")
                txt = a.get_text(strip=True)
                if not href or not txt:
                    continue
                full = normalize_link(url, href)
                if not full or full in seen_links:
                    continue
                seen_links.add(full)
                processed += 1
                art = process_article_from_link(full, "COMPR.AR", headers)
                if art and art.get("Ubicación (Hospital)") and art.get("Tipo"):
                    collected.append(art)
                count += 1
                progress.progress(min(100, int((processed / max(1, total_expected)) * 100)))
                if count >= max_links_per_site:
                    break
                time.sleep(0.2)
        except Exception:
            errors += 1

    status_text.text("Finalizado. Preparando resultados...")

    # construir DataFrame final
    if collected:
        df = pd.DataFrame(collected).drop_duplicates(subset=["Link"]).reset_index(drop=True)
        df["Confianza"] = df.apply(compute_confidence, axis=1)
        # ordenar por Confianza y fecha no-cursiva
        def parse_fecha_sort(x):
            if isinstance(x, str) and x.startswith("*") and x.endswith("*"):
                return pd.NaT
            try:
                return pd.to_datetime(x, errors="coerce")
            except:
                return pd.NaT
        df["Fecha_dt"] = df["Fecha instalación"].apply(parse_fecha_sort)
        df = df.sort_values(by=["Confianza", "Fecha_dt"], ascending=[False, False]).drop(columns=["Fecha_dt"])

        st.success(f"Se encontraron {len(df)} artículos de alta calidad. Errores: {errors}")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Descargar CSV (V15)", csv, "resultados_scraper_v15.csv", "text/csv")
    else:
        st.warning("No se encontraron artículos que cumplan el criterio (hospital + equipo). Probá aumentar páginas LinkedIn o agregar páginas institucionales concretas.")

