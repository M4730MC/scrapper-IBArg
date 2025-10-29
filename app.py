# app.py - Scraper Electromedicina V12 (Streamlit)
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re
import time

# ----------------- CONFIG -----------------
st.set_page_config(page_title="Scraper Electromedicina V12", layout="wide")
st.title("🩺 Scraper Electromedicina Argentina — V12 (Calidad sobre cantidad)")
st.write("Versión enfocada en resultados de alta calidad: solo artículos que mencionen un hospital y un equipo. "
         "Incluye columna de 'Confianza' que puntúa cuán completa es la evidencia (hospital, marca, modelo, fecha).")

# ----------------- FILTROS Y LISTAS (AMPLIADOS) -----------------
equipos_keywords = [
    "resonador", "resonancia magnética", "resonancia", "rmn",
    "tomógrafo", "tomografía", "tomografo", "tc", "scanner", "escáner",
    "rayos x", "radiografía", "radiografia", "radiología", "radiologia",
    "angiografo", "angiografía", "angiografia", "hemodinamia",
    "ecógrafo", "ecografía", "ecografo", "ecografia", "ultrasonido",
    "mamógrafo", "mamografía", "mamografo", "PET", "SPECT",
    # contextos
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

# ----------------- FUENTES -----------------
sources = {
    "Google News": "https://news.google.com/search?q={query}&hl=es-419&gl=AR&ceid=AR:es-419",
    "Clarin": "https://www.clarin.com/salud/",
    "Infobae": "https://www.infobae.com/salud/",
    "La Nación": "https://www.lanacion.com.ar/sociedad/salud/",
    "Cronista": "https://www.cronista.com/category/salud/",
    "Ministerio de Salud": "https://www.argentina.gob.ar/salud/noticias"
}

# Google News query (amplia, ya URL-encoded mínimamente)
gn_terms = [
    "electromedicina", "resonador", "resonancia", "tomógrafo", "tomografia", "rayos X",
    "angiografo", "ecógrafo", "mamógrafo", "hospital", "instaló", "adquirió", "donó",
    "nuevo equipo", "incorporó", "modernización"
]
gn_query = "+OR+".join([t.replace(" ", "+") for t in gn_terms])

# ----------------- SIDEBAR -----------------
st.sidebar.header("Opciones")
selected_source = st.sidebar.selectbox("Fuente principal", ["Todas"] + list(sources.keys()))
pages = st.sidebar.slider("Páginas Google News a recorrer (cada página ≈ 10 resultados)", 1, 10, 2)
include_traditional = st.sidebar.checkbox("Incluir fuentes tradicionales (Clarin, Infobae, La Nación, Cronista, Ministerio)", True)
max_links_per_site = st.sidebar.slider("Máx. enlaces por fuente (para acelerar)", 10, 200, 80, step=10)
st.sidebar.markdown("---")
st.sidebar.info("Esta versión prioriza calidad: mostrará solo artículos que contengan un hospital *y* mención de equipo.")

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
    # time tag
    time_tag = soup.find("time")
    if time_tag:
        dt = time_tag.get("datetime") or time_tag.get_text(strip=True)
        if dt:
            # buscar YYYY-MM-DD
            m = re.search(r"\d{4}-\d{2}-\d{2}", dt)
            if m:
                return m.group(0)
            # intentar parseo
            try:
                parsed = pd.to_datetime(dt, dayfirst=True, errors="coerce")
                if not pd.isna(parsed):
                    return parsed.strftime("%Y-%m-%d")
            except:
                return dt.strip()
    # meta tags comunes
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
    """Detecta nombre de hospital/clínica con regex que busque 'Hospital X', 'Clínica Y' etc."""
    for h in hospital_indicators:
        # busco mayúscula inicial para el nombre propio posterior
        m = re.search(rf'({h}\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9\-\s]+(?:de\s+[A-ZÁÉÍÓÚÑ][A-Za-z]+)?)', texto, re.IGNORECASE)
        if m:
            # limpiamos espacios extras
            return " ".join(m.group(1).split())
    return ""

def extract_modelo_heuristic(texto, marca):
    """Intento heurístico de modelo: marca + hasta 4 tokens, o patrones tipo 'X 1.5T'"""
    if not texto:
        return ""
    modelo = ""
    if marca:
        # buscar 'Marca' seguido de 1-4 tokens (no demasiado largos)
        m = re.search(rf'({re.escape(marca)})\s+([A-Za-z0-9\.\-\/]+(?:\s+[A-Za-z0-9\.\-\/]+){{0,3}})', texto, re.IGNORECASE)
        if m:
            modelo = (m.group(1) + " " + m.group(2)).strip()
    if not modelo:
        # buscar patrón con número y letras (ej. 'Ingenia 1.5T', 'Revolution EVO')
        m2 = re.search(r'([A-Z][A-Za-z0-9\-]{3,}\s+\d{1,2}\.\d[A-Za-z0-9]*)', texto)
        if m2:
            modelo = m2.group(0).strip()
    if not modelo:
        # fallback: palabra-capitalizada corta que siga a tipo
        m3 = re.search(r'(?:resonador|tomógrafo|tomografo|ecógrafo|mamógrafo)\s+([A-Z][A-Za-z0-9\-]{2,}(?:\s+[A-Za-z0-9\-]{1,3})?)', texto, re.IGNORECASE)
        if m3:
            modelo = m3.group(1).strip()
    return modelo

def compute_confidence(row):
    """Puntaje simple 0-100 según presencia de campos clave"""
    score = 0
    if row.get("Ubicación (Hospital)"):
        score += 35
    if row.get("Marca"):
        score += 25
    if row.get("Modelo"):
        score += 20
    # si fecha es clara (no cursiva) 20 pts
    fecha = row.get("Fecha instalación", "")
    if fecha and isinstance(fecha, str) and not (fecha.startswith("*") and fecha.endswith("*")):
        score += 20
    return min(100, score)

# ----------------- PROCESAR ARTÍCULO -----------------
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
        resp = requests.get(link, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return None

    # título
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    meta_title = soup.find("meta", {"property": "og:title"}) or soup.find("meta", {"name": "title"})
    if not title and meta_title and meta_title.get("content"):
        title = meta_title.get("content").strip()

    texto_completo = title + " " + safe_get_text_from_soup(soup)

    # detectar tipo por keywords (prioriza el texto completo)
    tipo_detectado = find_first_keyword(equipos_keywords, texto_completo)
    if not tipo_detectado:
        tipo_detectado = find_first_keyword(equipos_keywords, title)
    if tipo_detectado:
        result["Tipo"] = tipo_detectado

    # fecha publicación (intentar extraer)
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

    # marca (coincidencia parcial)
    marca = find_first_keyword(marcas_keywords, texto_completo)
    result["Marca"] = marca or ""

    # modelo heurístico
    modelo = extract_modelo_heuristic(texto_completo, marca)
    result["Modelo"] = modelo

    # ubicación (hospital/clínica)
    ubic = extract_hospital_name(texto_completo)
    result["Ubicación (Hospital)"] = ubic

    # modalidad
    result["Modalidad"] = detect_modalidad(texto_completo)

    result["Título"] = title
    result["Link"] = link

    # confianza
    result["Confianza"] = compute_confidence(result)

    return result

# ----------------- RUN: botón -----------------
if st.button("🔍 Iniciar scraping (V12)"):
    st.info("Iniciando scraping enfocado en calidad (solo artículos con hospital + equipo). Esto puede tardar varios minutos.")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    collected = []
    seen_links = set()
    progress = st.progress(0)
    status_text = st.empty()
    total_expected = 0

    # preparar lista de fuentes
    sources_to_run = []
    if selected_source == "Todas":
        sources_to_run.append(("Google News", sources["Google News"].format(query=gn_query)))
        if include_traditional:
            for k in ["Clarin", "Infobae", "La Nación", "Cronista", "Ministerio de Salud"]:
                sources_to_run.append((k, sources[k]))
    else:
        if selected_source == "Google News":
            sources_to_run.append(("Google News", sources["Google News"].format(query=gn_query)))
        else:
            sources_to_run.append((selected_source, sources[selected_source]))

    # estimación muy aproximada
    total_expected += pages * 10
    if include_traditional:
        total_expected += len([s for s in sources_to_run if s[0] != "Google News"]) * min(max_links_per_site, 50)

    processed = 0
    errors = 0

    # procesar fuentes
    for label, url in sources_to_run:
        status_text.text(f"Scrapeando fuente: {label}")
        if label == "Google News":
            for p in range(pages):
                start = p * 10
                gn_url = url + f"&start={start}"
                try:
                    resp = requests.get(gn_url, headers=headers, timeout=12)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    anchors = soup.find_all("a", href=True)
                    count = 0
                    for a in anchors:
                        href = a.get("href")
                        title_text = a.get_text().strip()
                        if not title_text:
                            continue
                        # heurística: preferir links que parezcan artículos
                        if "articles" in href or href.startswith("http"):
                            link = href
                            if href.startswith("./") or href.startswith("/"):
                                link = normalize_link(url, href.lstrip("."))
                            elif href.startswith("http"):
                                link = href
                            if link in seen_links:
                                continue
                            seen_links.add(link)
                            processed += 1
                            art = process_article_from_link(link, "Google News", headers)
                            if art:
                                # filtro calidad: requiere hospital y tipo/equipo detectado
                                if art.get("Ubicación (Hospital)") and art.get("Tipo"):
                                    collected.append(art)
                            count += 1
                            # actualizar progreso
                            progress.progress(min(100, int((processed / max(1, total_expected)) * 100)))
                            if count >= 15:
                                break
                    time.sleep(0.25)
                except Exception:
                    errors += 1
                    continue
        else:
            # tradicionales: recopilar enlaces desde la página principal
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
                    if not full_link or full_link in seen_links:
                        continue
                    links.append(full_link)
                    seen_links.add(full_link)
                    if len(links) >= max_links_per_site:
                        break
                # procesar los links encontrados
                for link in links:
                    processed += 1
                    art = process_article_from_link(link, label, headers)
                    if art:
                        if art.get("Ubicación (Hospital)") and art.get("Tipo"):
                            collected.append(art)
                    progress.progress(min(100, int((processed / max(1, total_expected)) * 100)))
                    time.sleep(0.2)
            except Exception:
                errors += 1
                continue

    status_text.text("Finalizado. Preparando resultados...")

    # construir DataFrame final con limpieza
    if collected:
        df = pd.DataFrame(collected)
        # eliminar duplicados por URL o título similar
        df = df.drop_duplicates(subset=["Link"]).reset_index(drop=True)

        # recalcular confianza en caso de cambios
        df["Confianza"] = df.apply(compute_confidence, axis=1)

        # ordenar por confianza y fecha (no-cursiva primero)
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
        st.download_button("📥 Descargar CSV (calidad)", csv, "resultados_scraper_v12.csv", "text/csv")
    else:
        st.warning("No se encontraron artículos que cumplan el criterio (hospital + equipo). Ajustá filtros o aumentá páginas.")
