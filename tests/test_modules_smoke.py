"""Smoke test interactivo de los siete módulos sin red ni PostgreSQL."""
import os
from pathlib import Path
import time
import unittest
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

MODULES = [
    "🌦️ Clima y Sugerencias",
    "📘 Asesoramiento Cultivo",
    "💧 Calculadora Riego",
    "🛡️ Diagnóstico & Plagas",
    "✂️ Estimador de Cosecha",
    "⚖️ Sugerencias Legales",
    "🌱 Seguimiento de Cultivo",
]


class ModuleSmokeTests(unittest.TestCase):
    def test_modules_render_without_live_services(self):
        conn = MagicMock()
        conn.cursor.return_value.fetchall.return_value = []
        conn.cursor.return_value.fetchone.return_value = None
        web_response = MagicMock()
        web_response.json.return_value = {}
        env = {
            "GLM_PERSONAL_ACCESS_PASSWORD": "Clave_Ficticia_QA_Mas_De_16_Caracteres",
            "GLM_PERSONAL_ACCOUNT": "qa-only@local.invalid",
            "DATABASE_URL": "postgresql://qa.invalid/no-real-connection",
        }

        with patch.dict(os.environ, env), \
             patch("psycopg2.connect", return_value=conn), \
             patch("requests.get", return_value=web_response), \
             patch("streamlit_js_eval.streamlit_js_eval", return_value=None), \
             patch("streamlit_js_eval.get_geolocation", return_value=None):
            app = AppTest.from_file(
                str(Path(__file__).resolve().parents[1] / "app.py"),
                default_timeout=45,
            )
            app.session_state["_glm_personal_authenticated_at"] = time.time()
            app.session_state["geo_disponible"] = False
            app.run()
            self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
            self.assertEqual(len(app.sidebar.radio), 1)
            for option in MODULES:
                with self.subTest(module=option):
                    app.sidebar.radio[0].set_value(option).run()
                    self.assertEqual(
                        len(app.exception), 0,
                        [e.message for e in app.exception],
                    )


if __name__ == "__main__":
    unittest.main()
