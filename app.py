import streamlit as st
import pandas as pd
import requests
import numpy as np
import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="AsesorPro La Carlota", layout="wide", page_icon="🌿")

# Ubicación Geográfica: La Carlota, Córdoba
LAT, LON = -33.42, -63.30

# --- LÓGICA DE CLIMA (Open-Meteo) ---
def fetch_data():
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,relative_humidity_2m,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=America%2FArgentina%2FCordoba&forecast_days=3"
    try:
        r = requests.get(url).json()
        return r['current'], r['daily']
    except: return None, None

def calcular_vpd(t, h):
    es = 0.61078 * np.exp((17.27 * t) / (t + 237.3))
    ea = es * (h / 100)
    return round(es - ea, 2)

# --- MENÚ LATERAL ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/628/628283.png", width=80)
st.sidebar.title("AsesorPro V2.0")
menu = st.sidebar.selectbox("Módulos", ["🏠 Inicio", "🌤️ Clima & VPD", "🧪 Nutrición", "✂️ Cosecha Criolla", "⚖️ Legal"])

# --- MÓDULOS ---
if menu == "🏠 Inicio":
    st.title("🌱 Portal de Cultivo La Carlota")
    st.write("Bienvenido a tu sistema de gestión agronómica. Este portal utiliza datos en tiempo real de tu ubicación para optimizar la salud de tus plantas.")
    st.info("💡 **Consejo:** Usá el menú lateral para navegar entre la calculadora de riego y el monitoreo climático.")

elif menu == "🌤️ Clima & VPD":
    st.header("Monitoreo en Tiempo Real")
    curr, daily = fetch_data()
    if curr:
        t, h, v = curr['temperature_2m'], curr['relative_humidity_2m'], curr['wind_speed_10m']
        vpd = calcular_vpd(t, h)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Temperatura", f"{t}°C")
        col2.metric("Humedad", f"{h}%")
        col3.metric("VPD", f"{vpd} kPa")
        col4.metric("Viento", f"{v} km/h")
        
        if v > 35: st.error(f"🚩 ALERTA VIENTO: {v} km/h. ¡Asegurá tus plantas!")
    
    
    
    st.divider()
    st.subheader("🔮 Pronóstico 3 Días")
    if daily:
        cols = st.columns(3)
        for i in range(3):
            with cols[i]:
                st.write(f"**{daily['time'][i]}**")
                st.write(f"🌡️ {daily['temperature_2m_min'][i]}°/{daily['temperature_2m_max'][i]}°")
                st.write(f"🌧️ Lluvia: {daily['precipitation_probability_max'][i]}%")

elif menu == "🧪 Nutrición":
    st.header("Calculadora de Mezclas")
    litros = st.number_input("Litros de agua", 1, 100, 5)
    fase = st.selectbox("Fase", ["Vegetativo", "Floración"])
    marca = st.radio("Marca", ["Namasté", "Top Crop", "Criolla (50% Dosis)"])
    
    # Lógica de dosis simplificada
    dosis = 2.0 if fase == "Vegetativo" else 4.0
    if marca == "Criolla (50% Dosis)": dosis *= 0.5
    
    st.success(f"Dosis recomendada: **{litros * dosis} ml** de fertilizante base.")

elif menu == "✂️ Cosecha Criolla":
    st.header("Estimación Genética")
    st.write("Ideal para plantas de origen incierto (semillas criollas).")
    
    hoja = st.radio("Forma de la hoja", ["Fina (Sativa/Paraguaya)", "Ancha (Índica/Cruza)"])
    inicio = st.date_input("Inicio de Floración")
    semanas = 13 if hoja == "Fina (Sativa/Paraguaya)" else 9
    
    
    
    fecha_c = inicio + datetime.timedelta(weeks=semanas)
    st.metric("Fecha Estimada de Corte", fecha_c.strftime("%d-%m-%Y"))
    st.warning("⚠️ Recordá: Las criollas sativas pueden tardar hasta fines de Mayo.")

elif menu == "⚖️ Legal":
    st.header("Documentación REPROCANN")
    st.markdown("""
    * **Límite:** 9 plantas en floración.
    * **Transporte:** 40g flores secas.
    * **Ubicación:** La Carlota, Córdoba.
    """)
    st.button("Generar PDF de Emergencia")