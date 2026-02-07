# --- MÓDULO: DIAGNÓSTICO NUTRICIONAL ---
elif menu == "Diagnóstico Nutricional":
    st.title("🍂 Diagnóstico por Sintomatología Visual")
    st.info("Observá las hojas de tu planta y seleccioná los síntomas. Los nutrientes se dividen en Móviles (afectan hojas viejas) e Inmóviles (afectan hojas nuevas).")

    col_diag1, col_diag2 = st.columns([1, 2])

    with col_diag1:
        st.subheader("🔍 Localización")
        zona = st.radio("¿Dónde empezaron los síntomas?", 
                        ["Hojas Bajas (Viejas)", "Hojas Superiores (Nuevas)", "Toda la Planta"])
        
        st.subheader("🎨 Color y Forma")
        sintoma = st.selectbox("¿Qué observás?", [
            "Amarilleamiento uniforme", 
            "Puntas quemadas/marrones", 
            "Manchas color óxido/bronce", 
            "Hojas verde muy oscuro y en garra",
            "Nervaduras verdes pero hoja amarilla",
            "Tallos púrpuras y crecimiento lento"
        ])

    with col_diag2:
        st.subheader("📋 Diagnóstico Probable")
        
        # Lógica de Diagnóstico
        if zona == "Hojas Bajas (Viejas)":
            if "Amarilleamiento" in sintoma:
                st.error("**Deficiencia de Nitrógeno (N):** La planta consume sus reservas para crecer. Común en vegetativo.")
                st.write("**Solución:** Aumentar dosis de fertilizante base o humus de lombriz.")
            elif "Puntas quemadas" in sintoma:
                st.warning("**Exceso de Nutrientes (Overfert):** Sales acumuladas. Lavar raíces.")
        
        elif zona == "Hojas Superiores (Nuevas)":
            if "Nervaduras verdes" in sintoma:
                st.error("**Deficiencia de Hierro (Fe):** Común por pH muy alto en La Carlota.")
                st.write("**Solución:** Regular el pH a 6.0 - 6.5.")
            elif "Puntas quemadas" in sintoma:
                st.warning("**Deficiencia de Calcio/Magnesio:** Ocurre con agua de lluvia o muy blanda.")

        elif "Toda la Planta" in zona:
            if "verde muy oscuro" in sintoma:
                st.error("**Exceso de Nitrógeno:** Peligroso en floración, atrae plagas y retrasa el engorde.")
        
        

    st.divider()
    
    # Tabla de Referencia Rápida
    st.subheader("💡 Tabla de Consulta de Nutrientes")