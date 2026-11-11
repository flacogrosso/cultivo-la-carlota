import streamlit as st
import pandas as pd
import requests
import numpy as np
import datetime
import json
import os
import base64
import xml.etree.ElementTree as ET
import re
import html
import mercadopago
import hashlib
import urllib.parse
import psycopg2
from psycopg2.extras import RealDictCursor
from streamlit_js_eval import get_geolocation, streamlit_js_eval
from personal_access import personal_access_gate, personal_account

# Esta rama es exclusivamente personal: no habilitar checkout ni acceso público.
PERSONAL_MODE = True
st.set_page_config(page_title="GLM App del Cultivador Argentino", layout="wide", page_icon="🌿")
personal_access_gate()

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_db_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    if not DATABASE_URL:
        print("[DB INIT] WARNING: DATABASE_URL not set. Database features will not work.")
        return
    try:
        conn = get_db_conn()
    except Exception as e:
        print(f"[DB INIT] Cannot connect to database: {e}")
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS suscriptores (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                plan VARCHAR(50) NOT NULL,
                payment_id VARCHAR(255),
                external_reference VARCHAR(500),
                fecha_registro TIMESTAMP DEFAULT NOW(),
                vencimiento TIMESTAMP NOT NULL,
                es_trial BOOLEAN DEFAULT FALSE
            );
            CREATE TABLE IF NOT EXISTS referidos (
                id SERIAL PRIMARY KEY,
                referrer_email VARCHAR(255) NOT NULL,
                codigo VARCHAR(100) UNIQUE NOT NULL,
                reward_claimed BOOLEAN DEFAULT FALSE
            );
            CREATE TABLE IF NOT EXISTS referidos_detalle (
                id SERIAL PRIMARY KEY,
                referido_id INTEGER REFERENCES referidos(id) ON DELETE CASCADE,
                referred_email VARCHAR(255) NOT NULL,
                fecha TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS codigos_referidos (
                id SERIAL PRIMARY KEY,
                codigo VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cultivos (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) DEFAULT '',
                nombre VARCHAR(255) NOT NULL,
                sistema VARCHAR(100) NOT NULL,
                categoria VARCHAR(100),
                maceta VARCHAR(50),
                inicio DATE NOT NULL
            );
        """)
        # Sin concesiones de acceso vitalicio codificadas en el repositorio.
        conn.commit()
        print("[DB INIT] Database initialized successfully.")
    except Exception as e:
        print(f"[DB INIT] Error: {e}")
        conn.rollback()
    finally:
        conn.close()

init_db()

TUTORIALES = {
    "Clima y Sugerencias": {
        "icono": "🌦️",
        "titulo": "Clima y Sugerencias",
        "desc": "Tu estación meteorológica personal para el cultivo.",
        "pasos": [
            "Activá la geolocalización para datos precisos de tu zona",
            "Consultá temperatura, humedad, viento y VPD en tiempo real",
            "Revisá el pronóstico de 3 días para planificar tareas",
            "Si tenés cultivos activos, verás consejos personalizados por planta"
        ]
    },
    "Asesoramiento Cultivo": {
        "icono": "📘",
        "titulo": "Asesoramiento de Cultivo",
        "desc": "Guías completas de sustrato, riego y ambiente para tu sistema.",
        "pasos": [
            "Elegí tu categoría y tipo de cultivo en la barra lateral",
            "Explorá las recomendaciones de sustrato, riego y ambiente",
            "Encontrá links directos a growshops argentinos verificados",
            "Los consejos se adaptan al sistema que selecciones"
        ]
    },
    "Calculadora Riego": {
        "icono": "💧",
        "titulo": "Calculadora de Riego",
        "desc": "Calculá el riego exacto y recibí recomendaciones por planta.",
        "pasos": [
            "Ingresá el volumen de tu maceta para calcular el riego ideal",
            "Ajustá frecuencia según el clima actual de tu zona",
            "Si tenés cultivos en seguimiento, verás riego personalizado por planta",
            "Incluye corrección de pH para agua de tu zona"
        ]
    },
    "Diagnóstico & Plagas": {
        "icono": "🛡️",
        "titulo": "Diagnóstico y Plagas",
        "desc": "Identificá problemas y encontrá remedios naturales.",
        "pasos": [
            "Seleccioná la zona afectada de la planta (hojas, tallo, raíz, etc.)",
            "Elegí el síntoma que observás para obtener el diagnóstico",
            "Recibí remedios caseros y naturales paso a paso",
            "Videos de YouTube complementarios para cada problema"
        ]
    },
    "Estimador de Cosecha": {
        "icono": "✂️",
        "titulo": "Estimador de Cosecha",
        "desc": "Estimá rendimiento y recibí guía completa de cosecha.",
        "pasos": [
            "Ingresá datos de tus plantas para estimar el rendimiento",
            "Si tenés cultivos activos, verás guía personalizada por planta",
            "6 pestañas: señales, tricomas, rendimiento, corte, secado y curado",
            "Alertas climáticas para proteger tu cosecha"
        ]
    },
    "Sugerencias Legales": {
        "icono": "⚖️",
        "titulo": "Sugerencias Legales",
        "desc": "Todo sobre REPROCANN y el marco legal en Argentina.",
        "pasos": [
            "Consultá las últimas noticias legales actualizadas automáticamente",
            "Seguí la guía paso a paso para registrarte en REPROCANN",
            "Conocé los requisitos, límites y tus derechos como cultivador",
            "Información oficial con links a fuentes gubernamentales"
        ]
    },
    "Seguimiento de Cultivo": {
        "icono": "🌱",
        "titulo": "Seguimiento de Cultivo",
        "desc": "Seguí tus plantas día a día con guías por etapa.",
        "pasos": [
            "Agregá un cultivo nuevo con nombre, sistema y fecha de inicio",
            "La app detecta automáticamente la etapa según los días",
            "Recibí instrucciones específicas para cada etapa de crecimiento",
            "Consejos diarios basados en el clima real de tu zona"
        ]
    }
}

def mostrar_tutorial(modulo_nombre):
    tut = TUTORIALES.get(modulo_nombre)
    if not tut:
        return
    
    visit_key = f"tutorial_visits_{modulo_nombre.replace(' ', '_').replace('&', 'y')}"
    dismiss_key = f"tutorial_dismissed_{modulo_nombre.replace(' ', '_').replace('&', 'y')}"
    
    if dismiss_key not in st.session_state:
        st.session_state[dismiss_key] = False
    if visit_key not in st.session_state:
        st.session_state[visit_key] = 0
    
    if f"tutorial_ls_checked_{modulo_nombre}" not in st.session_state:
        try:
            ls_key_visits = f"glm_tutorial_visits_{modulo_nombre.replace(' ', '_').replace('&', 'y')}"
            ls_key_dismiss = f"glm_tutorial_dismiss_{modulo_nombre.replace(' ', '_').replace('&', 'y')}"
            stored_visits = streamlit_js_eval(
                js_expressions=f"localStorage.getItem('{ls_key_visits}')",
                key=f"read_tut_visits_{modulo_nombre.replace(' ', '_')}", want_output=True
            )
            stored_dismiss = streamlit_js_eval(
                js_expressions=f"localStorage.getItem('{ls_key_dismiss}')",
                key=f"read_tut_dismiss_{modulo_nombre.replace(' ', '_')}", want_output=True
            )
            if stored_visits and str(stored_visits).isdigit():
                st.session_state[visit_key] = int(stored_visits)
            if stored_dismiss == "true":
                st.session_state[dismiss_key] = True
        except Exception:
            pass
        st.session_state[f"tutorial_ls_checked_{modulo_nombre}"] = True
    
    visits = st.session_state[visit_key]
    
    new_visits = visits + 1
    st.session_state[visit_key] = new_visits
    try:
        ls_key_visits = f"glm_tutorial_visits_{modulo_nombre.replace(' ', '_').replace('&', 'y')}"
        streamlit_js_eval(
            js_expressions=f"localStorage.setItem('{ls_key_visits}', '{new_visits}')",
            key=f"write_tut_visits_{modulo_nombre.replace(' ', '_')}"
        )
    except Exception:
        pass
    
    if st.session_state[dismiss_key]:
        return
    
    show_dismiss_option = new_visits >= 10
    
    pasos_html = "".join([f"<li>{p}</li>" for p in tut["pasos"]])
    
    st.markdown(f"""
    <div class="tutorial-card">
        <h4>{tut['icono']} {tut['titulo']} — Guía rápida</h4>
        <p>{tut['desc']}</p>
        <ul class="tutorial-steps">
            {pasos_html}
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    if show_dismiss_option:
        if st.button(f"✕ No mostrar más este tutorial", key=f"btn_dismiss_tut_{modulo_nombre.replace(' ', '_')}"):
            st.session_state[dismiss_key] = True
            try:
                ls_key_dismiss = f"glm_tutorial_dismiss_{modulo_nombre.replace(' ', '_').replace('&', 'y')}"
                streamlit_js_eval(
                    js_expressions=f"localStorage.setItem('{ls_key_dismiss}', 'true')",
                    key=f"write_tut_dismiss_{modulo_nombre.replace(' ', '_')}"
                )
            except Exception:
                pass
            st.rerun()

def guardar_cultivos(cultivos, user_email=""):
    email_key = user_email.strip().lower() if user_email else ""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM cultivos WHERE LOWER(email) = %s", (email_key,))
        for c in cultivos:
            inicio = c.get("inicio")
            if isinstance(inicio, datetime.datetime):
                inicio = inicio.date()
            elif isinstance(inicio, str):
                inicio = datetime.date.fromisoformat(inicio)
            cur.execute(
                "INSERT INTO cultivos (email, nombre, sistema, categoria, maceta, inicio) VALUES (%s, %s, %s, %s, %s, %s)",
                (email_key, c.get("nombre", ""), c.get("sistema", ""), c.get("categoria") or str(c.get("sistema", "")).split(" ")[0], str(c.get("maceta_litros") or c.get("maceta") or ""), inicio)
            )
        conn.commit()
    except Exception as e:
        print(f"[DB] Error guardando cultivos: {e}")
        conn.rollback()
    finally:
        conn.close()

def cargar_cultivos(user_email=""):
    email_key = user_email.strip().lower() if user_email else ""
    conn = get_db_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT nombre, sistema, categoria, maceta, inicio FROM cultivos WHERE LOWER(email) = %s", (email_key,))
        rows = cur.fetchall()
        cultivos = []
        for r in rows:
            cultivos.append({
                "nombre": r["nombre"],
                "sistema": r["sistema"],
                "categoria": r.get("categoria", ""),
                "maceta": r.get("maceta", ""),
                "maceta_litros": int(r["maceta"]) if str(r.get("maceta") or "").isdigit() else None,
                "inicio": r["inicio"]
            })
        return cultivos
    except Exception as e:
        print(f"[DB] Error cargando cultivos: {e}")
        return []
    finally:
        conn.close()

def guardar_suscriptores(suscriptores):
    pass

def cargar_suscriptores():
    conn = get_db_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT email, plan, payment_id, external_reference, fecha_registro, vencimiento, es_trial FROM suscriptores")
        rows = cur.fetchall()
        result = []
        for r in rows:
            result.append({
                "email": r["email"],
                "plan": r["plan"],
                "payment_id": r.get("payment_id", ""),
                "external_reference": r.get("external_reference", ""),
                "fecha_registro": r["fecha_registro"].isoformat() if r.get("fecha_registro") else "",
                "vencimiento": r["vencimiento"].isoformat() if r.get("vencimiento") else "",
                "es_trial": r.get("es_trial", False)
            })
        return result
    except Exception as e:
        print(f"[DB] Error cargando suscriptores: {e}")
        return []
    finally:
        conn.close()

def verificar_suscripcion(email):
    email_lower = email.strip().lower()
    conn = get_db_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT plan, vencimiento, es_trial FROM suscriptores WHERE LOWER(email) = %s AND vencimiento > NOW() ORDER BY vencimiento DESC LIMIT 1", (email_lower,))
        row = cur.fetchone()
        if row:
            venc = row["vencimiento"]
            dias_restantes = (venc - datetime.datetime.now()).days
            return {"activa": True, "plan": row["plan"], "vencimiento": venc.strftime("%d/%m/%Y"), "dias_restantes": dias_restantes, "es_trial": row.get("es_trial", False)}
        return {"activa": False, "plan": "", "vencimiento": "", "dias_restantes": 0, "es_trial": False}
    except Exception as e:
        print(f"[DB] Error verificando suscripcion: {e}")
        return {"activa": False, "plan": "", "vencimiento": "", "dias_restantes": 0, "es_trial": False}
    finally:
        conn.close()

def activar_trial(email):
    email_lower = email.strip().lower()
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM suscriptores WHERE LOWER(email) = %s", (email_lower,))
        if cur.fetchone():
            return False
        ahora = datetime.datetime.now()
        vencimiento = ahora + datetime.timedelta(days=7)
        cur.execute(
            "INSERT INTO suscriptores (email, plan, payment_id, external_reference, fecha_registro, vencimiento, es_trial) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (email_lower, "trial", "trial_free", "trial", ahora, vencimiento, True)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB] Error activando trial: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def registrar_suscripcion(email, plan, payment_id, external_reference):
    email_lower = email.strip().lower()
    ahora = datetime.datetime.now()
    if plan == "semanal":
        vencimiento = ahora + datetime.timedelta(days=7)
    elif plan == "mensual":
        vencimiento = ahora + datetime.timedelta(days=30)
    else:
        vencimiento = ahora + datetime.timedelta(days=365)
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM suscriptores WHERE LOWER(email) = %s", (email_lower,))
        cur.execute(
            "INSERT INTO suscriptores (email, plan, payment_id, external_reference, fecha_registro, vencimiento, es_trial) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (email_lower, plan, str(payment_id), external_reference, ahora, vencimiento, False)
        )
        conn.commit()
    except Exception as e:
        print(f"[DB] Error registrando suscripcion: {e}")
        conn.rollback()
    finally:
        conn.close()

def registrar_referido(referidor_email, nuevo_email, plan):
    ref_key = referidor_email.strip().lower()
    nuevo_key = nuevo_email.strip().lower()
    if ref_key == nuevo_key:
        return False
    conn = get_db_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id FROM referidos WHERE LOWER(referrer_email) = %s", (ref_key,))
        row = cur.fetchone()
        if not row:
            cur.execute("INSERT INTO referidos (referrer_email, codigo, reward_claimed) VALUES (%s, %s, %s) RETURNING id",
                        (ref_key, hashlib.md5(ref_key.encode()).hexdigest()[:8], False))
            ref_id = cur.fetchone()["id"]
        else:
            ref_id = row["id"]
        cur.execute("SELECT id FROM referidos_detalle WHERE referido_id = %s AND LOWER(referred_email) = %s", (ref_id, nuevo_key))
        if cur.fetchone():
            conn.commit()
            return False
        cur.execute("INSERT INTO referidos_detalle (referido_id, referred_email) VALUES (%s, %s)", (ref_id, nuevo_key))
        cur.execute("SELECT COUNT(*) as cnt FROM referidos_detalle rd JOIN referidos r ON rd.referido_id = r.id WHERE r.id = %s", (ref_id,))
        count_row = cur.fetchone()
        total = count_row["cnt"] if count_row else 0
        cur.execute("SELECT reward_claimed FROM referidos WHERE id = %s", (ref_id,))
        reward_row = cur.fetchone()
        if total >= 5 and not reward_row.get("reward_claimed", False):
            cur.execute("UPDATE referidos SET reward_claimed = TRUE WHERE id = %s", (ref_id,))
            conn.commit()
            registrar_suscripcion(ref_key, "anual", "referido_reward", "referido_5_anuales")
            return True
        conn.commit()
        return False
    except Exception as e:
        print(f"[DB] Error registrando referido: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def contar_referidos(email):
    ref_key = email.strip().lower()
    conn = get_db_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, reward_claimed FROM referidos WHERE LOWER(referrer_email) = %s", (ref_key,))
        row = cur.fetchone()
        if not row:
            return 0, False
        cur.execute("SELECT COUNT(*) as cnt FROM referidos_detalle WHERE referido_id = %s", (row["id"],))
        count_row = cur.fetchone()
        return (count_row["cnt"] if count_row else 0), row.get("reward_claimed", False)
    except Exception as e:
        print(f"[DB] Error contando referidos: {e}")
        return 0, False
    finally:
        conn.close()

def generar_codigo_referido(email):
    code = hashlib.md5(email.strip().lower().encode()).hexdigest()[:8]
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO codigos_referidos (codigo, email) VALUES (%s, %s) ON CONFLICT (codigo) DO NOTHING", (code, email.strip().lower()))
        conn.commit()
    except Exception as e:
        print(f"[DB] Error generando codigo referido: {e}")
        conn.rollback()
    finally:
        conn.close()
    return code

def resolver_codigo_referido(code):
    conn = get_db_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT email FROM codigos_referidos WHERE codigo = %s", (code,))
        row = cur.fetchone()
        if row:
            return row["email"]
        cur.execute("SELECT email FROM suscriptores")
        for r in cur.fetchall():
            e = r["email"]
            if hashlib.md5(e.strip().lower().encode()).hexdigest()[:8] == code:
                return e.strip().lower()
        return None
    except Exception as e:
        print(f"[DB] Error resolviendo codigo referido: {e}")
        return None
    finally:
        conn.close()

def _generar_hmac(data_str):
    secret = os.environ.get("MERCADOPAGO_ACCESS_TOKEN", "glm_secret")[:32]
    return hashlib.sha256(f"{secret}:{data_str}".encode()).hexdigest()[:16]

def _codificar_email(email):
    return base64.urlsafe_b64encode(email.strip().lower().encode()).decode()

def _decodificar_email(encoded):
    try:
        return base64.urlsafe_b64decode(encoded.encode()).decode()
    except Exception:
        return encoded

def eliminar_datos_usuario(email):
    email_lower = email.strip().lower()
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM suscriptores WHERE LOWER(email) = %s", (email_lower,))
        cur.execute("SELECT id FROM referidos WHERE LOWER(referrer_email) = %s", (email_lower,))
        ref_rows = cur.fetchall()
        for r in ref_rows:
            cur.execute("DELETE FROM referidos_detalle WHERE referido_id = %s", (r[0],))
        cur.execute("DELETE FROM referidos WHERE LOWER(referrer_email) = %s", (email_lower,))
        cur.execute("DELETE FROM referidos_detalle WHERE LOWER(referred_email) = %s", (email_lower,))
        cur.execute("DELETE FROM codigos_referidos WHERE LOWER(email) = %s", (email_lower,))
        cur.execute("DELETE FROM cultivos WHERE LOWER(email) = %s", (email_lower,))
        conn.commit()
    except Exception as e:
        print(f"[DB] Error eliminando datos: {e}")
        conn.rollback()
    finally:
        conn.close()
    return True

def crear_preferencia_mp(email, plan, ref_code=""):
    try:
        sdk = mercadopago.SDK(os.environ.get("MERCADOPAGO_ACCESS_TOKEN", ""))
        timestamp = int(datetime.datetime.now().timestamp())
        domain = os.environ.get("REPLIT_DEV_DOMAIN", os.environ.get("REPLIT_DOMAINS", ""))
        back_url = f"https://{domain}"
        if plan == "semanal":
            titulo = "GLM App - Suscripción Semanal"
            precio = 2000.00
        elif plan == "mensual":
            titulo = "GLM App - Suscripción Mensual"
            precio = 5000.00
        else:
            titulo = "GLM App - Suscripción Anual"
            precio = 48000.00
        email_encoded = _codificar_email(email)
        ref_data = f"{email_encoded}|{plan}|{timestamp}"
        sig = _generar_hmac(ref_data)
        external_ref = f"{ref_data}|{sig}"
        if ref_code:
            external_ref = f"{external_ref}|{ref_code}"
        preference_data = {
            "items": [
                {
                    "title": titulo,
                    "quantity": 1,
                    "unit_price": precio,
                    "currency_id": "ARS"
                }
            ],
            "back_urls": {
                "success": back_url,
                "failure": back_url,
                "pending": back_url
            },
            "auto_return": "approved",
            "external_reference": external_ref,
            "payer": {
                "email": email
            }
        }
        result = sdk.preference().create(preference_data)
        response = result.get("response", {})
        return response.get("init_point", "")
    except Exception as e:
        return ""

def verificar_pago_mp(payment_id):
    try:
        sdk = mercadopago.SDK(os.environ.get("MERCADOPAGO_ACCESS_TOKEN", ""))
        result = sdk.payment().get(int(payment_id))
        response = result.get("response", {})
        return response.get("status") == "approved"
    except Exception:
        return False

def mostrar_paywall(modulo_nombre):
    st.markdown(f"""
    <div style="background: linear-gradient(145deg, rgba(0, 155, 58, 0.08) 0%, rgba(30, 30, 30, 0.95) 100%);
                border: 2px solid rgba(254, 209, 0, 0.4); border-radius: 20px; padding: 45px 35px; text-align: center;
                margin: 20px 0; box-shadow: 0 12px 40px rgba(0,0,0,0.4);">
        <div style="font-size: 3em; margin-bottom: 10px;">🔒</div>
        <h2 style="color: #FED100 !important; font-family: 'Righteous', cursive; margin-bottom: 8px; font-size: 1.8em;">
            Módulo Premium
        </h2>
        <p style="color: #E0E0E0; font-size: 1.15em; margin-bottom: 15px;">
            <strong>{modulo_nombre}</strong> es exclusivo para suscriptores.
        </p>
        <div style="display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin-top: 15px;">
            <div style="color: #00C44F; font-size: 0.95em;">✅ 6 módulos premium</div>
            <div style="color: #00C44F; font-size: 0.95em;">✅ Riego personalizado</div>
            <div style="color: #00C44F; font-size: 0.95em;">✅ Diagnóstico completo</div>
        </div>
        <div style="display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin-top: 8px;">
            <div style="color: #00C44F; font-size: 0.95em;">✅ Guía de cosecha</div>
            <div style="color: #00C44F; font-size: 0.95em;">✅ Info legal REPROCANN</div>
            <div style="color: #00C44F; font-size: 0.95em;">✅ Seguimiento cultivos</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.get("pago_exitoso", False):
        st.markdown("""
        <div style="background: linear-gradient(135deg, rgba(0,155,58,0.2), rgba(0,155,58,0.05));
                    border: 1px solid #00C44F; border-radius: 12px; padding: 20px; text-align: center; margin: 15px 0;">
            <div style="font-size: 2em; margin-bottom: 5px;">🎉</div>
            <p style="color: #00C44F; font-size: 1.2em; font-weight: 700; margin: 0;">¡Pago procesado exitosamente!</p>
            <p style="color: #CCC; margin-top: 5px;">Ingresá tu email en la barra lateral para activar tu acceso completo.</p>
        </div>
        """, unsafe_allow_html=True)
        st.session_state["pago_exitoso"] = False

    paywall_email = st.session_state.get("suscriptor_email", "")
    if not paywall_email:
        paywall_email = st.text_input("📧 Ingresá tu email para ver opciones:", placeholder="ejemplo@email.com", key=f"paywall_email_{modulo_nombre}")
        if paywall_email:
            st.session_state["suscriptor_email"] = paywall_email

    if paywall_email:
        st.markdown("")
        trial_disponible = True
        suscriptores = cargar_suscriptores()
        for s in suscriptores:
            if s.get("email", "").lower() == paywall_email.strip().lower():
                trial_disponible = False
                break

        if trial_disponible:
            st.markdown("""
            <div style="background: linear-gradient(135deg, rgba(0,155,58,0.15), rgba(0,100,38,0.08));
                        border: 2px dashed #00C44F; border-radius: 14px; padding: 22px; text-align: center; margin-bottom: 20px;">
                <h3 style="color: #00C44F !important; margin-bottom: 5px;">🎁 Prueba Gratis — 7 Días</h3>
                <p style="color: #CCC; font-size: 0.95em; margin-bottom: 0;">Probá todos los módulos premium sin compromiso. Sin tarjeta de crédito.</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🚀 Activar Prueba Gratis", key=f"btn_trial_{modulo_nombre}"):
                if activar_trial(paywall_email):
                    st.session_state["suscripcion_activa"] = True
                    st.success("✅ ¡Prueba gratis activada! Ya tenés acceso a todos los módulos por 7 días.")
                    st.rerun()
                else:
                    st.warning("Ya usaste tu prueba gratis. Elegí un plan para continuar.")
            st.markdown("")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("""
            <div style="background: linear-gradient(145deg, rgba(80,80,80,0.15), rgba(20,20,20,0.9));
                        border: 1px solid rgba(255,255,255,0.15); border-radius: 14px; padding: 24px; text-align: center;
                        min-height: 220px; position: relative;">
                <h3 style="color: #E0E0E0 !important; font-size: 1.1em;">📅 Semanal</h3>
                <p style="color: #FED100; font-size: 2.2em; font-family: 'Righteous', cursive; margin: 12px 0 4px;">$2.000</p>
                <p style="color: #AAA; font-size: 0.85em;">por 7 días</p>
                <p style="color: #888; font-size: 0.8em; margin-top: 10px;">Ideal para probar</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("💳 Semanal", key=f"btn_semanal_{modulo_nombre}"):
                with st.spinner("Generando link de pago..."):
                    url = crear_preferencia_mp(paywall_email, "semanal", st.session_state.get("codigo_referido", ""))
                    if url:
                        st.markdown(f'<a href="{url}" target="_blank" style="display:inline-block;background:linear-gradient(135deg,#666,#444);color:white!important;padding:12px 24px;border-radius:10px;font-weight:700;font-size:1em;text-decoration:none!important;margin-top:8px;width:100%;text-align:center;box-sizing:border-box;">Pagar con MP →</a>', unsafe_allow_html=True)
                    else:
                        st.error("Error al generar el link.")
        with col2:
            st.markdown("""
            <div style="background: linear-gradient(145deg, rgba(0, 155, 58, 0.18), rgba(20,20,20,0.9));
                        border: 2px solid #009B3A; border-radius: 14px; padding: 24px; text-align: center;
                        min-height: 220px; position: relative; box-shadow: 0 0 20px rgba(0,155,58,0.15);">
                <div style="position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
                            background: linear-gradient(135deg, #009B3A, #00C44F); color: white;
                            padding: 3px 14px; border-radius: 20px; font-size: 0.75em; font-weight: 700;
                            letter-spacing: 0.5px;">MÁS POPULAR</div>
                <h3 style="color: #00C44F !important; font-size: 1.1em; margin-top: 8px;">📅 Mensual</h3>
                <p style="color: #FED100; font-size: 2.2em; font-family: 'Righteous', cursive; margin: 12px 0 4px;">$5.000</p>
                <p style="color: #AAA; font-size: 0.85em;">por mes</p>
                <p style="color: #00C44F; font-size: 0.8em; margin-top: 10px; font-weight: 600;">Mejor relación precio-valor</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("💳 Mensual", key=f"btn_mensual_{modulo_nombre}"):
                with st.spinner("Generando link de pago..."):
                    url = crear_preferencia_mp(paywall_email, "mensual", st.session_state.get("codigo_referido", ""))
                    if url:
                        st.markdown(f'<a href="{url}" target="_blank" style="display:inline-block;background:linear-gradient(135deg,#009B3A,#007A2E);color:white!important;padding:12px 24px;border-radius:10px;font-weight:700;font-size:1em;text-decoration:none!important;margin-top:8px;width:100%;text-align:center;box-sizing:border-box;">Pagar con MP →</a>', unsafe_allow_html=True)
                    else:
                        st.error("Error al generar el link.")
        with col3:
            st.markdown("""
            <div style="background: linear-gradient(145deg, rgba(254, 209, 0, 0.1), rgba(20,20,20,0.9));
                        border: 1px solid #FED100; border-radius: 14px; padding: 24px; text-align: center;
                        min-height: 220px; position: relative;">
                <div style="position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
                            background: linear-gradient(135deg, #FED100, #C8A600); color: #1A1A1A;
                            padding: 3px 14px; border-radius: 20px; font-size: 0.75em; font-weight: 700;
                            letter-spacing: 0.5px;">20% OFF</div>
                <h3 style="color: #FED100 !important; font-size: 1.1em; margin-top: 8px;">🌟 Anual</h3>
                <p style="color: #FED100; font-size: 2.2em; font-family: 'Righteous', cursive; margin: 12px 0 4px;">$48.000</p>
                <p style="color: #AAA; font-size: 0.85em;">por año</p>
                <p style="color: #FED100; font-size: 0.8em; margin-top: 10px; font-weight: 600;">Ahorrás $12.000 al año</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("💳 Anual", key=f"btn_anual_{modulo_nombre}"):
                with st.spinner("Generando link de pago..."):
                    url = crear_preferencia_mp(paywall_email, "anual", st.session_state.get("codigo_referido", ""))
                    if url:
                        st.markdown(f'<a href="{url}" target="_blank" style="display:inline-block;background:linear-gradient(135deg,#FED100,#C8A600);color:#1A1A1A!important;padding:12px 24px;border-radius:10px;font-weight:700;font-size:1em;text-decoration:none!important;margin-top:8px;width:100%;text-align:center;box-sizing:border-box;">Pagar con MP →</a>', unsafe_allow_html=True)
                    else:
                        st.error("Error al generar el link.")

        st.markdown("""
        <div style="text-align: center; margin-top: 20px; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 10px;">
            <p style="color: #888; font-size: 0.85em; margin: 0;">
                🔒 Pago seguro con <strong>Mercado Pago</strong> · Cancelá cuando quieras · Sin permanencia
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("👆 Ingresá tu email arriba o en la barra lateral para ver las opciones de suscripción.")

    st.markdown("---")
    st.markdown("**🌦️ El módulo Clima y Sugerencias es gratuito.** Seleccionalo en el menú lateral para usarlo sin suscripción.")

@st.cache_data(ttl=3600*6)
def obtener_novedades_cannabis():
    queries = [
        "cannabis+argentina+ley+REPROCANN",
        "cannabis+medicinal+argentina+legislación",
        "cannabis+argentina+regulación+2025+2026"
    ]
    noticias = []
    seen_titles = set()
    for q in queries:
        try:
            url = f"https://news.google.com/rss/search?q={q}&hl=es-419&gl=AR&ceid=AR:es-419"
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item"):
                    title_el = item.find("title")
                    link_el = item.find("link")
                    pubdate_el = item.find("pubDate")
                    source_el = item.find("source")
                    if title_el is not None and link_el is not None:
                        titulo = html.unescape(title_el.text or "")
                        titulo_clean = re.sub(r'\s*-\s*[^-]+$', '', titulo).strip()
                        if titulo_clean in seen_titles:
                            continue
                        seen_titles.add(titulo_clean)
                        fuente = source_el.text if source_el is not None else ""
                        fecha_str = pubdate_el.text if pubdate_el is not None else ""
                        fecha_display = ""
                        if fecha_str:
                            try:
                                from email.utils import parsedate_to_datetime
                                fecha_dt = parsedate_to_datetime(fecha_str)
                                fecha_display = fecha_dt.strftime("%d/%m/%Y")
                            except Exception:
                                fecha_display = fecha_str[:16]
                        noticias.append({
                            "titulo": titulo,
                            "link": link_el.text or "",
                            "fecha": fecha_display,
                            "fuente": fuente
                        })
        except Exception:
            continue
    noticias_unicas = []
    seen_final = set()
    for n in noticias:
        key = n["titulo"][:60]
        if key not in seen_final:
            seen_final.add(key)
            noticias_unicas.append(n)
    noticias_unicas.sort(key=lambda x: x["fecha"], reverse=True)
    return noticias_unicas[:20]

# --- CONFIGURACIÓN DE PÁGINA ---

query_params = st.query_params
if "ref" in query_params:
    st.session_state["codigo_referido"] = query_params.get("ref", "")
if not PERSONAL_MODE and "payment_id" in query_params and "status" in query_params:
    mp_payment_id = query_params.get("payment_id", "")
    mp_status = query_params.get("status", "")
    mp_external_ref = query_params.get("external_reference", "")
    if mp_status == "approved" and mp_external_ref and mp_payment_id:
        parts = mp_external_ref.split("|")
        if len(parts) >= 4:
            email_encoded = parts[0]
            plan_ref = parts[1]
            timestamp_ref = parts[2]
            sig_ref = parts[3]
            ref_code = parts[4] if len(parts) >= 5 else ""
            ref_data = f"{email_encoded}|{plan_ref}|{timestamp_ref}"
            expected_sig = _generar_hmac(ref_data)
            email_ref = _decodificar_email(email_encoded)
            if sig_ref == expected_sig and verificar_pago_mp(mp_payment_id):
                registrar_suscripcion(email_ref, plan_ref, mp_payment_id, f"mp_{plan_ref}_{timestamp_ref}")
                st.session_state["suscriptor_email"] = email_ref
                st.session_state["pago_exitoso"] = True
                if ref_code:
                    referidor_email = resolver_codigo_referido(ref_code)
                    if referidor_email:
                        registrar_referido(referidor_email, email_ref, plan_ref)
    st.query_params.clear()

BANNER_PATHS = {
    "clima": "static/images/banner_clima.png",
    "asesoramiento": "static/images/banner_asesoramiento.png",
    "riego": "static/images/banner_riego.png",
    "diagnostico": "static/images/banner_diagnostico.png",
    "cosecha": "static/images/banner_cosecha.png",
    "legal": "static/images/banner_legal.png",
    "seguimiento": "static/images/banner_seguimiento.png",
}

ICON_PATHS = {
    "clima": "static/images/icon_clima.png",
    "asesoramiento": "static/images/icon_asesoramiento.png",
    "riego": "static/images/icon_riego.png",
    "diagnostico": "static/images/icon_diagnostico.png",
    "cosecha": "static/images/icon_cosecha.png",
    "legal": "static/images/icon_legal.png",
    "seguimiento": "static/images/icon_seguimiento.png",
    "temp": "static/images/icon_temp.png",
    "humedad": "static/images/icon_humedad.png",
    "viento": "static/images/icon_viento.png",
    "seedling": "static/images/icon_seedling.png",
    "remedios": "static/images/icon_remedios.png",
    "alerta": "static/images/icon_alerta.png",
    "calendario": "static/images/icon_calendario.png",
    "vpd": "static/images/icon_vpd.png",
    "lluvia": "static/images/icon_lluvia.png",
}

@st.cache_data
def _load_icon_b64(icon_key):
    path = ICON_PATHS.get(icon_key, "")
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

def icon_html(icon_key, size=28):
    b64 = _load_icon_b64(icon_key)
    if b64:
        return f'<img class="glm-icon" src="data:image/png;base64,{b64}" style="width:{size}px;height:{size}px;vertical-align:middle;border-radius:6px;margin-right:8px;display:inline-block;"/>'
    return ""

def icon_title(icon_key, text, tag="h1", size=36):
    ic = icon_html(icon_key, size)
    st.markdown(f'<{tag} class="glm-icon-title">{ic}{text}</{tag}>', unsafe_allow_html=True)

def icon_subtitle(icon_key, text, size=26):
    ic = icon_html(icon_key, size)
    st.markdown(f'<h3 class="glm-icon-subtitle">{ic}{text}</h3>', unsafe_allow_html=True)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Righteous&family=Nunito:wght@400;600;700;800&display=swap');

:root {
    --jam-green: #009B3A;
    --jam-yellow: #FED100;
    --jam-red: #CE1126;
    --jam-black: #1A1A1A;
    --jam-green-dark: #006B28;
    --jam-green-light: #00C44F;
    --glass-bg: rgba(18, 22, 18, 0.85);
    --glass-border: rgba(0, 155, 58, 0.2);
    --card-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --spacing-xs: 4px;
    --spacing-sm: 8px;
    --spacing-md: 16px;
    --spacing-lg: 24px;
}

* { transition: background-color 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease, transform 0.2s ease; }

@keyframes logoFloat {
    0%, 100% { transform: translateY(0px) scale(1); }
    50% { transform: translateY(-3px) scale(1.01); }
}

@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes pulseGlow {
    0%, 100% { box-shadow: 0 2px 12px rgba(0, 155, 58, 0.12); }
    50% { box-shadow: 0 4px 24px rgba(0, 155, 58, 0.25); }
}

@keyframes shimmer {
    0% { background-position: -200% center; }
    100% { background-position: 200% center; }
}

@keyframes borderGlow {
    0%, 100% { border-color: rgba(0, 155, 58, 0.15); }
    50% { border-color: rgba(0, 155, 58, 0.4); }
}

[data-testid="stAppViewContainer"] {
    background: linear-gradient(180deg, #080808 0%, #0C1A0A 20%, #101010 50%, #0C1A0A 80%, #080808 100%);
    color: #F0F0F0;
}

[data-testid="stHeader"] {
    background: linear-gradient(90deg, #009B3A, #FED100, #CE1126, #FED100, #009B3A);
    background-size: 200% 100%;
    animation: shimmer 8s linear infinite;
    height: 3px !important;
    min-height: 3px !important;
}

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #040A06 0%, #081A0E 35%, #0A150A 65%, #0E0E0E 90%, #120808 100%);
    border-right: 1px solid rgba(0, 155, 58, 0.3);
    box-shadow: 4px 0 30px rgba(0, 0, 0, 0.6);
    animation: borderGlow 5s ease-in-out infinite;
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span {
    color: #C8C8C8 !important;
}

[data-testid="stSidebar"] .stRadio > div {
    background: rgba(0, 155, 58, 0.04);
    border: 1px solid rgba(0, 155, 58, 0.12);
    border-radius: var(--radius-md);
    padding: 6px 8px;
}

[data-testid="stSidebar"] .stRadio label {
    border-radius: var(--radius-sm);
    padding: 4px 8px;
    margin: 1px 0;
}

[data-testid="stSidebar"] .stRadio label span {
    color: #B0B0B0 !important;
    font-size: 0.9em;
    font-weight: 500;
}

[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(0, 155, 58, 0.08);
}

[data-testid="stSidebar"] .stRadio label[data-checked="true"] {
    background: rgba(0, 155, 58, 0.12);
}

[data-testid="stSidebar"] .stRadio label[data-checked="true"] span {
    color: #FED100 !important;
    font-weight: 700;
    text-shadow: 0 0 6px rgba(254, 209, 0, 0.2);
}

h1 {
    font-family: 'Righteous', cursive !important;
    color: #FED100 !important;
    text-shadow: 1px 1px 4px rgba(0,0,0,0.5), 0 0 20px rgba(0, 155, 58, 0.15);
    border-bottom: 2px solid rgba(0, 155, 58, 0.4);
    padding-bottom: 14px;
    margin-bottom: 24px !important;
    letter-spacing: 0.5px;
    animation: fadeInUp 0.5s ease-out;
    font-size: 1.6em !important;
}

h2, h3, [data-testid="stSubheader"] {
    font-family: 'Nunito', sans-serif !important;
    color: #00C44F !important;
    font-weight: 700 !important;
    letter-spacing: 0.2px;
}

h4 {
    color: #FED100 !important;
    font-weight: 700 !important;
}

p, li, span, div, label {
    font-family: 'Nunito', sans-serif !important;
    line-height: 1.7;
}

[data-testid="stMetric"] {
    background: var(--glass-bg);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-md);
    padding: 18px 22px !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    animation: fadeInUp 0.5s ease-out, pulseGlow 5s ease-in-out infinite;
}

[data-testid="stMetricValue"] {
    color: #FED100 !important;
    font-family: 'Righteous', cursive !important;
    font-size: 1.7rem !important;
}

[data-testid="stMetricLabel"] {
    color: #009B3A !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    text-transform: uppercase;
    letter-spacing: 1px;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: rgba(12, 12, 12, 0.9);
    border-radius: var(--radius-md);
    padding: 5px;
    border: 1px solid rgba(0, 155, 58, 0.12);
}

.stTabs [data-baseweb="tab"] {
    background: rgba(30, 30, 30, 0.7);
    border-radius: var(--radius-sm);
    color: #B0B0B0;
    border: 1px solid rgba(50, 50, 50, 0.5);
    font-weight: 600;
    font-size: 0.88em;
    padding: 8px 14px;
}

.stTabs [data-baseweb="tab"]:hover {
    background: rgba(0, 155, 58, 0.12);
    border-color: rgba(0, 155, 58, 0.25);
    color: #FFFFFF;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #009B3A 0%, #006B28 100%) !important;
    color: #FFFFFF !important;
    border: 1px solid #00C44F !important;
    box-shadow: 0 2px 12px rgba(0, 155, 58, 0.25);
}

.stButton > button {
    background: linear-gradient(135deg, #009B3A 0%, #006B28 100%);
    color: white !important;
    border: none;
    border-radius: var(--radius-sm);
    font-family: 'Nunito', sans-serif !important;
    font-weight: 700;
    padding: 10px 24px;
    letter-spacing: 0.3px;
    box-shadow: 0 2px 10px rgba(0, 155, 58, 0.2);
}

.stButton > button:hover {
    background: linear-gradient(135deg, #00C44F 0%, #009B3A 100%);
    box-shadow: 0 4px 20px rgba(0, 155, 58, 0.35);
    transform: translateY(-1px);
}

.stButton > button:active {
    transform: translateY(0px);
    box-shadow: 0 1px 4px rgba(0, 155, 58, 0.3);
}

[data-testid="stExpander"] {
    background: var(--glass-bg);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border: 1px solid rgba(0, 155, 58, 0.15);
    border-left: 3px solid #009B3A;
    border-radius: var(--radius-md);
    box-shadow: 0 2px 16px rgba(0, 0, 0, 0.2);
    margin-bottom: 10px;
    animation: fadeInUp 0.4s ease-out;
}

[data-testid="stExpander"]:hover {
    border-color: rgba(0, 155, 58, 0.35);
    box-shadow: 0 4px 20px rgba(0, 155, 58, 0.08);
}

[data-testid="stExpander"] summary span {
    color: #FED100 !important;
    font-weight: 600 !important;
}

.stAlert [data-testid="stAlertContentInfo"] {
    background: rgba(0, 155, 58, 0.06);
    border-left: 3px solid #009B3A;
    border-radius: var(--radius-sm);
    color: #E0E0E0;
}

.stAlert [data-testid="stAlertContentWarning"] {
    background: rgba(254, 209, 0, 0.05);
    border-left: 3px solid #FED100;
    border-radius: var(--radius-sm);
    color: #E0E0E0;
}

.stAlert [data-testid="stAlertContentError"] {
    background: rgba(206, 17, 38, 0.06);
    border-left: 3px solid #CE1126;
    border-radius: var(--radius-sm);
    color: #E0E0E0;
}

.stAlert [data-testid="stAlertContentSuccess"] {
    background: rgba(0, 196, 79, 0.06);
    border-left: 3px solid #00C44F;
    border-radius: var(--radius-sm);
    color: #E0E0E0;
}

[data-testid="stDataFrame"] {
    border: 1px solid rgba(0, 155, 58, 0.2);
    border-radius: var(--radius-md);
    overflow: hidden;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
}

.stSelectbox > div > div,
.stTextInput > div > div > input,
.stDateInput > div > div > input,
.stNumberInput > div > div > input {
    background-color: rgba(20, 24, 20, 0.95) !important;
    color: #E0E0E0 !important;
    border: 1px solid rgba(60, 60, 60, 0.5) !important;
    border-radius: var(--radius-sm) !important;
    font-size: 0.95em !important;
}

.stSelectbox > div > div:focus-within,
.stTextInput > div > div > input:focus {
    border-color: #009B3A !important;
    box-shadow: 0 0 0 2px rgba(0, 155, 58, 0.15) !important;
}

[data-testid="stSidebar"] .stSelectbox > div > div,
[data-testid="stSidebar"] .stTextInput > div > div > input {
    background-color: rgba(15, 20, 15, 0.95) !important;
    border: 1px solid rgba(0, 155, 58, 0.2) !important;
}

[data-testid="stSidebar"] .stSelectbox > div > div:focus-within,
[data-testid="stSidebar"] .stTextInput > div > div > input:focus {
    border-color: #FED100 !important;
    box-shadow: 0 0 0 2px rgba(254, 209, 0, 0.15) !important;
}

.stSlider > div > div > div {
    background-color: #009B3A !important;
}

.stProgress > div > div > div {
    background: linear-gradient(90deg, #CE1126 0%, #FED100 50%, #009B3A 100%) !important;
    border-radius: 10px;
}

.stProgress > div > div {
    background: rgba(30, 30, 30, 0.8) !important;
    border-radius: 10px;
}

hr {
    border-color: rgba(40, 50, 40, 0.5) !important;
    margin: 12px 0 !important;
}

a {
    color: #00C44F !important;
    text-decoration: none !important;
}

a:hover {
    color: #FED100 !important;
    text-decoration: underline !important;
}

[data-testid="stMarkdownContainer"] {
    color: #DCDCDC;
}

.stRadio > label {
    color: #E0E0E0 !important;
}

[data-testid="stImage"] {
    border-radius: var(--radius-md);
    overflow: hidden;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
}

::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: #0A0A0A;
}

::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, #009B3A, #007A2E);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg, #00C44F, #009B3A);
}

.cannabis-divider {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    margin: 22px 0;
    width: 100%;
}

.cannabis-divider .line-left {
    flex: 1;
    height: 2px;
    background: linear-gradient(90deg, transparent 0%, #009B3A 40%, #FED100 100%);
    border-radius: 2px;
}

.cannabis-divider .line-right {
    flex: 1;
    height: 2px;
    background: linear-gradient(90deg, #FED100 0%, #CE1126 60%, transparent 100%);
    border-radius: 2px;
}

.cannabis-divider .leaf-center {
    width: 28px;
    height: 28px;
    margin: 0 10px;
    filter: drop-shadow(0 0 6px rgba(0, 155, 58, 0.7));
    object-fit: contain;
}

.cannabis-divider-mini .leaf-mini {
    width: 18px;
    height: 18px;
    margin: 0 6px;
    filter: drop-shadow(0 0 4px rgba(0, 155, 58, 0.5));
    object-fit: contain;
}

.cannabis-divider-mini {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    margin: 12px 0;
    width: 100%;
}

.cannabis-divider-mini .line-left {
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, transparent 0%, #009B3A 80%, #009B3A 100%);
}

.cannabis-divider-mini .line-right {
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, #009B3A 0%, #009B3A 20%, transparent 100%);
}

.cannabis-divider-mini .dot-center {
    width: 6px;
    height: 6px;
    background: #009B3A;
    border-radius: 50%;
    margin: 0 6px;
    box-shadow: 0 0 6px rgba(0, 155, 58, 0.5);
}

.news-card {
    background: linear-gradient(145deg, rgba(25, 35, 25, 0.7) 0%, rgba(20, 20, 20, 0.8) 100%);
    border: 1px solid rgba(0, 155, 58, 0.15);
    border-left: 3px solid #009B3A;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 10px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.news-card:hover {
    border-color: rgba(0, 155, 58, 0.4);
    box-shadow: 0 4px 16px rgba(0, 155, 58, 0.1);
}

.news-card .news-title {
    color: #FED100;
    font-weight: 700;
    font-size: 1em;
    margin-bottom: 4px;
}

.news-card .news-meta {
    color: #888;
    font-size: 0.82em;
}

.forecast-card {
    background: linear-gradient(145deg, rgba(0, 155, 58, 0.06) 0%, rgba(25, 25, 25, 0.8) 100%);
    border: 1px solid rgba(0, 155, 58, 0.2);
    border-radius: 12px;
    padding: 18px;
    text-align: center;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
}

.forecast-card .forecast-date {
    color: #FED100;
    font-family: 'Righteous', cursive;
    font-size: 1.05em;
    margin-bottom: 8px;
}

.forecast-card .forecast-temp {
    color: #00C44F;
    font-size: 1.3em;
    font-weight: 700;
    margin-bottom: 4px;
}

.forecast-card .forecast-rain {
    color: #87CEEB;
    font-size: 0.95em;
}

.sidebar-footer {
    position: fixed;
    bottom: 0;
    width: inherit;
    padding: 12px 16px;
    background: linear-gradient(180deg, transparent, rgba(5, 13, 7, 0.95));
    text-align: center;
    font-size: 0.75em;
    color: #555;
    border-top: 1px solid rgba(0, 155, 58, 0.15);
}

.sidebar-footer span {
    color: #009B3A !important;
    font-weight: 700;
}

.glm-badge {
    display: inline-block;
    background: linear-gradient(135deg, #009B3A, #007A2E);
    color: white !important;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.75em;
    font-weight: 700;
    letter-spacing: 0.5px;
}

.cultivo-info-right {
    text-align: right;
    padding: 4px 0;
}

.cultivo-info-right .cultivo-nombre {
    color: #FED100;
    font-weight: 700;
    font-size: 1.1em;
}

.cultivo-info-right .cultivo-dia {
    color: #009B3A;
    font-size: 0.95em;
    font-weight: 600;
}

.glm-icon-title {
    display: flex;
    align-items: center;
    gap: 4px;
    font-family: 'Righteous', sans-serif;
    color: #FED100;
    text-shadow: 0 0 15px rgba(0, 155, 58, 0.4);
    margin-bottom: 0.5em;
}

.glm-icon-subtitle {
    display: flex;
    align-items: center;
    gap: 4px;
    font-family: 'Nunito', sans-serif;
    color: #E0E0E0;
    font-weight: 700;
    margin-bottom: 0.4em;
}

.glm-icon {
    filter: drop-shadow(0 0 4px rgba(0, 155, 58, 0.5));
    flex-shrink: 0;
}

.sidebar-icon-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 2px 0;
}

.sidebar-icon-item img {
    width: 22px;
    height: 22px;
    border-radius: 4px;
    filter: drop-shadow(0 0 3px rgba(0, 155, 58, 0.4));
}

@media (max-width: 768px) {
    [data-testid="stAppViewContainer"] > section > div {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    .glm-icon-title {
        font-size: 1.3em !important;
    }
    .glm-icon-subtitle {
        font-size: 1em !important;
    }
    .forecast-card {
        padding: 10px !important;
        font-size: 0.9em !important;
    }
    .cannabis-divider .leaf-center {
        width: 22px !important;
        height: 22px !important;
    }
    [data-testid="stMetric"] {
        padding: 8px !important;
    }
    [data-testid="stMetric"] label {
        font-size: 0.8em !important;
    }
    .cultivo-info-right {
        font-size: 0.85em !important;
    }
    [data-testid="stSidebar"] {
        min-width: 200px !important;
    }
    .sidebar-footer {
        font-size: 0.7em !important;
    }
}

@media (max-width: 480px) {
    .glm-icon-title {
        font-size: 1.1em !important;
    }
    .glm-icon-subtitle {
        font-size: 0.9em !important;
    }
    .forecast-card {
        padding: 8px !important;
        font-size: 0.8em !important;
    }
}

.tutorial-card {
    background: linear-gradient(145deg, rgba(0, 155, 58, 0.12) 0%, rgba(30, 30, 30, 0.85) 100%);
    border: 1px solid rgba(254, 209, 0, 0.3);
    border-left: 4px solid #FED100;
    border-radius: 14px;
    padding: 20px 24px;
    margin-bottom: 20px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    position: relative;
    overflow: hidden;
}

.tutorial-card::before {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    width: 80px;
    height: 80px;
    background: radial-gradient(circle at top right, rgba(254, 209, 0, 0.1), transparent 70%);
    pointer-events: none;
}

.tutorial-card h4 {
    color: #FED100 !important;
    font-family: 'Righteous', cursive !important;
    font-size: 1.1em !important;
    margin: 0 0 10px !important;
    display: flex;
    align-items: center;
    gap: 8px;
}

.tutorial-card p {
    color: #D0D0D0 !important;
    font-size: 0.92em !important;
    line-height: 1.7 !important;
    margin: 0 !important;
}

.tutorial-card .tutorial-steps {
    margin-top: 10px;
    padding-left: 0;
}

.tutorial-card .tutorial-steps li {
    color: #C8C8C8 !important;
    font-size: 0.88em !important;
    margin-bottom: 6px;
    list-style: none;
    padding-left: 20px;
    position: relative;
}

.tutorial-card .tutorial-steps li::before {
    content: '▸';
    color: #009B3A;
    position: absolute;
    left: 0;
    font-weight: bold;
}

.module-header-card {
    background: linear-gradient(145deg, rgba(0, 155, 58, 0.06) 0%, rgba(20, 20, 20, 0.7) 100%);
    border: 1px solid rgba(0, 155, 58, 0.15);
    border-radius: 16px;
    padding: 8px 0;
    margin-bottom: 16px;
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 0.5rem;
}

[data-testid="stSidebar"] [data-testid="stImage"] {
    display: flex;
    justify-content: center;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 4px 24px rgba(0, 155, 58, 0.2), 0 0 40px rgba(0, 155, 58, 0.08);
    margin: 0 auto;
}

[data-testid="stMetricDelta"] {
    font-size: 0.8rem !important;
}

.stTabs [data-baseweb="tab"] {
    transition: all 0.25s ease;
}

[data-testid="stExpander"] {
    transition: all 0.25s ease;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
[data-testid="stToolbar"] {visibility: hidden;}
[data-testid="manage-app-button"] {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

def cannabis_banner(modulo="clima"):
    path = BANNER_PATHS.get(modulo, "")
    if path and os.path.exists(path):
        st.image(path, width="stretch")

def _leaf_b64():
    leaf_path = "static/images/leaf_divider.png"
    if os.path.exists(leaf_path):
        with open(leaf_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

@st.cache_data
def _get_leaf_b64():
    return _leaf_b64()

def cannabis_divider():
    b64 = _get_leaf_b64()
    if b64:
        st.markdown(f'<div class="cannabis-divider"><div class="line-left"></div><img class="leaf-center" src="data:image/png;base64,{b64}" alt="🍃"/><div class="line-right"></div></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="cannabis-divider"><div class="line-left"></div><span style="font-size:1.3em;margin:0 8px;">🍃</span><div class="line-right"></div></div>', unsafe_allow_html=True)

def cannabis_divider_mini():
    b64 = _get_leaf_b64()
    if b64:
        st.markdown(f'<div class="cannabis-divider-mini"><div class="line-left"></div><img class="leaf-mini" src="data:image/png;base64,{b64}" alt="🍃"/><div class="line-right"></div></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="cannabis-divider-mini"><div class="line-left"></div><div class="dot-center"></div><div class="line-right"></div></div>', unsafe_allow_html=True)

LAT_DEFAULT, LON_DEFAULT = -33.42, -63.30
CIUDAD_DEFAULT = "La Carlota, Córdoba"

def obtener_ubicacion_usuario():
    if 'user_lat' not in st.session_state:
        st.session_state['user_lat'] = None
        st.session_state['user_lon'] = None
        st.session_state['user_ciudad'] = "Detectando ubicación..."
        st.session_state['geo_disponible'] = True

def reverse_geocode(lat, lon):
    try:
        r = requests.get(f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&accept-language=es", timeout=5, headers={"User-Agent": "GLMAppCultivador/1.0"}).json()
        ciudad = r.get('address', {}).get('city') or r.get('address', {}).get('town') or r.get('address', {}).get('village') or r.get('address', {}).get('municipality', '')
        estado = r.get('address', {}).get('state', '')
        if ciudad and estado:
            return f"{ciudad}, {estado}"
        elif ciudad:
            return ciudad
        elif estado:
            return estado
        return f"Lat {lat:.2f}, Lon {lon:.2f}"
    except Exception:
        return f"Lat {lat:.2f}, Lon {lon:.2f}"

def obtener_etapas(sist):
    if "Automáticas" in sist:
        return [
            {"nombre": "Germinación", "inicio": 0, "fin": 7, "semanas": "Semana 1"},
            {"nombre": "Plántula", "inicio": 7, "fin": 18, "semanas": "Semanas 2-3"},
            {"nombre": "Vegetativo", "inicio": 18, "fin": 32, "semanas": "Semanas 3-5"},
            {"nombre": "Pre-Floración", "inicio": 32, "fin": 42, "semanas": "Semanas 5-6"},
            {"nombre": "Floración Temprana", "inicio": 42, "fin": 56, "semanas": "Semanas 6-8"},
            {"nombre": "Floración Media", "inicio": 56, "fin": 70, "semanas": "Semanas 8-10"},
            {"nombre": "Floración Tardía / Maduración", "inicio": 70, "fin": 84, "semanas": "Semanas 10-12"},
            {"nombre": "Flush y Cosecha", "inicio": 84, "fin": 999, "semanas": "Semana 12+"},
        ]
    elif sist == "Interior Luz":
        return [
            {"nombre": "Germinación", "inicio": 0, "fin": 7, "semanas": "Semana 1"},
            {"nombre": "Plántula", "inicio": 7, "fin": 21, "semanas": "Semanas 2-3"},
            {"nombre": "Vegetativo Temprano", "inicio": 21, "fin": 42, "semanas": "Semanas 4-6"},
            {"nombre": "Vegetativo Avanzado", "inicio": 42, "fin": 63, "semanas": "Semanas 7-9"},
            {"nombre": "Cambio a Floración (12/12)", "inicio": 63, "fin": 77, "semanas": "Semanas 10-11"},
            {"nombre": "Floración Temprana", "inicio": 77, "fin": 98, "semanas": "Semanas 11-14"},
            {"nombre": "Floración Media", "inicio": 98, "fin": 119, "semanas": "Semanas 14-17"},
            {"nombre": "Floración Tardía / Maduración", "inicio": 119, "fin": 140, "semanas": "Semanas 17-20"},
            {"nombre": "Flush y Cosecha", "inicio": 140, "fin": 999, "semanas": "Semana 20+"},
        ]
    else:
        return [
            {"nombre": "Germinación", "inicio": 0, "fin": 10, "semanas": "Semana 1-2"},
            {"nombre": "Plántula", "inicio": 10, "fin": 25, "semanas": "Semanas 2-4"},
            {"nombre": "Vegetativo Temprano", "inicio": 25, "fin": 50, "semanas": "Semanas 4-7"},
            {"nombre": "Vegetativo Avanzado", "inicio": 50, "fin": 90, "semanas": "Semanas 7-13"},
            {"nombre": "Pre-Floración", "inicio": 90, "fin": 110, "semanas": "Semanas 13-16"},
            {"nombre": "Floración Temprana", "inicio": 110, "fin": 140, "semanas": "Semanas 16-20"},
            {"nombre": "Floración Media", "inicio": 140, "fin": 170, "semanas": "Semanas 20-24"},
            {"nombre": "Floración Tardía / Maduración", "inicio": 170, "fin": 200, "semanas": "Semanas 24-28"},
            {"nombre": "Flush y Cosecha", "inicio": 200, "fin": 999, "semanas": "Semana 28+"},
        ]

def obtener_etapa_actual(dias, etapas):
    for e in etapas:
        if e["inicio"] <= dias < e["fin"]:
            return e
    return etapas[-1]

def porcentaje_etapa(dias, etapa):
    rango = etapa["fin"] - etapa["inicio"]
    if rango <= 0 or rango > 500:
        return 1.0
    progreso = (dias - etapa["inicio"]) / rango
    return min(max(progreso, 0.0), 1.0)

def fetch_weather(lat=None, lon=None):
    if lat is None:
        lat = st.session_state.get('user_lat', LAT_DEFAULT)
    if lon is None:
        lon = st.session_state.get('user_lon', LON_DEFAULT)
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto&forecast_days=3"
    try:
        r = requests.get(url, timeout=10).json()
        return r.get('current'), r.get('daily')
    except Exception:
        return None, None

def calcular_vpd(t, h):
    es = 0.61078 * np.exp((17.27 * t) / (t + 237.3))
    ea = es * (h / 100)
    return round(es - ea, 2)

# --- SIDEBAR (MENÚ) ---
_logo_path = "static/images/logo_app_v2.png"
if not os.path.exists(_logo_path):
    _logo_path = "static/images/logo_cannabis.png"
if os.path.exists(_logo_path):
    _logo_b64 = ""
    with open(_logo_path, "rb") as _lf:
        _logo_b64 = base64.b64encode(_lf.read()).decode()
    st.sidebar.markdown(f"""
    <div style="text-align: center; margin: 4px auto 12px; display: flex; justify-content: center;">
        <img src="data:image/png;base64,{_logo_b64}" alt="GLM Logo"
             style="width: 110px; height: 110px; border-radius: 22px; object-fit: cover;
                    box-shadow: 0 0 20px rgba(0,155,58,0.35), 0 4px 16px rgba(0,0,0,0.4);
                    animation: logoFloat 3s ease-in-out infinite;
                    border: 2px solid rgba(0,155,58,0.3);" />
    </div>
    """, unsafe_allow_html=True)

obtener_ubicacion_usuario()

st.sidebar.markdown("""
<div style="
    background: rgba(0,155,58,0.06);
    border: 1px solid rgba(0,155,58,0.2);
    border-radius: 10px;
    padding: 8px 12px;
    margin: 10px 0 4px;
">
    <p style="color: #FED100; font-size: 0.78em; font-weight: 700; margin: 0; letter-spacing: 0.5px; text-transform: uppercase;">📍 Ubicación</p>
</div>
""", unsafe_allow_html=True)
usar_geo = st.sidebar.checkbox("Usar mi ubicación", value=st.session_state.get('geo_disponible', True), key="usar_geo_check")

if usar_geo:
    loc = get_geolocation()
    if loc and isinstance(loc, dict) and 'coords' in loc:
        new_lat = loc['coords']['latitude']
        new_lon = loc['coords']['longitude']
        st.session_state['user_lat'] = new_lat
        st.session_state['user_lon'] = new_lon
        if st.session_state.get('user_ciudad', '').startswith('Detectando') or st.session_state.get('user_ciudad', '') == CIUDAD_DEFAULT:
            st.session_state['user_ciudad'] = reverse_geocode(new_lat, new_lon)
        st.session_state['geo_disponible'] = True
    else:
        if st.session_state.get('user_lat') is None:
            st.sidebar.info("Esperando permiso de ubicación del navegador...")
else:
    st.session_state['user_lat'] = LAT_DEFAULT
    st.session_state['user_lon'] = LON_DEFAULT
    st.session_state['user_ciudad'] = CIUDAD_DEFAULT
    st.session_state['geo_disponible'] = False

ciudad_actual = st.session_state.get('user_ciudad', CIUDAD_DEFAULT)
user_lat = st.session_state.get('user_lat') or LAT_DEFAULT
user_lon = st.session_state.get('user_lon') or LON_DEFAULT
if ciudad_actual.startswith('Detectando'):
    st.sidebar.warning(f"📍 {ciudad_actual}")
else:
    st.sidebar.success(f"📍 {ciudad_actual}")

st.sidebar.markdown("""
<div style="
    background: rgba(0,155,58,0.06);
    border: 1px solid rgba(0,155,58,0.2);
    border-radius: 10px;
    padding: 8px 12px;
    margin: 10px 0 4px;
">
    <p style="color: #009B3A; font-size: 0.78em; font-weight: 700; margin: 0; letter-spacing: 0.5px; text-transform: uppercase;">🌱 Selección de Cultivo</p>
</div>
""", unsafe_allow_html=True)
categoria = st.sidebar.selectbox("Categoría de Cultivo", ["Interior", "Exterior", "Invernadero"])
if categoria == "Interior":
    subtipo = st.sidebar.selectbox("Tipo", ["Luz", "Automáticas"])
elif categoria == "Exterior":
    subtipo = st.sidebar.selectbox("Tipo", ["Maceta", "Tierra Madre", "Automáticas"])
else:
    subtipo = st.sidebar.selectbox("Tipo", ["Maceta", "Tierra"])
sistema = f"{categoria} {subtipo}"

menu = st.sidebar.radio("Navegación", 
    ["🌦️ Clima y Sugerencias", "📘 Asesoramiento Cultivo", "💧 Calculadora Riego", "🛡️ Diagnóstico & Plagas", "✂️ Estimador de Cosecha", "⚖️ Sugerencias Legales", "🌱 Seguimiento de Cultivo"])
menu = menu.split(" ", 1)[1] if " " in menu else menu

st.sidebar.markdown("""
<div style="
    background: rgba(254,209,0,0.04);
    border: 1px solid rgba(254,209,0,0.25);
    border-radius: 10px;
    padding: 8px 12px;
    margin: 10px 0 4px;
">
    <p style="color: #FED100; font-size: 0.78em; font-weight: 700; margin: 0; letter-spacing: 0.5px; text-transform: uppercase;">💳 Suscripción</p>
    <p style="color: #888; font-size: 0.68em; margin: 2px 0 0; font-weight: 400;">Ingresá tu email para acceder</p>
</div>
""", unsafe_allow_html=True)

if "email_cargado_ls" not in st.session_state:
    st.session_state["email_cargado_ls"] = False
if not st.session_state["email_cargado_ls"]:
    try:
        email_guardado = streamlit_js_eval(js_expressions="localStorage.getItem('glm_email')", key="leer_email_ls", want_output=True)
        if email_guardado and isinstance(email_guardado, str) and "@" in email_guardado:
            st.session_state["suscriptor_email"] = email_guardado
            st.session_state["recordar_usuario"] = True
    except Exception:
        pass
    st.session_state["email_cargado_ls"] = True

if PERSONAL_MODE:
    sub_email = personal_account()
    st.session_state["suscriptor_email"] = sub_email
    st.session_state["suscripcion_activa"] = True
    st.sidebar.caption("Modo personal · acceso protegido")
else:
    sub_email = st.sidebar.text_input("Tu email", value=st.session_state.get("suscriptor_email", ""), key="sub_email_input", placeholder="ejemplo@email.com")
    if sub_email:
        st.session_state["suscriptor_email"] = sub_email
        sub_info = verificar_suscripcion(sub_email)
        if sub_info["activa"]:
            plan_label = sub_info['plan'].upper()
            dias = sub_info['dias_restantes']
            es_trial = sub_info.get('es_trial', False)
            if es_trial:
                plan_label = "PRUEBA GRATIS"
                color_badge = "#00C44F"
            elif sub_info['plan'] == 'semanal':
                color_badge = "#888"
            elif sub_info['plan'] == 'mensual':
                color_badge = "#009B3A"
            else:
                color_badge = "#FED100"
            st.sidebar.markdown(f"""
            <div style="background: rgba(0,155,58,0.1); border: 1px solid {color_badge}; border-radius: 10px; padding: 12px; margin: 8px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="color: {color_badge}; font-weight: 700; font-size: 0.9em;">{plan_label}</span>
                    <span style="color: #AAA; font-size: 0.8em;">hasta {sub_info['vencimiento']}</span>
                </div>
                <div style="background: rgba(255,255,255,0.1); border-radius: 6px; height: 6px; margin-top: 8px; overflow: hidden;">
                    <div style="background: {color_badge}; height: 100%; width: {min(100, max(5, dias * 100 // max(1, 365 if sub_info['plan']=='anual' else 30 if sub_info['plan']=='mensual' else 7)))}%; border-radius: 6px;"></div>
                </div>
                <p style="color: #CCC; font-size: 0.8em; margin: 5px 0 0; text-align: center;">
                    {'⏳ ' + str(dias) + ' días restantes' if dias > 3 else '⚠️ ¡Quedan ' + str(dias) + ' días! Renová pronto'}
                </p>
            </div>
            """, unsafe_allow_html=True)
            st.session_state["suscripcion_activa"] = True
            recordar = st.sidebar.checkbox("🔒 Recordar mi usuario", value=st.session_state.get("recordar_usuario", False), key="chk_recordar")
            st.session_state["recordar_usuario"] = recordar
            if recordar:
                streamlit_js_eval(js_expressions=f"localStorage.setItem('glm_email', '{sub_email.strip().lower()}')", key="guardar_email_ls")
            else:
                streamlit_js_eval(js_expressions="localStorage.removeItem('glm_email')", key="borrar_email_ls")
            if es_trial and dias <= 3:
                st.sidebar.info("Tu prueba gratis termina pronto. Elegí un plan para seguir usando los módulos premium.")
        else:
            st.sidebar.warning("⚠️ Sin suscripción activa")
            st.session_state["suscripcion_activa"] = False
            streamlit_js_eval(js_expressions="localStorage.removeItem('glm_email')", key="borrar_email_exp")
    else:
        st.session_state["suscripcion_activa"] = False

if not PERSONAL_MODE:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🤝 Programa de Referidos")
    if sub_email and st.session_state.get("suscripcion_activa", False):
        mi_codigo = generar_codigo_referido(sub_email)
        domain = os.environ.get("REPLIT_DEV_DOMAIN", os.environ.get("REPLIT_DOMAINS", ""))
        link_referido = f"https://{domain}?ref={mi_codigo}"
        cant_referidos, recompensa = contar_referidos(sub_email)
        st.sidebar.markdown(f"""
        <div style="background: rgba(254,209,0,0.08); border: 1px solid rgba(254,209,0,0.3); border-radius: 10px; padding: 12px; margin: 8px 0;">
            <p style="color: #FED100; font-weight: 700; font-size: 0.9em; margin: 0 0 6px;">Tu link de referido:</p>
            <p style="color: #CCC; font-size: 0.75em; word-break: break-all; margin: 0 0 10px; background: rgba(0,0,0,0.3); padding: 6px; border-radius: 6px;">{link_referido}</p>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px;">
                <span style="color: #AAA; font-size: 0.8em;">Referidos anuales:</span>
                <span style="color: #FED100; font-weight: 700;">{cant_referidos}/5</span>
            </div>
            <div style="background: rgba(255,255,255,0.1); border-radius: 6px; height: 6px; margin-top: 6px; overflow: hidden;">
                <div style="background: #FED100; height: 100%; width: {min(100, cant_referidos * 20)}%; border-radius: 6px;"></div>
            </div>
            <p style="color: #888; font-size: 0.75em; margin: 6px 0 0; text-align: center;">
                {'🎉 ¡Recompensa obtenida! Plan Premium gratis' if recompensa else '5 suscriptores anuales = Premium gratis'}
            </p>
        </div>
        """, unsafe_allow_html=True)
        st.sidebar.text_input("Copiá tu link:", value=link_referido, key="ref_link_copy", disabled=True)
    else:
        st.sidebar.caption("Referí 5 amigos al plan anual y obtené tu cuenta Premium gratis. Ingresá tu email arriba para ver tu link.")

    _raw_domain = os.environ.get("REPLIT_DOMAINS", os.environ.get("REPLIT_DEV_DOMAIN", ""))
    app_domain = _raw_domain.split(",")[0].strip() if _raw_domain else ""
    app_link = f"https://{app_domain}" if app_domain else ""
    wa_msg_base = "🌿 Mirá esta app para cultivadores argentinos! Clima, diagnóstico, riego, cosecha y más. Todo en una app profesional. Descargala acá 👉 " + app_link

    videos_promo = [
        ("static/videos/promo_clima_interfaz.mp4", "GLM_Clima_Interfaz.mp4", "🌦️ Monitor Clima", "Mirá cómo GLM App te muestra el clima en tiempo real para tu cultivo. Temperatura, humedad, VPD y más 🌿👉 " + app_link),
        ("static/videos/promo_seguimiento_interfaz.mp4", "GLM_Seguimiento_Interfaz.mp4", "🌱 Seguimiento", "Con GLM App llevás el seguimiento completo de tus cultivos. Etapas, riego, cosecha, todo en tu celular 🌿👉 " + app_link),
        ("static/videos/promo_diagnostico_interfaz.mp4", "GLM_Diagnostico_Interfaz.mp4", "🔍 Diagnóstico", "GLM App te ayuda a diagnosticar problemas en tus plantas con remedios naturales. Probala gratis 🌿👉 " + app_link),
        ("static/videos/glm_ad_redes.mp4", "GLM_Teaser.mp4", "🎬 Teaser General", wa_msg_base),
        ("static/videos/clip_01_presentacion.mp4", "GLM_Presentacion.mp4", "🌿 Presentación", wa_msg_base),
        ("static/videos/clip_02_clima.mp4", "GLM_Clima.mp4", "☁️ Clima Original", wa_msg_base),
        ("static/videos/clip_03_diagnostico.mp4", "GLM_Diagnostico.mp4", "🔬 Diagnóstico Original", wa_msg_base),
        ("static/videos/clip_04_seguimiento.mp4", "GLM_Seguimiento.mp4", "📋 Seguimiento Original", wa_msg_base),
        ("static/videos/clip_05_legal.mp4", "GLM_Legal.mp4", "⚖️ Info Legal", wa_msg_base),
    ]
    videos_existentes = [(p, fn, lbl, wm) for p, fn, lbl, wm in videos_promo if os.path.exists(p)]
    if videos_existentes:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🎬 Videos Promocionales")
        st.sidebar.caption("Descargá, compartí por WhatsApp o publicá en redes")
        if app_link:
            st.sidebar.markdown(f"""
            <div style="background: rgba(0,155,58,0.1); border: 1px solid rgba(0,155,58,0.3); border-radius: 8px; padding: 8px; margin-bottom: 10px; text-align: center;">
                <p style="color: #009B3A; font-size: 0.75em; margin: 0 0 4px; font-weight: 600;">🔗 Link de la App</p>
                <p style="color: #CCC; font-size: 0.65em; word-break: break-all; margin: 0;">{app_link}</p>
            </div>
            """, unsafe_allow_html=True)
        import urllib.parse as _urlparse
        _svg_whatsapp = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>'
        _svg_instagram = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="white"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>'
        _svg_twitter = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="white"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>'
        _svg_facebook = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="white"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>'
        for vpath, vfname, vlabel, wa_text in videos_existentes:
            wa_encoded = _urlparse.quote(wa_text)
            wa_share_url = f"https://wa.me/?text={wa_encoded}"
            tw_encoded = _urlparse.quote(wa_text[:280])
            tw_share_url = f"https://twitter.com/intent/tweet?text={tw_encoded}"
            ig_share_url = f"https://www.instagram.com/reels/create/"
            fb_share_url = f"https://www.facebook.com/sharer/sharer.php?u={_urlparse.quote(app_link)}" if app_link else ""
            col_dl, col_wa = st.sidebar.columns([1, 1])
            with col_dl:
                st.download_button(
                    label=f"📥 {vlabel}",
                    data=open(vpath, "rb"),
                    file_name=vfname,
                    mime="video/mp4",
                    key=f"dl_{vfname}"
                )
            with col_wa:
                st.markdown(f"""
                <a href="{wa_share_url}" target="_blank" style="
                    display: flex; align-items: center; justify-content: center; gap: 6px;
                    background: #25D366; color: white !important; font-weight: 700;
                    padding: 8px 4px; border-radius: 6px; font-size: 0.78em;
                    text-decoration: none !important; margin-top: 2px;
                ">{_svg_whatsapp} WhatsApp</a>
                """, unsafe_allow_html=True)
            st.sidebar.markdown(f"""
            <div style="display: flex; gap: 8px; margin: -4px 0 10px; justify-content: center; align-items: center;">
                <a href="{ig_share_url}" target="_blank" title="Descargá el video y subilo como Reel en Instagram" style="
                    display: inline-flex; align-items: center; gap: 4px;
                    background: linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888);
                    color: white !important; text-decoration: none !important;
                    padding: 4px 10px; border-radius: 14px; font-size: 0.7em; font-weight: 600;
                ">{_svg_instagram} Instagram</a>
                <a href="{tw_share_url}" target="_blank" style="
                    display: inline-flex; align-items: center; gap: 4px;
                    background: #000000; color: white !important; text-decoration: none !important;
                    padding: 4px 10px; border-radius: 14px; font-size: 0.7em; font-weight: 600;
                ">{_svg_twitter} X</a>
                {'<a href="' + fb_share_url + '" target="_blank" style="display: inline-flex; align-items: center; gap: 4px; background: #1877F2; color: white !important; text-decoration: none !important; padding: 4px 10px; border-radius: 14px; font-size: 0.7em; font-weight: 600;">' + _svg_facebook + ' Facebook</a>' if fb_share_url else ''}
            </div>
            """, unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔐 Privacidad")
with st.sidebar.expander("📋 Política de Privacidad", expanded=False):
    st.markdown("""
    **GLM App del Cultivador Argentino** respeta tu privacidad:

    **Datos que recopilamos:**
    - Email: para asociar tus registros a una cuenta de esta instancia
    - Datos de cultivo: se almacenan en la base PostgreSQL configurada

    **Qué NO hacemos:**
    - No vendemos ni compartimos tus datos con terceros
    - No enviamos publicidad ni spam
    - No almacenamos datos de pago (los gestiona Mercado Pago)

    **Tus derechos:**
    - Podés eliminar todos tus datos en cualquier momento
    - Tus datos de pago están protegidos por Mercado Pago
    - Tu email se codifica en las comunicaciones de pago

    **Seguridad:**
    - Conexión cifrada (HTTPS)
    - Emails codificados en referencias de pago
    - Verificación HMAC para pagos
    - localStorage se borra al expirar la suscripción
    """)

if sub_email and not PERSONAL_MODE:
    if st.sidebar.button("🗑️ Eliminar mis datos", key="btn_eliminar_datos"):
        st.session_state["confirmar_eliminacion"] = True
    if st.session_state.get("confirmar_eliminacion", False):
        st.sidebar.warning("⚠️ Esto eliminará tu suscripción, referidos y datos asociados. Esta acción no se puede deshacer.")
        col_si, col_no = st.sidebar.columns(2)
        with col_si:
            if st.button("Sí, eliminar", key="btn_confirmar_eliminar"):
                eliminar_datos_usuario(sub_email)
                streamlit_js_eval(js_expressions="localStorage.removeItem('glm_email')", key="borrar_email_delete")
                st.session_state["suscriptor_email"] = ""
                st.session_state["suscripcion_activa"] = False
                st.session_state["confirmar_eliminacion"] = False
                st.session_state["recordar_usuario"] = False
                st.sidebar.success("✅ Tus datos fueron eliminados.")
                st.rerun()
        with col_no:
            if st.button("Cancelar", key="btn_cancelar_eliminar"):
                st.session_state["confirmar_eliminacion"] = False
                st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown('<div class="sidebar-footer"><span>GLM</span> App del Cultivador v3.1<br>Argentina 🇦🇷</div>', unsafe_allow_html=True)

if "cultivos" not in st.session_state:
    _user_email = st.session_state.get("suscriptor_email", "")
    st.session_state.cultivos = cargar_cultivos(_user_email)

MODULOS_PREMIUM = ["Asesoramiento Cultivo", "Calculadora Riego", "Diagnóstico & Plagas", "Estimador de Cosecha", "Sugerencias Legales", "Seguimiento de Cultivo"]
if menu in MODULOS_PREMIUM and not st.session_state.get("suscripcion_activa", False):
    mostrar_paywall(menu)
    st.stop()

def mostrar_banner_glm():
    user_email = st.session_state.get("suscriptor_email", "").strip().lower()
    tiene_email = bool(user_email and "@" in user_email)

    if "banner_glm_dismissed_check" not in st.session_state:
        st.session_state["banner_glm_dismissed_check"] = False
    if "banner_glm_visible" not in st.session_state:
        st.session_state["banner_glm_visible"] = True

    if tiene_email and not st.session_state["banner_glm_dismissed_check"]:
        try:
            dismissed_ts = streamlit_js_eval(
                js_expressions="localStorage.getItem('glm_banner_dismissed')",
                key="leer_banner_dismiss", want_output=True
            )
            if dismissed_ts and str(dismissed_ts).isdigit():
                import time as _time
                elapsed_days = (_time.time() - int(dismissed_ts) / 1000) / 86400
                if elapsed_days < 30:
                    st.session_state["banner_glm_visible"] = False
                else:
                    st.session_state["banner_glm_visible"] = True
        except Exception:
            pass
        st.session_state["banner_glm_dismissed_check"] = True

    if not tiene_email:
        st.session_state["banner_glm_visible"] = True

    if not st.session_state.get("banner_glm_visible", True):
        return

    _glm_digital_path = "static/images/glm_imagen_digital.png"
    _glm_digital_b64 = ""
    if os.path.exists(_glm_digital_path):
        with open(_glm_digital_path, "rb") as _gf:
            _glm_digital_b64 = base64.b64encode(_gf.read()).decode()

    _glm_img_html = f'<img src="data:image/png;base64,{_glm_digital_b64}" alt="GLM Imagen Digital" style="max-width: 240px; height: auto; border-radius: 10px; background: rgba(255,255,255,0.95); padding: 8px 12px;" />' if _glm_digital_b64 else '<span style="font-size: 1.6em; font-weight: 900; color: #FED100;">GLM</span>'

    st.markdown(f"""
    <style>
        #glm-consulting-banner a:hover {{
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 20px rgba(0,155,58,0.5) !important;
        }}
    </style>
    <div id="glm-consulting-banner" style="
        background: linear-gradient(135deg, rgba(0,155,58,0.15) 0%, rgba(26,26,26,0.95) 40%, rgba(254,209,0,0.1) 100%);
        border: 2px solid rgba(254,209,0,0.5);
        border-radius: 16px;
        padding: 24px 28px;
        margin: 0 0 24px 0;
        position: relative;
        overflow: hidden;
        box-shadow: 0 4px 24px rgba(0,0,0,0.4), 0 0 30px rgba(254,209,0,0.08);
    ">
        <div style="position: absolute; top: 0; right: 0; width: 120px; height: 120px;
                    background: radial-gradient(circle at top right, rgba(254,209,0,0.15), transparent 70%);
                    pointer-events: none;"></div>
        <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 14px;">
            {_glm_img_html}
        </div>
        <p style="color: #E0E0E0; font-size: 0.95em; line-height: 1.6; margin: 0 0 6px;">
            ¿Te gustó esta app? <strong style="color: #FED100;">Podemos crear una igual o mejor para tu negocio.</strong>
        </p>
        <p style="color: #BBB; font-size: 0.88em; line-height: 1.5; margin: 0 0 16px;">
            Apps para comercios, servicios, delivery, turnos, catálogos y más.
            Diseño profesional, publicación en Play Store y soporte continuo.
        </p>
        <div style="
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(254,209,0,0.2);
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 14px;
        ">
            <p style="color: #FED100; font-weight: 700; font-size: 0.9em; margin: 0 0 8px; letter-spacing: 0.5px;">📋 CONTACTANOS</p>
            <p style="color: #E0E0E0; font-size: 0.88em; margin: 0 0 4px;">
                ✉️ <strong>E-mail:</strong> <a href="mailto:flacogrosso@gmail.com" style="color: #FED100; text-decoration: none;">flacogrosso@gmail.com</a>
            </p>
            <p style="color: #E0E0E0; font-size: 0.88em; margin: 0;">
                📱 <strong>WhatsApp:</strong> <a href="https://wa.me/543584400880" target="_blank" style="color: #FED100; text-decoration: none;">3584400880</a>
            </p>
        </div>
        <div style="display: flex; gap: 10px; flex-wrap: wrap; align-items: center;">
            <a href="mailto:flacogrosso@gmail.com?subject=Consulta%20por%20app&body=Hola%20GLM%2C%20me%20interesa%20el%20desarrollo%20de%20una%20app%20para%20mi%20negocio.%20Me%20gustar%C3%ADa%20recibir%20m%C3%A1s%20informaci%C3%B3n."
               style="
                   display: inline-block;
                   background: linear-gradient(135deg, #009B3A, #007A2E);
                   color: #FED100;
                   font-weight: 800;
                   font-size: 0.95em;
                   padding: 12px 24px;
                   border-radius: 10px;
                   text-decoration: none;
                   box-shadow: 0 3px 14px rgba(0,155,58,0.35);
                   transition: all 0.3s ease;
                   letter-spacing: 0.3px;
               "
            >✉️ Sí, me interesa</a>
            <a href="https://wa.me/543584400880?text=Hola%20GLM%2C%20me%20interesa%20el%20desarrollo%20de%20una%20app%20para%20mi%20negocio."
               target="_blank"
               style="
                   display: inline-block;
                   background: linear-gradient(135deg, #25D366, #128C7E);
                   color: white;
                   font-weight: 800;
                   font-size: 0.95em;
                   padding: 12px 24px;
                   border-radius: 10px;
                   text-decoration: none;
                   box-shadow: 0 3px 14px rgba(37,211,102,0.35);
                   transition: all 0.3s ease;
                   letter-spacing: 0.3px;
               "
            >📱 WhatsApp</a>
            <span style="color: #666; font-size: 0.8em;">
                Consultá sin compromiso
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if tiene_email:
        if st.button("✕ No mostrar por 30 días", key="btn_dismiss_glm_banner", type="secondary"):
            streamlit_js_eval(
                js_expressions=f"localStorage.setItem('glm_banner_dismissed', String(Date.now()))",
                key="guardar_banner_dismiss"
            )
            st.session_state["banner_glm_visible"] = False
            st.rerun()

if not PERSONAL_MODE:
    mostrar_banner_glm()

# --- MÓDULO 1: CLIMA & VPD ---
if menu == "Clima y Sugerencias":
    cannabis_banner("clima")
    mostrar_tutorial("Clima y Sugerencias")

    if not st.session_state.get("suscripcion_activa", False):
        clima_email = st.session_state.get("suscriptor_email", "")
        if clima_email:
            clima_sub_info = verificar_suscripcion(clima_email)
            if not clima_sub_info["activa"]:
                trial_usado = False
                suscriptores_check = cargar_suscriptores()
                for s in suscriptores_check:
                    if s.get("email", "").lower() == clima_email.strip().lower():
                        trial_usado = True
                        break
                if trial_usado:
                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, rgba(254,209,0,0.12), rgba(206,17,38,0.08));
                                border: 1px solid rgba(254,209,0,0.4); border-radius: 14px; padding: 18px; margin-bottom: 20px; text-align: center;">
                        <p style="color: #FED100; font-size: 1.1em; font-weight: 700; margin: 0 0 8px;">⚠️ Tu suscripción expiró</p>
                        <p style="color: #CCC; font-size: 0.9em; margin: 0 0 12px;">Renová tu plan para seguir usando los 6 módulos premium. Este módulo siempre es gratuito.</p>
                        <p style="color: #AAA; font-size: 0.85em; margin: 0;">👈 Elegí un plan en la barra lateral o seleccioná un módulo premium para ver las opciones.</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div style="background: linear-gradient(135deg, rgba(0,155,58,0.15), rgba(0,100,38,0.08));
                                border: 2px dashed #00C44F; border-radius: 14px; padding: 18px; margin-bottom: 20px; text-align: center;">
                        <p style="color: #00C44F; font-size: 1.2em; font-weight: 700; margin: 0 0 8px;">🎁 ¡Tenés 7 días gratis esperándote!</p>
                        <p style="color: #CCC; font-size: 0.95em; margin: 0 0 12px;">Activá tu prueba gratuita y desbloqueá los 6 módulos premium: Asesoramiento, Riego, Diagnóstico, Cosecha, Legal y Seguimiento.</p>
                        <p style="color: #AAA; font-size: 0.85em; margin: 0;">👈 Seleccioná cualquier módulo premium en el menú para activar tu prueba gratis. Sin tarjeta de crédito.</p>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="background: linear-gradient(135deg, rgba(0,155,58,0.15), rgba(0,100,38,0.08));
                        border: 2px dashed #00C44F; border-radius: 14px; padding: 18px; margin-bottom: 20px; text-align: center;">
                <p style="color: #00C44F; font-size: 1.2em; font-weight: 700; margin: 0 0 8px;">🎁 ¡Probá la app completa gratis por 7 días!</p>
                <p style="color: #CCC; font-size: 0.95em; margin: 0 0 12px;">Este módulo es gratuito. Ingresá tu email en la barra lateral y seleccioná un módulo premium para activar tu prueba gratis.</p>
                <p style="color: #AAA; font-size: 0.85em; margin: 0;">Sin tarjeta de crédito. 6 módulos premium desbloqueados.</p>
            </div>
            """, unsafe_allow_html=True)
    else:
        clima_sub_info = verificar_suscripcion(st.session_state.get("suscriptor_email", ""))
        clima_dias = clima_sub_info.get("dias_restantes", 0)
        clima_plan = clima_sub_info.get("plan", "")
        clima_es_trial = clima_sub_info.get("es_trial", False)
        if clima_es_trial:
            st.markdown(f"""
            <div style="background: rgba(0,155,58,0.08); border: 1px solid rgba(0,155,58,0.3); border-radius: 10px; padding: 12px; margin-bottom: 15px; text-align: center;">
                <span style="color: #00C44F; font-weight: 700;">🎁 Prueba Gratis</span>
                <span style="color: #CCC;"> — Te quedan <b style="color: #FED100;">{clima_dias} días</b>. Elegí un plan para no perder acceso.</span>
            </div>
            """, unsafe_allow_html=True)
        elif clima_dias <= 5:
            st.markdown(f"""
            <div style="background: rgba(206,17,38,0.08); border: 1px solid rgba(206,17,38,0.3); border-radius: 10px; padding: 12px; margin-bottom: 15px; text-align: center;">
                <span style="color: #CE1126; font-weight: 700;">⏳ Plan {clima_plan.upper()}</span>
                <span style="color: #CCC;"> — Te quedan <b style="color: #FED100;">{clima_dias} días</b>. ¡Renová pronto!</span>
            </div>
            """, unsafe_allow_html=True)

    icon_title("clima", f"Monitor Ambiental - {ciudad_actual}")
    curr, daily = fetch_weather()
    t, h, v, vpd = 0.0, 0.0, 0.0, 0.0
    
    if curr:
        t, h, v = curr['temperature_2m'], curr['relative_humidity_2m'], curr['wind_speed_10m']
        vpd = calcular_vpd(t, h)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Temperatura", f"{t}°C")
        c2.metric("Humedad", f"{h}%")
        c3.metric("VPD (Transpiración)", f"{vpd} kPa")
        c4.metric(f"Viento {ciudad_actual.split(',')[0]}", f"{v} km/h")
        
        if v > 35: st.error(f"🚩 ALERTA VIENTO: {v} km/h. Reforzar tutores.")

        cannabis_divider()
        icon_subtitle("seedling", f"Recomendación del Día para: {sistema}")

        if "Maceta" in sistema:
            if t > 33:
                st.warning("🔥 **Calor extremo.** Mover macetas a media sombra por la tarde. Regar 2 veces al día (mañana temprano y atardecer). Usar mulch para retener humedad.")
            elif t < 5:
                st.error("❄️ **Riesgo de helada.** Entrar las macetas adentro o cubrir con tela antihelada. No regar de noche.")
            elif t < 12:
                st.info("🧊 **Fresco.** Reducir riego, el sustrato tarda más en secar. Aprovechar el sol del mediodía.")
            else:
                st.success("✅ **Clima favorable.** Buen día para regar, trasplantar o aplicar fertilizante foliar.")

            if h > 80:
                st.warning("💧 **Humedad alta.** Riesgo de hongos. Separar macetas para mejorar ventilación. No mojar las hojas.")
            if v > 25:
                st.warning(f"💨 **Viento fuerte ({v} km/h).** Proteger con malla cortaviento o reubicar las macetas.")
            if "Invernadero" in sistema:
                st.info("🏡 **Invernadero:** Protegido del viento y lluvia directa. Controlar ventilación interna y temperatura. Abrir ventanas en días calurosos para evitar acumulación de calor y humedad.")

        elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
            if t > 33:
                st.warning("🔥 **Calor extremo.** Regar profundo temprano a la mañana. Aplicar mulch grueso. Evitar fertilizar con sol fuerte.")
            elif t < 5:
                st.error("❄️ **Riesgo de helada.** Cubrir plantas con tela antihelada o campana plástica. Aporcar la base del tallo.")
            elif t < 12:
                st.info("🧊 **Fresco.** Día ideal para enmiendas de suelo y preparación de compost. Riego mínimo.")
            else:
                st.success("✅ **Clima favorable.** Buen momento para regar, aplicar neem preventivo o trasplantar.")

            if h > 80:
                st.warning("💧 **Humedad alta.** Vigilar aparición de oídio y botrytis. Podar hojas bajas para ventilación.")
            if v > 25:
                st.warning(f"💨 **Viento fuerte ({v} km/h).** Revisar tutores y amarres. Reforzar estructura de soporte.")
            if daily and daily['precipitation_probability_max'][0] > 60:
                st.info("🌧️ **Lluvia probable hoy.** No regar. Verificar drenaje del terreno para evitar encharcamiento.")
            if "Invernadero" in sistema:
                st.info("🏡 **Invernadero:** Protegido de lluvias y viento. Controlar ventilación y temperatura interna. En días calurosos, abrir ventanas laterales y cenitales.")

        elif sistema == "Interior Luz":
            if t > 30:
                st.warning("🔥 **Calor exterior alto.** Tu indoor se calentará más. Prendé las luces de noche (20-06hs). Reforzar extracción de aire.")
            elif t < 10:
                st.info("🧊 **Frío exterior.** El indoor perderá calor rápido con luces apagadas. Considerar calefactor en período oscuro.")
            else:
                st.success("✅ **Clima exterior templado.** Buenas condiciones para mantener temperatura estable en el indoor.")

            if vpd < 0.4:
                st.warning("💧 **VPD bajo.** Humedad excesiva en el ambiente. Aumentar extracción y usar deshumidificador si es necesario.")
            elif vpd > 1.6:
                st.warning("🏜️ **VPD alto.** Aire muy seco. Considerar humidificador en vegetativo o reducir temperatura.")
            else:
                st.success(f"✅ **VPD en rango ({vpd} kPa).** Transpiración saludable.")

        elif "Automáticas" in sistema:
            if t > 33:
                st.warning("🔥 **Calor extremo.** Las automáticas sufren estrés rápido. Si están afuera, proveer sombra parcial. Si están indoor, luces de noche.")
            elif t < 5:
                st.error("❄️ **Riesgo de helada.** Las autos no tienen tiempo de recuperarse. Proteger urgente: entrar o cubrir.")
            elif t < 12:
                st.info("🧊 **Fresco.** Reducir riego al mínimo. Las autos en exterior crecen lento con frío, cada día cuenta.")
            else:
                st.success("✅ **Clima favorable.** Buen día para las automáticas. Mantener rutina de riego y nutrición suave.")

            if h > 80:
                st.warning("💧 **Humedad alta.** Las autos son compactas y concentran humedad. Defoliar hojas interiores para ventilación.")
            if v > 25:
                st.warning(f"💨 **Viento fuerte ({v} km/h).** Las automáticas son pequeñas y frágiles. Proteger con cortaviento.")

    cannabis_divider()
    icon_subtitle("seedling", "Recomendaciones Diarias por Cultivo")
    if not st.session_state.cultivos:
        st.info("No tenés cultivos cargados en **Seguimiento de Cultivo**. Agregá al menos uno para ver recomendaciones personalizadas según el clima de hoy.")
    else:
        for idx_dash, cultivo_dash in enumerate(st.session_state.cultivos):
            nombre_d = cultivo_dash["nombre"]
            inicio_d = cultivo_dash["inicio"]
            sistema_d = cultivo_dash["sistema"]
            maceta_d = cultivo_dash.get("maceta_litros")
            dias_d = (datetime.date.today() - inicio_d).days
            etapas_d = obtener_etapas(sistema_d)
            etapa_d = obtener_etapa_actual(dias_d, etapas_d)
            progreso_d = porcentaje_etapa(dias_d, etapa_d)
            nombre_etapa_d = etapa_d["nombre"]
            info_mac = f" · {maceta_d}L" if maceta_d else ""

            with st.expander(f"🌱 {nombre_etapa_d} · {sistema_d}{info_mac}", expanded=(idx_dash == 0)):
                col_izq_d, col_der_d = st.columns([3, 1])
                with col_izq_d:
                    st.progress(progreso_d, text=f"{nombre_etapa_d} — {int(progreso_d*100)}%")
                with col_der_d:
                    ic_s = icon_html("seedling", 20)
                    st.markdown(f'<div class="cultivo-info-right"><div class="cultivo-nombre">{ic_s} {nombre_d}</div><div class="cultivo-dia">Día {dias_d}</div></div>', unsafe_allow_html=True)

                recs = []

                if curr:
                    es_flora = "Floración" in nombre_etapa_d or "Flush" in nombre_etapa_d or "Maduración" in nombre_etapa_d
                    es_veg = "Vegetativo" in nombre_etapa_d or "Plántula" in nombre_etapa_d
                    es_germ = "Germinación" in nombre_etapa_d

                    if es_germ:
                        recs.append("🌱 **Germinación:** Mantener humedad constante. No exponer al sol directo ni al viento.")
                        if t < 18:
                            recs.append(f"🧊 Temp. actual {t}°C — baja para germinar. Buscar un lugar más cálido (22-28°C ideal). Servilleta en lugar abrigado.")
                        elif t > 32:
                            recs.append(f"🔥 Temp. actual {t}°C — alta. Evitar que la semilla se seque. Rociar más seguido.")
                        else:
                            recs.append(f"✅ Temp. actual {t}°C — buena para germinar.")

                    elif es_veg:
                        if "Maceta" in sistema_d:
                            if t > 33:
                                recs.append(f"🔥 **{t}°C — Calor extremo.** Mover a media sombra después de las 12 hs. Regar temprano y al atardecer.")
                                if maceta_d and maceta_d <= 10:
                                    recs.append(f"⚠️ Maceta de {maceta_d}L se calienta rápido. Considerar envolver con tela o elevar del piso.")
                            elif t < 5:
                                recs.append(f"❄️ **{t}°C — Riesgo de helada.** Entrar las macetas o cubrir con tela antihelada. No regar de noche.")
                            elif t < 15:
                                recs.append(f"🧊 **{t}°C — Fresco.** El crecimiento será lento. Reducir riego. Aprovechar horas de sol.")
                            else:
                                recs.append(f"✅ **{t}°C — Temp. favorable.** Buen día para regar, aplicar neem preventivo o hacer LST/topping.")
                            if h > 75:
                                recs.append(f"💧 Humedad {h}% — alta para vegetativo. Separar macetas para mejorar circulación de aire.")
                            if v > 25:
                                recs.append(f"💨 Viento {v} km/h — proteger plantas jóvenes. Reforzar tutores si hiciste LST.")

                        elif sistema_d in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                            if t > 33:
                                recs.append(f"🔥 **{t}°C — Calor extremo.** Regar profundo temprano. Mulch grueso para proteger raíces. Media sombra si es posible.")
                            elif t < 5:
                                recs.append(f"❄️ **{t}°C — Riesgo de helada.** Cubrir con tela antihelada. Aporcar base del tallo.")
                            elif t < 15:
                                recs.append(f"🧊 **{t}°C — Fresco.** Buen día para enmiendas y preparar compost. Riego mínimo.")
                            else:
                                recs.append(f"✅ **{t}°C — Temp. favorable.** Ideal para regar, trasplantar, aplicar purín de ortiga.")
                            if h > 80:
                                recs.append(f"💧 Humedad {h}% — vigilar oídio. Podar hojas bajas para ventilación.")
                            if daily and daily['precipitation_probability_max'][0] > 60:
                                recs.append("🌧️ **Lluvia probable.** No regar hoy. Verificar drenaje del terreno.")

                        elif sistema_d == "Interior Luz":
                            if t > 30:
                                recs.append(f"🔥 **{t}°C exterior.** Tu indoor se calentará más. Prender luces de noche (20-06 hs). Reforzar extracción.")
                            elif t < 10:
                                recs.append(f"🧊 **{t}°C exterior.** El indoor perderá calor con luces apagadas. Considerar calefactor en período oscuro.")
                            else:
                                recs.append(f"✅ **{t}°C exterior** — buenas condiciones para mantener temp. estable en indoor.")
                            if vpd < 0.4:
                                recs.append(f"💧 VPD {vpd} kPa — bajo. Mucha humedad. Aumentar extracción o usar deshumidificador.")
                            elif vpd > 1.4:
                                recs.append(f"🏜️ VPD {vpd} kPa — alto. Aire seco. Considerar humidificador para vegetativo.")
                            else:
                                recs.append(f"✅ VPD {vpd} kPa — rango saludable para vegetativo.")

                        elif "Automáticas" in sistema_d:
                            if t > 33:
                                recs.append(f"🔥 **{t}°C — Calor extremo.** Las autos sufren rápido. Sombra parcial si están afuera. Regar 2 veces al día.")
                            elif t < 5:
                                recs.append(f"❄️ **{t}°C — Helada.** Proteger urgente. Las autos no tienen tiempo de recuperarse del estrés por frío.")
                            elif t < 15:
                                recs.append(f"🧊 **{t}°C — Fresco.** Crecimiento lento. Cada día cuenta en una auto. Buscar más horas de sol.")
                            else:
                                recs.append(f"✅ **{t}°C — Favorable.** Mantener rutina de riego y nutrición suave. Buen día para LST.")
                            if h > 80:
                                recs.append(f"💧 Humedad {h}% — alta. Defoliar hojas interiores para mejorar ventilación.")

                    elif es_flora:
                        if "Maceta" in sistema_d:
                            if t > 33:
                                recs.append(f"🔥 **{t}°C — Calor en floración.** Regar al amanecer y atardecer. El calor puede reducir producción de resina.")
                                if maceta_d and maceta_d <= 10:
                                    recs.append(f"⚠️ Maceta {maceta_d}L: la raíz sufre más el calor. Envolver maceta con tela o cartón para aislar.")
                            elif t < 5:
                                recs.append(f"❄️ **{t}°C — Helada en floración.** Proteger urgente. Los cogollos mojados + frío = botrytis segura.")
                            elif t < 12:
                                recs.append(f"🧊 **{t}°C — Fresco.** Buenas noches frías para colores, pero vigilar humedad sobre cogollos.")
                            else:
                                recs.append(f"✅ **{t}°C — Favorable para floración.** Mantener riego estable. No sobre-fertilizar.")
                            if h > 70:
                                recs.append(f"💧 Humedad {h}% — **ALERTA en floración.** Riesgo de moho en cogollos. Mejorar ventilación urgente. Defoliar si es necesario.")
                            if v > 25:
                                recs.append(f"💨 Viento {v} km/h — los cogollos pesan. Reforzar tutores para que no se quiebren ramas.")

                        elif sistema_d in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                            if t > 33:
                                recs.append(f"🔥 **{t}°C — Calor extremo en flora.** Regar profundo temprano. Media sombra si los cogollos se sienten calientes al tacto.")
                            elif t < 5:
                                recs.append(f"❄️ **{t}°C — Helada en floración.** Cubrir con tela antihelada. Cogollos mojados + frío = botrytis.")
                            elif t < 12:
                                recs.append(f"🧊 **{t}°C — Noches frías.** Puede dar colores morados. Vigilar humedad sobre cogollos, especialmente con rocío matinal.")
                            else:
                                recs.append(f"✅ **{t}°C — Favorable.** Mantener riego y vigilar tricomas con lupa.")
                            if h > 70:
                                recs.append(f"💧 Humedad {h}% — **PELIGRO en flora.** Riesgo de botrytis. Podar hojas que toquen cogollos. Ventilar.")
                            if daily and daily['precipitation_probability_max'][0] > 50:
                                recs.append("🌧️ **Lluvia probable + floración = riesgo de moho.** Cubrir si es posible. Si los cogollos se mojan, sacudir suavemente después de la lluvia.")

                        elif sistema_d == "Interior Luz":
                            if t > 30:
                                recs.append(f"🔥 **{t}°C exterior.** Indoor se calienta. En flora, temp. ideal es 20-26°C. Luces de noche obligatorio.")
                            elif t < 10:
                                recs.append(f"🧊 **{t}°C exterior.** Diferencia de temp. día/noche puede ser grande. Calefactor en período oscuro para mantener 18°C mínimo.")
                            else:
                                recs.append(f"✅ **{t}°C exterior.** Buenas condiciones para mantener indoor estable en floración.")
                            if vpd < 0.4:
                                recs.append(f"💧 VPD {vpd} kPa — bajo. **Peligroso en floración.** Deshumidificador urgente. Riesgo de moho.")
                            elif vpd > 1.6:
                                recs.append(f"🏜️ VPD {vpd} kPa — alto para flora. Puede estresar los cogollos. Bajar temperatura.")
                            elif vpd >= 0.8 and vpd <= 1.2:
                                recs.append(f"✅ VPD {vpd} kPa — rango perfecto para floración.")
                            else:
                                recs.append(f"✅ VPD {vpd} kPa — aceptable para floración.")

                        elif "Automáticas" in sistema_d:
                            if t > 33:
                                recs.append(f"🔥 **{t}°C — Calor extremo.** Las autos en flora necesitan sombra parcial y riego extra.")
                            elif t < 5:
                                recs.append(f"❄️ **{t}°C — Helada.** Proteger los cogollos urgente. Una helada puede destruir semanas de flora.")
                            else:
                                recs.append(f"✅ **{t}°C — Favorable.** Mantener rutina estable. No cambiar nada drásticamente en flora de autos.")
                            if h > 70:
                                recs.append(f"💧 Humedad {h}% — las autos son compactas. Defoliar interior para que el aire circule entre cogollos.")

                        if "Flush" in nombre_etapa_d:
                            recs.append("🚿 **Etapa de flush.** Regar solo con agua sin nutrientes. Lavar sales acumuladas.")
                            if daily and daily['precipitation_probability_max'][0] > 60 and sistema_d not in ["Interior Luz"]:
                                recs.append("🌧️ La lluvia ayuda al flush natural. Dejar que se moje si no hay riesgo de moho.")

                    if "Invernadero" in sistema_d:
                        if t > 30:
                            recs.append("🏡 **Invernadero:** Abrir ventanas y puertas. Riesgo de acumulación de calor y humedad alta.")
                        else:
                            recs.append("🏡 **Invernadero:** Protegido del viento y lluvia. Controlar ventilación interna.")

                if recs:
                    for r in recs:
                        st.markdown(f"- {r}")
                else:
                    st.info("Sin alertas especiales para hoy. Mantener rutina normal de cuidados.")

    cannabis_divider()
    icon_subtitle("clima", "Pronóstico Preventivo (3 Días)")
    if daily:
        cols = st.columns(3)
        for i in range(3):
            with cols[i]:
                ic_cal = icon_html("calendario", 18)
                ic_tmp = icon_html("temp", 18)
                ic_lluv = icon_html("lluvia", 18)
                st.markdown(f'''<div class="forecast-card">
                    <div class="forecast-date">{ic_cal} {daily['time'][i]}</div>
                    <div class="forecast-temp">{ic_tmp} {daily['temperature_2m_min'][i]}° / {daily['temperature_2m_max'][i]}°</div>
                    <div class="forecast-rain">{ic_lluv} Lluvia: {daily['precipitation_probability_max'][i]}%</div>
                </div>''', unsafe_allow_html=True)

    cannabis_divider()
    icon_subtitle("clima", "Radar Meteorológico en Vivo")
    st.markdown(f"Radar de precipitación en tiempo real centrado en **{ciudad_actual}**.")
    radar_url = f"https://embed.windy.com/embed.html?type=map&location=coordinates&metricRain=mm&metricTemp=°C&metricWind=km/h&zoom=8&overlay=radar&product=radar&level=surface&lat={user_lat}&lon={user_lon}&detailLat={user_lat}&detailLon={user_lon}&marker=true&message=true"
    st.components.v1.iframe(radar_url, height=450, scrolling=False)

# --- MÓDULO 2: ASESORAMIENTO POR SISTEMA DE CULTIVO ---
elif menu == "Asesoramiento Cultivo":
    cannabis_banner("asesoramiento")
    mostrar_tutorial("Asesoramiento Cultivo")
    icon_title("asesoramiento", f"Asesoramiento: {sistema}")

    if "Maceta" in sistema:
        if "Invernadero" in sistema:
            icon_subtitle("asesoramiento", "Cultivo en Maceta en Invernadero")
        else:
            icon_subtitle("asesoramiento", "Cultivo en Maceta al Exterior")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Sustrato Recomendado")
            st.markdown("""
            - **Mezcla base:** 40% tierra negra + 30% perlita + 20% humus de lombriz + 10% fibra de coco.
            - **Tamaño mínimo:** 20 litros (vegetativo), 50+ litros (floración).
            - Agregar micorrizas al trasplante para mejorar absorción.
            """)

            st.markdown("#### Riego")
            st.markdown("""
            - Regar cuando los primeros 3 cm de sustrato estén secos.
            - En verano cordobés (35°C+): regar temprano a la mañana o al atardecer.
            - Evitar platos con agua estancada para prevenir hongos en raíces.
            - pH del agua: **6.0 - 6.5**.
            """)

        with col2:
            st.markdown("#### Manejo Ambiental")
            st.markdown("""
            - Rotar la maceta cada 2-3 días para crecimiento parejo.
            - Usar maceta blanca o con aislante: el sol directo calienta las raíces.
            - Proteger del viento Pampero con malla media sombra (30-50%).
            - En heladas: entrar la planta o cubrir con tela antihelada.
            """)

            st.markdown("#### Tips La Carlota")
            st.markdown("""
            - El agua de red local tiende a pH alto (~7.5). Corregir con ácido cítrico.
            - En diciembre-enero, el calor extremo seca las macetas rápido: considerar riego 2 veces al día.
            - Usar mulch (paja, corteza) sobre el sustrato para retener humedad.
            """)

        if "Invernadero" in sistema:
            st.info("🏡 **Ventajas del Invernadero:** Protección contra lluvia directa, viento y granizo. Mayor control de temperatura. Permite extender la temporada de cultivo. Controlar ventilación para evitar exceso de calor y humedad.")

        cannabis_divider()
        icon_subtitle("asesoramiento", "Tiendas Recomendadas para Cultivo en Maceta")
        st.markdown("""
| Tienda | Especialidad | Web |
|--------|-------------|-----|
| Namasté Nutrientes | Fertilizantes orgánicos y biominerales | [namastenutrientes.com](https://namastenutrientes.com) |
| Top Crop | Línea completa de nutrición vegetal | [topcropfert.com/ar](https://www.topcropfert.com/ar/) |
| Ecomambo | Humus, micorrizas, enmiendas orgánicas | [ecomambo.com.ar](https://ecomambo.com.ar) |
| UP! Growshop | Macetas textiles, sustratos, perlita | [upgrowshop.com](https://www.upgrowshop.com) |
| Terrafertil | Sustratos, perlita, vermiculita | [terrafertil.com](https://www.terrafertil.com) |
        """)
        st.markdown("#### 📞 Contactos y Redes Sociales")
        st.markdown("""
- **Namasté Nutrientes** — IG: [@namastenutrientes](https://instagram.com/namastenutrientes) · 📧 contacto@namaste.ar
- **Top Crop** — IG: [@topcropoficial](https://instagram.com/topcropoficial) · 📧 info@topcropfert.com
- **Ecomambo** — IG: [@ecomambo](https://instagram.com/ecomambo) · [WhatsApp](https://wa.me/5491132350716) · 📧 info@ecomambo.com.ar
- **UP! Growshop** — IG: [@upgrowshop](https://instagram.com/upgrowshop) · [WhatsApp](https://wa.me/5491123298811) · Envíos a todo el país
- **Terrafertil** — IG: [@terrafertilsustratos](https://instagram.com/terrafertilsustratos) · 📱 0810-333-TERRA (83772)
        """)

    elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
        if "Invernadero" in sistema:
            icon_subtitle("asesoramiento", "Cultivo en Tierra en Invernadero")
        else:
            icon_subtitle("asesoramiento", "Cultivo en Tierra Madre (Suelo Directo)")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Preparación del Suelo")
            st.markdown("""
            - Cavar un pozo de **60x60x60 cm** mínimo y rellenar con mezcla enriquecida.
            - Mezclar tierra del lugar con compost maduro, humus y perlita.
            - El suelo arcilloso de La Carlota retiene mucha agua: agregar perlita para drenaje.
            - Incorporar harina de hueso y ceniza de madera como enmiendas de fondo.
            """)

            st.markdown("#### Riego")
            st.markdown("""
            - La tierra madre retiene más humedad que las macetas, regar menos frecuente.
            - Riego profundo 2-3 veces por semana según clima.
            - Considerar riego por goteo para eficiencia.
            - En época de lluvias, vigilar que no se encharque la zona.
            """)

        with col2:
            st.markdown("#### Ventajas del Sistema")
            st.markdown("""
            - Las raíces no tienen límite: plantas más grandes y productivas.
            - Menor estrés térmico: el suelo amortigua temperaturas extremas.
            - La microbiología del suelo aporta nutrientes naturalmente.
            - Requiere menos fertilizantes que en maceta.
            """)

            st.markdown("#### Precauciones")
            st.markdown("""
            - Proteger de animales (perros, liebres) con cerco perimetral.
            - Revisar napa freática: si está alta, elevar el cantero.
            - Mantener distancia entre plantas (1.5 m mínimo) para circulación de aire.
            - Aplicar neem preventivo cada 15 días en primavera-verano.
            """)

        if "Invernadero" in sistema:
            st.info("🏡 **Ventajas del Invernadero:** Protección contra lluvia, viento y granizo. Mejor control de temperatura y humedad. Menos presión de plagas externas. Requiere buena ventilación para evitar acumulación de calor.")

        cannabis_divider()
        icon_subtitle("asesoramiento", "Tiendas Recomendadas para Cultivo en Tierra")
        st.markdown("""
| Tienda | Especialidad | Web |
|--------|-------------|-----|
| Namasté Nutrientes | Fertilizantes orgánicos, humus, compost | [namastenutrientes.com](https://namastenutrientes.com) |
| Ecomambo | Enmiendas orgánicas, harina de hueso, guano | [ecomambo.com.ar](https://ecomambo.com.ar) |
| Top Crop | Nutrición orgánica y mineral para suelo | [topcropfert.com/ar](https://www.topcropfert.com/ar/) |
| Terrafertil | Sustratos, perlita, vermiculita a granel | [terrafertil.com](https://www.terrafertil.com) |
| UP! Growshop | Malla antigranizo, riego por goteo, cercos | [upgrowshop.com](https://www.upgrowshop.com) |
        """)
        st.markdown("#### 📞 Contactos y Redes Sociales")
        st.markdown("""
- **Namasté Nutrientes** — IG: [@namastenutrientes](https://instagram.com/namastenutrientes) · 📧 contacto@namaste.ar
- **Ecomambo** — IG: [@ecomambo](https://instagram.com/ecomambo) · [WhatsApp](https://wa.me/5491132350716) · 📧 info@ecomambo.com.ar
- **Top Crop** — IG: [@topcropoficial](https://instagram.com/topcropoficial) · 📧 info@topcropfert.com
- **Terrafertil** — IG: [@terrafertilsustratos](https://instagram.com/terrafertilsustratos) · 📱 0810-333-TERRA (83772) · 📧 ventas@terrafertil.com
- **UP! Growshop** — IG: [@upgrowshop](https://instagram.com/upgrowshop) · [WhatsApp](https://wa.me/5491123298811) · Envíos a todo el país
        """)

    elif sistema == "Interior Luz":
        icon_subtitle("asesoramiento", "Cultivo Indoor con Iluminación Artificial")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Iluminación")
            st.markdown("""
            - **Vegetativo:** 18 hs luz / 6 hs oscuridad.
            - **Floración:** 12 hs luz / 12 hs oscuridad estrictas.
            - LED recomendado: 200-400W para 1 m² de cultivo.
            - Mantener distancia de la luz según fabricante (generalmente 30-50 cm).
            """)

            st.markdown("#### Sustrato y Nutrición")
            st.markdown("""
            - Mezcla inerte con control total: fibra de coco + perlita (70/30).
            - Fertilización completa con cada riego (fertirrigación).
            - Controlar EC (electroconductividad): 0.8-1.2 en vege, 1.4-1.8 en flora.
            - pH estricto: **5.8 - 6.2**.
            """)

        with col2:
            st.markdown("#### Control Ambiental")
            st.markdown("""
            - Temperatura ideal: 24-28°C con luces encendidas, 18-22°C apagadas.
            - Humedad: 60-70% en vegetativo, 40-50% en floración.
            - VPD objetivo: 0.8-1.2 kPa.
            - Ventilación: extractor + ventilador oscilante obligatorios.
            - Filtro de carbón activado para control de olores.
            """)

            st.markdown("#### Tips Indoor")
            st.markdown("""
            - En verano, el indoor en La Carlota sufre calor: usar luces en horario nocturno.
            - Técnicas de entrenamiento (LST, SCROG) maximizan el rendimiento por m².
            - Limpiar bandejas y herramientas con agua oxigenada para evitar patógenos.
            - Timer digital obligatorio para precisión en fotoperiodo.
            """)

        cannabis_divider()
        icon_subtitle("asesoramiento", "Tiendas Recomendadas para Indoor")
        st.markdown("""
| Tienda | Especialidad | Web |
|--------|-------------|-----|
| UP! Growshop | Paneles LED, carpas, extractores | [upgrowshop.com](https://www.upgrowshop.com) |
| Insativa | Luminarias LED Samsung Horticulture | [insativa.com.ar](https://www.insativa.com.ar) |
| Agroled | Paneles Growtech y equipamiento LED | [agroled.com.ar](https://www.agroled.com.ar) |
| Namasté Nutrientes | Fertilizantes para indoor y fibra de coco | [namastenutrientes.com](https://namastenutrientes.com) |
| Top Crop | Línea completa indoor: nutrientes y aditivos | [topcropfert.com/ar](https://www.topcropfert.com/ar/) |
| Ecomambo | Insecticidas ecológicos, enraizantes | [ecomambo.com.ar](https://ecomambo.com.ar) |
        """)
        st.markdown("#### 📞 Contactos y Redes Sociales")
        st.markdown("""
- **UP! Growshop** — IG: [@upgrowshop](https://instagram.com/upgrowshop) · [WhatsApp](https://wa.me/5491123298811) · Envíos a todo el país
- **Insativa** — [WhatsApp](https://wa.me/5491157379179) · 📧 info@insativa.com.ar · Salta 3518, Villa Ballester
- **Agroled** — [WhatsApp](https://wa.me/5491128727061) · [agroled.com.ar/contacto](https://www.agroled.com.ar/contacto/)
- **Namasté Nutrientes** — IG: [@namastenutrientes](https://instagram.com/namastenutrientes) · 📧 contacto@namaste.ar
- **Top Crop** — IG: [@topcropoficial](https://instagram.com/topcropoficial) · 📧 info@topcropfert.com
- **Ecomambo** — IG: [@ecomambo](https://instagram.com/ecomambo) · [WhatsApp](https://wa.me/5491132350716) · 📧 info@ecomambo.com.ar
        """)

    elif "Automáticas" in sistema:
        icon_subtitle("asesoramiento", "Cultivo de Variedades Automáticas")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Características Clave")
            st.markdown("""
            - Florecen solas entre las **semanas 3-4** de vida, sin cambio de fotoperiodo.
            - Ciclo total: **8 a 11 semanas** desde germinación.
            - No se trasplantan: sembrar en maceta definitiva desde el inicio.
            - Tamaño compacto: ideal para espacios reducidos o discreción.
            """)

            st.markdown("#### Nutrición")
            st.markdown("""
            - Usar **dosis reducida (50-70%)** respecto a fotodependientes.
            - Son sensibles al exceso de fertilizante: menos es más.
            - Empezar con nutrientes suaves a partir de la semana 2.
            - No hacer lavado de raíces agresivo: mejor prevenir con dosis bajas.
            """)

        with col2:
            st.markdown("#### Fotoperiodo")
            st.markdown("""
            - Indoor: **20 hs luz / 4 hs oscuridad** durante todo el ciclo.
            - Exterior: aprovechar todo el sol disponible.
            - No dependen del fotoperiodo, pero más luz = más producción.
            """)

            st.markdown("#### Errores Comunes")
            st.markdown("""
            - **No trasplantar:** el estrés del trasplante les quita días de un ciclo ya corto.
            - **No podar en exceso:** técnicas agresivas (topping) pueden reducir el rendimiento.
            - **LST suave** es la mejor técnica de entrenamiento para autos.
            - Germinar en maceta definitiva de 15-20 litros.
            """)

        cannabis_divider()
        icon_subtitle("asesoramiento", "Tiendas Recomendadas para Automáticas")
        st.markdown("""
| Tienda | Especialidad | Web |
|--------|-------------|-----|
| Namasté Nutrientes | Fertilizantes suaves ideales para autos | [namastenutrientes.com](https://namastenutrientes.com) |
| Top Crop | Línea de nutrición con dosis ajustables | [topcropfert.com/ar](https://www.topcropfert.com/ar/) |
| UP! Growshop | Macetas definitivas, sustratos livianos | [upgrowshop.com](https://www.upgrowshop.com) |
| Ecomambo | Enmiendas orgánicas suaves para autos | [ecomambo.com.ar](https://ecomambo.com.ar) |
| Terrafertil | Sustratos livianos, perlita, vermiculita | [terrafertil.com](https://www.terrafertil.com) |
        """)
        st.markdown("#### 📞 Contactos y Redes Sociales")
        st.markdown("""
- **Namasté Nutrientes** — IG: [@namastenutrientes](https://instagram.com/namastenutrientes) · 📧 contacto@namaste.ar
- **Top Crop** — IG: [@topcropoficial](https://instagram.com/topcropoficial) · 📧 info@topcropfert.com
- **UP! Growshop** — IG: [@upgrowshop](https://instagram.com/upgrowshop) · [WhatsApp](https://wa.me/5491123298811) · Envíos a todo el país
- **Ecomambo** — IG: [@ecomambo](https://instagram.com/ecomambo) · [WhatsApp](https://wa.me/5491132350716) · 📧 info@ecomambo.com.ar
- **Terrafertil** — IG: [@terrafertilsustratos](https://instagram.com/terrafertilsustratos) · 📱 0810-333-TERRA (83772)
        """)

    cannabis_divider()
    st.info(f"Estos consejos están adaptados para el clima y suelo de **La Carlota, Córdoba** y el sistema **{sistema}**.")

# --- MÓDULO 3: CALCULADORA DE RIEGO ADAPTATIVA ---
elif menu == "Calculadora Riego":
    cannabis_banner("riego")
    mostrar_tutorial("Calculadora Riego")
    icon_title("riego", f"Nutrición: {sistema}")
    litros = st.number_input("Litros de agua", 1.0, 100.0, 5.0)
    fase = st.selectbox("Etapa", ["Vegetativo", "Pre-Flora", "Floración Plena"])
    marca = st.radio("Línea", ["Namasté", "Top Crop", "Dosis Criolla (50%)"])
    
    dosis = 2.0 if fase == "Vegetativo" else 4.0
    if "Automáticas" in sistema: dosis *= 0.7
    if "Criolla" in marca: dosis *= 0.5
    
    st.success(f"✅ Mezcla final: **{round(litros * dosis, 1)} ml** de fertilizante base.")

    cannabis_divider()
    icon_subtitle("riego", "Recomendaciones de Riego para Tus Cultivos Activos")

    if "cultivos" not in st.session_state or not st.session_state.cultivos:
        st.info("No tenés cultivos cargados en Seguimiento de Cultivo. Agregá al menos uno para recibir recomendaciones personalizadas de riego.")
    else:
        mes_actual = datetime.date.today().month
        curr_clima, _ = fetch_weather()
        temp_actual = curr_clima['temperature_2m'] if curr_clima else 25
        hum_actual = curr_clima['relative_humidity_2m'] if curr_clima else 50

        for idx_c, cultivo in enumerate(st.session_state.cultivos):
            nombre_c = cultivo["nombre"]
            inicio_c = cultivo["inicio"]
            sistema_c = cultivo["sistema"]
            maceta_c = cultivo.get("maceta_litros")
            dias = (datetime.date.today() - inicio_c).days

            if "Automáticas" in sistema_c:
                if dias < 7: etapa_nombre = "Germinación"
                elif dias < 18: etapa_nombre = "Plántula"
                elif dias < 32: etapa_nombre = "Vegetativo"
                elif dias < 42: etapa_nombre = "Pre-Floración"
                elif dias < 56: etapa_nombre = "Floración Temprana"
                elif dias < 70: etapa_nombre = "Floración Media"
                elif dias < 84: etapa_nombre = "Maduración"
                else: etapa_nombre = "Flush y Cosecha"
            elif sistema_c == "Interior Luz":
                if dias < 7: etapa_nombre = "Germinación"
                elif dias < 21: etapa_nombre = "Plántula"
                elif dias < 42: etapa_nombre = "Vegetativo Temprano"
                elif dias < 63: etapa_nombre = "Vegetativo Avanzado"
                elif dias < 77: etapa_nombre = "Cambio a Floración"
                elif dias < 98: etapa_nombre = "Floración Temprana"
                elif dias < 119: etapa_nombre = "Floración Media"
                elif dias < 140: etapa_nombre = "Maduración"
                else: etapa_nombre = "Flush y Cosecha"
            else:
                if dias < 10: etapa_nombre = "Germinación"
                elif dias < 25: etapa_nombre = "Plántula"
                elif dias < 50: etapa_nombre = "Vegetativo Temprano"
                elif dias < 90: etapa_nombre = "Vegetativo Avanzado"
                elif dias < 110: etapa_nombre = "Pre-Floración"
                elif dias < 140: etapa_nombre = "Floración Temprana"
                elif dias < 170: etapa_nombre = "Floración Media"
                elif dias < 200: etapa_nombre = "Maduración"
                else: etapa_nombre = "Flush y Cosecha"

            info_mac = f" · Maceta: {maceta_c}L" if maceta_c else ""
            with st.expander(f"💧 {etapa_nombre} · {sistema_c}{info_mac}", expanded=(idx_c == 0)):
                col_izq_r, col_der_r = st.columns([3, 1])
                with col_der_r:
                    ic_r = icon_html("riego", 20)
                    st.markdown(f'<div class="cultivo-info-right"><div class="cultivo-nombre">{ic_r} {nombre_c}</div><div class="cultivo-dia">Día {dias}</div></div>', unsafe_allow_html=True)
                volumen = ""
                frecuencia = ""
                ph_rec = ""
                agua_tipo = ""
                nutricion_riego = ""
                tecnica = ""
                errores = ""
                clima_ajuste = ""

                if etapa_nombre == "Germinación":
                    volumen = "Mínimo: solo rociar con pulverizador. 10-30 ml por aplicación."
                    frecuencia = "Mantener húmedo constantemente. Rociar 2-3 veces por día si se seca la superficie."
                    ph_rec = "pH 6.0-6.5. Si usás agua de red de La Carlota, bajar con vinagre o ácido cítrico (1-2 gotas por litro)."
                    agua_tipo = "Agua reposada 24 hs (evaporar cloro). Tibia, no fría. Ideal: agua de lluvia si tenés."
                    nutricion_riego = "No agregar ningún nutriente al agua. La semilla tiene reservas propias."
                    tecnica = "Usar rociador/pulverizador. Nunca chorro directo sobre la semilla. Si usás método servilleta, mantener húmeda sin charco."
                    errores = "No encharcar. El exceso de agua pudre la semilla antes de germinar. La servilleta debe estar húmeda, no empapada."

                elif etapa_nombre == "Plántula":
                    volumen = "50-150 ml por riego según tamaño del recipiente."
                    frecuencia = "Cada 2-3 días. Dejar secar la superficie entre riegos (primer cm de sustrato seco al tacto)."
                    ph_rec = "pH 6.0-6.5. El agua de La Carlota suele estar en 7.2-7.8, corregir siempre."
                    agua_tipo = "Agua reposada 24 hs. Temperatura ambiente (20-25°C). No usar agua fría de canilla directo."
                    nutricion_riego = "Solo agua limpia. Si el sustrato tiene humus, no hace falta nada más. Máximo: té de humus al 25% de dosis normal."
                    tecnica = "Regar en círculo a 3-5 cm del tallo, no encima. Esto obliga a las raíces a expandirse buscando agua."
                    errores = "Sobre-riego = causa #1 de muerte en plántulas. Si las hojas se ponen amarillas y el sustrato está húmedo, estás regando de más. Mejor menos que más."
                    if "Maceta" in sistema_c and maceta_c:
                        if maceta_c <= 3:
                            volumen = f"Maceta {maceta_c}L: 50-80 ml por riego. Muy poca agua, la maceta es chica."
                        elif maceta_c <= 7:
                            volumen = f"Maceta {maceta_c}L: 80-150 ml por riego. Regar alrededor del tallo en círculo pequeño."
                        else:
                            volumen = f"Maceta {maceta_c}L: 100-200 ml por riego, solo en la zona central. No mojar todo el sustrato, la plántula no lo necesita."

                elif etapa_nombre in ["Vegetativo Temprano", "Vegetativo"]:
                    volumen = "10-20% del volumen de la maceta por riego."
                    frecuencia = "Cada 2-3 días en clima templado. En verano La Carlota (35°C+), puede ser diario."
                    ph_rec = "pH 6.0-6.5. Corregir agua de red con ácido cítrico o vinagre de manzana."
                    agua_tipo = "Agua reposada 24 hs. En verano, cuidar que no esté caliente por estar al sol. Ideal: 20-22°C."
                    nutricion_riego = "Empezar fertilización con N alto. Alternar: un riego con nutrientes, uno solo con agua. Opciones naturales: purín de ortiga (1:10), té de humus, guano diluido."
                    tecnica = "Regar lento y parejo por toda la superficie del sustrato. Dejar que drene un 10-15% por abajo (run-off). Esto previene acumulación de sales."
                    errores = "No regar por encima de las hojas en exterior a pleno sol (efecto lupa = quemaduras). Regar temprano (antes de las 9 am) o al atardecer."
                    if "Maceta" in sistema_c and maceta_c:
                        if maceta_c <= 5:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.15, 1)}-{round(maceta_c * 0.2, 1)} litros por riego. Se seca rápido, revisar diario."
                            frecuencia = "Cada 1-2 días en verano. La maceta chica se seca rápido con calor."
                        elif maceta_c <= 15:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.15, 1)}-{round(maceta_c * 0.2, 1)} litros por riego."
                            frecuencia = "Cada 2-3 días. Levantar la maceta para sentir el peso: liviana = regar."
                        elif maceta_c <= 25:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.15, 1)}-{round(maceta_c * 0.2, 1)} litros por riego."
                            frecuencia = "Cada 2-4 días. Más sustrato = más retención. Meter el dedo 3 cm: si está seco, regar."
                        else:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.15, 1)}-{round(maceta_c * 0.2, 1)} litros por riego."
                            frecuencia = "Cada 3-5 días. Maceta grande retiene mucha humedad. Cuidado con el sobre-riego."
                    elif sistema_c in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                        volumen = "5-10 litros por planta, riego profundo."
                        frecuencia = "Cada 3-5 días. La tierra madre retiene mejor la humedad. Usar mulch para conservar."
                        tecnica = "Riego profundo: lento y abundante para que el agua llegue a las raíces profundas. Mejor que muchos riegos superficiales."
                    elif sistema_c == "Interior Luz":
                        tecnica = "Regar hasta obtener 10-15% de run-off. Medir pH y EC del run-off para monitorear la salud de las raíces."

                elif etapa_nombre == "Vegetativo Avanzado":
                    volumen = "15-25% del volumen de la maceta por riego."
                    frecuencia = "Cada 1-3 días según clima. Planta grande = más consumo."
                    ph_rec = "pH 6.0-6.5. Medir siempre antes de regar. La planta es grande y cualquier bloqueo se nota rápido."
                    agua_tipo = "Agua reposada. Si es posible, mezclar con agua de lluvia (50/50) para mejorar calidad."
                    nutricion_riego = "N alto + inicio de P. Purín de ortiga + harina de hueso diluida. O fertilizante completo de vegetativo. Riego alterno: nutrientes/agua limpia."
                    tecnica = "Regar toda la superficie de forma pareja. El run-off debe salir limpio. Si sale oscuro o con olor, hay acumulación de sales: hacer flush."
                    errores = "En La Carlota, el verano seca rápido las macetas. Si las hojas se caen al mediodía pero se recuperan a la noche, necesita más agua o riego más frecuente."
                    if "Maceta" in sistema_c and maceta_c:
                        if maceta_c <= 10:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.2, 1)}-{round(maceta_c * 0.25, 1)} litros. Planta grande en maceta chica = riego diario en verano."
                            frecuencia = "Posiblemente todos los días en verano. La planta consume mucho y la maceta se seca rápido."
                        elif maceta_c <= 20:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.2, 1)}-{round(maceta_c * 0.25, 1)} litros por riego."
                            frecuencia = "Cada 1-2 días. Revisar peso de la maceta."
                        else:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.15, 1)}-{round(maceta_c * 0.2, 1)} litros por riego."
                            frecuencia = "Cada 2-3 días. Sustrato amplio retiene bien."
                    elif sistema_c in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                        volumen = "10-20 litros por planta por riego."
                        frecuencia = "Cada 3-5 días. Riego profundo. Mulch grueso (5-10 cm de paja) para conservar humedad."
                    elif sistema_c == "Interior Luz":
                        frecuencia = "Cada 1-2 días. Controlar el peso de la maceta. Medir EC del run-off (debe ser similar a la de entrada)."

                elif etapa_nombre in ["Pre-Floración", "Cambio a Floración"]:
                    volumen = "15-20% del volumen de la maceta."
                    frecuencia = "Mantener riego constante y regular. No cambiar bruscamente la frecuencia."
                    ph_rec = "pH 6.0-6.5. Ir subiendo ligeramente hacia 6.3-6.5 para favorecer la absorción de P y K."
                    agua_tipo = "Agua reposada, temperatura ambiente. Evitar agua fría que estrese las raíces."
                    nutricion_riego = "Transición: reducir N, aumentar P y K. Melaza (1 cucharada por litro) en cada riego para alimentar microvida. Harina de hueso para P, ceniza de madera para K."
                    tecnica = "Riego parejo, sin mojar follaje ni futuros sitios de cogollos. Regar por la base siempre."
                    errores = "No estresar con sequía ni encharcamiento en esta etapa. El estrés hídrico puede causar hermafroditismo. Mantener constancia."
                    if "Maceta" in sistema_c and maceta_c:
                        volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.17, 1)}-{round(maceta_c * 0.22, 1)} litros por riego."
                    elif "Automáticas" in sistema_c:
                        nutricion_riego = "Inicio suave de nutrientes de floración. Las autos entran solas en flora, no estresar. Melaza + guano fructífero diluido."

                elif etapa_nombre in ["Floración Temprana", "Floración"]:
                    volumen = "15-20% del volumen de la maceta."
                    frecuencia = "Regular y constante. No dejar secar demasiado entre riegos."
                    ph_rec = "pH 6.2-6.5. Rango ligeramente más alto para favorecer absorción de P (fósforo) y K (potasio)."
                    agua_tipo = "Agua reposada 24 hs. No mojar cogollos NUNCA (riesgo de moho). Solo regar la base."
                    nutricion_riego = "P y K altos, N bajo. Melaza en cada riego (1 cucharada/litro). Harina de hueso (P), ceniza de madera (K), guano de murciélago fructífero. Alternar nutrientes/agua limpia."
                    tecnica = "Regar lento por la base. Si la planta es grande, regar en 2-3 pasadas para que el sustrato absorba bien. No dejar agua estancada en el plato."
                    errores = "NUNCA mojar los cogollos. Si llueve en exterior, sacudir suavemente después. Si se mojan de noche, riesgo alto de botrytis (moho gris)."
                    if "Maceta" in sistema_c and maceta_c:
                        if maceta_c <= 10:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.2, 1)}-{round(maceta_c * 0.25, 1)} litros. Raíces al tope, regar frecuente."
                            frecuencia = "Cada 1-2 días. La planta en flora consume mucho. Si la maceta se seca en un día, regar diario."
                        elif maceta_c <= 20:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.18, 1)}-{round(maceta_c * 0.22, 1)} litros."
                            frecuencia = "Cada 1-3 días. Controlar peso de maceta."
                        else:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.15, 1)}-{round(maceta_c * 0.2, 1)} litros."
                            frecuencia = "Cada 2-3 días. Buen volumen de sustrato."
                    elif sistema_c in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                        volumen = "10-25 litros por planta. Riego profundo."
                        tecnica = "Riego profundo 2-3 veces por semana. Mulch obligatorio para conservar humedad. No regar de noche si hay rocío (suma humedad = moho)."
                    elif sistema_c == "Interior Luz":
                        tecnica = "Regar al inicio del período de luz. Mantener humedad ambiental baja (40-50%). Run-off: medir EC para detectar acumulación."
                    elif "Automáticas" in sistema_c:
                        nutricion_riego = "Flora completa: P+K altos. Las autos responden bien a melaza + guano fructífero. Dosis moderadas (70% de lo recomendado)."

                elif etapa_nombre == "Floración Media":
                    volumen = "15-20% del volumen de la maceta."
                    frecuencia = "Constante. No cambiar el patrón de riego ahora."
                    ph_rec = "pH 6.2-6.5. Constancia es clave."
                    agua_tipo = "Agua reposada, limpia. Si notás costras blancas en la superficie del sustrato, hay acumulación de sales."
                    nutricion_riego = "Máximo P y K. Potasio extra: ceniza de madera (1 cucharada por 5L). Melaza en cada riego. Si usás fertilizante comercial, dosis completa de floración."
                    tecnica = "Riego por base exclusivamente. Si los cogollos son muy densos, asegurar buena ventilación después de regar para evitar humedad atrapada."
                    errores = "Si ves puntas quemadas = exceso de sales. Hacer flush suave (3x volumen de maceta con agua limpia pH 6.3). Si ves hojas amarilleando desde abajo = normal, la planta consume reservas."
                    if "Maceta" in sistema_c and maceta_c:
                        if maceta_c <= 10:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.2, 1)}-{round(maceta_c * 0.25, 1)} litros. Raíces copadas, posiblemente riego diario."
                        elif maceta_c <= 20:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.18, 1)}-{round(maceta_c * 0.22, 1)} litros."
                        else:
                            volumen = f"Maceta {maceta_c}L: {round(maceta_c * 0.15, 1)}-{round(maceta_c * 0.2, 1)} litros."
                    elif sistema_c in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                        volumen = "15-25 litros por planta. La planta está en máxima producción."
                        errores = "Si llueve sobre cogollos densos: sacudir suavemente cada rama. Inspeccionar por dentro buscando moho."

                elif etapa_nombre in ["Maduración", "Floración Tardía / Maduración"]:
                    volumen = "Reducir gradualmente. 10-15% del volumen de la maceta."
                    frecuencia = "Espaciar los riegos. Cada 3-4 días si se empieza flush."
                    ph_rec = "pH 6.0-6.5. Solo agua limpia si estás haciendo flush."
                    agua_tipo = "Agua limpia sin nutrientes para flush. Agua de lluvia ideal. Reposada 24 hs mínimo."
                    nutricion_riego = "FLUSH: dejar de fertilizar. Solo agua limpia las últimas 1-2 semanas. Esto limpia sales del sustrato y mejora el sabor final."
                    tecnica = "Regar con 3x el volumen de la maceta en agua limpia para hacer flush. Después, regar normal solo con agua. Las hojas van a amarillear: es lo esperado."
                    errores = "No agregar nutrientes en flush. Si las hojas no amarillean durante el flush, puede haber acumulación de N en el sustrato. Extender el flush unos días más."
                    if "Maceta" in sistema_c and maceta_c:
                        if maceta_c <= 10:
                            tecnica = f"Maceta {maceta_c}L: Flush rápido, 3-5 días de solo agua. En maceta chica se limpia más rápido. Regar con {round(maceta_c * 3, 0)} litros de agua limpia para el flush inicial."
                        elif maceta_c <= 20:
                            tecnica = f"Maceta {maceta_c}L: Flush de 7-10 días. Regar con {round(maceta_c * 3, 0)} litros de agua limpia para lavar sales. Después solo agua normal."
                        else:
                            tecnica = f"Maceta {maceta_c}L: Flush de 10-14 días. Regar con {round(maceta_c * 3, 0)} litros para el lavado inicial. Más sustrato = más tiempo de limpieza."
                    elif sistema_c in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                        tecnica = "En tierra madre el flush es menos efectivo. Dejar de fertilizar 2-3 semanas antes del corte. Regar solo con agua limpia. Las lluvias naturales ayudan."
                    elif "Automáticas" in sistema_c:
                        nutricion_riego = "Flush corto de 5-7 días. Las autos maduran rápido, no extender demasiado. Solo agua limpia."

                elif etapa_nombre == "Flush y Cosecha":
                    volumen = "Reducir al mínimo. Dejar de regar 1-2 días antes del corte."
                    frecuencia = "Solo si el sustrato está muy seco. Idealmente, cortar con sustrato seco."
                    ph_rec = "pH no importa en esta etapa. Solo agua limpia si regás."
                    agua_tipo = "Agua limpia, sin nada."
                    nutricion_riego = "Ningún nutriente. Solo agua si es necesario."
                    tecnica = "Dejar secar el sustrato antes de cortar. Cosechar por la mañana temprano cuando los terpenos están más concentrados."
                    errores = "No regar el día del corte. Sustrato húmedo = secado más lento y riesgo de moho."

                col_riego1, col_riego2 = st.columns(2)
                with col_riego1:
                    st.markdown("#### Volumen de Agua")
                    st.markdown(volumen if volumen else "Según necesidad del sustrato.")
                    st.markdown("#### Frecuencia")
                    st.markdown(frecuencia if frecuencia else "Revisar humedad del sustrato.")
                    st.markdown("#### pH Recomendado")
                    st.markdown(ph_rec if ph_rec else "pH 6.0-6.5 como regla general.")
                with col_riego2:
                    st.markdown("#### Tipo de Agua")
                    st.markdown(agua_tipo if agua_tipo else "Agua reposada 24 hs.")
                    st.markdown("#### Nutrición en el Riego")
                    st.markdown(nutricion_riego if nutricion_riego else "Según plan de fertilización.")
                    st.markdown("#### Técnica de Riego")
                    st.markdown(tecnica if tecnica else "Regar lento y parejo.")

                if errores:
                    st.error(f"**Errores comunes a evitar:** {errores}")

                if temp_actual > 33:
                    st.warning(f"🌡️ **Alerta calor ({temp_actual}°C):** Aumentar frecuencia de riego. Regar temprano y al atardecer. Evitar regar al mediodía. Considerar mulch para retener humedad.")
                elif temp_actual > 28:
                    st.info(f"🌡️ Temperatura actual {temp_actual}°C: Puede necesitar riego más frecuente. Revisar el sustrato al mediodía.")
                elif temp_actual < 10:
                    st.warning(f"🌡️ **Frío ({temp_actual}°C):** Reducir riego. Las raíces absorben menos con frío. Regar solo por la mañana para que seque durante el día.")
                if hum_actual > 70:
                    st.warning(f"💨 **Humedad alta ({hum_actual}%):** Espaciar riegos. El sustrato tarda más en secar. Cuidado con hongos en el sustrato.")
                elif hum_actual < 30:
                    st.info(f"💨 Humedad baja ({hum_actual}%): El sustrato se seca más rápido. Aumentar frecuencia de riego si es necesario.")

