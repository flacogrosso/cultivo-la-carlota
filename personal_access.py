"""Acceso de propietario para la versión personal: cerrado por defecto."""
import hmac
import os
import time

MIN_PASSWORD_LENGTH = 16
SESSION_SECONDS = 12 * 60 * 60
DEFAULT_ACCOUNT = "personal@local.invalid"


def personal_account():
    """Cuenta interna que delimita los registros en la base existente."""
    email = os.environ.get("GLM_PERSONAL_ACCOUNT", DEFAULT_ACCOUNT).strip().lower()
    return email if "@" in email and " " not in email else DEFAULT_ACCOUNT


def verify_private_password(candidate, configured):
    """No admite secreto vacío/corto ni compara usando ==."""
    if not isinstance(candidate, str) or not isinstance(configured, str):
        return False
    if len(configured) < MIN_PASSWORD_LENGTH:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), configured.encode("utf-8"))


def personal_access_gate():
    """No deja cargar datos ni funcionalidades antes de autenticar."""
    import streamlit as st

    secret = os.environ.get("GLM_PERSONAL_ACCESS_PASSWORD", "")
    if len(secret) < MIN_PASSWORD_LENGTH:
        st.title("GLM Cultivador · acceso privado")
        st.error("Instancia cerrada. Configurá GLM_PERSONAL_ACCESS_PASSWORD (mínimo 16 caracteres) como secreto del entorno.")
        st.stop()

    authenticated_at = st.session_state.get("_glm_personal_authenticated_at", 0)
    if not isinstance(authenticated_at, (int, float)):
        authenticated_at = 0
    if not authenticated_at or time.time() - authenticated_at > SESSION_SECONDS:
        st.session_state.pop("_glm_personal_authenticated_at", None)
        st.title("GLM Cultivador · acceso privado")
        with st.form("glm_personal_login", clear_on_submit=True):
            candidate = st.text_input("Contraseña personal", type="password")
            submit = st.form_submit_button("Ingresar")
        if submit:
            if verify_private_password(candidate, secret):
                st.session_state["_glm_personal_authenticated_at"] = time.time()
                st.rerun()
            else:
                st.error("Credenciales incorrectas.")
        st.stop()

    if st.sidebar.button("Cerrar sesión privada", key="glm_logout"):
        st.session_state.pop("_glm_personal_authenticated_at", None)
        st.session_state.pop("cultivos", None)
        st.rerun()

    if not os.environ.get("DATABASE_URL", "").strip():
        st.error("Falta la conexión DATABASE_URL. No se cargaron ni modificaron datos.")
        st.stop()
