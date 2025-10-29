# app.py - Scraper Electromedicina V13 (Streamlit)
# Versión: añade LinkedIn (pasivo) + fuentes institucionales + COMPR.AR
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re
import time
from urllib.parse import quote_plus

# ----------------- CONFIG -----------------
st.set_page_config(page_title="Scraper Electromedicina V13", layout="wide")
st.title("🩺 Scraper Electromedicina Argentina — V13")
st.write("Añadidas fuentes: LinkedIn (pasivo), sitios institucionales y COMPR.AR. Prioridad: calidad sobre cantidad.")

# ----------------- FILTROS Y LISTAS (AMPLIADOS) -----------------
equipos_keywords = [
    "resonador", "resonancia magnética", "resonancia", "rmn",
    "tomógrafo", "tomografía", "tomografo", "tc", "scanner", "escáner",
    "rayos x", "radiografía", "radiografia", "radiología", "radiologia",
    "angiografo", "angiografía", "angiografia", "hemodinamia",
    "ecógrafo", "ecografía", "ecografo", "ecografia", "ultrasonido",
    "mamógrafo", "mamografía", "mamografo", "PET", "SPECT",
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

# ----------------- FUENTES BASE -----------------
sources = {
    "Google News": "https://news.google.com/search?q={query}&hl=es-419&gl=AR&ceid=AR:es-419",
    "Clarin": "https://www.clarin.com/salud/",
    "Infobae": "https://www.infobae.com/salud/",
    "La Nación": "https://www.lanacion.com.ar/sociedad/salud/",
    "Cronista": "https://www.cronista.com/category/salud/",
    "Ministerio de Salud": "https://www.argentina.gob.ar/salud/noticias"
}

# ----------------- FUENTES INSTITUCIONALES (ejemplos) -----------------
institutional_sites = {
    "Philips AR": "https://www.philips.com.ar/healthcare",
    "Siemens Healthineers AR": "https://www.siemens-healthineers.com/ar",
    "Mindray LatAm": "https://www.mindray.com/en/",
    # Ten en cuenta que algunos de estos tienen estructura internacional; se usan como ejemplos.
}

# COMPR.AR (heurística de búsqueda pública) - usar comprar.gob.ar si disponible
comprar_search = "https://www.argentina.gob.ar/compras?search="  # heurística, puede variar por región

# ----------------- GOOGLE NEWS QUERY (ARGENTINA, ESPAÑOL) -----------------
gn_terms = [
    "electromedicina", "resonador", "resonancia", "tomógrafo", "tomografia", "rayos X",
    "angiografo", "ecógrafo", "mamógrafo", "hospital", "instaló", "adquirió", "donó",
    "nuevo equipo", "incorporó", "modernización"
]
gn_query = "+OR+".join([t.replace(" ", "+") for t in gn_terms])

# ----------------- SIDEBAR -----------------
st.sidebar.header("Opciones")
selected_source = st.sidebar.selectbox("Fuente principal", ["Todas"] + list(sources.keys()) + list(institutional_sites.keys()))
pages = st.sidebar.slider("Páginas Google News a recorrer (cada página ≈ 10 resultados)", 1, 6, 2)
include_traditional = st.sidebar.checkbox("Incluir medios tradicionales", True)
include_linkedin = st.sidebar.checkbox("Incluir LinkedIn (pasivo via Google Search)", True)
include_institutional = st.sidebar.checkbox("Incluir sitios institucionales (Philips, Siemens...)", True)
include_comprar = st.sidebar.checkbox("Incluir COMPR.AR (licitaciones)", True)
max_links_per_site = st.sidebar.slider("Máx. enlaces por fuente (para acelerar)", 10, 150, 60, step=10)
st.sidebar.markdown("---")
st.sidebar.info("LinkedIn (pasivo) busca posts públicos vía Google Search (site:linkedin.com/posts). No requiere login.")

# ----------------- UTIL / EXTRACCIONES -----------------
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

def safe_get_text_from_soup(soup):
    if not soup:
        return ""
    return " ".join(p.get_text(separator=" ", strip=True) for p in soup.find_all("p"))

def extract_hospital_name(texto):
    for h in hospital_indicators:
        m = re.search(rf'({h}\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9\-\s]+(?:de\s+[A-ZÁÉÍÓÚÑ][A-Za-z]+)?)', texto, re.IGNORECASE)
        if m:
            return " ".join(m.group(1).split())
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

# ----------------- PROCESS ARTICLE -----------------
def process_article_from_link(link, source_label, headers):
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
    try:
        resp = requests.get(link, headers=headers, timeout=12)
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return None

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    meta_title = soup.find("meta", {"property": "og:title"}) or soup.find("meta", {"name": "title"})
    if not title and meta_title and meta_title.get("content"):
        title = meta_title.get("content").strip()

    texto_completo = title + " " + safe_get_text_from_soup(soup)

    tipo_detectado = find_first_keyword(equipos_keywords, texto_completo)
    if not tipo_detectado:
        tipo_detectado = find_first_keyword(equipos_keywords, title)
    if tipo_detectado:
        result["Tipo"] = tipo_detectado

    fecha_pub = extract_fecha_from_soup(soup)
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
        result["Fecha instalación"] = f"*{datetime.today().strftime('%Y-%m-%d')}*"

    marca = find_first_keyword(marcas_keywords, texto_completo) or ""
    result["Marca"] = marca

    modelo = extract_modelo_heuristic(texto_completo, marca)
    result["Modelo"] = modelo

    ubic = extract_hospital_name(texto_completo)
    result["Ubicación (Hospital)"] = ubic

    result["Modalidad"] = detect_modalidad(texto_completo)
    result["Título"] = title
    result["Link"] = link

    result["Confianza"] = compute_confidence(result)
    return result

# ----------------- LINKEDIN (PASIVO via Google Search) -----------------
def linkedin_search_links(query, pages_to_check=1, headers=None):
    """
    Busca posts públicos en LinkedIn mediante Google Search con site:linkedin.com/posts
    Retorna lista de URLs (puede fallar por bloqueos; es pasivo).
    """
    results = []
    headers = headers or {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    base = "https://www.google.com/search?q="
    q = f"site:linkedin.com/posts/+({query})+Argentina+\"hospital\""
    q_enc = quote_plus(q)
    for p in range(pages_to_check):
        # google uses start param for pagination: start=0,10,20...
        start = p * 10
        url = f"{base}{q_enc}&hl=es&start={start}"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            # Google shows links in <a> within search results; try to find 'a' tags that contain linkedin
            for a in soup.find_all("a", href=True):
                href = a.get("href")
                if not href:
                    continue
                # google search wraps actual url in '/url?q=ACTUAL&sa=...'
                m = re.search(r'/url\?q=(https?://[^&]+)&', href)
                if m:
                    actual = m.group(1)
                else:
                    actual = href
                if "linkedin.com" in actual and actual.startswith("http"):
                    if actual not in results:
                        results.append(actual)
            time.sleep(0.3)
        except Exception:
            continue
    return results

# ----------------- RUN: botón -----------------
if st.button("🔍 Iniciar scraping (V13)"):
    st.info("Iniciando scraping (fuentes ampliadas). Esto puede tardar varios minutos según opciones.")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    collected = []
    seen_links = set()
    progress = st.progress(0)
    status_text = st.empty()
    total_expected = 0

    # preparar fuentes a ejecutar
    sources_to_run = []
    if selected_source == "Todas":
        sources_to_run.append(("Google News", sources["Google News"].format(query=gn_query)))
        if include_traditional:
            for k in ["Clarin", "Infobae", "La Nación", "Cronista", "Ministerio de Salud"]:
                sources_to_run.append((k, sources[k]))
        if include_institutional:
            for k, v in institutional_sites.items():
                sources_to_run.append((k, v))
        if include_comprar:
            sources_to_run.append(("COMPR.AR", comprar_search + quote_plus("equipamiento OR tomógrafo OR resonador")))
        if include_linkedin:
            # linkedin handled separately below
            pass
    else:
        # single selection: may be base source or institutional
        if selected_source in sources:
            sources_to_run.append((selected_source, sources[selected_source].format(query=gn_query)))
        elif selected_source in institutional_sites:
            sources_to_run.append((selected_source, institutional_sites[selected_source]))

    # estimación (muy aproximada)
    total_expected += pages * 10
    total_expected += len(sources_to_run) * min(max_links_per_site, 50)

    processed = 0
    errors = 0

    # 1) Google News (paginado)
    for label, url in sources_to_run:
        status_text.text(f"Scrapeando fuente: {label}")
        # special handling for Google News URLs which contain 'news.google'
        if "news.google" in url:
            for p in range(pages):
                start = p * 10
                gn_url = url + f"&start={start}"
                try:
                    resp = requests.get(gn_url, headers=headers, timeout=12)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    anchors = soup.find_all("a", href=True)
                    local_count = 0
                    for a in anchors:
                        href = a.get("href")
                        title_text = a.get_text().strip()
                        if not title_text or not href:
                            continue
                        # heurística para link real
                        if href.startswith("./") or href.startswith("/"):
                            link = normalize_link(url, href.lstrip("."))
                        elif href.startswith("/url?"):
                            # google redirect pattern: parse actual url
                            m = re.search(r'/url\?q=(https?://[^&]+)&', href)
                            if m:
                                link = m.group(1)
                            else:
                                link = href
                        else:
                            link = href
                        if not link or link in seen_links:
                            continue
                        seen_links.add(link)
                        processed += 1
                        art = process_article_from_link(link, "Google News", headers)
                        if art and art.get("Ubicación (Hospital)") and art.get("Tipo"):
                            collected.append(art)
                        local_count += 1
                        progress.progress(min(100, int((processed / max(1, total_expected)) * 100)))
                        if local_count >= 12:
                            break
                    time.sleep(0.3)
                except Exception:
                    errors += 1
                    continue
        elif label == "COMPR.AR":
            # heurística: buscar en la página pública (si disponible) y extraer links con 'compra' o 'licitacion'
            try:
                resp = requests.get(url, headers=headers, timeout=12)
                soup = BeautifulSoup(resp.text, "html.parser")
                anchors = soup.find_all("a", href=True)
                links = []
                for a in anchors:
                    href = a.get("href")
                    text = a.get_text().strip()
                    if not href or not text:
                        continue
                    full = normalize_link(url, href)
                    if full and full not in seen_links:
                        links.append(full)
                        seen_links.add(full)
                    if len(links) >= max_links_per_site:
                        break
                for link in links:
                    processed += 1
                    art = process_article_from_link(link, "COMPR.AR", headers)
                    if art and art.get("Ubicación (Hospital)") and art.get("Tipo"):
                        collected.append(art)
                    progress.progress(min(100, int((processed / max(1, total_expected)) * 100)))
                    time.sleep(0.2)
            except Exception:
                errors += 1
                continue
        else:
            # sitios tradicionales o institucionales
            try:
                resp = requests.get(url, headers=headers, timeout=12)
                soup = BeautifulSoup(resp.text, "html.parser")
                anchors = soup.find_all("a", href=True)
                links = []
                for a in anchors:
                    href = a.get("href")
                    text = a.get_text().strip()
                    if not href or not text:
                        continue
                    full = normalize_link(url, href)
                    if not full or full in seen_links:
                        continue
                    links.append(full)
                    seen_links.add(full)
                    if len(links) >= max_links_per_site:
                        break
                for link in links:
                    processed += 1
                    art = process_article_from_link(link, label, headers)
                    if art and art.get("Ubicación (Hospital)") and art.get("Tipo"):
                        collected.append(art)
                    progress.progress(min(100, int((processed / max(1, total_expected)) * 100)))
                    time.sleep(0.25)
            except Exception:
                errors += 1
                continue

    # 2) LinkedIn (pasivo) - buscar posts públicos vía Google Search site:linkedin.com/posts
    if include_linkedin:
        status_text.text("Buscando posts públicos en LinkedIn (pasivo)")
        # query para linkedin: usar términos similares a gn_terms
        linkedin_query = " OR ".join([q for q in gn_terms if q])
        # limitar páginas a same 'pages' param
        ln_links = linkedin_search_links(linkedin_query, pages_to_check=pages, headers=headers)
        for link in ln_links[:max_links_per_site]:
            if link in seen_links:
                continue
            seen_links.add(link)
            processed += 1
            art = process_article_from_link(link, "LinkedIn", headers)
            if art and art.get("Ubicación (Hospital)") and art.get("Tipo"):
                collected.append(art)
            progress.progress(min(100, int((processed / max(1, total_expected)) * 100)))
            time.sleep(0.3)

    status_text.text("Finalizado. Preparando resultados...")

    # construir DataFrame y filtrado final (calidad)
    if collected:
        df = pd.DataFrame(collected).drop_duplicates(subset=["Link"]).reset_index(drop=True)
        df["Confianza"] = df.apply(compute_confidence, axis=1)

        # mantener solo filas con hospital + tipo (criterio de calidad)
        df = df[(df["Ubicación (Hospital)"].astype(bool)) & (df["Tipo"].astype(bool))].copy()

        # ordenar por Confianza y Fecha (no cursiva)
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
        st.download_button("📥 Descargar CSV (V13)", csv, "resultados_scraper_v13.csv", "text/csv")
    else:
        st.warning("No se encontraron artículos que cumplan el criterio (hospital + equipo). Intentá aumentar páginas o incluir más fuentes.")