# --- MÓDULO 3: DIAGNÓSTICO & PLAGAS ---
elif menu == "Diagnóstico & Plagas":
    cannabis_banner("diagnostico")
    mostrar_tutorial("Diagnóstico & Plagas")
    icon_title("diagnostico", "Salud Vegetal y Prevención")
    
    mes = datetime.date.today().month
    if mes in [12, 1, 2]: st.error("⚠️ Temporada de Orugas y Arañuela en Córdoba.")
    elif mes in [3, 4, 5]: st.warning("⚠️ Riesgo de Oídio y Botrytis por rocío nocturno.")
    elif mes in [6, 7, 8]: st.info("🧊 Invierno: menor presión de plagas, pero vigilar hongos por humedad.")
    elif mes in [9, 10, 11]: st.warning("🌱 Primavera: pulgones y trips aparecen con el calor. Prevención temprana.")

    cannabis_divider()

    zona = st.radio("¿Zona afectada?", ["Hojas Viejas (Abajo)", "Hojas Nuevas (Arriba)", "Tallos y Ramas", "Raíces y Base", "Toda la Planta"])
    sintoma = st.selectbox("Síntoma", [
        "Amarilleamiento uniforme",
        "Puntas y bordes quemados",
        "Manchas óxido/bronce",
        "Hojas en garra (hacia abajo)",
        "Hojas en garra (hacia arriba)",
        "Manchas blancas (polvo)",
        "Puntos blancos o telarañas",
        "Agujeros en hojas",
        "Tallos púrpuras",
        "Moho gris en cogollos",
        "Mosquitas en el sustrato"
    ])

    cannabis_divider_mini()

    diagnostico = ""
    remedio_casero = ""
    remedio_sistema = ""
    video_url = ""

    if zona == "Hojas Viejas (Abajo)":
        if "Amarilleamiento" in sintoma:
            diagnostico = "**Deficiencia de Nitrógeno (N).** La planta mueve el N de hojas viejas a las nuevas. Común en vegetativo avanzado."
            remedio_casero = """
            - **Té de humus:** Remojar 1 kg de humus de lombriz en 10 litros de agua 24-48 hs. Colar y regar.
            - **Agua de lentejas germinadas:** Remojar lentejas 48 hs, usar el agua de remojo para regar (rico en enzimas y N).
            - **Ortiga fermentada (purín):** Fermentar 1 kg de ortiga en 10 litros de agua por 7-10 días. Diluir 1:10 y regar.
            - **Café usado:** Esparcir borra de café seca sobre el sustrato (libera N lentamente).
            """
            video_url = "https://www.youtube.com/results?search_query=deficiencia+nitrogeno+cannabis+solucion+casera"
            if "Maceta" in sistema:
                remedio_sistema = "Aplicar humus líquido cada 3 días. Si es urgente, usar fertilizante con N alto (ej: Namasté Veg). Revisar que la maceta no esté subdimensionada."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Incorporar compost maduro alrededor de la base. El suelo de La Carlota suele necesitar aportes orgánicos periódicos. Aplicar purín de ortiga directo al suelo."
            elif sistema == "Interior Luz":
                remedio_sistema = "Aumentar dosis de N en la solución nutritiva. Verificar EC: si está baja, la planta no está comiendo suficiente. Revisar pH (5.8-6.2)."
            elif "Automáticas" in sistema:
                remedio_sistema = "Subir dosis suavemente (no más del 20% por vez). Las autos son sensibles, pero la deficiencia de N las frena mucho. Usar té de humus como opción segura."

        elif "Puntas" in sintoma:
            diagnostico = "**Exceso de Nutrientes (Quemadura).** Sales acumuladas queman las puntas. También puede ser exceso de riego."
            remedio_casero = """
            - **Lavado de raíces:** Regar con 3 veces el volumen de la maceta en agua limpia con pH 6.0-6.5.
            - **Agua de arroz:** El agua del primer lavado de arroz ayuda a recomponer la microbiología tras un flush.
            - **Reposo:** No fertilizar por 5-7 días después del lavado. Solo agua.
            - **Riego con agua de lluvia:** Si tenés acceso, el agua de lluvia es ideal para lavar sales.
            """
            video_url = "https://www.youtube.com/results?search_query=exceso+nutrientes+cannabis+flush+raices"
            if "Maceta" in sistema:
                remedio_sistema = "Hacer flush con agua de lluvia o filtrada. Reducir fertilizante al 50% por 2 semanas. Verificar drenaje de la maceta: los agujeros deben estar libres."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Regar abundante con agua limpia. En tierra madre es menos común, puede ser por fertilizante químico excesivo. Volver a orgánico. Las lluvias naturales ayudan a lavar."
            elif sistema == "Interior Luz":
                remedio_sistema = "Bajar EC inmediatamente. Hacer flush con agua a pH 6.0 y EC 0.3-0.4. Retomar nutrientes al 50% después de 5 días. Revisar run-off."
            elif "Automáticas" in sistema:
                remedio_sistema = "Flush suave (2x volumen de maceta). Las autos son muy sensibles al overfert. Retomar con dosis al 30% y subir gradualmente."

        elif "Manchas óxido" in sintoma:
            diagnostico = "**Deficiencia de Magnesio (Mg) o Calcio (Ca).** Manchas óxido entre las nervaduras de hojas viejas."
            remedio_casero = """
            - **Sal de Epsom (sulfato de magnesio):** 1 cucharadita por litro de agua. Regar o aplicar foliar.
            - **Cáscara de huevo molida:** Triturar y mezclar en el sustrato (aporta calcio lento).
            - **Vinagre de manzana:** 1 ml por litro de agua de riego (ayuda a liberar Ca y Mg del sustrato).
            - **Melaza:** 1 cucharada por litro de agua de riego. Aporta micronutrientes y alimenta la microbiología.
            """
            video_url = "https://www.youtube.com/results?search_query=deficiencia+magnesio+calcio+cannabis+tratamiento"
            if "Maceta" in sistema:
                remedio_sistema = "Aplicar CalMag comercial o sal de Epsom. Revisar pH del agua (el agua de La Carlota con pH alto bloquea Mg). Considerar regar con agua reposada 24hs para evaporar cloro."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Incorporar dolomita al suelo (aporta Ca y Mg a largo plazo). Aplicar sal de Epsom foliar como solución rápida. La cal agrícola también funciona."
            elif sistema == "Interior Luz":
                remedio_sistema = "Agregar CalMag a la solución nutritiva (2-3 ml/L). Verificar pH: fuera de rango 5.8-6.2 se bloquean estos elementos. Revisar EC total."
            elif "Automáticas" in sistema:
                remedio_sistema = "Sal de Epsom foliar (1g/L) es la vía más segura. No sobre-corregir: empezar con dosis baja. Respuesta visible en 3-5 días."

        elif "garra" in sintoma and "abajo" in sintoma:
            diagnostico = "**Exceso de riego o Exceso de Nitrógeno.** Las hojas viejas caen en garra hacia abajo. El sustrato permanece encharcado."
            remedio_casero = """
            - **Dejar secar:** No regar hasta que los primeros 4-5 cm de sustrato estén secos. Levantar la maceta: si pesa mucho, tiene exceso de agua.
            - **Mejorar drenaje:** Agregar perlita al sustrato si está muy compacto.
            - **Palito de madera:** Clavarlo en el sustrato; si sale húmedo al sacarlo, no regar todavía.
            - **Ventilar la base:** Si la maceta está en plato, retirarlo para que drene libremente.
            """
            video_url = "https://www.youtube.com/results?search_query=exceso+riego+cannabis+hojas+garra+abajo+solucion"
            if "Maceta" in sistema:
                remedio_sistema = "Verificar agujeros de drenaje. Elevar la maceta con ladrillos para mejor escurrimiento. En verano regar menos cantidad pero más seguido. Nunca dejar agua en el plato."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Revisar si la zona se encharca. Hacer canales de drenaje alrededor. El suelo arcilloso de La Carlota retiene mucho: agregar arena gruesa o perlita en la zona de raíces."
            elif sistema == "Interior Luz":
                remedio_sistema = "Espaciar riegos. Usar macetas con mucho drenaje (tela o air-pot). Verificar que la bandeja de drenaje no acumule agua. Ventilar bien la zona de raíces."
            elif "Automáticas" in sistema:
                remedio_sistema = "Las autos en maceta chica se sobre-riegan fácil. Regar menos cantidad y verificar peso de la maceta antes de regar. El exceso de riego las frena severamente."

        elif "garra" in sintoma and "arriba" in sintoma:
            diagnostico = "**Estrés hídrico (falta de agua) o calor en raíces.** Las hojas viejas se curvan hacia arriba por deshidratación."
            remedio_casero = """
            - **Regar inmediatamente:** Agua a temperatura ambiente, lentamente para que el sustrato absorba bien.
            - **Mulch:** Cubrir el sustrato con paja, corteza o fibra de coco para retener humedad.
            - **Aloe vera foliar:** 20 ml de gel de aloe en 1 litro de agua. Pulverizar para hidratar hojas mientras se recuperan raíces.
            """
            video_url = "https://www.youtube.com/results?search_query=falta+agua+cannabis+hojas+marchitas+solucion"
            if "Maceta" in sistema:
                remedio_sistema = "Si el sustrato se separó de las paredes de la maceta, regar por inmersión: sumergir la maceta en un balde con agua 10 minutos. Usar mulch. Considerar maceta más grande."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Regar profundo y lento. Instalar riego por goteo para mantener humedad constante. Mulch grueso (10 cm) alrededor de la base."
            elif sistema == "Interior Luz":
                remedio_sistema = "Si usás fibra de coco, se seca rápido: considerar riego automático por goteo. Verificar que la temperatura del indoor no esté secando demasiado rápido."
            elif "Automáticas" in sistema:
                remedio_sistema = "Regar inmediatamente. Las autos no toleran bien el estrés hídrico. Establecer rutina fija de riego y verificar peso de maceta diariamente."

        elif "Manchas blancas" in sintoma:
            diagnostico = "**Oídio en hojas viejas.** El hongo aparece primero en hojas bajas con poca ventilación y más humedad."
            remedio_casero = """
            - **Leche foliar:** 1 parte de leche + 9 partes de agua. Pulverizar con sol directo.
            - **Bicarbonato:** 1 cucharadita por litro de agua + 2 gotas de jabón potásico. Aplicar cada 5 días.
            - **Vinagre de manzana diluido:** 5 ml por litro. Pulverizar. Cambia el pH de la superficie de la hoja.
            - **Podar hojas afectadas:** Retirar y descartar lejos del cultivo (no compostar).
            """
            video_url = "https://www.youtube.com/results?search_query=oidio+hojas+viejas+cannabis+tratamiento+natural"
            if "Maceta" in sistema:
                remedio_sistema = "Podar las hojas bajas más afectadas. Separar macetas para mejorar flujo de aire. Aplicar leche foliar preventiva cada 5 días. Evitar regar las hojas."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Defoliar ramas bajas para subir la ventilación desde el suelo. El rocío de La Carlota favorece el oídio en otoño. Leche + bicarbonato preventivo."
            elif sistema == "Interior Luz":
                remedio_sistema = "Bajar humedad a 45%. Aumentar ventilación con oscilante apuntando a la zona baja. Podar hojas afectadas. Desinfectar tijeras con alcohol entre cortes."
            elif "Automáticas" in sistema:
                remedio_sistema = "Podar hojas bajas con cuidado (no excederse). Leche foliar es segura para autos. Mejorar ventilación alrededor de la planta."

        elif "Puntos blancos" in sintoma:
            diagnostico = "**Arañuela roja en hojas viejas.** Los ácaros suelen empezar por las hojas bajas donde hay menos movimiento de aire."
            remedio_casero = """
            - **Jabón potásico:** 5 ml por litro de agua. Pulverizar bien el envés de las hojas bajas. Repetir cada 3 días.
            - **Aceite de neem:** 3 ml por litro + jabón potásico. Aplicar al atardecer para evitar quemaduras.
            - **Agua a presión suave:** Lavar el envés de las hojas con spray de agua.
            - **Infusión de ajo:** 4 dientes machacados en 1 litro de agua caliente. Dejar enfriar, colar y pulverizar.
            """
            video_url = "https://www.youtube.com/results?search_query=arañuela+hojas+viejas+cannabis+jabon+potasico"
            if "Maceta" in sistema:
                remedio_sistema = "Lavar hojas con manguera suave. Neem + jabón potásico cada 3 días. Mover macetas a zona más ventilada. Las arañuelas se reproducen con calor seco."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Neem preventivo en verano. Plantar aromáticas (albahaca, menta) cerca para repeler. Lavar con manguera las hojas bajas regularmente."
            elif sistema == "Interior Luz":
                remedio_sistema = "Subir humedad a 55-60%. Neem + jabón potásico intensivo. Considerar control biológico (Phytoseiulus persimilis). Limpiar bien la carpa."
            elif "Automáticas" in sistema:
                remedio_sistema = "Jabón potásico cada 3 días. No usar neem en floración avanzada. Retirar hojas muy afectadas si la planta tiene suficiente follaje."

        elif "Agujeros" in sintoma:
            diagnostico = "**Orugas, caracoles o insectos masticadores.** Agujeros en hojas viejas bajas. Caracoles y orugas prefieren las hojas cercanas al suelo."
            remedio_casero = """
            - **BT (Bacillus thuringiensis):** Pulverizar cada 7 días. Solo mata orugas, seguro para la planta.
            - **Cerveza trampa:** Plato enterrado al ras del suelo con cerveza. Los caracoles caen y se ahogan.
            - **Ceniza alrededor de la base:** Barrera física que los caracoles no cruzan.
            - **Inspección nocturna:** Revisar con linterna al atardecer y de noche. Retirar a mano.
            - **Cáscara de huevo triturada:** Esparcir alrededor de la base como barrera cortante.
            """
            video_url = "https://www.youtube.com/results?search_query=orugas+caracoles+cannabis+hojas+bajas+control+natural"
            if "Maceta" in sistema:
                remedio_sistema = "Barrera de cáscara de huevo en el borde de la maceta. BT semanal en verano. Elevar macetas del suelo para dificultar acceso de caracoles."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "BT esencial dic-feb en La Carlota. Trampas de cerveza cada 2 metros. Mantener zona limpia de malezas que sirvan de refugio. Ceniza perimetral."
            elif sistema == "Interior Luz":
                remedio_sistema = "Si aparecen, vinieron con el sustrato o entraron del exterior. Inspeccionar sustrato antes de usar. Sellar entradas de aire con malla fina."
            elif "Automáticas" in sistema:
                remedio_sistema = "BT preventivo semanal obligatorio en exterior. Las autos tienen menos hojas: cada hoja cuenta. Inspección diaria."

        elif "Moho gris" in sintoma:
            diagnostico = "**Botrytis en zona baja.** Humedad acumulada cerca del suelo favorece el moho gris en hojas y ramas bajas."
            remedio_casero = """
            - **Retirar parte afectada inmediatamente.** Cortar con tijera desinfectada (alcohol 70%).
            - **Agua oxigenada:** 3 ml de agua oxigenada (10 vol) por litro de agua. Pulverizar zona cercana.
            - **Canela en polvo:** Aplicar sobre el corte para sellar y prevenir reinfección.
            - **Defoliar zona baja:** Mejorar ventilación retirando hojas innecesarias cerca del suelo.
            """
            video_url = "https://www.youtube.com/results?search_query=botrytis+hojas+bajas+cannabis+prevencion"
            if "Maceta" in sistema:
                remedio_sistema = "Podar ramas bajas que toquen el sustrato. Separar macetas. Si hay rocío frecuente, mover a zona cubierta de noche."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Defoliar zona baja completamente. Mantener limpio el suelo debajo de la planta. El rocío matinal de La Carlota es el principal factor: ventilar temprano."
            elif sistema == "Interior Luz":
                remedio_sistema = "Bajar humedad urgente. Podar la zona baja (lollipop). Asegurar flujo de aire en la base con ventilador. Desinfectar herramientas."
            elif "Automáticas" in sistema:
                remedio_sistema = "Retirar parte afectada. Defoliar suavemente hojas bajas que retengan humedad. Canela sobre el corte."

        elif "Tallos púrpuras" in sintoma:
            diagnostico = "**Deficiencia de Fósforo visible en hojas viejas.** Los pecíolos y tallos de hojas bajas se tornan púrpuras. Puede ser también frío nocturno."
            remedio_casero = """
            - **Té de banana:** Hervir 3 cáscaras de banana en 1 litro, enfriar, colar y regar (alto en P y K).
            - **Harina de hueso:** 2 cucharadas mezcladas en el sustrato cerca de las raíces.
            - **Guano de murciélago:** 1 cucharada en 5 litros de agua, remojar 24 hs y regar.
            """
            video_url = "https://www.youtube.com/results?search_query=deficiencia+fosforo+cannabis+tallos+purpuras+hojas+viejas"
            if "Maceta" in sistema:
                remedio_sistema = "Verificar temperatura nocturna: debajo de 10°C bloquea absorción de P. Harina de hueso + té de banana. Si es otoño, puede ser normal."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Incorporar harina de hueso en la zona de raíces. El P se mueve poco en el suelo. En noches frías, cubrir la base con mulch grueso."
            elif sistema == "Interior Luz":
                remedio_sistema = "Verificar temperatura nocturna (no menor a 18°C). Aumentar P en la solución nutritiva. Revisar pH: el P se bloquea fuera de 6.0-7.0."
            elif "Automáticas" in sistema:
                remedio_sistema = "Té de banana suave cada 5 días. Si la planta crece bien y es solo color, puede ser genético. No sobre-corregir."

        elif "Mosquitas" in sintoma:
            diagnostico = "**Mosquita del sustrato visible en hojas bajas.** Adultos vuelan alrededor de las hojas viejas y el sustrato. Larvas dañan raíces superficiales."
            remedio_casero = """
            - **Canela en polvo:** Capa fina sobre el sustrato. Antifúngica y repelente.
            - **Trampas amarillas pegajosas:** Colocar a la altura de la planta para capturar adultos.
            - **Dejar secar sustrato:** Las larvas mueren sin humedad constante.
            - **Tierra de diatomeas:** Espolvorear en superficie cuando el sustrato esté seco.
            """
            video_url = "https://www.youtube.com/results?search_query=mosquita+sustrato+cannabis+canela+trampas"
            if "Maceta" in sistema:
                remedio_sistema = "Canela + secar entre riegos. Trampas amarillas pegajosas. Agregar vermiculita o arena gruesa en la superficie para dificultar oviposición."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Menos frecuente. Si aparecen, mejorar drenaje y reducir frecuencia de riego. Tierra de diatomeas alrededor de la base."
            elif sistema == "Interior Luz":
                remedio_sistema = "Muy común. Canela + trampas + BTi en agua de riego. Cubrir superficie con perlita gruesa. No sobre-regar nunca."
            elif "Automáticas" in sistema:
                remedio_sistema = "Canela preventiva desde el inicio. Las autos sufren mucho el daño en raíces por larvas. Mantener sustrato con ciclos de secado."

    elif zona == "Hojas Nuevas (Arriba)":
        if "Amarilleamiento" in sintoma:
            diagnostico = "**Deficiencia de Hierro (Fe).** Las hojas nuevas amarillean pero las nervaduras quedan verdes (clorosis intervenal)."
            remedio_casero = """
            - **Clavos oxidados en agua:** Dejar 5-6 clavos oxidados en 5 litros de agua 48 hs. Regar con esa agua.
            - **Vinagre de manzana:** 2 ml por litro de agua de riego (baja pH y libera Fe del sustrato).
            - **Té de compost ácido:** Fermentar hojas de pino o corteza en agua 1 semana. Diluir y regar.
            - **Ácido cítrico:** 0.5 g por litro de agua de riego para bajar pH y liberar hierro del sustrato.
            """
            video_url = "https://www.youtube.com/results?search_query=deficiencia+hierro+cannabis+pH+solucion"
            if "Maceta" in sistema:
                remedio_sistema = "Bajar el pH del agua a 6.0-6.3. El agua de red de La Carlota es dura (pH ~7.5): usar ácido cítrico (1g por 10L). Aplicar quelato de hierro EDDHA."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "El suelo alcalino de La Carlota bloquea el Fe. Acidificar zona de raíces con azufre elemental o compost de hojas de pino. Quelato de hierro foliar para respuesta rápida."
            elif sistema == "Interior Luz":
                remedio_sistema = "Corregir pH a 5.8-6.0 urgente. Agregar quelato de hierro EDDHA a la solución. Revisar que la EC no esté muy alta (bloquea absorción)."
            elif "Automáticas" in sistema:
                remedio_sistema = "Ajustar pH inmediatamente. Aplicar hierro foliar quelado (dosis baja). Las autos no tienen tiempo de esperar correcciones lentas: actuar en 24 hs."

        elif "Puntas" in sintoma:
            diagnostico = "**Deficiencia de Calcio (Ca).** Puntas quemadas y deformes en hojas nuevas. Común con agua blanda o de lluvia."
            remedio_casero = """
            - **Cáscara de huevo en vinagre:** Disolver cáscaras trituradas en vinagre blanco 24-48 hs. Diluir 1:20 y regar.
            - **Leche diluida:** 50 ml de leche entera en 1 litro de agua. Regar cada 10 días (aporta Ca).
            - **Cal dolomita:** Espolvorear sobre el sustrato y regar (corrección lenta pero duradera).
            - **Agua de cáscara de huevo:** Hervir 10 cáscaras en 2 litros 10 min. Enfriar y regar.
            """
            video_url = "https://www.youtube.com/results?search_query=deficiencia+calcio+cannabis+hojas+nuevas"
            if "Maceta" in sistema:
                remedio_sistema = "Agregar CalMag al agua de riego. Si usás agua de lluvia, siempre suplementar calcio. Revisar pH. En La Carlota el agua de red tiene calcio, pero si filtrás mucho lo perdés."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Incorporar yeso agrícola o cal dolomita al suelo. El agua de lluvia no aporta Ca: complementar con riego de red intercalado."
            elif sistema == "Interior Luz":
                remedio_sistema = "Agregar CalMag (2-3 ml/L). Si usás agua de ósmosis, el CalMag es obligatorio siempre. Verificar pH 5.8-6.2."
            elif "Automáticas" in sistema:
                remedio_sistema = "CalMag a dosis baja (1-2 ml/L). Aplicar desde la semana 2 como prevención constante."

        elif "Manchas óxido" in sintoma:
            diagnostico = "**Deficiencia de Zinc (Zn) o Manganeso (Mn).** Manchas óxido en hojas nuevas con deformación. Los micronutrientes se bloquean con pH alto."
            remedio_casero = """
            - **Vinagre de manzana:** 2 ml por litro de agua de riego. Baja pH y libera micronutrientes.
            - **Algas marinas (kelp):** Extracto líquido de algas, 2 ml por litro. Rico en micronutrientes.
            - **Compost de calidad:** Incorporar compost maduro que aporta micronutrientes variados.
            - **Ceniza de madera diluida:** 1 cucharada en 5 litros de agua, remojar 24 hs, colar y regar (aporta Zn y Mn).
            """
            video_url = "https://www.youtube.com/results?search_query=deficiencia+zinc+manganeso+cannabis+hojas+nuevas"
            if "Maceta" in sistema:
                remedio_sistema = "Corregir pH del agua a 6.0-6.5. Aplicar micronutrientes quelatados foliar. El agua dura de La Carlota puede bloquear Zn y Mn."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Incorporar compost rico y extracto de algas. El suelo alcalino bloquea micronutrientes: acidificar zona de raíces con azufre o vinagre."
            elif sistema == "Interior Luz":
                remedio_sistema = "Verificar pH estricto (5.8-6.2). Agregar micronutrientes quelatados a la solución. Revisar si la EC está demasiado alta."
            elif "Automáticas" in sistema:
                remedio_sistema = "Extracto de algas foliar es la opción más segura. Corregir pH del agua. Las autos son sensibles a bloqueos de micronutrientes."

        elif "garra" in sintoma and "arriba" in sintoma:
            diagnostico = "**Estrés por calor o luz excesiva.** Las hojas nuevas se curvan hacia arriba buscando protegerse del exceso de energía."
            remedio_casero = """
            - **Extracto de aloe vera:** 30 ml de gel de aloe en 1 litro de agua. Pulverizar sobre hojas al atardecer.
            - **Agua fresca:** Regar con agua a temperatura ambiente (no fría) para refrescar raíces.
            - **Sombra temporal:** Usar tela o sombrilla en horas pico (12-16 hs).
            - **Pulverizar agua al atardecer:** Refrescar las hojas cuando baje el sol.
            """
            video_url = "https://www.youtube.com/results?search_query=estres+calor+cannabis+hojas+garra+arriba+solucion"
            if "Maceta" in sistema:
                remedio_sistema = "Mover a media sombra en horas pico (12-16 hs). Regar al atardecer. Usar maceta blanca para reflejar calor. Mulch sobre sustrato."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Instalar malla media sombra 30-50%. Mulch grueso (10 cm) para mantener raíces frescas. Regar temprano a la mañana."
            elif sistema == "Interior Luz":
                remedio_sistema = "Subir la luz 10-15 cm. Bajar temperatura con extracción reforzada. Pasar las luces a horario nocturno en verano. Verificar VPD."
            elif "Automáticas" in sistema:
                remedio_sistema = "Reducir intensidad de luz o alejar el panel. Las autos sufren más el estrés por calor. Sombra parcial en exterior durante picos de calor."

        elif "garra" in sintoma and "abajo" in sintoma:
            diagnostico = "**Exceso de riego o toxicidad.** Hojas nuevas caídas en garra hacia abajo. Las raíces no pueden respirar."
            remedio_casero = """
            - **Dejar secar completamente:** No regar hasta que el sustrato esté seco al menos 3-4 cm.
            - **Mejorar aireación:** Pinchar suavemente el sustrato con un palito para dejar entrar aire a las raíces.
            - **Agua oxigenada:** 2 ml de H2O2 (10 vol) por litro de agua de riego para oxigenar raíces.
            """
            video_url = "https://www.youtube.com/results?search_query=exceso+riego+cannabis+hojas+nuevas+garra+abajo"
            if "Maceta" in sistema:
                remedio_sistema = "Dejar secar. Verificar drenaje: levantar la maceta, debe pesar poco cuando necesita riego. Considerar trasplante a sustrato más aireado con más perlita."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Espaciar riegos. Si el suelo está compacto, aflojar superficie con cuidado sin dañar raíces. Agregar mulch seco para absorber exceso."
            elif sistema == "Interior Luz":
                remedio_sistema = "Espaciar riegos. Usar macetas con drenaje excelente. H2O2 en el agua ayuda a oxigenar. Verificar que el sustrato no esté compactado."
            elif "Automáticas" in sistema:
                remedio_sistema = "Dejar secar urgente. Las autos con raíces ahogadas pierden días valiosos. Regar menos cantidad, más seguido, cuando estén secas."

        elif "Manchas blancas" in sintoma:
            diagnostico = "**Oídio en brotes nuevos.** Ataque temprano de oídio en las hojas jóvenes. Muy agresivo si no se trata."
            remedio_casero = """
            - **Leche foliar:** 1:9 con agua, pulverizar con sol (la caseína + UV mata las esporas).
            - **Bicarbonato de sodio:** 1 cucharadita por litro + 2 gotas jabón potásico.
            - **Aceite de neem preventivo:** 3 ml por litro, aplicar cada 7 días como barrera.
            - **Cola de caballo (infusión):** Hervir 50g de cola de caballo seca en 1 litro. Diluir 1:5 y pulverizar (antifúngico natural).
            """
            video_url = "https://www.youtube.com/results?search_query=oidio+hojas+nuevas+cannabis+tratamiento+leche"
            if "Maceta" in sistema:
                remedio_sistema = "Leche foliar urgente. Mover maceta a zona con más sol y viento. No pulverizar de noche. Repetir cada 4-5 días hasta que desaparezca."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Aplicar leche + bicarbonato. Asegurar buena distancia entre plantas. El rocío matinal de La Carlota es factor de riesgo: ventilar temprano."
            elif sistema == "Interior Luz":
                remedio_sistema = "Bajar humedad a 40-45%. Bicarbonato foliar con luces apagadas. Aumentar renovación de aire. Desinfectar todo con agua oxigenada."
            elif "Automáticas" in sistema:
                remedio_sistema = "Leche foliar inmediata (segura para autos). El oídio en hojas nuevas frena el crecimiento. Defoliar lo afectado si hay suficiente follaje sano."

        elif "Puntos blancos" in sintoma:
            diagnostico = "**Arañuela roja en brotes.** Ataque en hojas nuevas indica infestación avanzada. Los ácaros suben hacia los brotes."
            remedio_casero = """
            - **Jabón potásico intensivo:** 5 ml por litro, pulverizar envés cada 2 días.
            - **Neem + jabón:** 3 ml neem + 3 ml jabón potásico por litro. Al atardecer.
            - **Ajo + ají macerado:** 5 dientes + 1 ají en 1 litro 24 hs. Colar y pulverizar.
            - **Agua jabonosa de platos (ecológico):** 2 gotas de detergente biodegradable por litro. Emergencia.
            """
            video_url = "https://www.youtube.com/results?search_query=arañuela+roja+brotes+cannabis+tratamiento+urgente"
            if "Maceta" in sistema:
                remedio_sistema = "Aislar planta afectada. Neem + jabón potásico intensivo. Lavar con manguera el envés. Si está en flora, jabón potásico solo (sin neem)."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Tratamiento de choque: neem + jabón potásico + lavado con manguera. Plantar albahaca entre las plantas como repelente. Repetir cada 3 días."
            elif sistema == "Interior Luz":
                remedio_sistema = "Emergencia: subir humedad a 60%, bajar temperatura. Neem + jabón potásico diario por 1 semana. Considerar ácaros depredadores (Phytoseiulus)."
            elif "Automáticas" in sistema:
                remedio_sistema = "Solo jabón potásico en floración. Retirar hojas muy infestadas. Actuar ya: en autos cada día de estrés se nota en la cosecha."

        elif "Agujeros" in sintoma:
            diagnostico = "**Insectos masticadores en brotes.** Orugas pequeñas o trips pueden hacer agujeros en hojas nuevas tiernas."
            remedio_casero = """
            - **BT (Bacillus thuringiensis):** Seguro para la planta, mata orugas en 24-48 hs. Aplicar cada 7 días.
            - **Inspección con lupa:** Las orugas pequeñas se esconden en el centro de los brotes.
            - **Tabaco macerado:** 2 cigarrillos en 1 litro de agua 24 hs. Colar y pulverizar (insecticida natural).
            - **Aceite de neem:** 3 ml/L preventivo cada 7 días.
            """
            video_url = "https://www.youtube.com/results?search_query=orugas+brotes+cannabis+BT+tratamiento"
            if "Maceta" in sistema:
                remedio_sistema = "BT preventivo semanal en temporada (dic-feb). Inspección diaria de brotes. Usar malla fina sobre la planta si el ataque es severo."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "BT obligatorio en La Carlota en verano. Revisar envés de hojas nuevas cada día. Trampas de luz nocturna para atraer polillas adultas."
            elif sistema == "Interior Luz":
                remedio_sistema = "Si hay orugas en indoor, entraron con el sustrato o al ventilar. Sellar entradas con malla. Retirar manualmente y aplicar BT."
            elif "Automáticas" in sistema:
                remedio_sistema = "BT urgente. Las autos no pueden perder brotes nuevos. Inspección con lupa dentro de los apicales cada atardecer."

        elif "Moho gris" in sintoma:
            diagnostico = "**Botrytis en brotes apicales.** El moho gris ataca los brotes superiores cuando hay humedad y poca ventilación. Muy peligroso."
            remedio_casero = """
            - **Retirar inmediatamente** el brote afectado. Cortar 5 cm debajo del moho visible.
            - **Desinfectar tijeras** con alcohol 70% entre cada corte.
            - **Canela en polvo:** Sellar el corte con canela para prevenir reinfección.
            - **Agua oxigenada:** 3 ml por litro, pulverizar zona circundante.
            """
            video_url = "https://www.youtube.com/results?search_query=botrytis+brotes+apicales+cannabis+emergencia"
            if "Maceta" in sistema:
                remedio_sistema = "Cortar parte afectada. Mover a lugar ventilado y cubierto de lluvia. Si llueve mucho, considerar cosecha anticipada de lo sano."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Retirar parte afectada. Instalar cobertura contra lluvia si es posible. Defoliar agresivamente para ventilación. Considerar cosecha parcial."
            elif sistema == "Interior Luz":
                remedio_sistema = "Emergencia: humedad a 35%. Máxima extracción. Retirar con guantes, no sacudir (dispersa esporas). Desinfectar todo el espacio."
            elif "Automáticas" in sistema:
                remedio_sistema = "Retirar urgente. Si la auto está cerca de cosecha, cosechar todo lo sano ahora. La botrytis se expande rápido y arruina todo."

        elif "Tallos púrpuras" in sintoma:
            diagnostico = "**Pecíolos púrpuras en hojas nuevas.** Puede ser genético, frío nocturno, o deficiencia de Fósforo que afecta el crecimiento nuevo."
            remedio_casero = """
            - **Té de banana:** Hervir 3 cáscaras en 1 litro, enfriar, colar y regar.
            - **Guano de murciélago:** Rico en P. 1 cucharada en 5 litros, remojar 24 hs.
            - **Proteger del frío nocturno:** Cubrir la planta o entrarla de noche si baja de 10°C.
            """
            video_url = "https://www.youtube.com/results?search_query=tallos+purpuras+hojas+nuevas+cannabis+fosforo"
            if "Maceta" in sistema:
                remedio_sistema = "Entrar la maceta de noche si la temperatura baja de 10°C. Aplicar harina de hueso + té de banana. Si la planta crece bien, puede ser genético."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Mulch grueso para aislar raíces del frío. Harina de hueso en la zona de raíces. En otoño tardío puede ser normal."
            elif sistema == "Interior Luz":
                remedio_sistema = "Verificar que la temperatura con luces apagadas no baje de 18°C. Aumentar P en la solución. Si crece bien, ignorar."
            elif "Automáticas" in sistema:
                remedio_sistema = "Té de banana cada 5 días. Proteger del frío. Si crece bien y es solo color, probablemente genético."

        elif "Mosquitas" in sintoma:
            diagnostico = "**Mosquitas volando alrededor de brotes.** Los adultos de fungus gnat revolotean cerca de las partes húmedas de la planta."
            remedio_casero = """
            - **Trampas amarillas pegajosas:** A la altura de los brotes para capturar adultos.
            - **Canela sobre sustrato:** Previene reproducción en la superficie.
            - **Dejar secar:** Las larvas están en el sustrato, no en los brotes. Controlar desde abajo.
            """
            video_url = "https://www.youtube.com/results?search_query=mosquita+sustrato+cannabis+control+trampas"
            if "Maceta" in sistema:
                remedio_sistema = "Las mosquitas no dañan las hojas directamente, el problema son las larvas en las raíces. Trampas amarillas + canela + secar sustrato."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Raro en tierra madre. Si aparecen, es por exceso de materia orgánica fresca en superficie. Dejar secar y aplicar tierra de diatomeas."
            elif sistema == "Interior Luz":
                remedio_sistema = "Trampas amarillas + BTi en agua de riego. Cubrir sustrato con perlita gruesa. Ventilar bien."
            elif "Automáticas" in sistema:
                remedio_sistema = "Controlar desde el sustrato: canela + secar + trampas. Las mosquitas adultas son molestas pero inofensivas; las larvas son el problema real."

    elif zona == "Tallos y Ramas":
        if "Tallos púrpuras" in sintoma:
            diagnostico = "**Deficiencia de Fósforo (P) o genética.** Tallos púrpuras con crecimiento lento = deficiencia. Si la planta crece bien, puede ser genético."
            remedio_casero = """
            - **Harina de hueso:** Mezclar 2 cucharadas por planta en el sustrato y regar.
            - **Té de banana:** Hervir 3 cáscaras de banana en 1 litro de agua 15 min. Enfriar, colar y regar (rico en P y K).
            - **Guano de murciélago:** 1 cucharada en 5 litros de agua. Remojar 24 hs y regar.
            - **Ceniza de madera:** 1 cucharada en 5 litros de agua. Remojar, colar y regar (rico en K y P).
            """
            video_url = "https://www.youtube.com/results?search_query=deficiencia+fosforo+cannabis+tallos+purpuras"
            if "Maceta" in sistema:
                remedio_sistema = "Agregar harina de hueso al sustrato. Usar fertilizante con P alto en floración. Verificar que la temperatura nocturna no baje de 10°C (frío bloquea P)."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Incorporar guano de murciélago o harina de hueso en la zona de raíces. El fósforo se mueve poco en el suelo, aplicar lo más cerca posible de las raíces."
            elif sistema == "Interior Luz":
                remedio_sistema = "Aumentar P en la solución nutritiva. Verificar pH (el P se bloquea fuera de 6.0-7.0). Revisar temperatura de raíces (mínimo 18°C)."
            elif "Automáticas" in sistema:
                remedio_sistema = "Té de banana es la opción más suave y segura. Aplicar cada 5 días en floración. Si crece bien, puede ser genético."

        elif "Manchas blancas" in sintoma:
            diagnostico = "**Oídio en tallos.** El hongo puede atacar tallos y ramas, especialmente en nudos donde se acumula humedad."
            remedio_casero = """
            - **Bicarbonato + jabón potásico:** 1 cucharadita bicarbonato + 2 gotas jabón en 1 litro. Frotar tallos afectados con paño embebido.
            - **Leche pura:** Aplicar con algodón sobre las manchas blancas del tallo.
            - **Cola de caballo:** Infusión concentrada aplicada con pincel sobre los tallos.
            """
            video_url = "https://www.youtube.com/results?search_query=oidio+tallos+cannabis+tratamiento"
            if "Maceta" in sistema:
                remedio_sistema = "Limpiar tallos con paño embebido en bicarbonato. Mejorar ventilación entre macetas. Podar ramas interiores que estén muy juntas."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Defoliar ramas interiores. Asegurar distancia entre plantas. Aplicar cola de caballo preventiva. Evitar mojar los tallos al regar."
            elif sistema == "Interior Luz":
                remedio_sistema = "Limpiar tallos manualmente. Bajar humedad. Aumentar circulación de aire directo sobre los tallos con ventilador oscilante."
            elif "Automáticas" in sistema:
                remedio_sistema = "Limpiar con paño + bicarbonato. Mejorar ventilación. Las autos compactas concentran humedad en el centro: defoliar suavemente."

        elif "Manchas óxido" in sintoma:
            diagnostico = "**Roya o infección fúngica en tallos.** Manchas óxido-marrón en ramas pueden ser hongo de roya (Puccinia). Raro pero posible."
            remedio_casero = """
            - **Podar ramas afectadas:** Cortar por debajo de la lesión con tijera desinfectada.
            - **Canela en polvo:** Sellar heridas de poda con canela (antifúngica natural).
            - **Aceite de neem:** 3 ml/L pulverizado sobre los tallos cada 5 días como barrera.
            - **Azufre en polvo:** Aplicar sobre las manchas si están localizadas (fungicida tradicional).
            """
            video_url = "https://www.youtube.com/results?search_query=roya+tallos+cannabis+hongos+tratamiento"
            if "Maceta" in sistema:
                remedio_sistema = "Podar rama afectada y sellar con canela. Separar de otras plantas. Neem preventivo sobre el resto de tallos. Desinfectar tijeras."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Podar y eliminar (no compostar). Mejorar ventilación podando ramas interiores. El rocío nocturno de La Carlota favorece hongos en tallos."
            elif sistema == "Interior Luz":
                remedio_sistema = "Podar y desinfectar. Bajar humedad. Revisar que no haya agua estancada que salpique los tallos. Desinfectar toda la carpa."
            elif "Automáticas" in sistema:
                remedio_sistema = "Podar rama afectada con cuidado. Canela sobre el corte. Las autos soportan pocas podas, ser conservador."

        elif "Agujeros" in sintoma:
            diagnostico = "**Barrenadores o daño mecánico en tallos.** Insectos barrenadores pueden hacer agujeros en ramas. También puede ser daño por viento."
            remedio_casero = """
            - **Inspección detallada:** Buscar excremento o aserrín en la base del agujero (indica barrenador).
            - **Alambre fino:** Si hay barrenador dentro, insertar un alambre fino para eliminarlo.
            - **Sellar con canela:** Aplicar canela + miel sobre la herida para proteger y cicatrizar.
            - **Cinta de injerto:** Envolver la zona dañada para dar soporte estructural.
            """
            video_url = "https://www.youtube.com/results?search_query=barrenador+tallos+cannabis+reparar"
            if "Maceta" in sistema:
                remedio_sistema = "Si es daño de viento, entutorar y reparar con cinta. Si es barrenador, tratar con alambre + sellar con canela y miel. Reforzar tutores."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Los barrenadores son más comunes en plantas grandes. Inspeccionar semanalmente. Sellar heridas con canela. Neem preventivo en la base."
            elif sistema == "Interior Luz":
                remedio_sistema = "Muy raro en indoor. Si es daño mecánico, reparar con cinta de injerto. Reforzar soporte de ramas pesadas en floración."
            elif "Automáticas" in sistema:
                remedio_sistema = "Reparar con cinta + canela. Las autos son más frágiles: usar tutores desde temprano para prevenir quiebres."

        elif "Moho gris" in sintoma:
            diagnostico = "**Botrytis en ramas.** El moho gris puede atacar ramas, especialmente donde hay heridas de poda o quiebres."
            remedio_casero = """
            - **Retirar rama afectada:** Cortar por debajo del moho con tijera desinfectada.
            - **Agua oxigenada:** 3 ml por litro sobre la zona cercana.
            - **Canela:** Sellar todos los cortes de poda con canela preventivamente.
            """
            video_url = "https://www.youtube.com/results?search_query=botrytis+ramas+cannabis+poda+prevencion"
            if "Maceta" in sistema:
                remedio_sistema = "Retirar rama. Sellar heridas previas con canela. Mover a zona ventilada. Evitar mojarse con lluvia."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Podar y eliminar (no compostar). Sellar todos los cortes de poda con canela o pasta cicatrizante. Defoliar para ventilación."
            elif sistema == "Interior Luz":
                remedio_sistema = "Retirar urgente. Bajar humedad. Revisar que todas las heridas de LST o poda estén selladas. Desinfectar carpa."
            elif "Automáticas" in sistema:
                remedio_sistema = "Retirar con cuidado. Canela sobre el corte. Si hay muchas ramas afectadas, considerar cosecha anticipada."

        else:
            diagnostico = f"**Síntoma '{sintoma}' en tallos y ramas.** Puede estar relacionado con estrés general, daño mecánico o problemas de nutrición que se manifiestan en la estructura."
            remedio_casero = """
            - **Inspección visual detallada:** Revisar si hay insectos, moho o heridas.
            - **Reforzar tutores:** Si los tallos están débiles, entutorar con cañas de bambú.
            - **Silicio foliar:** 1 ml de silicato de potasio por litro de agua. Fortalece tallos y paredes celulares.
            - **Té de cola de caballo:** Rico en silicio natural. Hervir, diluir 1:5, pulverizar sobre tallos.
            """
            video_url = "https://www.youtube.com/results?search_query=tallos+debiles+cannabis+fortalecer+silicio"
            if "Maceta" in sistema:
                remedio_sistema = "Entutorar si es necesario. Aplicar silicio foliar para endurecer tallos. El viento de La Carlota puede debilitar plantas sin soporte."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Instalar tutores firmes. Aplicar cola de caballo para fortalecer. Las plantas en tierra madre crecen más y necesitan más soporte."
            elif sistema == "Interior Luz":
                remedio_sistema = "Ventilar con oscilante para que los tallos se fortalezcan naturalmente. Silicio en la solución nutritiva. Usar red SCROG para soporte."
            elif "Automáticas" in sistema:
                remedio_sistema = "Las autos tienen tallos finos: silicio foliar desde la semana 2 ayuda. Usar tutores suaves de bambú."

    elif zona == "Raíces y Base":
        if "Mosquitas" in sintoma:
            diagnostico = "**Mosquita del Sustrato (Fungus Gnat).** Larvas que comen raíces finas. Causan marchitez y crecimiento lento."
            remedio_casero = """
            - **Canela en polvo:** Espolvorear sobre el sustrato. Es antifúngica y repele mosquitas.
            - **Trampa de vinagre:** Vaso con vinagre de manzana + gota de detergente. Atrapa adultos.
            - **Dejar secar el sustrato:** Las larvas necesitan humedad. Espaciar riegos hasta que los primeros 3 cm estén secos.
            - **Tierra de diatomeas:** Espolvorear sobre el sustrato seco. Mata larvas por contacto.
            - **Arena gruesa en superficie:** Capa de 1-2 cm dificulta la puesta de huevos.
            """
            video_url = "https://www.youtube.com/results?search_query=mosquita+sustrato+fungus+gnat+cannabis+control"
            if "Maceta" in sistema:
                remedio_sistema = "Canela + dejar secar entre riegos. Agregar perlita en superficie para dificultar la puesta de huevos. Usar trampas amarillas pegajosas cerca de la maceta."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Menos común en tierra madre. Si aparecen, reducir riego y aplicar tierra de diatomeas alrededor de la base. Revisar que el drenaje sea bueno."
            elif sistema == "Interior Luz":
                remedio_sistema = "Problema muy común en indoor. Dejar secar, canela, trampas amarillas pegajosas. BTi (Bacillus thuringiensis israelensis) en el agua de riego es lo más efectivo."
            elif "Automáticas" in sistema:
                remedio_sistema = "Actuar rápido: las autos no tienen tiempo de recuperarse del daño en raíces. Canela + dejar secar. No sobre-regar nunca."

        elif "Amarilleamiento" in sintoma:
            diagnostico = "**Pudrición de raíces (Root Rot).** Raíces marrones, blandas y con mal olor. La planta amarillea desde abajo uniformemente."
            remedio_casero = """
            - **Agua oxigenada:** 3-5 ml de H2O2 (10 vol) por litro de agua de riego. Oxigena y desinfecta raíces.
            - **Canela en polvo:** Espolvorear en la base y sobre el sustrato (antifúngica potente).
            - **Dejar secar completamente:** Las raíces necesitan oxígeno para recuperarse.
            - **Carbón activado:** Mezclar en el sustrato para absorber toxinas y patógenos.
            - **Trichoderma:** Si conseguís, agregar al sustrato para proteger raíces (hongo benéfico).
            """
            video_url = "https://www.youtube.com/results?search_query=pudricion+raices+cannabis+root+rot+solucion"
            if "Maceta" in sistema:
                remedio_sistema = "Sacar la planta, revisar raíces: si son marrones y huelen mal, cortar las podridas. Trasplantar a sustrato nuevo con más perlita. H2O2 en cada riego por 2 semanas."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Más raro en tierra madre. Si ocurre, el suelo está encharcado: hacer canales de drenaje urgentes. Aplicar Trichoderma si está disponible."
            elif sistema == "Interior Luz":
                remedio_sistema = "H2O2 en cada riego. Verificar temperatura del agua (no mayor a 22°C, el calor fomenta root rot). En hidro: agregar oxigenador permanente."
            elif "Automáticas" in sistema:
                remedio_sistema = "Emergencia: H2O2 inmediato. Las autos con root rot pueden morir en días. Reducir riego drásticamente. Trasplantar solo si es muy urgente (las autos no toleran trasplante)."

        elif "Puntas" in sintoma:
            diagnostico = "**Daño por sales acumuladas en la zona de raíces.** El exceso de fertilizante se acumula en la base y quema las raíces superficiales."
            remedio_casero = """
            - **Flush (lavado):** Regar con 3x el volumen de la maceta en agua limpia pH 6.0-6.5.
            - **Agua de lluvia:** Ideal para lavar sales por su bajo contenido mineral.
            - **Reposo:** Solo agua por 7-10 días después del lavado.
            - **Revisar EC del run-off:** Si sale muy alta, seguir lavando.
            """
            video_url = "https://www.youtube.com/results?search_query=exceso+sales+raices+cannabis+flush+lavado"
            if "Maceta" in sistema:
                remedio_sistema = "Flush generoso con agua de lluvia o filtrada. Verificar que el run-off salga claro. Reducir dosis de fertilizante un 50% por 2 semanas."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Regar abundante. En tierra madre las sales se dispersan mejor, pero si se usó mucho químico, lavar bien. Volver a nutrición orgánica."
            elif sistema == "Interior Luz":
                remedio_sistema = "Flush con agua pH 6.0, EC 0.3. Medir EC del run-off: debe bajar a menos de 1.5. Retomar nutrientes al 50% después de 5 días."
            elif "Automáticas" in sistema:
                remedio_sistema = "Flush suave (2x volumen). Las autos son sensibles: retomar con dosis al 30%. Prevenir siempre es mejor que corregir."

        elif "Moho gris" in sintoma:
            diagnostico = "**Pudrición del cuello (Damping Off o Botrytis basal).** Moho gris en la base del tallo, donde toca el sustrato. Muy peligroso."
            remedio_casero = """
            - **Canela en polvo:** Aplicar generosamente alrededor de la base del tallo y sobre el sustrato.
            - **Agua oxigenada:** 3 ml por litro, regar alrededor de la base (no sobre el moho).
            - **Mejorar ventilación basal:** Retirar hojas bajas que toquen el sustrato.
            - **Secar el sustrato:** Reducir riego inmediatamente.
            """
            video_url = "https://www.youtube.com/results?search_query=pudricion+cuello+cannabis+damping+off+base"
            if "Maceta" in sistema:
                remedio_sistema = "Canela urgente. Verificar que el sustrato no esté permanentemente húmedo en la zona del cuello. Elevar maceta para mejorar drenaje."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Aporcar con sustrato seco mezclado con canela. Mejorar drenaje alrededor de la planta. No regar directamente sobre el tallo."
            elif sistema == "Interior Luz":
                remedio_sistema = "Emergencia: secar, canela, ventilación. Si el cuello está blando y marrón, la planta puede no sobrevivir. H2O2 en riego."
            elif "Automáticas" in sistema:
                remedio_sistema = "Canela urgente + secar. Si el cuello está firme todavía, puede salvarse. Si está blando, la auto probablemente no se recupere."

        elif "Manchas óxido" in sintoma:
            diagnostico = "**Oxidación en zona de raíces.** Puede indicar exceso de hierro en el agua o sustrato compactado con mal drenaje."
            remedio_casero = """
            - **Revisar agua de riego:** Si tiene mucho hierro, dejar reposar 24 hs para que precipite.
            - **Mejorar drenaje:** Agregar perlita al sustrato.
            - **Flush suave:** Lavar con agua limpia para eliminar acumulación.
            """
            video_url = "https://www.youtube.com/results?search_query=exceso+hierro+raices+cannabis+agua+oxidada"
            if "Maceta" in sistema:
                remedio_sistema = "Si el agua de red tiene mucho hierro (común en pozos de La Carlota), dejar reposar 24 hs en balde destapado. Filtrar antes de regar."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Si la napa freática es ferruginosa, elevar el cantero. Usar mulch para filtrar. El exceso de Fe en suelo se contrarresta con buen drenaje."
            elif sistema == "Interior Luz":
                remedio_sistema = "Revisar la fuente de agua. Si es de pozo, puede tener exceso de hierro. Considerar filtro o agua embotellada. Ajustar pH."
            elif "Automáticas" in sistema:
                remedio_sistema = "Filtrar el agua si tiene exceso de hierro. Las autos son sensibles a desequilibrios. Usar agua reposada 24 hs."

        else:
            diagnostico = f"**Síntoma '{sintoma}' en la zona de raíces.** Los problemas en raíces se manifiestan en toda la planta. Revisar sustrato, drenaje y frecuencia de riego."
            remedio_casero = """
            - **Revisar raíces:** Sacar la planta con cuidado y observar: blancas = sanas, marrones/blandas = problemas.
            - **Agua oxigenada:** 3 ml por litro como tratamiento general para raíces.
            - **Canela preventiva:** Siempre es segura sobre el sustrato.
            - **Trichoderma:** Si está disponible, excelente protector de raíces.
            """
            video_url = "https://www.youtube.com/results?search_query=problemas+raices+cannabis+diagnostico+solucion"
            if "Maceta" in sistema:
                remedio_sistema = "Verificar drenaje, tamaño de maceta y frecuencia de riego. Si las raíces salen por abajo, trasplantar a maceta más grande."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Revisar si hay encharcamiento o compactación del suelo. Aflojar superficie con cuidado. Agregar compost y perlita."
            elif sistema == "Interior Luz":
                remedio_sistema = "Controlar temperatura del agua (18-22°C ideal). Verificar pH y EC del run-off. Oxigenar si es necesario."
            elif "Automáticas" in sistema:
                remedio_sistema = "Las autos son especialmente sensibles en raíces. Maceta definitiva desde semilla, buen drenaje, no sobre-regar."

    elif zona == "Toda la Planta":
        if "Amarilleamiento" in sintoma:
            diagnostico = "**Amarilleamiento general.** Puede ser: deficiencia severa de N, pH muy desajustado, root rot, o final de ciclo natural (flush pre-cosecha)."
            remedio_casero = """
            - **Si está en vegetativo:** Probablemente deficiencia de N severa. Aplicar purín de ortiga o té de humus urgente.
            - **Si está en floración tardía:** Puede ser normal (la planta consume sus reservas). Verificar tricomas.
            - **Revisar pH del agua:** pH desajustado bloquea todos los nutrientes. Rango: 6.0-6.5.
            - **Revisar raíces:** Si huelen mal, es root rot. Tratar con H2O2.
            """
            video_url = "https://www.youtube.com/results?search_query=amarilleamiento+general+cannabis+causas+solucion"
            if "Maceta" in sistema:
                remedio_sistema = "Si es vege: aumentar N urgente (humus líquido o purín de ortiga). Si es flora tardía: verificar tricomas, puede ser hora de cosechar. Revisar pH del agua de La Carlota."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Incorporar compost fresco alrededor de la base. El suelo puede estar agotado: aplicar purín de ortiga + té de humus. Si es flora final, puede ser normal."
            elif sistema == "Interior Luz":
                remedio_sistema = "Verificar pH y EC inmediatamente. Si ambos están bien, revisar raíces. En flora tardía (últimas 2 semanas) es normal y deseable."
            elif "Automáticas" in sistema:
                remedio_sistema = "Si la auto tiene más de 8 semanas, puede ser final de ciclo. Si es joven, corregir N y pH urgente. Las autos amarillean rápido al final."

        elif "Puntas" in sintoma:
            diagnostico = "**Quemadura generalizada.** Puntas quemadas en toda la planta indica exceso severo de nutrientes o agua con EC muy alta."
            remedio_casero = """
            - **Flush urgente:** 3x volumen de la maceta con agua limpia pH 6.0.
            - **Solo agua por 10 días:** No agregar ningún nutriente.
            - **Agua de arroz:** Después del flush, regar con agua de arroz para recomponer microbiología.
            - **Melaza diluida:** 1 cucharada por 5 litros después del flush para alimentar microorganismos beneficiosos.
            """
            video_url = "https://www.youtube.com/results?search_query=quemadura+nutrientes+cannabis+toda+planta+flush"
            if "Maceta" in sistema:
                remedio_sistema = "Flush generoso. Verificar EC del run-off. Si usás fertilizantes comerciales, probablemente la dosis era muy alta. Reducir al 30% y subir gradual."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Regar abundante con agua limpia durante 2-3 días. Dejar de fertilizar 2 semanas. Volver a dosis orgánicas moderadas."
            elif sistema == "Interior Luz":
                remedio_sistema = "Flush con agua pH 6.0 EC 0.3. Medir run-off. No retomar nutrientes hasta que las puntas nuevas crezcan sanas. Empezar al 30% de la dosis."
            elif "Automáticas" in sistema:
                remedio_sistema = "Flush suave pero urgente. Las autos quemadas en flora producen poco. Solo agua por 7 días, luego retomar al 25% de dosis."

        elif "Manchas óxido" in sintoma:
            diagnostico = "**Deficiencia múltiple de micronutrientes o pH muy desajustado.** Manchas óxido en toda la planta sugiere bloqueo generalizado de nutrientes."
            remedio_casero = """
            - **Corregir pH urgente:** El pH es la causa más común. Rango ideal: 6.0-6.5 en tierra, 5.8-6.2 en hidro/coco.
            - **Extracto de algas (kelp):** 2 ml por litro. Aporta micronutrientes variados.
            - **Sal de Epsom foliar:** 1g por litro como corrección rápida de Mg.
            - **Vinagre de manzana:** 1-2 ml por litro de riego para acidificar suavemente.
            """
            video_url = "https://www.youtube.com/results?search_query=manchas+oxido+toda+planta+cannabis+pH+micronutrientes"
            if "Maceta" in sistema:
                remedio_sistema = "Medir y corregir pH del agua. En La Carlota el agua es dura (~7.5): usar ácido cítrico. Aplicar extracto de algas + sal de Epsom foliar."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Acidificar zona de raíces con azufre elemental o vinagre diluido. Incorporar compost ácido (hojas de pino). Extracto de algas en riego."
            elif sistema == "Interior Luz":
                remedio_sistema = "Verificar pH estricto en cada riego. Agregar micronutrientes quelatados. Si usás agua de La Carlota sin corregir, el pH alto bloquea todo."
            elif "Automáticas" in sistema:
                remedio_sistema = "Corregir pH ya. Las autos no toleran bloqueos prolongados. Extracto de algas foliar + sal de Epsom como corrección rápida."

        elif "garra" in sintoma and "abajo" in sintoma:
            diagnostico = "**Exceso de Nitrógeno.** Hojas verde oscuro y en garra hacia abajo. Peligroso en floración."
            remedio_casero = """
            - **Lavado de raíces (Flush):** Regar con 3x el volumen de la maceta en agua limpia pH 6.0-6.5.
            - **Reposo de nutrientes:** Solo agua por 7-10 días.
            - **Carbón activado:** Mezclar un puñado en el sustrato para absorber exceso de sales.
            """
            video_url = "https://www.youtube.com/results?search_query=exceso+nitrogeno+cannabis+hojas+garra+solucion"
            if "Maceta" in sistema:
                remedio_sistema = "Flush generoso. Cambiar a fertilizante de floración si ya está en flora. Reducir dosis general un 40%."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Regar abundante con agua limpia. Dejar de fertilizar por 2 semanas. En tierra madre se corrige más lento, paciencia."
            elif sistema == "Interior Luz":
                remedio_sistema = "Bajar EC a 0.5-0.8 por 1 semana. Flush con agua pH 6.0. Retomar con dosis reducida."
            elif "Automáticas" in sistema:
                remedio_sistema = "Flush suave y urgente. Las autos en flora con exceso de N producen cogollos aireados. Solo agua por 7 días."

        elif "garra" in sintoma and "arriba" in sintoma:
            diagnostico = "**Estrés térmico o lumínico generalizado.** Toda la planta con hojas hacia arriba indica calor excesivo o luz demasiado intensa."
            remedio_casero = """
            - **Sombra temporal:** Cubrir con malla media sombra 30-50% en horas pico.
            - **Aloe vera foliar:** 30 ml gel en 1 litro de agua, pulverizar al atardecer.
            - **Riego refrescante:** Regar al atardecer para bajar temperatura de raíces.
            - **Mulch grueso:** 10 cm de paja o corteza sobre sustrato para aislar raíces del calor.
            """
            video_url = "https://www.youtube.com/results?search_query=estres+calor+cannabis+toda+planta+solucion"
            if "Maceta" in sistema:
                remedio_sistema = "Mover a media sombra (12-16 hs). Macetas blancas reflejan calor. Regar 2 veces/día en olas de calor. Mulch obligatorio."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Instalar malla media sombra urgente. Mulch grueso. Regar profundo temprano. El calor extremo de La Carlota (40°C+) requiere protección."
            elif sistema == "Interior Luz":
                remedio_sistema = "Subir luces 15-20 cm. Luces de noche en verano. Reforzar extracción. Considerar aire acondicionado si supera 32°C."
            elif "Automáticas" in sistema:
                remedio_sistema = "Proteger urgente: sombra parcial exterior o alejar luces indoor. Las autos estresadas por calor producen mucho menos."

        elif "Manchas blancas" in sintoma:
            diagnostico = "**Oídio (Hongo).** Polvo blanco sobre las hojas. Muy común en otoño con rocío nocturno en La Carlota."
            remedio_casero = """
            - **Leche diluida:** 1 parte de leche + 9 partes de agua. Pulverizar con sol (la caseína + UV mata el oídio).
            - **Bicarbonato de sodio:** 1 cucharadita + 1 litro de agua + 2 gotas de jabón potásico. Pulverizar cada 5 días.
            - **Ajo macerado:** 5 dientes machacados en 1 litro de agua 24 hs. Colar y pulverizar.
            - **Cola de caballo:** Hervir 50g seca en 1 litro. Diluir 1:5 y pulverizar (antifúngico potente).
            """
            video_url = "https://www.youtube.com/results?search_query=oidio+cannabis+leche+bicarbonato+tratamiento+casero"
            if "Maceta" in sistema:
                remedio_sistema = "Leche foliar cada 5 días con sol. Separar macetas para ventilación. Podar hojas muy afectadas. Mover a zona con más circulación de aire."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Podar ramas bajas para circulación. Aplicar leche + bicarbonato foliar. Mantener distancia entre plantas (1.5 m mínimo). El rocío de La Carlota es factor clave."
            elif sistema == "Interior Luz":
                remedio_sistema = "Bajar humedad a 40-45%. Aumentar ventilación. Aplicar bicarbonato foliar con luces apagadas. Desinfectar la carpa con agua oxigenada."
            elif "Automáticas" in sistema:
                remedio_sistema = "Leche foliar es lo más seguro para autos. Defoliar hojas interiores para ventilación. Actuar rápido: las autos no tienen tiempo de recuperarse."

        elif "Puntos blancos" in sintoma:
            diagnostico = "**Arañuela Roja (Ácaro).** Puntos blancos en el haz, telarañas finas en el envés. Plaga grave en verano."
            remedio_casero = """
            - **Jabón potásico:** 5 ml por litro de agua. Pulverizar cubriendo el envés de las hojas. Repetir cada 3 días.
            - **Aceite de neem:** 3 ml por litro + jabón potásico como emulsionante. Aplicar al atardecer.
            - **Agua a presión:** Lavar las hojas con manguera suave para desalojar ácaros (solo exterior).
            - **Ajo + ají picante:** Licuar 5 dientes de ajo + 1 ají en 1 litro de agua. Colar y pulverizar.
            - **Tabaco macerado:** 2 cigarrillos en 1 litro 24 hs. Colar y pulverizar (solo en vegetativo).
            """
            video_url = "https://www.youtube.com/results?search_query=arañuela+roja+cannabis+tratamiento+jabón+potasico+neem"
            if "Maceta" in sistema:
                remedio_sistema = "Neem + jabón potásico cada 3 días. Lavar hojas con manguera. Aislar plantas afectadas. Subir humedad ambiental (las arañuelas odian la humedad alta)."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Neem preventivo cada 10 días en verano. Lavado con manguera intensivo. Plantar albahaca o caléndula cerca como repelente natural."
            elif sistema == "Interior Luz":
                remedio_sistema = "Emergencia: neem + jabón potásico intensivo. Subir humedad a 60%. Bajar temperatura. Considerar ácaros depredadores (Phytoseiulus) como control biológico."
            elif "Automáticas" in sistema:
                remedio_sistema = "Jabón potásico es lo más seguro. Neem con precaución en floración (puede afectar sabor). Actuar desde el primer punto blanco visible."

        elif "Agujeros" in sintoma:
            diagnostico = "**Orugas o Caracoles.** Agujeros irregulares en las hojas. Orugas dejan excremento negro; caracoles dejan baba brillante."
            remedio_casero = """
            - **Bacillus thuringiensis (BT):** Spray biológico que mata orugas sin dañar la planta. Aplicar cada 7 días.
            - **Inspección manual:** Revisar al atardecer y de noche con linterna. Retirar orugas y caracoles a mano.
            - **Ceniza o cáscara de huevo:** Barrera física alrededor de la base contra caracoles.
            - **Cerveza trampa:** Plato con cerveza enterrado al ras del suelo atrae y ahoga caracoles.
            - **Pimienta de cayena:** Espolvorear alrededor de la planta como repelente.
            """
            video_url = "https://www.youtube.com/results?search_query=orugas+caracoles+cannabis+control+natural+BT"
            if "Maceta" in sistema:
                remedio_sistema = "Inspección nocturna obligatoria en verano. BT preventivo cada 7 días dic-feb. Barrera de cáscara de huevo en el borde de la maceta."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "BT es esencial en La Carlota en temporada (dic-feb). Trampas de cerveza cada 2 metros. Revisar el envés de cada hoja y dentro de cogollos."
            elif sistema == "Interior Luz":
                remedio_sistema = "Raro en indoor cerrado. Si aparecen, vinieron en el sustrato o al ventilar. Inspeccionar y retirar manualmente. Sellar entradas con malla."
            elif "Automáticas" in sistema:
                remedio_sistema = "BT preventivo semanal. Una oruga puede destruir un cogollo entero en una auto. Inspección diaria en floración es obligatoria."

        elif "Moho gris" in sintoma:
            diagnostico = "**Botrytis (Moho Gris).** Hongo que pudre cogollos desde adentro. Letal en floración tardía con humedad alta."
            remedio_casero = """
            - **No hay cura casera efectiva.** El cogollo afectado debe retirarse inmediatamente.
            - **Prevención:** Defoliar para ventilación. No mojar cogollos. Reducir humedad.
            - **Agua oxigenada:** Pulverizar 3 ml de agua oxigenada (10 vol) en 1 litro de agua sobre zonas cercanas para frenar propagación.
            - **Canela en cortes:** Sellar toda herida de poda con canela.
            """
            video_url = "https://www.youtube.com/results?search_query=botrytis+moho+gris+cannabis+prevencion+cogollos"
            if "Maceta" in sistema:
                remedio_sistema = "Cortar cogollo afectado 5 cm por debajo del moho. Mover a zona ventilada. Si llueve, cubrir con plástico sin tocar la planta. Considerar cosecha anticipada."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Retirar partes afectadas. Podar ramas interiores para airear. Si hay pronóstico de lluvia, considerar cosechar anticipada. No compostar partes con botrytis."
            elif sistema == "Interior Luz":
                remedio_sistema = "Bajar humedad a 35-40% urgente. Máxima extracción. Retirar partes afectadas con guantes y desinfectar tijeras con alcohol entre cada corte."
            elif "Automáticas" in sistema:
                remedio_sistema = "Retirar la parte afectada inmediatamente. Si falta poco para cosechar, considerar corte anticipado para salvar el resto de la planta."

        elif "Tallos púrpuras" in sintoma:
            diagnostico = "**Fósforo bajo o estrés por frío generalizado.** Tallos y pecíolos púrpuras en toda la planta."
            remedio_casero = """
            - **Té de banana:** 3 cáscaras hervidas en 1 litro. Regar semanalmente.
            - **Harina de hueso:** 2 cucharadas en el sustrato.
            - **Protección nocturna:** Si hay frío, cubrir o entrar la planta de noche.
            - **Melaza:** 1 cucharada por litro de riego, ayuda a movilizar P.
            """
            video_url = "https://www.youtube.com/results?search_query=tallos+purpuras+cannabis+fosforo+frio+toda+planta"
            if "Maceta" in sistema:
                remedio_sistema = "Si las noches bajan de 10°C, entrar las macetas. Harina de hueso + té de banana. Si crece bien, probablemente es genético."
            elif sistema in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                remedio_sistema = "Mulch grueso para aislar raíces. Guano de murciélago cerca de las raíces. Las noches frías de La Carlota en otoño pueden causar esto."
            elif sistema == "Interior Luz":
                remedio_sistema = "Verificar temperatura con luces apagadas (mínimo 18°C). Aumentar P en nutrientes. Diferencia térmica día/noche mayor a 10°C causa esto."
            elif "Automáticas" in sistema:
                remedio_sistema = "Proteger del frío. Té de banana suave. Si la auto está sana y crece, puede ser genético y no hay problema."

    if not diagnostico:
        st.info("Seleccioná la zona afectada y el síntoma para obtener un diagnóstico detallado con remedios caseros y consejos para tu sistema de cultivo.")
    else:
        icon_subtitle("diagnostico", "Diagnóstico")
        st.error(diagnostico)

        col_rem1, col_rem2 = st.columns(2)
        with col_rem1:
            icon_subtitle("remedios", "Remedios Caseros y Naturales")
            st.markdown(remedio_casero)

        with col_rem2:
            icon_subtitle("asesoramiento", f"Consejo para: {sistema}")
            st.info(remedio_sistema)
            if "Invernadero" in sistema:
                st.success("🏡 **Nota Invernadero:** Estás protegido del viento y lluvia directa. Controlar ventilación interna para evitar acumulación de humedad. Abrir ventanas laterales durante el día.")

        cannabis_divider_mini()
        icon_subtitle("diagnostico", "Video Tutoriales")
        st.markdown(f"Encontrá tutoriales en video sobre este problema:")
        st.markdown(f"[Ver videos sobre este diagnóstico en YouTube]({video_url})")

    cannabis_divider()
    icon_subtitle("diagnostico", "Guía Rápida de Plagas Comunes en La Carlota")
    plagas_data = {
        "Plaga/Problema": ["Arañuela Roja", "Orugas", "Pulgones", "Trips", "Oídio", "Botrytis", "Mosquita del Sustrato"],
        "Temporada": ["Dic-Mar (calor)", "Dic-Feb", "Sep-Nov", "Oct-Dic", "Mar-May (otoño)", "Abr-Jun (humedad)", "Todo el año (indoor)"],
        "Prevención Natural": ["Neem cada 10 días", "BT semanal", "Jabón potásico", "Aceite de neem", "Leche foliar", "Defoliación", "Canela + secar sustrato"],
        "Urgencia": ["Alta", "Alta", "Media", "Media", "Media", "Crítica", "Baja"]
    }
    st.dataframe(pd.DataFrame(plagas_data), width="stretch", hide_index=True)

