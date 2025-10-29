# app.py - Scraper Electromedicina V11 (Streamlit)
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re
import time

# ----------------- CONFIG -----------------
st.set_page_config(page_title="Scraper Electromedicina V11", layout="wide")
st.title("🩺 Scraper Electromedicina Argentina — V11")
st.write("Busca noticias sobre equipos médicos (resonador, tomógrafo, rayos X, angiógrafo, etc.) en Google News y medios argentinos. "
         "Podés seleccionar cuántas páginas de Google News recorrer y descargar los resultados en CSV.")

# ----------------- FILTROS Y LISTAS -----------------
# filtros amplios y sinónimos
equipos_keywords = [
    "resonador", "resonancia magnética", "resonancia", "RMN",
    "tomógrafo", "tomografía", "tomografo", "TC", "scanner", "escáner",
    "rayos X", "rayos x", "radiografía", "radiografía", "radiologia", "radiología",
    "angiografo", "angiografía", "hemodinamia", "angiografía",
    "ecógrafo", "ecografía", "ecografo", "ultrasonido", "ecografia",
    "mamógrafo", "mamografía", "mamografo",
    "PET", "SPECT", "monitores", "ventilador", "imagenología", "imagenologia",
    # verbos / contextos de adquisición
    "instaló", "instaló un", "instalado", "instalaron", "adquirió", "adquirieron",
    "donó", "donaron", "incorporó", "incorporaron", "estrenó", "sumó", "entregó", "renovó"
]

marcas_keywords = [
    "Philips", "Siemens", "GE", "Canon", "Mindray", "Hitachi", "Fujifilm", "Agfa",
    "Medtronic", "Dräger", "Drager", "Samsung", "Neusoft", "Esaote", "Carestream", "Toshiba", "Hologic"
]

hospital_keywords = [
    "Hospital", "Hospital Provincial", "Hospital Regional", "Hospital Municipal", "Hospital Público",
    "Clínica", "Sanatorio", "Centro de Salud", "Instituto", "Fundación"
]

# modalidad mapping por keywords (busca en el texto)
modalidad_dict = {
    "CT": ["tomógrafo", "tomografia", "tomografía", "tc", "escáner", "scanner"],
    "DXR": ["rayos x", "radiografía", "radiografia", "radiología", "radiologia"],
    "MR": ["resonador", "resonancia", "rmn", "resonancia magnética"],
    "IGT": ["angiografo", "angiografía", "angiografia", "hemodinamia", "intervencionista"],
    "US": ["ecógrafo", "ecografia", "ecografía", "ultrasonido", "doppler"],
    "MG": ["mamógrafo", "mamografia", "mamografía"]
}

# ----------------- FUENTES -----------------
sources = {
    "Google News": "https://news.google.com/search?q={query}&hl=es-419&gl=AR&ceid=AR:es-419",
    "Clarin": "https://www.clarin.com/salud/",
    "Infobae": "https://www.infobae.com/salud/",
    "La Nación": "https://www.lanacion.com.ar/sociedad/salud/",
    "Cronista": "https://www.cronista.com/category/salud/",
    "Ministerio de Salud": "https://www.argentina.gob.ar/salud/noticias"
}

# query base para Google News (amplia)
gn_query_keywords = [
    "electromedicina", "resonador", "resonancia", "tomógrafo", "tomografia", "tomógrafo",
    "rayos X", "angiografo", "ecógrafo", "mamógrafo", "hospital", "instaló", "adquirió", "donó"
]
gn_query = "+OR+".join([q.replace(" ", "+") for q in gn_query_keywords])

# ----------------- SIDEBAR (opciones de usuario) -----------------
st.sidebar.header("Opciones")
selected_source = st.sidebar.selectbox("Fuente principal", ["Todas"] + list(sources.keys()))
pages = st.sidebar.slider("Páginas Google News a recorrer (cada página ≈ 10 resultados)", 1, 10, 2)
include_traditional = st.sidebar.checkbox("Incluir fuentes tradicionales (Clarin, Infobae, La Nación, Cronista, Ministerio)", True)
max_links_per_site = st.sidebar.slider("Máx. enlaces por fuente (para acelerar)", 10, 200, 50, step=10)

st.sidebar.markdown("---")
st.sidebar.info("Advertencia: Scraping web puede tardar varios minutos si recorrés muchas páginas. "
                 "La app intenta ser tolerante a fallos y no detenerse si una fuente falla.")

# ----------------- UTIL / EXTRACCIONES -----------------
def normalize_link(base_url, link):
    if link.startswith("//"):
        return "https:" + link
    if link.startswith("/"):
        base = base_url.split("/")[0] + "//" + base_url.split("/")[2]
        return base + link
    return link

def detect_modalidad(texto):
    texto_l = texto.lower()
    for mod, terms in modalidad_dict.items():
        for t in terms:
            if t.lower() in texto_l:
                return mod
    return ""

def find_first_keyword(keywords, texto):
    texto_l = texto.lower()
    for k in keywords:
        if k.lower() in texto_l:
            return k
    return ""

