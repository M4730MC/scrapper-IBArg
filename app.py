if st.button("🔍 Iniciar scraping"):
    st.info("Buscando noticias, esto puede tardar un poco...")

    all_articles = []  # Inicializar SIEMPRE antes de todo

    def scrap_url(name, url):
        headers = {"User-Agent": "Mozilla/5.0"}
        articles = []
        try:
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            st.warning(f"No se pudo acceder a {name}: {e}")
            return articles  # devuelve lista vacía, no corta todo

        for a in soup.find_all("a"):
            title = a.get_text().strip()
            link = a.get("href", "")
            if not title or not link:
                continue

            # Normalizar links relativos
            if link.startswith("/"):
                base = url.split("/")[0] + "//" + url.split("/")[2]
                link = base + link

            tipo = next((k for k in equipos_keywords if k.lower() in title.lower()), None)
            if not tipo:
                continue

            texto_completo = title
            soup2 = None
            try:
                resp2 = requests.get(link, headers=headers, timeout=10)
                soup2 = BeautifulSoup(resp2.text, "html.parser")
                texto_completo += " " + " ".join([p.get_text() for p in soup2.find_all("p")])
            except:
                pass

            fecha_tag = soup2.find("time") if soup2 else None
            if fecha_tag and fecha_tag.has_attr("datetime"):
                fecha = fecha_tag["datetime"][:10]
            elif fecha_tag:
                fecha = fecha_tag.get_text().strip()[:10]
            else:
                fecha = f"*{datetime.today().strftime('%Y-%m-%d')}*"

            marca = next((m for m in marcas_keywords if re.search(rf'\b{m}\b', texto_completo, re.IGNORECASE)), "")
            modelo_match = re.search(
                rf"({'|'.join(marcas_keywords + equipos_keywords)})\s+([A-Za-z0-9\.\-\s]+)",
                texto_completo,
                re.IGNORECASE
            )
            modelo = modelo_match.group(0) if modelo_match else ""

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

    # Asegurar siempre inicialización
    try:
        if selected_source == "Todas":
            for name, url in sources.items():
                all_articles.extend(scrap_url(name, url))
        else:
            all_articles = scrap_url(selected_source, sources[selected_source])
    except Exception as e:
        st.error(f"Ocurrió un error inesperado: {e}")
        all_articles = []

    # Mostrar resultados
    if all_articles:
        df = pd.DataFrame(all_articles).drop_duplicates()
        st.success(f"Se encontraron {len(df)} noticias relevantes.")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Descargar CSV", csv, "noticias_equipos_medicos.csv", "text/csv")
    else:
        st.warning("No se encontraron resultados.")
