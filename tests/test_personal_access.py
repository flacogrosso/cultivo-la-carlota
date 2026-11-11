"""Pruebas unitarias de acceso privado, sin base de datos ni servicios externos."""
import os
import unittest
from unittest.mock import patch

from personal_access import (
    DEFAULT_ACCOUNT, MIN_PASSWORD_LENGTH, personal_account,
    verify_private_password,
)


class PrivateAccessTests(unittest.TestCase):
    def test_missing_password_fails_closed(self):
        self.assertFalse(verify_private_password("", ""))
        self.assertFalse(verify_private_password("correct", "correct"))

    def test_short_password_is_rejected(self):
        self.assertFalse(verify_private_password("123456789012345", "123456789012345"))

    def test_valid_password_only_matches_exactly(self):
        secret = "UnaClavePrivadaDePrueba2026!"
        self.assertGreaterEqual(len(secret), MIN_PASSWORD_LENGTH)
        self.assertTrue(verify_private_password(secret, secret))
        self.assertFalse(verify_private_password(secret + "X", secret))

    def test_invalid_password_types(self):
        self.assertFalse(verify_private_password(None, "UnaClavePrivadaLarga"))
        self.assertFalse(verify_private_password("algo", None))

    def test_default_account_does_not_use_real_identity(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(personal_account(), DEFAULT_ACCOUNT)

    def test_account_can_reuse_existing_data_scope(self):
        with patch.dict(os.environ, {"GLM_PERSONAL_ACCOUNT": "  Prueba@Example.com "}):
            self.assertEqual(personal_account(), "prueba@example.com")


if __name__ == "__main__":
    unittest.main()