# --- MÓDULO 4: COSECHA CRIOLLA ---
elif menu == "Estimador de Cosecha":
    cannabis_banner("cosecha")
    mostrar_tutorial("Estimador de Cosecha")
    icon_title("cosecha", "Estimación de Cosecha")
    st.write("Identificación morfológica para semillas de origen incierto.")
    
    col_a, col_b = st.columns(2)
    with col_a:
        hoja = st.select_slider("Morfología de Hoja", options=["Índica", "Híbrida", "Sativa"])
        inicio = st.date_input("Inicio de Floración")
        
        
    with col_b:
        semanas = {"Índica": 8, "Híbrida": 10, "Sativa": 13}[hoja]
        cosecha = inicio + datetime.timedelta(weeks=semanas)
        st.metric("Fecha de Corte Estimada", cosecha.strftime("%d-%m-%Y"))
        st.info(f"Ciclo estimado: {semanas} semanas.")

    cannabis_divider()
    icon_subtitle("cosecha", "Guía de Cosecha para Tus Cultivos Activos")

    if "cultivos" not in st.session_state or not st.session_state.cultivos:
        st.info("No tenés cultivos cargados en Seguimiento de Cultivo. Agregá al menos uno para recibir recomendaciones de cosecha personalizadas.")
    else:
        curr_clima_cos, _ = fetch_weather()
        temp_cos = curr_clima_cos['temperature_2m'] if curr_clima_cos else 25
        hum_cos = curr_clima_cos['relative_humidity_2m'] if curr_clima_cos else 50
        mes_cos = datetime.date.today().month

        for idx_cos, cultivo_cos in enumerate(st.session_state.cultivos):
            nombre_cos = cultivo_cos["nombre"]
            inicio_cos = cultivo_cos["inicio"]
            sistema_cos = cultivo_cos["sistema"]
            maceta_cos = cultivo_cos.get("maceta_litros")
            dias_cos = (datetime.date.today() - inicio_cos).days

            if "Automáticas" in sistema_cos:
                total_semanas = 12
                if dias_cos < 7: etapa_cos = "Germinación"
                elif dias_cos < 18: etapa_cos = "Plántula"
                elif dias_cos < 32: etapa_cos = "Vegetativo"
                elif dias_cos < 42: etapa_cos = "Pre-Floración"
                elif dias_cos < 56: etapa_cos = "Floración Temprana"
                elif dias_cos < 70: etapa_cos = "Floración Media"
                elif dias_cos < 84: etapa_cos = "Maduración"
                else: etapa_cos = "Flush y Cosecha"
                fecha_cosecha_est = inicio_cos + datetime.timedelta(weeks=total_semanas)
            elif sistema_cos == "Interior Luz":
                total_semanas = 20
                if dias_cos < 7: etapa_cos = "Germinación"
                elif dias_cos < 21: etapa_cos = "Plántula"
                elif dias_cos < 42: etapa_cos = "Vegetativo Temprano"
                elif dias_cos < 63: etapa_cos = "Vegetativo Avanzado"
                elif dias_cos < 77: etapa_cos = "Cambio a Floración"
                elif dias_cos < 98: etapa_cos = "Floración Temprana"
                elif dias_cos < 119: etapa_cos = "Floración Media"
                elif dias_cos < 140: etapa_cos = "Maduración"
                else: etapa_cos = "Flush y Cosecha"
                fecha_cosecha_est = inicio_cos + datetime.timedelta(weeks=total_semanas)
            else:
                total_semanas = 28
                if dias_cos < 10: etapa_cos = "Germinación"
                elif dias_cos < 25: etapa_cos = "Plántula"
                elif dias_cos < 50: etapa_cos = "Vegetativo Temprano"
                elif dias_cos < 90: etapa_cos = "Vegetativo Avanzado"
                elif dias_cos < 110: etapa_cos = "Pre-Floración"
                elif dias_cos < 140: etapa_cos = "Floración Temprana"
                elif dias_cos < 170: etapa_cos = "Floración Media"
                elif dias_cos < 200: etapa_cos = "Maduración"
                else: etapa_cos = "Flush y Cosecha"
                fecha_cosecha_est = inicio_cos + datetime.timedelta(weeks=total_semanas)

            dias_restantes = (fecha_cosecha_est - datetime.date.today()).days
            progreso = min(max(dias_cos / (total_semanas * 7), 0), 1.0)
            info_mac_cos = f" · Maceta: {maceta_cos}L" if maceta_cos else ""

            with st.expander(f"✂️ {etapa_cos} · {sistema_cos}{info_mac_cos}", expanded=(idx_cos == 0)):
                col_cos_izq, col_cos_der = st.columns([3, 1])
                with col_cos_der:
                    ic_co = icon_html("cosecha", 20)
                    st.markdown(f'<div class="cultivo-info-right"><div class="cultivo-nombre">{ic_co} {nombre_cos}</div><div class="cultivo-dia">Día {dias_cos}</div></div>', unsafe_allow_html=True)
                col_prog1, col_prog2 = st.columns([2, 1])
                with col_prog1:
                    st.progress(progreso, text=f"Progreso: {round(progreso * 100)}%")
                with col_prog2:
                    if dias_restantes > 0:
                        st.metric("Días para cosecha estimada", f"{dias_restantes} días")
                    else:
                        st.metric("Cosecha", "Lista para cortar")

                st.caption(f"Fecha de cosecha estimada: **{fecha_cosecha_est.strftime('%d/%m/%Y')}** | Sistema: **{sistema_cos}**")

                rendimiento_est = ""
                senales_cosecha = ""
                tricomas = ""
                flush_guia = ""
                corte_tecnica = ""
                secado = ""
                curado = ""
                errores_cos = ""
                clima_cosecha = ""

                if etapa_cos in ["Germinación", "Plántula"]:
                    st.info("Tu planta recién empieza. La cosecha está lejos todavía, pero podés ir preparándote.")
                    senales_cosecha = "Aún no hay señales de cosecha. La planta necesita completar todo el ciclo vegetativo y de floración antes de pensar en cosechar."
                    corte_tecnica = "No aplica todavía. Enfocate en que la planta desarrolle un buen sistema de raíces y estructura sana."
                    if "Automáticas" in sistema_cos:
                        rendimiento_est = "Automáticas: rendimiento estimado 30-100g por planta según genética, luz y nutrición."
                    elif sistema_cos == "Interior Luz":
                        rendimiento_est = "Indoor: rendimiento estimado 50-150g por planta con buena iluminación y manejo."
                    elif "Maceta" in sistema_cos:
                        if maceta_cos and maceta_cos <= 10:
                            rendimiento_est = f"Maceta {maceta_cos}L exterior: rendimiento estimado 30-80g. Maceta chica limita el tamaño final."
                        elif maceta_cos and maceta_cos <= 20:
                            rendimiento_est = f"Maceta {maceta_cos}L exterior: rendimiento estimado 80-200g con buena nutrición."
                        elif maceta_cos and maceta_cos > 20:
                            rendimiento_est = f"Maceta {maceta_cos}L exterior: rendimiento estimado 150-400g. Buen volumen de sustrato."
                        else:
                            rendimiento_est = "Exterior maceta: rendimiento variable según tamaño de maceta, entre 50-300g."
                    elif sistema_cos in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                        rendimiento_est = "Tierra madre exterior: rendimiento estimado 200-1000g+ por planta. Sin límite de raíces, el potencial es enorme."

                elif etapa_cos in ["Vegetativo Temprano", "Vegetativo", "Vegetativo Avanzado"]:
                    st.info("Tu planta está en crecimiento vegetativo. La cosecha aún está lejos, pero hay cosas que podés hacer ahora para maximizarla.")
                    senales_cosecha = "Todavía no. La planta debe completar la floración antes de cosechar. Si estás en exterior, la flora empieza naturalmente cuando los días se acortan (marzo en La Carlota)."
                    corte_tecnica = "**Ahora es momento de técnicas de entrenamiento para mejorar el rendimiento futuro:**"
                    if "Automáticas" in sistema_cos:
                        corte_tecnica += "\n- LST (Low Stress Training): doblar ramas suavemente con alambre. No hacer topping a las autos."
                        corte_tecnica += "\n- Defoliación mínima: solo hojas que bloqueen luz a sitios de cogollos."
                        rendimiento_est = "Automáticas bien entrenadas: 50-120g por planta."
                    elif sistema_cos == "Interior Luz":
                        corte_tecnica += "\n- Topping: cortar la punta principal para generar 2 ramas líderes. Hacer en 4to-5to nudo."
                        corte_tecnica += "\n- SCROG (Screen of Green): red horizontal para distribuir ramas parejas bajo la luz."
                        corte_tecnica += "\n- Lollipopping: limpiar ramas bajas que no reciben luz."
                        rendimiento_est = "Indoor bien manejado: 80-200g por planta."
                    elif "Maceta" in sistema_cos:
                        corte_tecnica += "\n- Topping: cortar la punta para ramificar. Ideal en 5to-6to nudo."
                        corte_tecnica += "\n- LST: amarrar ramas para abrir la planta al sol."
                        corte_tecnica += "\n- Poda de bajos: limpiar las ramas inferiores que no reciben sol directo."
                        if maceta_cos and maceta_cos <= 10:
                            rendimiento_est = f"Maceta {maceta_cos}L: 40-100g estimados. Considerar trasplante a maceta más grande si aún hay tiempo."
                        elif maceta_cos and maceta_cos <= 20:
                            rendimiento_est = f"Maceta {maceta_cos}L: 100-250g estimados con buen manejo."
                        else:
                            rendimiento_est = f"Maceta {maceta_cos}L: 200-500g estimados. Excelente volumen de sustrato."
                    elif sistema_cos in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                        corte_tecnica += "\n- Topping múltiple: se puede hacer 2-3 veces en tierra madre para generar un arbusto grande."
                        corte_tecnica += "\n- Tutores: ir preparando la estructura de soporte, la planta va a crecer mucho."
                        corte_tecnica += "\n- Poda selectiva: ir limpiando ramas interiores sin luz para concentrar energía."
                        rendimiento_est = "Tierra madre: 300-1500g+ por planta. El potencial es enorme con buena nutrición."

                elif etapa_cos in ["Pre-Floración", "Cambio a Floración"]:
                    senales_cosecha = "La planta muestra los primeros pistilos (pelitos blancos). No es momento de cosechar, pero empieza la cuenta regresiva. Desde los primeros pistilos, faltan 8-12 semanas para la cosecha según genética."
                    tricomas = "Todavía no se observan tricomas maduros. Los pistilos blancos indican inicio de floración. No revisar tricomas todavía, es muy pronto."
                    corte_tecnica = "**Último momento para entrenar:**\n- Defoliación estratégica: quitar hojas grandes que tapen sitios de cogollos.\n- Lollipopping: limpiar el tercio inferior de la planta.\n- Colocar tutores o malla de soporte para los cogollos que vienen."
                    flush_guia = "No hacer flush ahora. La planta necesita nutrición completa para formar flores. Flush se hace 1-2 semanas antes del corte."
                    if "Automáticas" in sistema_cos:
                        senales_cosecha = "Las autos entran en flora solas. Si ves pistilos, faltan aproximadamente 5-7 semanas para la cosecha."
                        rendimiento_est = "Automáticas en pre-flora: el rendimiento ya se puede estimar mejor. Si la planta es robusta con muchos sitios de cogollos: 60-120g. Si es flaca: 20-50g."
                    elif sistema_cos in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                        rendimiento_est = "La planta en tierra madre debería ser grande a esta altura. Estimación: 300-1000g+ según tamaño y ramificación."
                    errores_cos = "No podar ramas principales en esta etapa. No estresar la planta con cambios bruscos. El estrés puede causar hermafroditismo (bananas/nanners)."

                elif etapa_cos in ["Floración Temprana", "Floración"]:
                    senales_cosecha = "Los cogollos empiezan a formarse y engordar. Pistilos blancos abundantes. **No cosechar todavía**, la planta recién está empezando a producir resina y cannabinoides."
                    tricomas = "Empiezan a aparecer tricomas (cristales) visibles a simple vista. Con lupa 60x se ven transparentes/cristalinos = aún inmaduros. Falta mucho para el punto de cosecha."
                    flush_guia = "No hacer flush. Mantener nutrición de floración (P y K altos). La planta necesita toda la energía para engordar cogollos."
                    corte_tecnica = "No podar nada. Solo quitar hojas amarillas o muertas que puedan generar moho. No defoliar en exceso durante la flora."
                    errores_cos = "NUNCA mojar los cogollos. Si llueve, sacudir las ramas suavemente. Inspeccionar el interior de cogollos densos buscando moho."
                    if "Automáticas" in sistema_cos:
                        rendimiento_est = "El rendimiento se define ahora. Cogollos densos y blancos de pistilos = buen camino. Estimación: 40-120g según genética y manejo."
                    elif sistema_cos == "Interior Luz":
                        rendimiento_est = "Revisá la distancia de la luz: los cogollos superiores deben estar a 30-40cm del panel. Si están más lejos, acercar para engordar."
                    elif "Maceta" in sistema_cos:
                        if maceta_cos and maceta_cos <= 10:
                            errores_cos += f" Maceta {maceta_cos}L: la planta puede estar limitada en raíces. Si los cogollos no engordan, puede ser falta de espacio."
                        rendimiento_est = "Exterior maceta en floración: los cogollos empiezan a engordar. Usar tutores si las ramas se doblan por el peso."
                    elif sistema_cos in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                        rendimiento_est = "Tierra madre en floración: cogollos pueden ser muy grandes y pesados. Tutores y malla de soporte son fundamentales."
                    clima_cosecha = "En La Carlota, la floración exterior suele caer en otoño (marzo-mayo). Vigilar el rocío nocturno que aumenta el riesgo de botrytis (moho gris)."

                elif etapa_cos == "Floración Media":
                    senales_cosecha = "Cogollos engordando fuerte. Pistilos empiezan a cambiar de blanco a naranja/marrón (30-50%). Olor intenso. **Todavía no es momento de cortar.** Faltan 2-4 semanas."
                    tricomas = """**Empezá a revisar tricomas con lupa 60x o microscopio de celular:**
- Transparentes/cristalinos = inmaduros, falta.
- Lechosos/blancos opacos = THC alto, efecto más cerebral y energético.
- Ámbar/dorados = CBD sube, efecto más corporal y relajante.
**Punto ideal para la mayoría: 70-80% lechosos + 20-30% ámbar.**"""
                    flush_guia = "**Preparar el flush:** Si estimás que faltan 2 semanas para cortar, empezar flush ahora. Solo agua limpia, sin nutrientes. Esto limpia sales del sustrato y mejora el sabor final del producto."
                    corte_tecnica = "Preparar el espacio de secado: lugar oscuro, ventilado, 18-22°C, 55-65% humedad. Limpiar las tijeras de poda con alcohol. Preparar cuerdas o malla para colgar ramas."
                    secado = "Tener listo el espacio antes de cortar. Necesitás oscuridad total, buena circulación de aire (ventilador indirecto, nunca apuntando directo a las plantas), y temperatura/humedad controlada."
                    errores_cos = "No cosechar con pistilos todavía blancos (inmaduros). No cosechar solo por los días: siempre revisar tricomas. Cada genética madura diferente."
                    if "Automáticas" in sistema_cos:
                        flush_guia = "Autos: flush más corto, 5-7 días. Las autos maduran rápido, no extender demasiado el flush."
                    if sistema_cos in ["Exterior Maceta", "Exterior Tierra Madre", "Invernadero Maceta", "Invernadero Tierra"]:
                        clima_cosecha = "**Otoño en La Carlota:** Las lluvias de abril-mayo son el mayor riesgo. Si se anuncian lluvias sobre cogollos maduros, considerar cosechar antes aunque falte un poco. Mejor cortar levemente antes que perder todo por moho."

                elif etapa_cos in ["Maduración", "Floración Tardía / Maduración"]:
                    senales_cosecha = """**La cosecha está cerca. Señales clave:**
- 70-90% de pistilos cambiaron a naranja/marrón.
- Cogollos firmes y densos al tacto.
- Olor muy intenso y definido.
- Las hojas grandes (abanico) empiezan a amarillear naturalmente.
- Tricomas: la señal definitiva (ver abajo)."""
                    tricomas = """**Revisá tricomas TODOS LOS DÍAS con lupa 60x:**
- **Mayoría transparentes:** NO CORTAR. Falta.
- **Mayoría lechosos (70-80%) + pocos ámbar (10-20%):** Efecto más cerebral, energético, eufórico. Buena ventana para cortar.
- **50% lechosos + 50% ámbar:** Efecto balanceado, cerebral + corporal. Punto medio ideal para uso medicinal.
- **Mayoría ámbar (60%+):** Efecto muy corporal, sedante, couchlock. Ideal para insomnio y dolor crónico.
**Elegí el punto de corte según el efecto que buscás.**"""
                    flush_guia = "Deberías estar en flush (solo agua) hace al menos una semana. Si no empezaste, hacelo ya. Las hojas amarilleando = normal y deseado. La planta consume sus reservas."
                    corte_tecnica = """**Preparación para el corte:**
1. Elegir el día: mañana fresca, antes de que pegue el sol. Los terpenos están más concentrados temprano.
2. Dejar de regar 1-2 días antes del corte para que el sustrato esté seco.
3. Oscuridad 24-48 hs antes del corte (opcional pero mejora la resina). Algunas técnicas sugieren dejar en oscuridad total 2 días antes.
4. Cortar rama por rama o la planta entera según preferencia.
5. Manicurado: en húmedo (cortar hojitas al momento del corte) o en seco (colgar con hojas y manicurar después del secado)."""
                    secado = """**Secado correcto (fase más importante):**
- Colgar ramas boca abajo en un espacio **oscuro y ventilado**.
- Temperatura ideal: **18-22°C**. Nunca superar 25°C (se degradan terpenos y cannabinoides).
- Humedad ideal: **55-65%**. Muy seca = secado rápido y áspero. Muy húmeda = moho.
- Circulación de aire suave (ventilador indirecto, NO apuntando a las ramas).
- Duración: **7-14 días** hasta que los tallos finos se quiebren al doblarlos (no se doblen).
- **NO usar ventilador directo, microondas, horno ni secadora.** Arruinan la calidad."""
                    curado = """**Curado (la diferencia entre porro bueno y excelente):**
- Después del secado, poner los cogollos en frascos de vidrio herméticos (tipo Mason o mermelada).
- Llenar el frasco al 70-75% (dejar espacio de aire).
- Primeras 2 semanas: abrir los frascos 2-3 veces por día por 10-15 minutos ("eructar" los frascos).
- Semanas 3-4: abrir 1 vez por día.
- Después del primer mes: abrir 1 vez por semana.
- Duración ideal: **mínimo 2 semanas, óptimo 1-3 meses**. A mayor curado, mejor sabor y suavidad.
- Si olés a amoníaco al abrir: hay humedad de más. Sacar cogollos del frasco y airear unas horas.
- Guardar frascos en lugar **oscuro y fresco** (no en la heladera)."""
                    errores_cos = "No apurarse. Mejor esperar 2-3 días de más que cortar antes de tiempo. Cogollos inmaduros = efecto débil y sabor verde. No secar rápido con calor. No usar bolsas de plástico para curar."
                    if "Automáticas" in sistema_cos:
                        corte_tecnica += "\n\n**Autos:** Pueden madurar desparejo (cogollos superiores antes que inferiores). Podés hacer cosecha escalonada: cortar los de arriba primero y dejar madurar los de abajo 5-7 días más."
                    elif "Maceta" in sistema_cos:
                        if maceta_cos and maceta_cos <= 10:
                            rendimiento_est = f"Maceta {maceta_cos}L: rendimiento estimado 30-80g secos. La maceta chica limitó el potencial."
                        elif maceta_cos and maceta_cos <= 20:
                            rendimiento_est = f"Maceta {maceta_cos}L: rendimiento estimado 80-200g secos."
                        else:
                            rendimiento_est = f"Maceta {maceta_cos}L: rendimiento estimado 150-400g secos."
                    elif sistema_cos in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                        rendimiento_est = "Tierra madre: rendimiento estimado 200-1000g+ secos según tamaño de la planta."
                        clima_cosecha = "**La Carlota otoño:** Si las lluvias amenazan cogollos maduros, NO dudar en cortar. Un temporal puede causar botrytis en horas y perder toda la cosecha."
                    elif sistema_cos == "Interior Luz":
                        rendimiento_est = "Indoor: rendimiento estimado 50-200g secos por planta según iluminación y manejo."

                elif etapa_cos == "Flush y Cosecha":
                    senales_cosecha = """**¡Es hora de cosechar!** Confirmá estos indicadores finales:
- Pistilos: 80-90%+ naranjas/marrones.
- Tricomas: según tu preferencia de efecto (ver guía arriba).
- Hojas abanico: amarillas y cayendo naturalmente.
- Cogollos: firmes, pesados, aromáticos.
- Si todo coincide: **cortá mañana temprano, antes de que salga el sol.**"""
                    tricomas = """**Último chequeo de tricomas:**
- Lechosos + pocos ámbar = efecto cerebral, creativo, energético.
- Mitad lechosos + mitad ámbar = balanceado, versátil.
- Mayoría ámbar = corporal, sedante, medicinal para dolor/insomnio.
**Una vez decidido, no esperes más.** Los tricomas se degradan si pasás el punto."""
                    corte_tecnica = """**Paso a paso del corte:**
1. No regar 1-2 días antes.
2. Cortar a primera hora de la mañana, antes del sol.
3. Cortar ramas individuales o la planta entera por la base.
4. **Manicurado húmedo** (recomendado para La Carlota por la humedad): recortar las hojas con resina (sugar leaves) al momento del corte con tijeras afiladas. Guardar los recortes para hacer manteca o extracciones.
5. Colgar ramas boca abajo con hilo o gancho.
6. Si la humedad ambiente es alta (>65%), usar deshumidificador o ventilación extra."""
                    secado = """**Protocolo de secado para La Carlota:**
- La Carlota tiene humedad variable: en otoño puede ser alta. Tener ventilación y controlar con higrómetro.
- Lugar: pieza interior oscura, NO al aire libre (polvo, insectos, lluvia).
- Temperatura: 18-22°C (en otoño suele estar bien naturalmente).
- Humedad: 55-65%. Si sube de 70%, usar deshumidificador o ventilador extra.
- Duración: 7-14 días. Los tallos finos deben quebrarse (no doblarse) al finalizar.
- Inspeccionar diariamente buscando moho, especialmente en cogollos densos."""
                    curado = """**Curado final:**
- Frascos de vidrio al 70-75% de capacidad.
- Semanas 1-2: abrir 2-3 veces/día, 10-15 min cada vez.
- Semanas 3-4: abrir 1 vez/día.
- Mes 2 en adelante: abrir 1 vez/semana.
- Curado mínimo 2 semanas, ideal 1-3 meses. Más tiempo = mejor sabor.
- Guardar en oscuridad y fresco (20°C). No heladera. No freezer.
- Los cogollos bien curados pueden guardarse 6-12 meses sin perder calidad."""
                    errores_cos = "No secar con calor (horno, microondas, secador). No usar bolsas plásticas. No apretar los cogollos en el frasco. Si olés amoníaco = sacar y airear. Si ves moho = descartar esa parte."
                    if "Automáticas" in sistema_cos:
                        corte_tecnica += "\n\n**Cosecha escalonada de autos:** Los cogollos superiores maduran antes. Cortá los de arriba, bajá la luz para los de abajo, y esperá 5-7 días más."
                    if sistema_cos in ["Exterior Maceta", "Exterior Tierra Madre", "Invernadero Maceta", "Invernadero Tierra"]:
                        clima_cosecha = "**Atención:** Si se pronostican lluvias, no esperar. Cosechar antes de la lluvia. Un chaparrón sobre cogollos maduros es la receta del desastre (moho gris/botrytis). Mejor unos días antes que perder todo."

                tab_cos1, tab_cos2, tab_cos3, tab_cos4, tab_cos5, tab_cos6 = st.tabs([
                    "Señales de Cosecha", "Tricomas", "Rendimiento", "Flush & Corte", "Secado", "Curado"
                ])

                with tab_cos1:
                    st.markdown("#### ¿Cuándo Cosechar?")
                    st.markdown(senales_cosecha if senales_cosecha else "Revisá las señales según la etapa de tu planta.")
                    if errores_cos:
                        st.error(f"**Errores a evitar:** {errores_cos}")

                with tab_cos2:
                    st.markdown("#### Lectura de Tricomas")
                    st.markdown(tricomas if tricomas else "Los tricomas se revisan en las últimas semanas de floración con lupa 60x o microscopio de celular.")
                    if etapa_cos not in ["Germinación", "Plántula", "Vegetativo Temprano", "Vegetativo", "Vegetativo Avanzado"]:
                        st.info("**Tip:** Los microscopios para celular se consiguen baratos en Mercado Libre (buscar 'microscopio celular 60x'). Es la mejor inversión para saber cuándo cortar.")

                with tab_cos3:
                    st.markdown("#### Rendimiento Estimado")
                    st.markdown(rendimiento_est if rendimiento_est else "El rendimiento depende del sistema, genética, nutrición y manejo general.")
                    if "Maceta" in sistema_cos and maceta_cos:
                        st.info(f"**Nota sobre maceta {maceta_cos}L:** El tamaño de la maceta es el factor más limitante en exterior. Más litros = más raíces = más producción.")
                    elif sistema_cos in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                        st.info("**Tierra madre** no tiene límite de raíces. Con buena nutrición y sol, una planta puede dar 500g-1.5kg+ en seco.")

                with tab_cos4:
                    st.markdown("#### Flush y Técnica de Corte")
                    if flush_guia:
                        st.markdown("**Flush (lavado de raíces):**")
                        st.markdown(flush_guia)
                    st.markdown("**Corte y Preparación:**")
                    st.markdown(corte_tecnica if corte_tecnica else "Las técnicas de corte se aplican en las etapas finales de la planta.")

                with tab_cos5:
                    st.markdown("#### Secado")
                    st.markdown(secado if secado else "El secado se planifica cuando la cosecha está cerca. Preparar un espacio oscuro, ventilado, 18-22°C y 55-65% humedad.")
                    if etapa_cos in ["Maduración", "Flush y Cosecha", "Floración Tardía / Maduración"]:
                        st.warning("**Recordatorio:** El secado rápido arruina meses de trabajo. Paciencia. 7-14 días mínimo. No usar calor artificial.")

                with tab_cos6:
                    st.markdown("#### Curado")
                    st.markdown(curado if curado else "El curado es el paso final que mejora drásticamente el sabor y la suavidad. Se realiza después del secado en frascos de vidrio.")
                    if etapa_cos in ["Maduración", "Flush y Cosecha", "Floración Tardía / Maduración"]:
                        st.success("**Consejo:** Los frascos de vidrio tipo Mason o de mermelada son ideales. Se consiguen en ferreterías y bazares de La Carlota. Comprar suficientes antes de cosechar.")

                if clima_cosecha:
                    st.warning(f"🌦️ **Alerta Clima La Carlota:** {clima_cosecha}")

                if temp_cos > 28 and etapa_cos in ["Maduración", "Flush y Cosecha"]:
                    st.warning(f"🌡️ **Calor actual ({temp_cos}°C):** El calor excesivo degrada tricomas y terpenos. Si podés, cosechá a primera hora de la mañana cuando hace más fresco. Para el secado, buscar el lugar más fresco de la casa.")
                if hum_cos > 65 and etapa_cos in ["Maduración", "Flush y Cosecha", "Floración Media"]:
                    st.error(f"💧 **Humedad alta ({hum_cos}%):** Riesgo de moho elevado. En exterior, inspeccionar cogollos densos por dentro. En secado, usar deshumidificador o ventilación extra. No dejar cogollos sin supervisión.")