def extract_fecha_from_soup(soup):
    # intenta distintos formatos comunes
    if not soup:
        return None
    # <time datetime="...">
    time_tag = soup.find("time")
    if time_tag:
        # datetime attribute
        dt = time_tag.get("datetime")
        if dt:
            # guardar solo fecha YYYY-MM-DD cuando posible
            m = re.search(r"\d{4}-\d{2}-\d{2}", dt)
            if m:
                return m.group(0)
            return dt.strip()
        # texto dentro de <time>
        txt = time_tag.get_text().strip()
        if txt:
            # intentar parseo rápido dd/mm/yyyy o similar
            try:
                parsed = pd.to_datetime(txt, dayfirst=True, errors="coerce")
                if not pd.isna(parsed):
                    return parsed.strftime("%Y-%m-%d")
            except:
                pass
    # meta tags comunes
    meta_dt = soup.find("meta", {"property": "article:published_time"}) or soup.find("meta", {"name": "pubdate"})
    if meta_dt and meta_dt.get("content"):
        m = re.search(r"\d{4}-\d{2}-\d{2}", meta_dt.get("content"))
        if m:
            return m.group(0)
        return meta_dt.get("content").strip()
    return None

def safe_get_text_from_soup(soup):
    if not soup:
        return ""
    return " ".join(p.get_text(separator=" ", strip=True) for p in soup.find_all("p"))

