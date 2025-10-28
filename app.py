import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd

st.set_page_config(page_title="Scraper Electromedicina Argentina V4", layout="wide")
st.title("🩺 Scraper de Noticias de Electromedicina - Argentina V4")
st.write("Busca noticias sobre equipos médicos (resonador, tomógrafo, rayos X, angiógrafo) y tecnología médica en varias fuentes.")

# --- Fuentes disponibles ---
sources = {
    "Google News": "https://news.google.com/search?q=electromedicina+OR+resonador+OR+resonancia+OR+tomógrafo+OR+tomografía+OR+rayos+X+OR+angiografo&hl=es-419&gl=AR&ceid=AR:es-419",
    "Ministerio de Salud": "https://www.argentina.gob.ar/salud/noticias",
    "Clarin Salud": "https://www.clarin.com/salud/",
    "Cronista Salud": "https://www.cronista.com/category/salud/",
    "Infobae Salud": "https://www.infobae.com/salud/",
    "La Nación Salud": "https://www.lanacion.com.ar/salud/"
}

st.sidebar.header("Seleccionar fuente (o dejar Todas)")
selected_source = st.sidebar.selectbox("Fuente", ["Todas"] + list(sources.keys()))

st.write(f"### Fuente seleccionada: {selected_source}")

if st.button("🔍 Iniciar scraping"):
    st.info("Buscando noticias...")

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
            if title and link:
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
                # Filtrar solo títulos que contengan al menos una palabra clave
                keywords = ["electromedicina", "resonador", "resonancia", "tomógrafo", "tomografía",
                            "rayos X", "angiografo", "rayos x", "angiografía"]
                if any(k.lower() in title.lower() for k in keywords):
                    articles.append({"Fuente": name, "Título": title, "Link": link})
        return articles

    # --- Scrapear todas o una fuente ---
    if selected_source == "Todas":
        for name, url in sources.items():
            all_articles.extend(scrap_url(name, url))
    else:
        all_articles = scrap_url(selected_source, sources[selected_source])

    if all_articles:
        df = pd.DataFrame(all_articles).drop_duplicates()
        st.success(f"Se encontraron {len(df)} noticias relevantes.")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Descargar CSV", csv, "noticias_equipos_medicos.csv", "text/csv")
    else:
        st.warning("No se encontraron resultados relevantes.")