# --- MÓDULO 5: LEGAL ---
elif menu == "Sugerencias Legales":
    cannabis_banner("legal")
    mostrar_tutorial("Sugerencias Legales")
    icon_title("legal", "REPROCANN & Normativa")

    tab_novedades, tab_info, tab_requisitos, tab_tramite, tab_limites, tab_derechos = st.tabs([
        "📰 Novedades Legales", "Información General", "Requisitos", "Cómo Tramitar", "Límites Legales", "Derechos y Consejos"
    ])

    with tab_novedades:
        icon_subtitle("legal", "Novedades sobre Legislación Cannábica en Argentina")
        st.caption("Se actualiza automáticamente cada 6 horas buscando noticias recientes sobre leyes, REPROCANN y regulación del cannabis en Argentina.")

        noticias = obtener_novedades_cannabis()

        if noticias:
            st.success(f"Se encontraron **{len(noticias)}** noticias recientes. Última actualización: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")
            for i, noticia in enumerate(noticias):
                fecha_txt = noticia['fecha'] if noticia['fecha'] else ""
                fuente_txt = noticia['fuente'] if noticia['fuente'] else ""
                meta_parts = []
                if fecha_txt:
                    meta_parts.append(f"📅 {fecha_txt}")
                if fuente_txt:
                    meta_parts.append(f"📰 {fuente_txt}")
                meta_str = " · ".join(meta_parts)
                st.markdown(f'''<div class="news-card">
                    <div class="news-title"><a href="{noticia['link']}" target="_blank">{noticia['titulo']}</a></div>
                    <div class="news-meta">{meta_str}</div>
                </div>''', unsafe_allow_html=True)
        else:
            st.info("No se encontraron noticias recientes. Esto puede deberse a una conexión limitada. Reintentá más tarde.")

        cannabis_divider_mini()
        st.markdown("#### 🔗 Fuentes Oficiales para Consultar")
        st.markdown("""
        - **REPROCANN:** [reprocann.salud.gob.ar](https://reprocann.salud.gob.ar)
        - **Boletín Oficial:** [boletinoficial.gob.ar](https://www.boletinoficial.gob.ar) — Donde se publican las leyes y decretos.
        - **InfoLEG:** [infoleg.gob.ar](http://www.infoleg.gob.ar) — Base de datos de legislación argentina.
        - **Ley 27.350:** [Texto completo en InfoLEG](http://servicios.infoleg.gob.ar/infolegInternet/anexos/270000-274999/273801/norma.htm)
        - **Decreto 883/2020:** Reglamentación de la Ley 27.350 que creó el REPROCANN.
        - **ANMAT:** [argentina.gob.ar/anmat](https://www.argentina.gob.ar/anmat) — Regulación de productos de cannabis.
        """)

    with tab_info:
        icon_subtitle("legal", "¿Qué es el REPROCANN?")
        st.markdown("""
        El **REPROCANN** (Registro del Programa de Cannabis) es el registro nacional del Ministerio de Salud de Argentina
        que autoriza a pacientes, familiares y cultivadores solidarios a cultivar cannabis con fines medicinales y/o terapéuticos.

        Fue creado por el **Decreto 883/2020** que reglamenta la **Ley 27.350** (Ley de Cannabis Medicinal).

        **¿Para qué sirve?**
        - Autoriza legalmente el cultivo de cannabis para uso medicinal/terapéutico.
        - Permite la tenencia de plantas, semillas y derivados (aceites, cremas, tinturas).
        - Brinda un marco legal que protege al cultivador inscripto ante las fuerzas de seguridad.
        """)

        st.info("El REPROCANN no autoriza la venta ni la comercialización de cannabis ni sus derivados.")

    with tab_requisitos:
        icon_subtitle("legal", "Requisitos para Inscribirse")

        st.markdown("#### Documentación Necesaria")
        st.markdown("""
        1. **DNI argentino** vigente (frente y dorso escaneado o foto clara).
        2. **Indicación médica** firmada por un/a profesional de la salud (médico/a matriculado/a).
           - Debe especificar que el paciente requiere tratamiento con cannabis.
           - No hace falta que sea especialista: cualquier médico/a con matrícula nacional puede indicarlo.
        3. **CUIL** del solicitante.
        4. **Correo electrónico** activo para recibir notificaciones.
        5. **Foto carnet** actualizada del solicitante.
        6. **Domicilio de cultivo** (dirección donde se cultivará, en La Carlota, Córdoba).
        """)

        st.markdown("#### ¿Quiénes pueden inscribirse?")
        st.markdown("""
        - **Paciente cultivador/a:** La persona que necesita el tratamiento cultiva para sí misma.
        - **Familiar cultivador/a:** Un familiar directo cultiva para el/la paciente (padre, madre, hijo/a, hermano/a, cónyuge).
        - **Cultivador/a solidario/a:** Una persona registrada cultiva para hasta 5 pacientes que no pueden cultivar por sí mismos.
        - **ONG o Asociación Civil:** Organizaciones registradas que cultivan para sus asociados.
        """)

        st.warning("El/la médico/a que firma la indicación NO necesita estar especializado en cannabis. Cualquier médico/a con matrícula puede hacerlo.")

    with tab_tramite:
        icon_subtitle("legal", "Paso a Paso para Obtener el Certificado")

        st.markdown("""
        #### Paso 1: Conseguir la Indicación Médica
        - Consultá con tu médico/a de confianza (clínico, generalista, o cualquier especialidad).
        - Pedile que te haga una **indicación médica** para tratamiento con cannabis.
        - La indicación debe incluir: nombre del paciente, diagnóstico o condición, firma y sello del médico/a, y matrícula.
        - **En La Carlota:** Podés consultar en el Hospital Regional o con médicos/as particulares de la zona.

        #### Paso 2: Registrarse en la Plataforma
        - Ingresá a la web oficial del REPROCANN: **https://reprocann.salud.gob.ar**
        - Creá una cuenta con tu correo electrónico y una contraseña.
        - Completá tus datos personales (nombre, DNI, CUIL, domicilio).

        #### Paso 3: Cargar la Documentación
        - Subí la foto/escaneo de tu DNI (frente y dorso).
        - Subí la indicación médica firmada (foto clara o PDF).
        - Subí tu foto carnet actualizada.
        - Indicá el domicilio donde vas a cultivar.
        - Elegí la modalidad: paciente, familiar o cultivador solidario.

        #### Paso 4: Esperar la Aprobación
        - El Ministerio de Salud revisa la solicitud.
        - **Plazo estimado:** entre 15 y 90 días hábiles (puede variar).
        - Recibís la respuesta por correo electrónico.
        - Si es aprobada, podés descargar tu **certificado REPROCANN** desde la plataforma.

        #### Paso 5: Descargar e Imprimir el Certificado
        - Descargá el certificado en PDF desde la plataforma.
        - Imprimí una copia y guardá otra digital en tu celular.
        - El certificado tiene **vigencia de 1 año** y debe renovarse.
        """)

        st.success("El trámite es **100% gratuito** y se realiza de forma online.")

        st.markdown("#### Renovación")
        st.markdown("""
        - El certificado vence al año de su emisión.
        - Para renovar, necesitás una **nueva indicación médica** actualizada.
        - El trámite de renovación se hace por la misma plataforma web.
        - **Recomendación:** Empezar la renovación 30-60 días antes del vencimiento.
        """)

    with tab_limites:
        icon_subtitle("legal", "Límites Legales del Cultivo")

        col_lim1, col_lim2 = st.columns(2)
        with col_lim1:
            st.markdown("#### Cantidades Autorizadas")
            limites_data = {
                "Concepto": [
                    "Plantas en floración",
                    "Plantas en vegetativo",
                    "Flores secas (tenencia)",
                    "Semillas",
                    "Aceite/Tintura (tenencia)",
                    "Transporte de flores secas"
                ],
                "Límite": [
                    "Hasta 9 plantas",
                    "Sin límite específico",
                    "Hasta 40 gramos",
                    "Permitidas (sin límite específico)",
                    "Hasta 6 frascos de 30 ml",
                    "Hasta 40 gramos con certificado"
                ]
            }
            st.dataframe(pd.DataFrame(limites_data), width="stretch", hide_index=True)

        with col_lim2:
            st.markdown("#### Lo que NO está permitido")
            st.markdown("""
            - Vender o comercializar cannabis ni derivados.
            - Cultivar sin estar registrado en REPROCANN.
            - Superar los límites de plantas en floración.
            - Conducir bajo los efectos del cannabis.
            - Cultivar en espacios públicos.
            - Proveer a personas no registradas como pacientes.
            """)

        cannabis_divider_mini()
        st.markdown("#### Ante un Control Policial")
        st.markdown("""
        Si te para la policía o hay un allanamiento:

        1. **Mantené la calma.** Tenés derecho a cultivar si estás registrado.
        2. **Mostrá tu certificado REPROCANN** (digital o impreso) y tu DNI.
        3. **No resistás** el procedimiento, pero dejá constancia de que estás registrado.
        4. **Pedí que se labre acta** de todo lo que suceda.
        5. **Contactá a un abogado** si la situación se complica.
        6. **No declares sin abogado** presente si te llevan a declarar.
        """)
        st.error("Importante: Las fuerzas de seguridad deben respetar tu inscripción. Si no lo hacen, es una irregularidad denunciable.")

    with tab_derechos:
        icon_subtitle("legal", "Tus Derechos como Cultivador/a Registrado/a")

        st.markdown("""
        #### Derechos que te otorga el REPROCANN

        - **Cultivar:** Hasta 9 plantas en floración en tu domicilio registrado.
        - **Poseer:** Semillas, plantines, flores secas (hasta 40g) y derivados.
        - **Transportar:** Hasta 40g de flores secas con certificado + DNI.
        - **Elaborar derivados:** Aceites, tinturas, cremas para uso personal medicinal.
        - **Protección legal:** Ante controles policiales, tu registro te protege.

        #### Obligaciones

        - Cultivar solo en el domicilio registrado.
        - Respetar los límites de plantas y cantidades.
        - Renovar el certificado antes de su vencimiento.
        - No comercializar ni proveer a terceros no registrados.
        - Mantener el cultivo en un espacio seguro, fuera del alcance de menores.
        """)

        cannabis_divider()
        icon_subtitle("legal", "Recursos y Contactos Útiles")

        st.markdown("""
        - **Plataforma REPROCANN:** [https://reprocann.salud.gob.ar](https://reprocann.salud.gob.ar)
        - **Ministerio de Salud:** 0800-222-1002 (línea gratuita)
        - **ANMAT:** [https://www.argentina.gob.ar/anmat](https://www.argentina.gob.ar/anmat)
        - **Defensoría del Pueblo:** Para denuncias por irregularidades en controles.
        """)

        st.markdown("#### Organizaciones y Redes de Apoyo en Córdoba")
        st.markdown("""
        - **Mamá Cultiva Argentina:** Red de madres que cultivan para hijos con patologías. Orientación y acompañamiento.
        - **Asociaciones cannábicas locales:** Buscar en redes sociales grupos de cultivadores de La Carlota y zona sur de Córdoba.
        - **Médicos amigables:** Consultar en redes de cannabis medicinal por profesionales en la zona de La Carlota que firmen indicaciones.
        """)

        cannabis_divider()
        icon_subtitle("legal", "Preguntas Frecuentes")

        with st.expander("¿Necesito un médico especialista para la indicación?"):
            st.markdown("No. Cualquier médico/a con matrícula nacional puede firmar la indicación. No necesita ser especialista en cannabis ni en ninguna especialidad particular.")

        with st.expander("¿El trámite tiene costo?"):
            st.markdown("No. El trámite de inscripción y renovación en REPROCANN es **100% gratuito**. Desconfiá de gestores que cobren por hacerlo.")

        with st.expander("¿Cuánto tarda la aprobación?"):
            st.markdown("El plazo oficial es de 15 a 90 días hábiles, pero puede variar. En general, tarda entre 30 y 60 días. Revisá tu correo electrónico regularmente.")

        with st.expander("¿Puedo cultivar mientras espero la aprobación?"):
            st.markdown("Legalmente, la autorización rige desde la aprobación. Sin embargo, una vez presentada la solicitud, tenés el comprobante de inicio de trámite que demuestra tu intención de registrarte.")

        with st.expander("¿Qué pasa si me vence el certificado y no renové?"):
            st.markdown("Si tu certificado venció, legalmente no estás cubierto. Es importante renovar **antes** del vencimiento. Si venció, iniciá la renovación lo antes posible y guardá el comprobante de trámite en curso.")

        with st.expander("¿Puedo cultivar en un departamento o en un balcón?"):
            st.markdown("Sí, siempre que sea en el domicilio registrado. Podés cultivar en interior (indoor), balcón o terraza. No es obligatorio tener patio o terreno.")

        with st.expander("¿Puedo tener más de 9 plantas si algunas están en vegetativo?"):
            st.markdown("El límite de 9 se refiere a plantas **en floración**. Podés tener plantines, esquejes y plantas en vegetativo adicionales, siempre y cuando no superes las 9 en floración simultáneamente.")

    cannabis_divider()
    st.warning("Mantené siempre una copia digital del certificado REPROCANN y el DNI en tu teléfono. En caso de control, son los dos documentos que necesitás mostrar.")

