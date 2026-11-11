"""Smoke test: sin secreto, la app nunca llega al panel ni inicializa PostgreSQL."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class SmokeGateTests(unittest.TestCase):
    def test_access_denied_without_configured_password(self):
        with patch.dict(os.environ, {"GLM_PERSONAL_ACCESS_PASSWORD": "", "DATABASE_URL": ""}):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=25).run()
        self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
        self.assertTrue(any("acceso privado" in t.value.lower() for t in app.title))
        self.assertGreater(len(app.error), 0, "La app debe avisar que faltan credenciales")


if __name__ == "__main__":
    unittest.main()
