# --- IMPORTS NECESARIOS ---
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re

# --- CONFIGURACIÓN DE LA APP ---
st.set_page_config(page_title="Scraper Electromedicina Argentina", layout="wide")
st.title("🩺 Scraper Avanzado de Noticias de Electromedicina - Argentina")
st.write("Busca noticias sobre equipos médicos, hospitales y tecnología en salud en diversas fuentes argentinas.")

# --- LISTAS DE PALABRAS CLAVE ---
equipos_keywords = [
    "resonador", "tomógrafo", "rayos X", "angiografo", "ecógrafo",
    "mamógrafo", "electrocardiógrafo", "equipamiento médico", "equipo médico",
    "PET", "SPECT", "RMN", "CT", "DXR", "MR", "IGT", "ultrasonido", "monitores", "ventilador"
]

marcas_keywords = [
    "Philips", "Siemens", "GE", "Canon", "Mindray", "Hitachi", "Fujifilm", "Agfa",
    "Medtronic", "Dräger", "Samsung", "Neusoft", "Esaote"
]

hospital_keywords = [
    "hospital", "sanatorio", "clínica", "centro de salud", "instituto", "fundación", "hospital público"
]

# --- AGRUPACIÓN POR MODALIDAD ---
modalidad_dict = {
    "CT": ["tomógrafo", "TC", "escáner"],
    "DXR": ["rayos X", "radiografía", "radiología"],
    "MR": ["resonador", "RMN", "resonancia"],
    "IGT": ["angiografo", "angiografía", "intervencionista"],
    "US": ["ecógrafo", "ultrasonido"],
    "MG": ["mamógrafo", "mamografía"]
}

# --- FUENTES PREDEFINIDAS ---
sources = {
    "Google News": "https://news.google.com/search?q=site:clarin.com+OR+site:lanacion.com.ar+OR+site:infobae.com+equipos+médicos+OR+hospital+OR+resonador+OR+tomógrafo",
    "Clarin": "https://www.clarin.com/salud/",
    "Infobae": "https://www.infobae.com/salud/",
    "La Nación": "https://www.lanacion.com.ar/sociedad/salud/",
    "Ministerio de Salud": "https://www.argentina.gob.ar/salud/noticias"
}

# --- SIDEBAR ---
st.sidebar.header("Configuración")
selected_source = st.sidebar.selectbox("Seleccionar fuente", ["Todas"] + list(sources.keys()))
st.sidebar.write("Podés agregar nuevas fuentes en el código si querés ampliar la búsqueda.")

# --- BOTÓN PRINCIPAL ---
if st.button("🔍 Iniciar scraping"):
    st.info("Buscando noticias, esto puede tardar unos minutos...")

    all_articles = []
    headers = {"User-Agent": "Mozilla/5.0"}

    # --- SELECCIONAR FUENTES ---
    selected_sources = sources.values() if selected_source == "Todas" else [sources[selected_source]]

    for base_url in selected_sources:
        try:
            resp = requests.get(base_url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            links = [a.get("href") for a in soup.find_all("a", href=True)]

            for link in links:
                if not link.startswith("http"):
                    continue

                try:
                    resp2 = requests.get(link, headers=headers, timeout=10)
                    soup2 = BeautifulSoup(resp2.text, "html.parser")

                    title = soup2.title.get_text() if soup2.title else ""
                    texto_completo = " ".join(p.get_text() for p in soup2.find_all("p"))
                    fecha_tag = soup2.find("time")

                    # Fecha
                    fecha = (
                        datetime.strptime(fecha_tag.get("datetime"), "%Y-%m-%d")
                        if fecha_tag and fecha_tag.get("datetime")
                        else None
                    )

                    # Extracción de palabras clave
                    equipos = [k for k in equipos_keywords if re.search(k, texto_completo, re.IGNORECASE)]
                    marca = next((m for m in marcas_keywords if re.search(m, texto_completo, re.IGNORECASE)), "")
                    hospital = next((h for h in hospital_keywords if re.search(h, texto_completo, re.IGNORECASE)), "")

                    # Deducción de modalidad
                    modalidad = next(
                        (mod for mod, terms in modalidad_dict.items() if any(t in texto_completo for t in terms)), ""
                    )

                    # Fecha de instalación o de noticia
                    fecha_mostrar = (
                        f"*{fecha.strftime('%d/%m/%Y')}*" if not fecha else fecha.strftime("%d/%m/%Y")
                    )

                    all_articles.append({
                        "Título": title.strip(),
                        "Fuente": base_url.split("//")[1].split("/")[0],
                        "Fecha": fecha_mostrar,
                        "Modalidad": modalidad,
                        "Equipo(s)": ", ".join(equipos),
                        "Marca": marca,
                        "Ubicación (Hospital)": hospital,
                        "URL": link
                    })

                except Exception:
                    continue
        except Exception:
            continue

    # --- RESULTADOS ---
    if all_articles:
        df = pd.DataFrame(all_articles)
        st.success(f"Se encontraron {len(df)} artículos relevantes.")
        st.dataframe(df)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Descargar CSV", csv, "resultados_scraper.csv", "text/csv")
    else:
        st.warning("No se encontraron resultados con los filtros actuales.")
