import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd

st.set_page_config(page_title="Scraper de Electromedicina Argentina V2", layout="wide")
st.title("🩺 Scraper de Noticias de Electromedicina - Argentina V2")
st.write("Busca noticias sobre equipos médicos, hospitales y tecnología en salud en varias fuentes.")

# --- Fuentes disponibles ---
sources = {
    "Google News - Electromedicina": "https://news.google.com/search?q=electromedicina+Argentina&hl=es-419&gl=AR&ceid=AR:es-419",
    "Ministerio de Salud - Noticias": "https://www.argentina.gob.ar/salud/noticias",
    "Clarin - Salud": "https://www.clarin.com/salud/",
    "Cronista - Salud": "https://www.cronista.com/category/salud/"
}

# --- Sidebar ---
st.sidebar.header("Seleccionar fuente")
selected_source = st.sidebar.selectbox("Elegí una fuente", list(sources.keys()))
url = sources[selected_source]
st.write(f"### Fuente seleccionada: {selected_source}")
st.write(url)

# Botón para scrapear
if st.button("🔍 Iniciar scraping"):
    st.info("Buscando noticias...")

    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    articles = []

    # --- Google News ---
    if "Google News" in selected_source:
        for item in soup.find_all("a"):
            title = item.get_text().strip()
            link = item.get("href", "")
            if title and "articles" in link:
                link = "https://news.google.com" + link[1:]
                articles.append({"Título": title, "Link": link})

    # --- Ministerio de Salud ---
    elif "Ministerio" in selected_source:
        for item in soup.find_all("div", class_="field--title"):
            a_tag = item.find("a")
            if a_tag:
                title = a_tag.get_text().strip()
                link = "https://www.argentina.gob.ar" + a_tag.get("href", "")
                articles.append({"Título": title, "Link": link})

    # --- Clarin ---
    elif "Clarin" in selected_source:
        for item in soup.find_all("a", class_="headline"):
            title = item.get_text().strip()
            link = item.get("href", "")
            if link and not link.startswith("http"):
                link = "https://www.clarin.com" + link
            if title and link:
                articles.append({"Título": title, "Link": link})

    # --- Cronista ---
    elif "Cronista" in selected_source:
        for item in soup.find_all("h3"):
            a_tag = item.find("a")
            if a_tag:
                title = a_tag.get_text().strip()
                link = a_tag.get("href", "")
                if title and link:
                    articles.append({"Título": title, "Link": link})

    # --- Mostrar resultados ---
    if articles:
        df = pd.DataFrame(articles).drop_duplicates()
        st.success(f"Se encontraron {len(df)} noticias.")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Descargar CSV", csv, "noticias_electromedicina.csv", "text/csv")
    else:
        st.warning("No se encontraron resultados.")

