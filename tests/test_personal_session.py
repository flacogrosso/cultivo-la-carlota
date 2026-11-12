"""Pruebas de sesión privada sin servicios externos ni secretos reales."""
import contextlib
import datetime
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import personal_access as access


class StopExecution(Exception):
    pass


class RerunExecution(Exception):
    pass


class FakeSidebar:
    def __init__(self, logout=False):
        self.logout = logout

    def button(self, *args, **kwargs):
        return self.logout


class FakeStreamlit:
    def __init__(self, state=None, candidate="", submit=False, logout=False):
        self.session_state = dict(state or {})
        self.candidate = candidate
        self.submit = submit
        self.sidebar = FakeSidebar(logout)
        self.errors = []
        self.titles = []

    def title(self, value):
        self.titles.append(value)

    def error(self, value):
        self.errors.append(value)

    def form(self, *args, **kwargs):
        return contextlib.nullcontext()

    def text_input(self, *args, **kwargs):
        return self.candidate

    def form_submit_button(self, *args, **kwargs):
        return self.submit

    def stop(self):
        raise StopExecution()

    def rerun(self):
        raise RerunExecution()


class PrivateSessionTests(unittest.TestCase):
    SECRET = "ClaveTemporalQA_SoloTests_2026!"

    def gate(self, fake, secret=None, database_url="postgresql://qa.invalid/test", now=1000000):
        env = {
            "GLM_PERSONAL_ACCESS_PASSWORD": self.SECRET if secret is None else secret,
            "DATABASE_URL": database_url,
        }
        with patch.dict(sys.modules, {"streamlit": fake}), \
             patch.dict(os.environ, env, clear=True), \
             patch.object(access.time, "time", return_value=now):
            return access.personal_access_gate()

    def test_missing_secret_blocks_before_loading_application(self):
        fake = FakeStreamlit()
        with self.assertRaises(StopExecution):
            self.gate(fake, secret="")
        self.assertTrue(any("Instancia cerrada" in e for e in fake.errors))

    def test_wrong_password_never_creates_session(self):
        fake = FakeStreamlit(candidate="wrong", submit=True)
        with self.assertRaises(StopExecution):
            self.gate(fake)
        self.assertNotIn("_glm_personal_authenticated_at", fake.session_state)
        self.assertTrue(any("incorrectas" in e for e in fake.errors))

    def test_valid_password_sets_timestamp_and_reruns(self):
        fake = FakeStreamlit(candidate=self.SECRET, submit=True)
        with self.assertRaises(RerunExecution):
            self.gate(fake)
        self.assertEqual(fake.session_state["_glm_personal_authenticated_at"], 1000000)

    def test_session_is_valid_before_12_hours(self):
        fake = FakeStreamlit(state={"_glm_personal_authenticated_at": 1000000 - 100})
        self.assertIsNone(self.gate(fake))
        self.assertFalse(fake.errors)

    def test_expired_session_requires_login(self):
        old = 1000000 - access.SESSION_SECONDS - 1
        fake = FakeStreamlit(state={"_glm_personal_authenticated_at": old})
        with self.assertRaises(StopExecution):
            self.gate(fake)
        self.assertNotIn("_glm_personal_authenticated_at", fake.session_state)

    def test_logout_clears_authorization_and_cached_cultivos(self):
        fake = FakeStreamlit(state={
            "_glm_personal_authenticated_at": 1000000,
            "cultivos": [{"id": 77}]
        }, logout=True)
        with self.assertRaises(RerunExecution):
            self.gate(fake)
        self.assertNotIn("_glm_personal_authenticated_at", fake.session_state)
        self.assertNotIn("cultivos", fake.session_state)

    def test_valid_session_blocks_without_database_url(self):
        fake = FakeStreamlit(state={"_glm_personal_authenticated_at": 1000000})
        with self.assertRaises(StopExecution):
            self.gate(fake, database_url="")
        self.assertTrue(any("DATABASE_URL" in e for e in fake.errors))

    def test_seven_existing_modules_remain_in_application(self):
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        modules = [
            "Clima y Sugerencias", "Asesoramiento Cultivo",
            "Calculadora Riego", "Diagnóstico & Plagas",
            "Estimador de Cosecha", "Sugerencias Legales",
            "Seguimiento de Cultivo",
        ]
        for module in modules:
            self.assertIn('menu == "' + module + '"', source)


if __name__ == "__main__":
    unittest.main()
