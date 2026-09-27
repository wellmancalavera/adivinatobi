import ast
import copy
from pathlib import Path
import sys
import types
import unittest

from streamlit.testing.v1 import AppTest


class TramasTest(unittest.TestCase):
    def setUp(self):
        self.store = types.ModuleType("adivinatobi_test_store")
        self.store.data = {
            "usuarios": ["Wellman", "Nico"],
            "tramas": [{
                "id": "trama-1", "pregunta": "¿Quién llega primero?",
                "descripcion": "El domingo", "creador": "Wellman",
                "abierta": False, "ganadoras_prediccion_ids": ["p1"],
                "creada": "2026-09-27 10:00:00",
            }],
            "predicciones": [
                {"id": pid, "trama_id": "trama-1", "autor": autor,
                 "texto": texto, "creada": "2026-09-27 11:00:00",
                 "ultima_edicion": None}
                for pid, autor, texto in [
                    ("p1", "Nico", "Llega Juan"),
                    ("p2", "Nico", "Llega Pedro"),
                    ("p3", "Wellman", "Llega Ana"),
                ]
            ],
        }
        sys.modules[self.store.__name__] = self.store
        self.addCleanup(sys.modules.pop, self.store.__name__)
        tree = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8"))
        # Replace persistence before running any app code: tests never contact Supabase.
        replacements = ast.parse('''
def load_data():
    import copy, adivinatobi_test_store
    return copy.deepcopy(adivinatobi_test_store.data)
def save_data(data):
    import copy, adivinatobi_test_store
    adivinatobi_test_store.data = copy.deepcopy(data)
''')
        funcs = {node.name: node for node in replacements.body}
        tree.body = [funcs.get(node.name, node) if isinstance(node, ast.FunctionDef) else node for node in tree.body]
        self.source = ast.unparse(ast.fix_missing_locations(tree))

    def app(self, usuario="Wellman"):
        app = AppTest.from_string(self.source)
        app.session_state["usuario"] = usuario
        app.session_state["pantalla"] = "trama"
        app.session_state["trama_seleccionada"] = "trama-1"
        app.run()
        self.assertFalse(app.exception)
        return app

    def click(self, app, label):
        next(button for button in app.button if button.label == label).click().run()
        self.assertFalse(app.exception)

    def test_reopen_and_close_again(self):
        app = self.app()
        original_predictions = copy.deepcopy(self.store.data["predicciones"])
        self.assertIn("¿Quién llega primero?", [header.value for header in app.header])
        self.assertTrue(any("Nico" in item.value and "2 pts" in item.value for item in app.markdown))
        self.click(app, "🔓 Reabrir trama")
        self.assertTrue(self.store.data["tramas"][0]["abierta"])
        self.assertEqual(self.store.data["tramas"][0]["ganadoras_prediccion_ids"], [])
        self.assertEqual(self.store.data["predicciones"], original_predictions)
        self.assertTrue(any("Sin puntos todavía" in item.value for item in app.caption))
        winners = app.multiselect[0]
        self.assertEqual(winners.options, ["Nico · Predicción 1", "Nico · Predicción 2", "Wellman"])
        winners.select("p2").run()
        self.click(app, "Cerrar con ganador(es)")
        self.assertEqual(self.store.data["tramas"][0]["ganadoras_prediccion_ids"], ["p2"])
        self.assertFalse(self.store.data["tramas"][0]["abierta"])
        self.assertTrue(any("Nico" in item.value and "2 pts" in item.value for item in app.markdown))
        self.click(app, "🔓 Reabrir trama")
        self.assertEqual(app.multiselect[0].value, [])

    def test_other_user_cannot_reopen(self):
        app = self.app("Nico")
        self.assertNotIn("🔓 Reabrir trama", [button.label for button in app.button])
        namespace = {}
        tree = ast.parse(self.source)
        required = {"load_data", "save_data", "get_trama", "reabrir_trama"}
        functions = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in required], type_ignores=[])
        namespace["st"] = types.SimpleNamespace(error=lambda message: None)
        exec(compile(functions, "app.py", "exec"), namespace)
        before = copy.deepcopy(self.store.data)
        namespace["reabrir_trama"]("trama-1", "Nico")
        namespace["reabrir_trama"]("missing", "Wellman")
        self.assertEqual(self.store.data, before)

    def test_reopen_deserted_and_accept_prediction(self):
        self.store.data["tramas"][0]["ganadoras_prediccion_ids"] = []
        app = self.app()
        self.click(app, "🔓 Reabrir trama")
        next(field for field in app.text_input if field.label == "Tu predicción").input("Llega Luis")
        self.click(app, "Agregar predicción")
        self.assertEqual(len(self.store.data["predicciones"]), 4)
        self.assertEqual(self.store.data["predicciones"][-1]["texto"], "Llega Luis")


if __name__ == "__main__":
    unittest.main()
