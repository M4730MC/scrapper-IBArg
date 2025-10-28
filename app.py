import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re

st.set_page_config(page_title="Scraper Electromedicina Argentina V8", layout="wide")
st.title("🩺 Scraper de Noticias de Electromedicina - Argentina V8")
st.write("Noticias sobre equipos médicos, priorizando las más recientes por tipo de equipo, con extracción automática de marca y ubicación.")

# Palabras clave de equipos
equipos_keywords = ["resonador", "resonancia", "tomógrafo", "tomografía", "rayos X", "angiografo", "angiografía"]

# Posibles marcas
marcas_keywords = ["Philips", "Siemens", "GE", "Toshiba", "Canon", "Hitachi", "Fujifilm"]

# Palabras clave de ubicación
ubicaciones_keywords = ["Hospital", "Clínica", "Sanatorio", "Buenos Aires", "Córdoba", "Rosario", "Mendoza", "La Plata"]

# Fuentes
sources = {
    "Google News": "https://news.google.com/search?q=electromedicina+OR+resonador+OR+resonancia+OR+tomógrafo+OR+tomografía+OR+rayos+X+OR+angiografo&hl=es-419&gl=AR&ceid=AR:es-419",
    "Ministerio de Salud": "https://www.argentina.gob.ar/salud/noticias",
    "Clarin Salud": "https://www.clarin.com/salud/",
    "Cronista Salud": "https://www.cronista.com/category/salud/",
    "Infobae Salud": "https://www.infobae.com/salud/",
    "La Nación Salud": "https://www.lanacion.com.ar/salud/"
}

st.sidebar.header("Seleccionar fuente (o Todas)")
selected_source = st.sidebar.selectbox("Fuente", ["Todas"] + list(sources.keys()))
st.write(f"### Fuente seleccionada: {selected_source}")

if st.button("🔍 Iniciar scraping"):
    st.info("Buscando noticias, esto puede tardar un poco...")

    all_articles = []

    def scrap_url(name, url):
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            response = requests.get(url, headers=headers, timeout=10)
        except:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        articles = []

        for a in soup.find_all("a"):
            title = a.get_text().strip()
            link = a.get("href", "")
            if not title or not link:
                continue

            # Normalizar links relativos
            if link.startswith("/"):
                if "google.com" in url:
                    link = "https://news.google.com" + link[1:]
                elif "argentina.gob.ar" in url:
                    link = "https://www.argentina.gob.ar" + link
                elif "clarin.com" in url:
                    link = "https://www.clarin.com" + link
                elif "cronista.com" in url:
                    link = "https://www.cronista.com" + link
                elif "infobae.com" in url:
                    link = "https://www.infobae.com" + link
                elif "lanacion.com.ar" in url:
                    link = "https://www.lanacion.com.ar" + link

            # Filtrar títulos relevantes
            tipo = next((k for k in equipos_keywords if k.lower() in title.lower()), None)
            if tipo:
                texto_completo = title

                # Descargar contenido completo de la noticia
                try:
                    resp2 = requests.get(link, headers=headers, timeout=10)
                    soup2 = BeautifulSoup(resp2.text, "html.parser")
                    texto_completo += " " + " ".join([p.get_text() for p in soup2.find_all("p")])
                except:
                    pass

                # Fecha
                fecha_tag = soup2.find("time") if 'soup2' in locals() else None
                fecha = None
                if fecha_tag and fecha_tag.has_attr("datetime"):
                    fecha = fecha_tag["datetime"][:10]
                elif fecha_tag:
                    fecha = fecha_tag.get_text().strip()[:10]
                if not fecha:
                    fecha = f"*{datetime.today().strftime('%Y-%m-%d')}*"

                # Marca
                marca = next((m for m in marcas_keywords if re.search(r'\b{}\b'.format(m), texto_completo, re.IGNORECASE)), "")

                # Ubicación
                ubicacion = next((u for u in ubicaciones_keywords if re.search(r'\b{}\b'.format(u), texto_completo, re.IGNORECASE)), "")

                articles.append({
                    "Tipo": tipo,
                    "Fecha instalación": fecha,
                    "Ubicación": ubicacion,
                    "Marca": marca,
                    "Fuente": name,
                    "Título": title,
                    "Link": link
                })
        return articles

    # Scrapear todas o una fuente
    if selected_source == "Todas":
        for name, url in sources.items():
            all_articles.extend(scrap_url(name, url))
    else:
        all_articles = scrap_url(selected_source, sources[selected_source])

    if all_articles:
        df = pd.DataFrame(all_articles).drop_duplicates()

        # Convertir fechas reales a datetime para ordenar (ignorar cursivas)
        def parse_fecha(x):
            return datetime.today() if '*' in x else pd.to_datetime(x)
        df['Fecha_ord'] = df['Fecha instalación'].apply(parse_fecha)

        # Ordenar por Tipo y Fecha descendente
        df = df.sort_values(['Tipo', 'Fecha_ord'], ascending=[True, False]).drop(columns=['Fecha_ord'])

        st.success(f"Se encontraron {len(df)} noticias relevantes.")

        # Resaltar las más recientes (primeras por Tipo)
        def highlight_recent(row):
            fecha = row['Fecha instalación']
            return ['background-color: #FFFACD' if '*' not in fecha else '' for _ in row]

        st.dataframe(df.style.apply(highlight_recent, axis=1), use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Descargar CSV", csv, "noticias_equipos_medicos_v8.csv", "text/csv")
    else:
        st.warning("No se encontraron resultados.")
