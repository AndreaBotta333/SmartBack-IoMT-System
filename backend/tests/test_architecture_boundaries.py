import ast
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


class ArchitectureBoundariesTests(unittest.TestCase):
    def test_main_is_only_the_asgi_entrypoint(self):
        main = (APP_ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(main)
        functions = [
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(functions, [])
        self.assertLessEqual(len(main.splitlines()), 10)

    def test_internal_modules_do_not_import_main(self):
        violations = []
        for path in APP_ROOT.rglob("*.py"):
            if path.name == "main.py":
                continue
            source = path.read_text(encoding="utf-8")
            if "app.main" in source:
                violations.append(str(path.relative_to(APP_ROOT)))
        self.assertEqual(violations, [])

    def test_sql_execution_stays_in_repositories_or_database_adapter(self):
        violations = []
        allowed = {
            "repositories",
            "infrastructure/database.py",
        }
        for path in APP_ROOT.rglob("*.py"):
            relative = path.relative_to(APP_ROOT).as_posix()
            if relative.startswith("repositories/"):
                continue
            if relative in allowed:
                continue
            source = path.read_text(encoding="utf-8")
            if ".execute(" in source:
                violations.append(relative)
        self.assertEqual(violations, [])

    def test_legacy_root_modules_have_been_reclassified(self):
        legacy_modules = {
            "database.py",
            "device_contract.py",
            "influx_manager.py",
            "mqtt_handler.py",
            "night_service.py",
            "posture_service.py",
            "push_service.py",
        }
        existing = {
            path.name for path in APP_ROOT.iterdir() if path.is_file()
        }
        self.assertEqual(existing & legacy_modules, set())


if __name__ == "__main__":
    unittest.main()