# --- MÓDULO 6: SEGUIMIENTO DE CULTIVO ---
elif menu == "Seguimiento de Cultivo":
    cannabis_banner("seguimiento")
    mostrar_tutorial("Seguimiento de Cultivo")
    icon_title("seguimiento", "Seguimiento de Cultivo")
    st.markdown("Registrá tus cultivos activos y recibí consejos paso a paso según la etapa, el sistema y las condiciones climáticas en tiempo real para lograr el mejor rendimiento.")

    seg_curr, seg_daily = fetch_weather()

    def consejo_diario_rinde(nombre_etapa, sist, maceta_litros, curr_w, daily_w):
        tips = []
        if not curr_w:
            tips.append("⚠️ No se pudieron obtener datos climáticos. Seguir los consejos generales de la etapa.")
            return tips

        t = curr_w.get('temperature_2m', 20)
        h = curr_w.get('relative_humidity_2m', 50)
        v = curr_w.get('wind_speed_10m', 0)
        vpd = calcular_vpd(t, h)
        lluvia_prob = 0
        temp_max = t
        temp_min = t
        if daily_w:
            lluvia_prob = daily_w.get('precipitation_probability_max', [0])[0]
            temp_max = daily_w.get('temperature_2m_max', [t])[0]
            temp_min = daily_w.get('temperature_2m_min', [t])[0]

        es_exterior = sist in ["Exterior Maceta", "Exterior Tierra Madre", "Exterior Automáticas", "Invernadero Maceta", "Invernadero Tierra"]
        es_interior = sist == "Interior Luz" or sist == "Interior Automáticas"
        es_maceta = "Maceta" in sist
        es_auto = "Automáticas" in sist
        es_invern = "Invernadero" in sist
        maceta_chica = maceta_litros and maceta_litros <= 10
        maceta_med = maceta_litros and maceta_litros > 10 and maceta_litros <= 20

        tips.append(f"📊 **Clima ahora:** {t}°C | Humedad {h}% | Viento {v} km/h | VPD {vpd} kPa | Lluvia hoy: {lluvia_prob}%")

        amplitud = temp_max - temp_min

        if nombre_etapa == "Germinación":
            tips.append("🎯 **Objetivo de rinde:** Lograr una germinación rápida y saludable. El éxito acá define todo el ciclo.")
            if t < 18:
                tips.append(f"🧊 **{t}°C es bajo para germinar.** La semilla tarda más o no germina. Poné la servilleta/vasito en un lugar más cálido (arriba de la heladera, cerca de un calefactor). Ideal: 22-28°C.")
            elif t > 32:
                tips.append(f"🔥 **{t}°C es alto.** La semilla puede deshidratarse. Rociar la servilleta cada 6-8 hs. Mantener en lugar fresco y oscuro.")
            else:
                tips.append(f"✅ **{t}°C — temperatura ideal para germinar.** Revisar la semilla cada 12 hs. La raíz sale entre 24-72 hs.")
            if h < 40:
                tips.append(f"🏜️ Humedad {h}% baja. Cubrir la servilleta/vasito con film para mantener humedad. Rociar si se seca.")
            elif h > 85:
                tips.append(f"💧 Humedad {h}% muy alta. Cuidar que no se acumule agua. Ventilar levemente para evitar hongos en la semilla.")

        elif nombre_etapa == "Plántula":
            tips.append("🎯 **Objetivo de rinde:** Tallo fuerte y raíces sanas. No espigarse. La base de una buena planta se forma acá.")
            if es_exterior:
                if t > 33:
                    tips.append(f"🔥 **{t}°C — la plántula puede quemarse.** Media sombra obligatoria (12-16 hs). Regar suave con rociador.")
                elif t < 8:
                    tips.append(f"❄️ **{t}°C — la plántula sufre mucho el frío.** Cubrir con botella cortada o entrar adentro. No regar.")
                elif t < 15:
                    tips.append(f"🧊 **{t}°C — crecimiento lento.** Aprovechar las horas de sol directo. Regar poco y con agua tibia.")
                else:
                    tips.append(f"✅ **{t}°C — buena temperatura.** Sol directo por la mañana, sombra parcial al mediodía si supera 30°C.")
                if v > 20:
                    tips.append(f"💨 Viento {v} km/h puede quebrar la plántula. Proteger con cortaviento o moverla a un lugar reparado.")
                if lluvia_prob > 60:
                    tips.append("🌧️ Lluvia probable. Cubrir la plántula o entrar la maceta. El impacto de gotas puede dañar hojas tiernas.")
                if es_invern:
                    tips.append("🏡 Invernadero: buen refugio para plántulas. Ventilar en horas de calor para evitar damping off.")
            elif es_interior:
                if t > 30:
                    tips.append(f"🔥 **{t}°C exterior — el indoor puede recalentarse.** Ventilar bien. Separar la lámpara de la plántula (40-60 cm LED).")
                elif t < 10:
                    tips.append(f"🧊 **{t}°C exterior — frío.** Asegurar que el indoor no baje de 18°C con luces apagadas.")
                else:
                    tips.append(f"✅ **{t}°C exterior — fácil de mantener 22-25°C indoor.** Fotoperiodo 18/6.")
                if vpd < 0.3:
                    tips.append(f"💧 VPD {vpd} kPa muy bajo. Riesgo de damping off. Aumentar ventilación, reducir riego.")
                elif vpd > 1.2:
                    tips.append(f"🏜️ VPD {vpd} kPa alto para plántula. Rociar las hojas suavemente o usar humidificador.")
            if es_maceta and maceta_chica:
                tips.append(f"🪴 Maceta {maceta_litros}L: suficiente para plántula. Preparar la maceta de vegetativo (7-15L) para trasplantar cuando tenga 3-4 nudos.")

        elif "Vegetativo" in nombre_etapa:
            tips.append("🎯 **Objetivo de rinde:** Maximizar ramas y sitios de floración. Entrenamiento (LST/topping), nutrición rica en nitrógeno, raíces sanas = más cogollos después.")
            if es_exterior:
                if t > 35:
                    tips.append(f"🔥 **{t}°C — calor extremo.** El crecimiento se frena arriba de 35°C. Media sombra después de las 12 hs. Regar profundo temprano y al atardecer. Mulch obligatorio.")
                    if es_maceta and maceta_chica:
                        tips.append(f"⚠️ Maceta {maceta_litros}L se recalienta rápido. Envolver con tela húmeda o poner dentro de maceta más grande como aislante.")
                elif t > 30:
                    tips.append(f"🌡️ **{t}°C — caliente pero tolerable.** Regar bien temprano. Buen día para aplicar purín de ortiga diluido (nutrición + fortalecimiento).")
                elif t < 5:
                    tips.append(f"❄️ **{t}°C — riesgo de helada.** Cubrir o entrar plantas. El frío extremo detiene el crecimiento y puede matar tejidos jóvenes.")
                elif t < 15:
                    tips.append(f"🧊 **{t}°C — crecimiento lento.** Aprovechar horas de sol. No fertilizar hoy (la planta absorbe menos con frío).")
                else:
                    tips.append(f"✅ **{t}°C — temperatura ideal para vegetativo.** Buen día para entrenar (LST/topping), fertilizar, o trasplantar.")
                if h > 75:
                    tips.append(f"💧 Humedad {h}% alta. Separar las macetas/plantas para ventilación. Revisar envés de hojas por pulgones. Preventivo: neem.")
                elif h < 30:
                    tips.append(f"🏜️ Humedad {h}% muy baja. La planta transpira más. Aumentar frecuencia de riego. Mulch para retener humedad en sustrato.")
                if v > 30:
                    tips.append(f"💨 Viento {v} km/h fuerte. Revisar tutores. Si hiciste LST, verificar que los amarres estén firmes. El viento fuerte deshidrata.")
                elif v > 15 and v <= 30:
                    tips.append(f"💨 Viento {v} km/h moderado. Esto fortalece los tallos. Buen día para dejar la planta expuesta sin protección.")
                if lluvia_prob > 60:
                    tips.append("🌧️ Lluvia probable. No regar hoy. Si acabas de fertilizar, la lluvia puede lavar los nutrientes. Buen día para enmiendas de suelo que necesitan humedad.")
                if amplitud > 15:
                    tips.append(f"🌡️ Amplitud térmica alta ({temp_min:.0f}°C a {temp_max:.0f}°C). Esto puede estresar plantas jóvenes. Proteger de noche si baja de 10°C.")
                if es_invern:
                    tips.append(f"🏡 **Invernadero:** {'Abrir ventanas, el calor se acumula rápido.' if t > 28 else 'Cerrar por la noche para conservar calor.' if t < 15 else 'Buenas condiciones. Ventilar moderadamente.'}")
            elif es_interior:
                if t > 30:
                    tips.append(f"🔥 **{t}°C exterior.** Indoor se calienta. Prender luces de noche (20-06 hs) para aprovechar frescura nocturna. Reforzar extracción.")
                elif t < 10:
                    tips.append(f"🧊 **{t}°C exterior.** El indoor pierde calor en período oscuro. Calefactor con termostato a 18°C mínimo.")
                else:
                    tips.append(f"✅ **{t}°C exterior.** Fácil mantener 22-28°C indoor. Fotoperiodo 18/6. Buen día para topping si tiene 4-5 nudos.")
                if vpd < 0.4:
                    tips.append(f"💧 VPD {vpd} kPa bajo. Mucha humedad ambiental. Aumentar extracción. Riesgo de hongos si no se ventila.")
                elif vpd > 1.4:
                    tips.append(f"🏜️ VPD {vpd} kPa alto. La planta transpira demasiado. Humidificador o bajar temperatura. En vegetativo ideal: 0.6-1.0 kPa.")
                else:
                    tips.append(f"✅ VPD {vpd} kPa — rango óptimo para crecimiento vegetativo. La planta transpira bien.")
            if es_auto:
                tips.append("⚡ **Auto en veg:** El vegetativo de las autos es corto (3-4 semanas). No estresar con podas agresivas. Solo LST suave. Maximizar horas de luz.")
            if es_maceta:
                if maceta_chica:
                    tips.append(f"🪴 Maceta {maceta_litros}L: las raíces se están llenando. Trasplantar pronto a 15-20L para no limitar el rinde final.")
                elif maceta_med:
                    tips.append(f"🪴 Maceta {maceta_litros}L: buen tamaño. Si querés más rinde, trasplantar a 25L+ antes de floración.")

        elif nombre_etapa == "Pre-Floración":
            tips.append("🎯 **Objetivo de rinde:** Transición suave a floración. No estresar la planta. Cada pistilo que aparece es un futuro cogollo.")
            if es_exterior:
                if t > 33:
                    tips.append(f"🔥 **{t}°C — calor en pre-flora.** Puede retrasar la floración. Regar bien y dar sombra al mediodía.")
                elif t < 8:
                    tips.append(f"❄️ **{t}°C — frío puede causar hermafroditismo por estrés.** Proteger de noche. Cubrir con tela.")
                else:
                    tips.append(f"✅ **{t}°C — buena transición.** La planta está definiendo su sexo. Revisar diariamente por pistilos o sacos.")
                if h > 70:
                    tips.append(f"💧 Humedad {h}% — empezar a controlar. En floración no debe superar 55%. Ir preparando ventilación.")
                if lluvia_prob > 50:
                    tips.append("🌧️ Lluvia probable. No mojar la parte superior de la planta. Los pistilos son sensibles al agua directa.")
            elif es_interior:
                tips.append("💡 Si aún no cambiaste, es momento del fotoperiodo 12/12. Oscuridad total en las 12 hs de noche.")
                if vpd > 1.2:
                    tips.append(f"🏜️ VPD {vpd} kPa — empezar a bajar para flora. Ideal en floración: 0.8-1.2 kPa.")
            if es_auto:
                tips.append("⚡ La auto entra sola en pre-flora. No cambiar nada. Empezar nutrientes de floración suavemente (P+K). Mantener fotoperiodo 18/6 o 20/4.")

        elif "Floración" in nombre_etapa or "Maduración" in nombre_etapa:
            if "Temprana" in nombre_etapa or nombre_etapa == "Floración":
                tips.append("🎯 **Objetivo de rinde:** Los cogollos se están formando. Cada cuidado ahora se traduce directamente en gramos de cosecha. Máxima atención a nutrición P+K, humedad y plagas.")
            elif "Media" in nombre_etapa:
                tips.append("🎯 **Objetivo de rinde:** Engorde máximo de cogollos. Esta es la etapa que más define el peso final. Potasio + melaza. Proteger de humedad alta y plagas.")
            elif "Tardía" in nombre_etapa or "Maduración" in nombre_etapa:
                tips.append("🎯 **Objetivo de rinde:** Maduración de tricomas y resina. No fertilizar, solo agua. Cada día extra puede mejorar potencia pero ojo con el moho.")

            if es_exterior:
                if t > 33:
                    tips.append(f"🔥 **{t}°C — calor extremo en floración.** Los cogollos sufren. La resina se degrada con calor. Sombra parcial después del mediodía. Regar al amanecer y atardecer.")
                    if es_maceta and maceta_chica:
                        tips.append(f"⚠️ Maceta {maceta_litros}L: las raíces están al límite con este calor. Regar 2-3 veces al día en pequeñas cantidades. Envolver maceta con tela.")
                elif t < 5:
                    tips.append(f"❄️ **{t}°C — HELADA en floración.** Los cogollos mojados + frío = botrytis segura. Cubrir urgente o cosechar si los tricomas están listos.")
                elif t < 12:
                    tips.append(f"🧊 **{t}°C — fresco.** Las noches frías potencian colores y resina. Pero vigilar rocío matinal sobre cogollos. Sacudir suavemente si se mojan.")
                elif t >= 18 and t <= 26:
                    tips.append(f"✅ **{t}°C — rango perfecto para floración.** Los cogollos engordan mejor entre 18-26°C. Mantener rutina estable.")
                else:
                    tips.append(f"✅ **{t}°C — temperatura aceptable.** Mantener riego y vigilar cogollos.")
                if h > 65:
                    tips.append(f"💧 **ALERTA: Humedad {h}% — peligrosa en floración.** Riesgo de moho/botrytis en cogollos densos. Defoliar hojas que toquen cogollos. No regar de noche.")
                elif h > 55:
                    tips.append(f"💧 Humedad {h}% — en el límite. Mejorar ventilación entre plantas. Ideal para flora: 40-50%.")
                elif h < 30:
                    tips.append(f"🏜️ Humedad {h}% baja. Los cogollos pueden perder terpenos. Regar para mantener algo de humedad ambiental.")
                if v > 30:
                    tips.append(f"💨 **Viento {v} km/h fuerte.** Los cogollos pesan y las ramas pueden quebrarse. Revisar tutores y malla SCROG urgente.")
                if lluvia_prob > 40:
                    tips.append(f"🌧️ **Lluvia probable ({lluvia_prob}%) + floración = riesgo de moho.** Cubrir las plantas si es posible. Después de la lluvia, sacudir suavemente cada cogollo para sacar agua.")
                if amplitud > 12:
                    tips.append(f"🌡️ Amplitud {temp_min:.0f}°C→{temp_max:.0f}°C. La diferencia día/noche ayuda a producir más resina y colores, pero vigilar condensación sobre cogollos.")
                if es_invern:
                    if h > 60:
                        tips.append("🏡 **Invernadero en flora:** humedad acumulada peligrosa. Abrir ventanas y puertas durante el día. Deshumidificador si es posible.")
                    else:
                        tips.append("🏡 **Invernadero:** Protegido de lluvia directa. Mantener ventilación activa para que la humedad no suba de noche.")
            elif es_interior:
                tips.append("💡 Fotoperiodo 12/12 estricto. Ni un segundo de luz durante la oscuridad (causa hermafroditismo).")
                if t > 30:
                    tips.append(f"🔥 **{t}°C exterior — indoor se recalienta.** Luces de noche obligatorio. Extractor al máximo. Temp. ideal en flora: 20-26°C.")
                elif t < 10:
                    tips.append(f"🧊 **{t}°C exterior — frío.** Calefactor en período oscuro. La diferencia día/noche de 8-10°C es positiva para resina.")
                else:
                    tips.append(f"✅ **{t}°C exterior.** Buenas condiciones para mantener flora estable indoor.")
                if vpd < 0.4:
                    tips.append(f"💧 **VPD {vpd} kPa — PELIGRO en floración.** Deshumidificador urgente. El moho puede destruir la cosecha.")
                elif vpd > 1.6:
                    tips.append(f"🏜️ VPD {vpd} kPa alto para flora. Los cogollos se estresan. Bajar temperatura o subir humedad levemente.")
                elif vpd >= 0.8 and vpd <= 1.2:
                    tips.append(f"✅ VPD {vpd} kPa — rango perfecto para floración. Máxima producción de resina.")
                else:
                    tips.append(f"✅ VPD {vpd} kPa — aceptable para floración.")
            if es_auto:
                tips.append("⚡ **Auto en flora:** Mantener luz 18/6 o 20/4. No cambiar nada drásticamente. Las autos maduran rápido: revisar tricomas ya.")
            if "Flush" in nombre_etapa or "Tardía" in nombre_etapa or "Maduración" in nombre_etapa:
                tips.append("🚿 **Flush/Maduración:** Solo agua sin nutrientes. Las hojas deben amarillear naturalmente. Mejora sabor y suavidad del humo.")
                if lluvia_prob > 60 and es_exterior:
                    tips.append("🌧️ La lluvia puede servir como flush natural. Pero proteger cogollos maduros del exceso de agua.")

        elif nombre_etapa == "Flush y Cosecha":
            tips.append("🎯 **Objetivo:** Cosecha exitosa. El momento perfecto define la potencia y el sabor final.")
            if es_exterior:
                if lluvia_prob > 40:
                    tips.append(f"🌧️ Lluvia probable ({lluvia_prob}%). Si los tricomas están listos, **cosechar hoy antes de la lluvia** para evitar moho post-cosecha.")
                if h > 65:
                    tips.append(f"💧 Humedad {h}% alta. Si ya cortaste, cuidar el secado: ventilación constante, oscuridad, 18-22°C. No secar al sol.")
                if t > 30:
                    tips.append(f"🔥 {t}°C — cosechar temprano por la mañana cuando hay más terpenos. El calor degrada los aromas.")
                elif t < 5:
                    tips.append(f"❄️ {t}°C — cosechar antes de que congele. Los cogollos se cristalizan y pierden calidad.")
                else:
                    tips.append(f"✅ {t}°C — buena temperatura para cosechar y secar. Lugar de secado: oscuro, 18-22°C, humedad 50-60%.")
            elif es_interior:
                tips.append("💡 Algunos hacen 48 hs de oscuridad antes del corte (opcional). Cosechar cuando tricomas estén 70% lechosos + 30% ámbar.")
            tips.append("✂️ **Tip de rinde:** Secar lento (7-14 días) y curar mínimo 2 semanas en frascos mejora peso, sabor y potencia notablemente.")

        return tips

    def consejos_etapa(nombre_etapa, sist, maceta_litros=None):
        consejos = {}
        riego = ""
        sustrato = ""
        nutricion = ""
        ambiente = ""
        cuidados = ""
        plagas = ""
        maceta_consejo = ""

        if nombre_etapa == "Germinación":
            consejos["resumen"] = "La semilla necesita humedad constante, oscuridad y calor para germinar."
            riego = "Mantener el medio húmedo pero no encharcado. Usar rociador. No regar con chorro directo."
            sustrato = "Sustrato liviano y aireado. Ideal: 50% turba + 30% perlita + 20% humus de lombriz."
            nutricion = "No agregar nutrientes. La semilla tiene reservas propias para los primeros días."
            ambiente = "Temperatura ideal: 22-28°C. Humedad: 70-90%. Oscuridad hasta que asome la radícula."
            cuidados = "Método servilleta: semilla entre servilletas húmedas en plato tapado, lugar cálido y oscuro. Revisar cada 12 hs. Cuando sale la raíz blanca (1-2 cm), plantar con la raíz hacia abajo a 1 cm de profundidad."
            plagas = "No hay riesgo de plagas en esta etapa. Cuidar que no haya hongos en la servilleta."
            if sist in ["Exterior Maceta", "Invernadero Maceta"]:
                maceta_consejo = "Germinar en vasito de 200 ml o maceta de 1 litro. No usar la maceta definitiva todavía."
            elif sist in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                maceta_consejo = "Podés germinar directo en tierra preparada o en vasito para trasplantar después. Si es directo, proteger con botella cortada como mini-invernadero."
            elif sist == "Interior Luz":
                maceta_consejo = "Germinar en vasito o jiffy. Luz suave 18/6 una vez que asome el tallo. No acercar demasiado la luz."
            elif "Automáticas" in sist:
                maceta_consejo = "IMPORTANTE: Germinar directamente en la maceta definitiva. Las autos no toleran bien el trasplante. Plantar en el centro de la maceta final."

        elif nombre_etapa == "Plántula":
            consejos["resumen"] = "La planta es muy frágil. Necesita luz suave, humedad alta y poco riego."
            riego = "Regar en círculo alrededor del tallo, no sobre él. Poco volumen, frecuente. Dejar secar la superficie entre riegos."
            sustrato = "El mismo de germinación. No trasplantar todavía si está en vasito pequeño (esperar a que tenga 3-4 nudos)."
            nutricion = "Aún no necesita fertilizantes. Si el sustrato tiene humus, alcanza. Máximo: té de humus muy diluido (1/4 de dosis)."
            ambiente = "Temperatura: 20-26°C. Humedad: 60-70%. Brisa suave para fortalecer el tallo."
            cuidados = "Si el tallo se estira mucho (espigamiento), la luz está muy lejos o es muy débil. Acercar la luz o mover a lugar más luminoso. Sostener tallos débiles con palito."
            plagas = "Cuidado con damping off (cuello del tallo se pudre). Prevenir con canela en polvo sobre el sustrato. No sobre-regar."
            if sist in ["Exterior Maceta", "Invernadero Maceta"]:
                if maceta_litros and maceta_litros <= 5:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Suficiente para plántula. Primer trasplante cuando tenga 3-4 pares de hojas a maceta de 5-7L."
                elif maceta_litros and maceta_litros <= 15:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Si plantaste directo acá, está bien pero cuidá de no sobre-regar. La plántula usa poca agua en maceta grande."
                else:
                    maceta_consejo = "Mantener en vasito o maceta chica (1-3L). Trasplantar a la siguiente medida cuando las hojas superen el borde de la maceta."
            elif sist in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                maceta_consejo = "Si está en tierra directa, proteger del sol fuerte del mediodía con media sombra. Si está en vasito, esperar 3-4 nudos para trasplantar al cantero."
            elif sist == "Interior Luz":
                maceta_consejo = "Luz 18/6. Distancia: LED 40-60 cm, bajo consumo 15-20 cm. No usar HPS/sodio todavía, es demasiado fuerte."
            elif "Automáticas" in sist:
                maceta_consejo = "Ya debe estar en maceta definitiva. Regar muy poco, solo alrededor de la plántula (no toda la maceta). Circulo de 5 cm de radio."

        elif nombre_etapa in ["Vegetativo Temprano", "Vegetativo"]:
            consejos["resumen"] = "La planta crece rápido. Necesita más agua, luz y nutrientes. Es momento de entrenar y dar forma."
            riego = "Aumentar volumen gradualmente. Regar cuando los primeros 2-3 cm de sustrato estén secos. Agua reposada 24 hs para evaporar cloro."
            sustrato = "Primer trasplante si está en vasito. Sustrato enriquecido: turba + perlita + humus + guano suave."
            nutricion = "Empezar con nitrógeno (N). Opciones naturales: purín de ortiga, té de humus, guano de murciélago. Empezar con dosis bajas."
            ambiente = "Temperatura: 22-28°C. Humedad: 50-65%. Buena ventilación para fortalecer tallos."
            cuidados = "Técnicas de entrenamiento: LST (atar ramas para abrir la planta), topping (cortar la punta para ramificar) a partir del 4to-5to nudo. Tutores si crece rápido."
            plagas = "En La Carlota, ojo con pulgones y arañuela en verano (Dic-Feb). Revisar envés de hojas. Preventivo: aceite de neem cada 10-15 días."
            if sist in ["Exterior Maceta", "Invernadero Maceta"]:
                if maceta_litros and maceta_litros <= 5:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Es chica para vegetativo. Trasplantar pronto a 10-15L para que desarrolle bien las raíces."
                elif maceta_litros and maceta_litros <= 15:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Buen tamaño para vegetativo. Si querés una planta grande, trasplantar a 20-25L antes de floración."
                elif maceta_litros and maceta_litros <= 25:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Excelente tamaño. Puede completar todo el ciclo acá. Regar hasta que drene un 15-20% por abajo."
                else:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Gran tamaño, la planta tendrá mucho espacio. Cuidar de no sobre-regar, dejar secar entre riegos."
            elif sist in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                maceta_consejo = "Raíces libres = crecimiento explosivo. Mulch de paja para mantener humedad y frescura. Aportar compost alrededor de la base. Tutores desde temprano si crece mucho."
            elif sist == "Interior Luz":
                maceta_consejo = "Fotoperiodo 18/6. Trasplantar a maceta de 10-15L. Rotar la maceta cada 2 días para crecimiento parejo. Ventilador apuntando al tallo."
            elif "Automáticas" in sist:
                maceta_consejo = "No hacer topping en autos. Solo LST suave (atar la punta principal). El vegetativo es corto (3-4 semanas), aprovecharlo sin estresar."

        elif nombre_etapa == "Vegetativo Avanzado":
            consejos["resumen"] = "Crecimiento intenso. La planta define su estructura. Último momento para entrenar antes de floración."
            riego = "Riego abundante. En verano en La Carlota puede necesitar riego diario. Siempre revisar el peso de la maceta."
            sustrato = "Si no trasplantaste a la maceta final, este es el último momento. No trasplantar una vez que empiece la floración."
            nutricion = "Máxima demanda de N. Top dress con guano o humus. Té de ortiga semanal. Si las hojas son verde oscuro intenso, bajar dosis."
            ambiente = "Temperatura: 22-30°C. Humedad: 45-60%. En La Carlota el verano supera los 35°C: media sombra de 12 a 16 hs."
            cuidados = "Último topping o poda apical. Defoliar hojas que tapen sitios de luz. Asegurar tutores. Limpiar ramas bajas que no reciban luz (lollipopping)."
            plagas = "Pulgones, trips, arañuela roja. Revisar diariamente. Neem preventivo. Jabón potásico si hay plaga activa."
            if sist in ["Exterior Maceta", "Invernadero Maceta"]:
                if maceta_litros and maceta_litros <= 10:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Última chance de trasplantar a algo más grande. En maceta chica la planta será más chica pero puede completar el ciclo."
                elif maceta_litros and maceta_litros <= 20:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Buen tamaño para la definición del ciclo. Empezar a preparar los nutrientes de floración."
                else:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Excelente, la planta va a desarrollar mucha masa. Asegurar tutores firmes."
            elif sist in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                maceta_consejo = "La planta puede alcanzar 1.5-2.5 m. Tutores robustos. Riego profundo. Si el suelo es alcalino (pH 7.5, típico de La Carlota), aportar azufre o turba ácida para bajar pH."
            elif sist == "Interior Luz":
                maceta_consejo = "Evaluar el espacio: cuando la planta ocupe el 50-60% del espacio vertical disponible, cambiar a 12/12. La planta duplicará su altura en floración."
            elif "Automáticas" in sist:
                maceta_consejo = "Las autos entran en pre-flora solas entre semana 3-5. No hacer podas agresivas. LST suave si está disponible."

        elif nombre_etapa == "Pre-Floración":
            consejos["resumen"] = "La planta muestra su sexo. Aparecen pistilos (pelos blancos = hembra) o sacos (macho). Transición crítica."
            riego = "Mantener riego constante. No estresar con sequía ni encharcamiento."
            sustrato = "No trasplantar. El sustrato debe estar bien aireado y con buen drenaje."
            nutricion = "Transición de N a P y K. Reducir nitrógeno gradualmente, empezar con fósforo (harina de hueso, guano de murciélago fructífero). Melaza 1 cucharada/litro."
            ambiente = "Temperatura: 20-28°C. Humedad: 40-55%. En exterior, las noches más largas de marzo-abril disparan la floración."
            cuidados = "Identificar sexo: pistilos blancos = hembra (deseado), bolitas/sacos = macho (eliminar inmediatamente). Si es regular (no feminizada), revisar a diario."
            plagas = "En La Carlota, marzo-mayo: riesgo de oídio (manchas blancas). Preventivo: bicarbonato 3g/L + jabón potásico pulverizado semanal."
            if sist in ["Exterior Maceta", "Invernadero Maceta"]:
                if maceta_litros and maceta_litros <= 10:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Ya no trasplantar. La planta florecerá según el tamaño de raíces que tenga. Optimizar nutrición."
                else:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Buen volumen de raíces. La floración será proporcional. Preparar malla de soporte para cogollos."
            elif sist in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                maceta_consejo = "En La Carlota, la pre-floración exterior ocurre naturalmente en Feb-Mar cuando los días se acortan. La planta puede ser grande: preparar soportes."
            elif sist == "Interior Luz":
                maceta_consejo = "Cambiar fotoperiodo a 12/12. Oscuridad total durante las 12 hs de noche (ni un rayo de luz, puede causar hermafroditismo). Revisar sellos de luz."
            elif "Automáticas" in sist:
                maceta_consejo = "La auto entra sola en pre-flora. No cambiar nada. Mantener luz 18/6 o 20/4. Empezar nutrientes de floración suavemente."

        elif nombre_etapa in ["Floración Temprana", "Floración"]:
            consejos["resumen"] = "Los cogollos empiezan a formarse. Etapa crítica: máxima demanda de P y K. Cuidar la humedad."
            riego = "Riego regular y constante. No mojar los cogollos. Regar por la base. Si es verano en La Carlota, regar temprano y al atardecer."
            sustrato = "No tocar el sustrato. Mantener buena aireación. Si hay costras en la superficie, romper suavemente con tenedor."
            nutricion = "Fósforo y potasio altos, nitrógeno bajo. Harina de hueso, ceniza de madera (potasio), melaza. Guano de murciélago fructífero. Aplicar cada riego alterno."
            ambiente = "Temperatura: 18-26°C. Humedad: 40-50% máximo. En La Carlota, el otoño es ideal. Si es verano, cuidar calor excesivo."
            cuidados = "No podar ni estresar. Sostener ramas con cogollos pesados con tutores/malla. Defoliar solo hojas que tapen cogollos directamente. No tocar los cogollos con las manos."
            plagas = "Orugas en los cogollos (Dic-Feb): revisar a diario, sacar a mano. Bacillus thuringiensis (BT) preventivo. Oídio: bicarbonato + jabón potásico."
            if sist in ["Exterior Maceta", "Invernadero Maceta"]:
                if maceta_litros and maceta_litros <= 10:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Los cogollos serán más chicos en maceta limitada. Compensar con buena nutrición. Regar más seguido (raíces copadas)."
                elif maceta_litros and maceta_litros <= 20:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Buenos cogollos posibles. Malla SCROG o tutores para sostener. Regar cuando la maceta se sienta liviana."
                else:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Excelente volumen. Cogollos generosos. Tutores y malla obligatorios para sostener el peso."
            elif sist in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                maceta_consejo = "Cogollos grandes en tierra madre. Tutores resistentes obligatorios. Malla SCROG horizontal si es posible. Proteger de lluvias fuertes con techo/plástico."
            elif sist == "Interior Luz":
                maceta_consejo = "Fotoperiodo 12/12 estricto. Mantener temperatura estable. Buena extracción de aire para bajar humedad. SCROG ideal para maximizar producción."
            elif "Automáticas" in sist:
                maceta_consejo = "Mantener luz 18/6 o 20/4 durante toda la flora. Las autos no dependen del fotoperiodo. Nutrición de floración completa."

        elif nombre_etapa == "Floración Media":
            consejos["resumen"] = "Los cogollos engordan rápido. Aparecen tricomas (cristales). Máxima producción de resina. Etapa de mayor cuidado."
            riego = "Riego constante, sin excesos. Si los cogollos se mojan, riesgo de moho. Regar solo la base. En La Carlota, cuidar lluvias de otoño."
            sustrato = "No modificar. Si hay acumulación de sales (costras blancas), hacer un flush suave con el triple de agua del volumen de la maceta."
            nutricion = "Continuar P+K. Agregar potasio extra (ceniza de madera diluida). Melaza en cada riego para alimentar microvida y engordar cogollos."
            ambiente = "Temperatura: 18-26°C nocturna / 22-28°C diurna. Humedad: 35-45%. Diferencia de temperatura día/noche de 8-10°C mejora colores y resina."
            cuidados = "Revisar tricomas con lupa (60x): transparentes = falta, lechosos = punto óptimo, ámbar = más efecto narcótico. No tocar los cogollos."
            plagas = "Máximo riesgo de botrytis (moho gris) en cogollos densos. Si llueve, sacudir suavemente y secar. Revisar el interior de cogollos grandes."
            if sist in ["Exterior Maceta", "Invernadero Maceta"]:
                if maceta_litros and maceta_litros <= 10:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Las raíces están al máximo. Regar con frecuencia, posiblemente todos los días. Flush corto si hay puntas quemadas."
                elif maceta_litros and maceta_litros <= 20:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Buena reserva de sustrato. Regar día por medio. Controlar el peso de la maceta."
                else:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Sustrato amplio. Regar cuando seque los primeros 3-4 cm. Los cogollos deben estar engordando bien."
            elif sist in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                maceta_consejo = "Proteger de lluvias con plástico/techo si es posible. Inspeccionar cogollos grandes por dentro (abrir suavemente) buscando moho. Sostener ramas pesadas."
            elif sist == "Interior Luz":
                maceta_consejo = "Bajar humedad al mínimo posible. Buena circulación de aire entre cogollos. Deshumidificador si supera 50%. Mantener 12/12 sin interrupciones."
            elif "Automáticas" in sist:
                maceta_consejo = "Mantener condiciones estables. Las autos suelen tener cogollos más compactos. Revisar tricomas: las autos maduran más rápido."

        elif nombre_etapa == "Floración Tardía / Maduración":
            consejos["resumen"] = "Los cogollos maduran. Hojas amarillean naturalmente (la planta consume reservas). Revisar tricomas para determinar punto de cosecha."
            riego = "Reducir riego gradualmente. Si vas a hacer flush, empezar ahora: regar solo con agua limpia (sin nutrientes) las últimas 1-2 semanas."
            sustrato = "Flush: regar con 3x el volumen de la maceta en agua limpia para limpiar sales. Mejora el sabor final."
            nutricion = "Dejar de fertilizar. Solo agua limpia. La planta vive de sus reservas. Las hojas se ponen amarillas: es normal y deseable."
            ambiente = "Temperatura: 18-24°C. Humedad: 30-40%. Noches frescas ayudan a producir colores púrpuras. Cuidar mucho el moho."
            cuidados = "Revisar tricomas diariamente con lupa: 70% lechosos + 30% ámbar = cosecha ideal para mayoría. Solo lechosos = efecto más activo. Más ámbar = más relajante."
            plagas = "Último control de orugas y botrytis. Si encontrás moho en un cogollo, cortarlo inmediatamente. No fumar cogollos con moho."
            if sist in ["Exterior Maceta", "Invernadero Maceta"]:
                if maceta_litros and maceta_litros <= 10:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Flush rápido (3 días de solo agua). En maceta chica se lava más rápido. Preparar espacio de secado."
                elif maceta_litros and maceta_litros <= 20:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Flush de 7-10 días con agua limpia. Observar que las hojas amarillean uniformemente."
                else:
                    maceta_consejo = f"Maceta de {maceta_litros}L: Flush de 10-14 días. Mayor volumen de sustrato requiere más tiempo de lavado."
            elif sist in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                maceta_consejo = "En tierra madre el flush es menos efectivo pero igual dejar de fertilizar 2-3 semanas antes. Regar solo con agua. Preparar tijeras de podar afiladas."
            elif sist == "Interior Luz":
                maceta_consejo = "Flush de 7-14 días con agua limpia. Algunos bajan la temperatura nocturna a 15-18°C los últimos días para estimular resina. 48 hs de oscuridad antes del corte es opcional."
            elif "Automáticas" in sist:
                maceta_consejo = "Flush de 5-7 días. Las autos maduran rápido, no esperar demasiado. Cuando los tricomas estén 50-70% lechosos, ya está cerca."

        elif nombre_etapa == "Flush y Cosecha":
            consejos["resumen"] = "Momento de cosechar. Cortar, hacer manicura (quitar hojas), secar y curar."
            riego = "Dejar de regar 1-2 días antes de cortar para que el sustrato esté seco. Facilita el corte y secado."
            sustrato = "Ya no importa. Después de la cosecha, el sustrato se puede reutilizar compostándolo."
            nutricion = "Ninguna. Solo agua si no terminaste el flush."
            ambiente = "Secado: 18-22°C, 50-60% humedad, oscuridad total, buena ventilación suave (no directo sobre las ramas). 7-14 días hasta que los tallos crujan."
            cuidados = """Proceso de cosecha:
1. Cortar la planta por la base o por ramas.
2. Manicura: quitar hojas grandes y recortar hojas de azúcar (guardarlas para extracciones).
3. Colgar boca abajo en lugar oscuro, ventilado, 18-22°C.
4. Secar 7-14 días (tallos deben crujir al doblar).
5. Curado: poner en frascos de vidrio, abrir 15 min/día las primeras 2 semanas. Mínimo 2 semanas, ideal 1-2 meses."""
            plagas = "Durante el secado: vigilar moho. Si aparece, descartar ese cogollo. Ventilación constante."
            if sist in ["Exterior Maceta", "Invernadero Maceta"]:
                maceta_consejo = "Mover la maceta adentro 2 días antes del corte si hay pronóstico de lluvia. Cosechar por la mañana cuando los terpenos están más concentrados."
            elif sist in ["Exterior Tierra Madre", "Invernadero Tierra"]:
                maceta_consejo = "Cortar planta completa o por ramas. Si es grande, ir rama por rama. Tener hilo o perchas listas para colgar. Lugar de secado preparado."
            elif sist == "Interior Luz":
                maceta_consejo = "Apagar las luces 48 hs antes del corte (opcional, algunos cultivadores creen que aumenta resina). Cosechar con luz verde o en penumbra."
            elif "Automáticas" in sist:
                maceta_consejo = "Cosecha alrededor de semana 10-12 desde germinación. Las autos suelen ser más compactas, el secado puede ser más rápido (5-10 días)."

        else:
            consejos["resumen"] = "Etapa no reconocida. Consultá el módulo de Asesoramiento para orientación general."
            riego = "Regar según necesidad del sustrato."
            sustrato = "Mantener buena aireación."
            nutricion = "Seguir plan de nutrición habitual."
            ambiente = "Mantener condiciones óptimas."
            cuidados = "Observar la planta a diario."
            plagas = "Inspección preventiva regular."
            maceta_consejo = ""

        consejos["riego"] = riego
        consejos["sustrato"] = sustrato
        consejos["nutricion"] = nutricion
        consejos["ambiente"] = ambiente
        consejos["cuidados"] = cuidados
        consejos["plagas"] = plagas
        consejos["maceta_consejo"] = maceta_consejo
        return consejos

    if "cultivos" not in st.session_state:
        _seg_email = st.session_state.get("suscriptor_email", "")
        st.session_state.cultivos = cargar_cultivos(_seg_email)

    icon_subtitle("seguimiento", "Agregar Nuevo Cultivo")
    col_add1, col_add2, col_add3, col_add4 = st.columns(4)
    with col_add1:
        nuevo_nombre = st.text_input("Nombre del cultivo", placeholder="Ej: Sativa balcón", key="nuevo_nombre")
    with col_add2:
        nuevo_inicio = st.date_input("Fecha de inicio", value=datetime.date.today(), key="nuevo_inicio")
    with col_add3:
        nuevo_cat = st.selectbox("Categoría", ["Interior", "Exterior", "Invernadero"], key="nuevo_cat")
    with col_add4:
        if nuevo_cat == "Interior":
            nuevo_sub = st.selectbox("Tipo", ["Luz", "Automáticas"], key="nuevo_sub")
        elif nuevo_cat == "Exterior":
            nuevo_sub = st.selectbox("Tipo", ["Maceta", "Tierra Madre", "Automáticas"], key="nuevo_sub")
        else:
            nuevo_sub = st.selectbox("Tipo", ["Maceta", "Tierra"], key="nuevo_sub")
        nuevo_sistema = f"{nuevo_cat} {nuevo_sub}"

    maceta_litros_nuevo = None
    if "Maceta" in nuevo_sistema:
        maceta_litros_nuevo = st.slider("Tamaño de maceta (litros)", min_value=1, max_value=50, value=15, key="maceta_litros_nuevo")

    if st.button("Agregar Cultivo"):
        if nuevo_nombre.strip():
            st.session_state.cultivos.append({
                "nombre": nuevo_nombre.strip(),
                "inicio": nuevo_inicio,
                "sistema": nuevo_sistema,
                "maceta_litros": maceta_litros_nuevo
            })
            guardar_cultivos(st.session_state.cultivos, st.session_state.get("suscriptor_email", ""))
            st.success(f"Cultivo '{nuevo_nombre}' agregado correctamente.")
            st.rerun()
        else:
            st.error("Ingresá un nombre para el cultivo.")

    cannabis_divider()

    if not st.session_state.cultivos:
        st.info("No tenés cultivos registrados. Agregá uno arriba para empezar el seguimiento.")
    else:
        icon_subtitle("seguimiento", f"Tus Cultivos Activos ({len(st.session_state.cultivos)})")

        indices_a_eliminar = []

        for i, cultivo in enumerate(st.session_state.cultivos):
            nombre_c = cultivo["nombre"]
            inicio_c = cultivo["inicio"]
            sistema_c = cultivo["sistema"]
            maceta_c = cultivo.get("maceta_litros")

            dias_transcurridos = (datetime.date.today() - inicio_c).days
            semanas_transcurridas = dias_transcurridos / 7

            etapas = obtener_etapas(sistema_c)
            etapa_actual = obtener_etapa_actual(dias_transcurridos, etapas)
            progreso = porcentaje_etapa(dias_transcurridos, etapa_actual)

            info_maceta = f" · Maceta: {maceta_c}L" if maceta_c else ""
            with st.expander(f"🌱 {etapa_actual['nombre']} · {sistema_c}{info_maceta}", expanded=(i == 0)):
                col_seg_izq, col_seg_der = st.columns([3, 1])
                with col_seg_der:
                    ic_sg = icon_html("seguimiento", 20)
                    st.markdown(f'<div class="cultivo-info-right"><div class="cultivo-nombre">{ic_sg} {nombre_c}</div><div class="cultivo-dia">Día {dias_transcurridos}</div></div>', unsafe_allow_html=True)
                col_info1, col_info2, col_info3 = st.columns(3)
                with col_info1:
                    st.metric("Días desde inicio", f"{dias_transcurridos} días")
                with col_info2:
                    st.metric("Semanas", f"{semanas_transcurridas:.1f}")
                with col_info3:
                    st.metric("Sistema", sistema_c)

                st.markdown(f"**Etapa actual:** {etapa_actual['nombre']} ({etapa_actual['semanas']})")
                st.progress(progreso, text=f"Progreso en etapa: {int(progreso*100)}%")

                idx_actual = etapas.index(etapa_actual)
                etapas_nombres = [e["nombre"] for e in etapas]
                barra_etapas = ""
                for j, en in enumerate(etapas_nombres):
                    if j < idx_actual:
                        barra_etapas += f"~~{en}~~ → "
                    elif j == idx_actual:
                        barra_etapas += f"**{en}** → "
                    else:
                        barra_etapas += f"{en} → "
                st.markdown("Recorrido: " + barra_etapas.rstrip(" → "))

                cannabis_divider_mini()
                consejos = consejos_etapa(etapa_actual["nombre"], sistema_c, maceta_c)

                st.markdown(f"### Guía para: {etapa_actual['nombre']}")
                st.info(consejos["resumen"])

                tab_r, tab_s, tab_n, tab_a, tab_cu, tab_p = st.tabs([
                    "Riego", "Sustrato", "Nutrición", "Ambiente", "Cuidados", "Plagas"
                ])
                with tab_r:
                    st.markdown(consejos["riego"])
                with tab_s:
                    st.markdown(consejos["sustrato"])
                with tab_n:
                    st.markdown(consejos["nutricion"])
                with tab_a:
                    st.markdown(consejos["ambiente"])
                with tab_cu:
                    st.markdown(consejos["cuidados"])
                with tab_p:
                    st.markdown(consejos["plagas"])

                if consejos["maceta_consejo"]:
                    cannabis_divider_mini()
                    st.markdown(f"**Consejo específico ({sistema_c}{info_maceta}):**")
                    st.success(consejos["maceta_consejo"])

                cannabis_divider()
                st.markdown(f"### 🌤️ Consejo Diario para Mejor Rinde — Hoy")
                tips_rinde = consejo_diario_rinde(etapa_actual["nombre"], sistema_c, maceta_c, seg_curr, seg_daily)
                for tip in tips_rinde:
                    st.markdown(f"- {tip}")

                if idx_actual < len(etapas) - 1:
                    prox = etapas[idx_actual + 1]
                    dias_para_prox = prox["inicio"] - dias_transcurridos
                    if dias_para_prox > 0:
                        st.markdown(f"**Próxima etapa:** {prox['nombre']} en ~{dias_para_prox} días.")
                    else:
                        st.markdown(f"**Próxima etapa:** {prox['nombre']} (inminente o ya comenzando).")

                if st.button(f"Eliminar cultivo '{nombre_c}'", key=f"del_{i}"):
                    indices_a_eliminar.append(i)

        if indices_a_eliminar:
            for idx in sorted(indices_a_eliminar, reverse=True):
                st.session_state.cultivos.pop(idx)
            guardar_cultivos(st.session_state.cultivos, st.session_state.get("suscriptor_email", ""))
            st.rerun()
