# --- IMPORTS ---
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re

# --- CONFIGURACIÓN DE LA APP ---
st.set_page_config(page_title="Scraper Electromedicina Argentina", layout="wide")
st.title("🩺 Scraper Avanzado de Noticias de Electromedicina - Argentina")
st.write("Busca noticias sobre equipos médicos, hospitales y tecnología en salud en varias fuentes oficiales y medios argentinos.")

# --- PALABRAS CLAVE ---
equipos_keywords = ["resonador", "resonancia", "tomógrafo", "tomografía", "rayos X", "angiografo", "angiografía"]
marcas_keywords = ["Philips", "Siemens", "GE", "Toshiba", "Canon", "Hitachi", "Fujifilm"]
hospital_keywords = ["Hospital", "Clínica", "Sanatorio", "Fundación", "Instituto", "Centro de Salud"]
modalidad_dict = {
    "resonador": "MR",
    "resonancia": "MR",
    "tomógrafo": "CT",
    "tomografía": "CT",
    "rayos X": "DXR",
    "angiografo": "IGT",
    "angiografía": "IGT"
}

# --- FUENTES ---
sources = {
    "Google News": "https://news.google.com/search?q=electromedicina+OR+resonador+OR+resonancia+OR+tomógrafo+OR+tomografía+OR+rayos+X+OR+angiografo&hl=es-419&gl=AR&ceid=AR:es-419",
    "Ministerio de Salud": "https://www.argentina.gob.ar/salud/noticias",
    "Clarin Salud": "https://www.clarin.com/salud/",
    "Cronista Salud": "https://www.cronista.com/category/salud/",
    "Infobae Salud": "https://www.infobae.com/salud/",
    "La Nación Salud": "https://www.lanacion.com.ar/salud/"
}

# --- SIDEBAR ---
st.sidebar.header("Seleccionar fuente (o Todas)")
selected_source = st.sidebar.selectbox("Fuente", ["Todas"] + list(sources.keys()))
st.write(f"### Fuente seleccionada: {selected_source}")

# --- FUNCIÓN DE SCRAPEO ---
def scrap_url(name, url):
    headers = {"User-Agent": "Mozilla/5.0"}
    articles = []

    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        st.warning(f"No se pudo acceder a {name}: {e}")
        return articles  # lista vacía

    for a in soup.find_all("a"):
        title = a.get_text().strip()
        link = a.get("href", "")
        if not title or not link:
            continue

        # Normalizar links relativos
        if link.startswith("/"):
            base = url.split("/")[0] + "//" + url.split("/")[2]
            link = base + link

        # Detectar tipo de equipo
        tipo = next((k for k in equipos_keywords if k.lower() in title.lower()), None)
        if not tipo:
            continue

        texto_completo = title
        soup2 = None

        # Intentar descargar texto completo de la noticia
        try:
            resp2 = requests.get(link, headers=headers, timeout=10)
            soup2 = BeautifulSoup(resp2.text, "html.parser")
            texto_completo += " " + " ".join([p.get_text() for p in soup2.find_all("p")])
        except:
            pass

        # Fecha
        fecha_tag = soup2.find("time") if soup2 else None
        if fecha_tag and fecha_tag.has_attr("datetime"):
            fecha = fecha_tag["datetime"][:10]
        elif fecha_tag:
            fecha = fecha_tag.get_text().strip()[:10]
        else:
            fecha = f"*{datetime.today().strftime('%Y-%m-%d')}*"

        # Marca
        marca = next((m for m in marcas_keywords if re.search(rf'\b{m}\b', texto_completo, re.IGNORECASE)), "")

        # Modelo (ej: “Philips Ingenia 1.5T”)
        modelo_match = re.search(
            rf"({'|'.join(marcas_keywords + equipos_keywords)})\s+([A-Za-z0-9\.\-\s]+)",
            texto_completo,
            re.IGNORECASE
        )
        modelo = modelo_match.group(0) if modelo_match else ""

        # Ubicación (Hospital, Clínica, etc.)
        ubicacion = ""
        for h in hospital_keywords:
            match = re.search(rf'({h} [A-Za-zÁÉÍÓÚÑáéíóúñ0-9\s]+)', texto_completo)
            if match:
                ubicacion = match.group(1)
                break

        modalidad = modalidad_dict.get(tipo.lower(), "")

        articles.append({
            "Tipo": tipo,
            "Modelo": modelo,
            "Modalidad": modalidad,
            "Fecha instalación": fecha,
            "Ubicación": ubicacion,
            "Marca": marca,
            "Fuente": name,
            "Título": title,
            "Link": link
        })
    return articles

# --- BOTÓN PRINCIPAL ---
if st.button("🔍 Iniciar scraping"):
    st.info("Buscando noticias, esto puede tardar unos minutos...")

    all_articles = []  # siempre inicializada

    try:
        if selected_source == "Todas":
            for name, url in sources.items():
                st.write(f"Scrapeando {name}...")
                all_articles.extend(scrap_url(name, url))
        else:
            all_articles = scrap_url(selected_source, sources[selected_source])
    except Exception as e:
        st.error(f"Ocurrió un error inesperado: {e}")
        all_articles = []

    # --- RESULTADOS ---
    if all_articles:
        df = pd.DataFrame(all_articles).drop_duplicates()

        def parse_fecha(x):
            return datetime.today() if '*' in x else pd.to_datetime(x)
        df['Fecha_ord'] = df['Fecha instalación'].apply(parse_fecha)
        df = df.sort_values(['Tipo', 'Fecha_ord'], ascending=[True, False]).drop(columns=['Fecha_ord'])

        st.success(f"Se encontraron {len(df)} noticias relevantes.")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Descargar CSV", csv, "noticias_equipos_medicos.csv", "text/csv")
    else:
        st.warning("No se encontraron resultados.")
