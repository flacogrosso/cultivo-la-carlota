"""QA sin conexión real: transacciones y alcance de cultivos personales."""
import ast
import datetime
from pathlib import Path
import unittest
from unittest.mock import Mock

APP = Path(__file__).resolve().parents[1] / "app.py"


def isolated_function(name, connection_factory):
    """Carga solo una función AST; evita ejecutar Streamlit e init_db()."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = {"get_db_conn": connection_factory, "datetime": datetime}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(APP), "exec"), scope)
    return scope[name]


class SafeDeleteTests(unittest.TestCase):
    def test_delete_all_success_commits_and_scopes_parameters(self):
        conn = Mock()
        conn.cursor.return_value.fetchall.return_value = [(13,)]
        fun = isolated_function("eliminar_datos_usuario", Mock(return_value=conn))
        self.assertTrue(fun(" Owner@Example.com "))
        conn.commit.assert_called_once_with()
        conn.rollback.assert_not_called()
        conn.close.assert_called_once_with()
        executed = conn.cursor.return_value.execute.call_args_list
        self.assertEqual(len(executed), 7)
        self.assertTrue(all("owner@example.com" in str(call.args[1]) or
                            call.args[1] == (13,) for call in executed))
        self.assertTrue(all("%s" in call.args[0] for call in executed))

    def test_delete_all_sql_failure_rolls_back_and_returns_false(self):
        conn = Mock()
        conn.cursor.return_value.execute.side_effect = RuntimeError("fallo simulado")
        fun = isolated_function("eliminar_datos_usuario", Mock(return_value=conn))
        self.assertFalse(fun("owner@example.com"))
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once_with()
        conn.close.assert_called_once_with()

    def test_delete_all_commit_failure_returns_false(self):
        conn = Mock()
        conn.cursor.return_value.fetchall.return_value = []
        conn.commit.side_effect = RuntimeError("commit simulado")
        fun = isolated_function("eliminar_datos_usuario", Mock(return_value=conn))
        self.assertFalse(fun("owner@example.com"))
        conn.rollback.assert_called_once_with()
        conn.close.assert_called_once_with()

    def test_delete_all_connection_error_returns_false(self):
        factory = Mock(side_effect=RuntimeError("sin conexion"))
        fun = isolated_function("eliminar_datos_usuario", factory)
        self.assertFalse(fun("owner@example.com"))
        factory.assert_called_once_with()

    def test_delete_all_invalid_identity_does_not_connect(self):
        factory = Mock()
        fun = isolated_function("eliminar_datos_usuario", factory)
        for email in ("", "sin_correo", "mal @mail.com", None):
            self.assertFalse(fun(email))
        factory.assert_not_called()

    def test_delete_one_requires_matching_id_and_account(self):
        conn = Mock()
        conn.cursor.return_value.rowcount = 1
        fun = isolated_function("eliminar_cultivo", Mock(return_value=conn))
        self.assertTrue(fun(17, " OWNER@Example.COM "))
        query, args = conn.cursor.return_value.execute.call_args.args
        self.assertIn("WHERE id = %s AND LOWER(email) = %s", query)
        self.assertEqual(args, (17, "owner@example.com"))
        conn.commit.assert_called_once_with()
        conn.rollback.assert_not_called()

    def test_delete_one_no_matching_row_returns_false(self):
        conn = Mock()
        conn.cursor.return_value.rowcount = 0
        fun = isolated_function("eliminar_cultivo", Mock(return_value=conn))
        self.assertFalse(fun(17, "other@example.com"))
        conn.commit.assert_called_once_with()
        conn.close.assert_called_once_with()

    def test_delete_one_rejects_missing_identity_or_id(self):
        factory = Mock()
        fun = isolated_function("eliminar_cultivo", factory)
        for ident, email in [(1, ""), (1, "sin_correo"), (1, None),
                             (True, "owner@example.com"), (0, "owner@example.com"),
                             (-5, "owner@example.com"), ("1", "owner@example.com")]:
            self.assertFalse(fun(ident, email))
        factory.assert_not_called()

    def test_delete_one_db_failure_rolls_back(self):
        conn = Mock()
        conn.cursor.return_value.execute.side_effect = RuntimeError("fallo simulado")
        fun = isolated_function("eliminar_cultivo", Mock(return_value=conn))
        self.assertFalse(fun(17, "owner@example.com"))
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once_with()

    def test_delete_one_connection_failure_returns_false(self):
        factory = Mock(side_effect=RuntimeError("no disponible"))
        fun = isolated_function("eliminar_cultivo", factory)
        self.assertFalse(fun(17, "owner@example.com"))

    def test_add_new_cultivo_only_inserts_and_assigns_id_after_commit(self):
        conn = Mock()
        conn.cursor.return_value.fetchone.return_value = (77,)
        fun = isolated_function("guardar_cultivos", Mock(return_value=conn))
        item = {"nombre": "Cultivo QA en memoria", "sistema": "Interior",
                "categoria": "Interior", "maceta": "10",
                "inicio": datetime.date(2026, 11, 11)}
        existing = {"id": 2, "nombre": "Existente"}
        self.assertTrue(fun([existing, item], "owner@example.com"))
        self.assertEqual(item["id"], 77)
        self.assertEqual(existing["id"], 2)
        query, args = conn.cursor.return_value.execute.call_args.args
        self.assertIn("INSERT INTO cultivos", query)
        self.assertNotIn("DELETE", query.upper())
        self.assertEqual(args[0], "owner@example.com")
        conn.commit.assert_called_once_with()

    def test_failed_add_does_not_assign_id(self):
        conn = Mock()
        conn.cursor.return_value.execute.side_effect = RuntimeError("fallo simulado")
        fun = isolated_function("guardar_cultivos", Mock(return_value=conn))
        item = {"nombre": "Cultivo QA en memoria", "sistema": "Interior",
                "inicio": datetime.date(2026, 11, 11)}
        self.assertFalse(fun([item], "owner@example.com"))
        self.assertNotIn("id", item)
        conn.rollback.assert_called_once_with()

    def test_delete_all_ui_requires_success_before_clearing_identity(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("if eliminar_datos_usuario(sub_email):", source)
        self.assertIn("No se pudieron eliminar los datos", source)


if __name__ == "__main__":
    unittest.main()