# ----------------- SCRAPEO PRINCIPAL -----------------
def process_article_from_link(link, source_label, headers):
    """Visita link, extrae título, texto completo, fecha, marca, modelo, hospital, modalidad."""
    result = {
        "Tipo": "",
        "Modelo": "",
        "Modalidad": "",
        "Fecha instalación": "",
        "Ubicación (Hospital)": "",
        "Marca": "",
        "Fuente": source_label,
        "Título": "",
        "Link": link
    }
    try:
        resp = requests.get(link, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return None

    # título
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    # fallback: meta og:title
    if not title:
        meta_title = soup.find("meta", {"property": "og:title"}) or soup.find("meta", {"name": "title"})
        if meta_title and meta_title.get("content"):
            title = meta_title.get("content").strip()

    texto_completo = title + " " + safe_get_text_from_soup(soup)

    # detectar tipo por keywords en texto completo
    tipo_detectado = find_first_keyword(equipos_keywords, texto_completo)
    if tipo_detectado:
        result["Tipo"] = tipo_detectado

    # fecha de publicación (intentar)
    fecha_pub = extract_fecha_from_soup(soup)
    if fecha_pub:
        # formatear a YYYY-MM-DD si posible
        try:
            fecha_dt = pd.to_datetime(fecha_pub, errors="coerce")
            if not pd.isna(fecha_dt):
                result["Fecha instalación"] = fecha_dt.strftime("%Y-%m-%d")
            else:
                # si no parsea, dejar raw
                result["Fecha instalación"] = fecha_pub
        except:
            result["Fecha instalación"] = fecha_pub
    else:
        # fecha de scraping en cursiva si no hay otra
        result["Fecha instalación"] = f"*{datetime.today().strftime('%Y-%m-%d')}*"

    # marca
    marca = find_first_keyword(marcas_keywords, texto_completo)
    result["Marca"] = marca or ""

    # modelo heurístico: buscar secuencia "Marca <palabras/números>" o "<tipo> <palabras/números>"
    modelo = ""
    # busca "Marca <texto corto>"
    if marca:
        m = re.search(rf'({re.escape(marca)})\s+([A-Za-z0-9\.\-\s/]+)', texto_completo, re.IGNORECASE)
        if m:
            modelo = m.group(0).strip()
    if not modelo:
        # buscar patrón "Philips Ingenia 1.5T" u "Ingenia 1.5T" o "Ingenia"
        m2 = re.search(r'([A-Z][A-Za-z0-9\-]{3,}\s*[A-Za-z0-9\.\-\/]*)', texto_completo)
        if m2:
            candidate = m2.group(0)
            # solo aceptar si contiene digits or model-like tokens
            if re.search(r'\d', candidate) or len(candidate.split()) <= 3:
                modelo = candidate.strip()
    result["Modelo"] = modelo

    # hospital (buscar frases tipo "Hospital San Martín", "Clínica Santa María")
    ubicacion = ""
    for h in hospital_keywords:
        # busco expresiones como "Hospital San Martín", "Hospital Regional de X", "Clínica Santa Fe"
        m = re.search(rf'({h}\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9\s\-]+)', texto_completo, re.IGNORECASE)
        if m:
            ubicacion = m.group(1).strip()
            break
    result["Ubicación (Hospital)"] = ubicacion

    # modalidad
    modalidad = detect_modalidad(texto_completo)
    result["Modalidad"] = modalidad

    # título limpio
    result["Título"] = title
    result["Link"] = link

    # Si no detectó Tipo, pero título tiene palabra clave, usarla
    if not result["Tipo"]:
        tipo_from_title = find_first_keyword(equipos_keywords, title)
        if tipo_from_title:
            result["Tipo"] = tipo_from_title

    return result

# ----------------- RUN: botón -----------------
if st.button("🔍 Iniciar scraping (V11)"):
    st.info("Iniciando scraping. Esto puede tardar varios minutos si pediste muchas páginas.")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    collected = []
    seen_links = set()
    progress = st.progress(0)
    status_text = st.empty()
    total_expected = 0

    # preparar lista de fuentes a procesar
    sources_to_run = []
    if selected_source == "Todas":
        # siempre incluimos Google News + (opcional) tradicionales
        sources_to_run.append(("Google News", sources["Google News"].format(query=gn_query)))
        if include_traditional:
            for k in ["Clarin", "Infobae", "La Nación", "Cronista", "Ministerio de Salud"]:
                sources_to_run.append((k, sources[k]))
    else:
        # si eligió una en particular
        if selected_source == "Google News":
            sources_to_run.append(("Google News", sources["Google News"].format(query=gn_query)))
        else:
            sources_to_run.append((selected_source, sources[selected_source]))

    # calcular total estimado de requests para barra (muy aproximado)
    # Google News: pages * 10, otras: max_links_per_site
    total_expected += pages * 10
    if include_traditional:
        total_expected += len([s for s in sources_to_run if s[0] != "Google News"]) * min(max_links_per_site, 50)

    processed = 0
    errors = 0

    # Procesar Google News (paginado)
    for label, url in sources_to_run:
        status_text.text(f"Scrapeando fuente: {label}")
        if label == "Google News":
            # recorrer X páginas (cada página de GN ≈ 10 resultados): usar 'start' param
            for p in range(pages):
                start = p * 10
                gn_url = url + f"&start={start}"
                try:
                    resp = requests.get(gn_url, headers=headers, timeout=12)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    # los links verdaderos de noticias en GN suelen apuntar a "/articles/..." o contener "articles"
                    anchors = soup.find_all("a", href=True)
                    count = 0
                    for a in anchors:
                        href = a.get("href")
                        title_text = a.get_text().strip()
                        # heurística: link contiene 'articles' o es un URL absoluto que no sea google internals
                        if not title_text:
                            continue
                        if "articles" in href or href.startswith("http"):
                            link = href
                            # GN links internos a veces empiezan con ./, /, etc.
                            if href.startswith("./") or href.startswith("/"):
                                link = normalize_link(url, href.lstrip("."))
                            elif href.startswith("http"):
                                link = href
                            # evitar duplicados y limitar por fuente
                            if link in seen_links:
                                continue
                            seen_links.add(link)
                            processed += 1
                            total_expected = max(total_expected, processed)  # evitar zero
                            # procesar artículo
                            art = process_article_from_link(link, "Google News", headers)
                            if art:
                                collected.append(art)
                            # control de cantidad por página si se desea
                            count += 1
                            # actualizar progreso
                            progress.progress(min(100, int((processed / max(1, total_expected)) * 100)))
                            if count >= 10:
                                break
                    time.sleep(0.3)  # pequeño delay para ser amable
                except Exception:
                    errors += 1
                    continue
        else:
            # Fuentes tradicionales: extraer links de la página principal
            try:
                resp = requests.get(url, headers=headers, timeout=12)
                soup = BeautifulSoup(resp.text, "html.parser")
                anchors = soup.find_all("a", href=True)
                links = []
                for a in anchors:
                    href = a.get("href")
                    title_text = a.get_text().strip()
                    if not href or not title_text:
                        continue
                    full_link = normalize_link(url, href)
                    if full_link in seen_links:
                        continue
                    links.append((full_link, title_text))
                    seen_links.add(full_link)
                    if len(links) >= max_links_per_site:
                        break
                # procesar links encontrados
                for link, _ in links:
                    processed += 1
                    art = process_article_from_link(link, label, headers)
                    if art:
                        collected.append(art)
                    progress.progress(min(100, int((processed / max(1, total_expected)) * 100)))
                    time.sleep(0.25)
            except Exception:
                errors += 1
                continue

    status_text.text("Finalizado. Preparando resultados...")
    # construir DataFrame y ordenar
    if collected:
        df = pd.DataFrame(collected).drop_duplicates(subset=["Link"])
        # convertir fechas a datetime cuando no estén cursivas
        def parse_fecha(x):
            if isinstance(x, str) and x.startswith("*") and x.endswith("*"):
                return pd.NaT
            try:
                return pd.to_datetime(x, errors="coerce")
            except:
                return pd.NaT
        df["Fecha_dt"] = df["Fecha instalación"].apply(parse_fecha)
        # ordenar por Tipo y Fecha (desc)
        df = df.sort_values(by=["Tipo", "Fecha_dt"], ascending=[True, False]).drop(columns=["Fecha_dt"])
        st.success(f"Se encontraron {len(df)} artículos relevantes. Errores de scraping: {errors}")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Descargar CSV", csv, "resultados_scraper_v11.csv", "text/csv")
    else:
        st.warning("No se encontraron resultados con los filtros y páginas seleccionadas.")
