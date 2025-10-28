import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd

st.set_page_config(page_title="Scraper de Electromedicina Argentina", layout="wide")
st.title("🩺 Scraper de Base Instalada de Electromedicina en Argentina")
st.write("Esta app busca noticias recientes sobre equipos médicos, hospitales y tecnología en salud en Argentina.")

default_sources = {
    "Google News - Electromedicina": "https://news.google.com/search?q=electromedicina+Argentina&hl=es-419&gl=AR&ceid=AR:es-419",
}

st.sidebar.header("Fuentes de scraping")
new_url = st.sidebar.text_input("Agregar nueva URL")

if "sources" not in st.session_state:
    st.session_state.sources = default_sources.copy()

if new_url:
    st.session_state.sources[f"Nueva fuente {len(st.session_state.sources)+1}"] = new_url

selected_source = st.sidebar.selectbox("Elegí una fuente", list(st.session_state.sources.keys()))
url = st.session_state.sources[selected_source]

st.write(f"### Fuente seleccionada: {selected_source}")
st.write(url)

if st.button("🔍 Iniciar scraping"):
    st.info("Buscando noticias...")

    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    articles = []
    for item in soup.find_all("a"):
        title = item.get_text().strip()
        link = item.get("href", "")
        if title and "articles" in link:
            link = "https://news.google.com" + link[1:]
            articles.append({"Título": title, "Link": link})

    if articles:
        df = pd.DataFrame(articles).drop_duplicates()
        st.success(f"Se encontraron {len(df)} noticias.")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Descargar CSV", csv, "noticias_electromedicina.csv", "text/csv")
    else:
        st.warning("No se encontraron resultados.")

