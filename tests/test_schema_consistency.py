import ast
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _runtime_schema_statements():
    module = ast.parse((PROJECT_ROOT / "data_queries.py").read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "SCHEMA_STATEMENTS" for target in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError("data_queries.py does not define SCHEMA_STATEMENTS")


def _normalise_create_table(statement):
    statement = re.sub(r"\s+", " ", statement.strip()).lower()
    return statement.replace("create table if not exists", "create table")


class SchemaConsistencyTests(unittest.TestCase):
    def test_bootstrap_sql_matches_runtime_schema(self):
        bootstrap_statements = [
            statement for statement in (PROJECT_ROOT / "db_setup.sql").read_text(encoding="utf-8").split(";")
            if statement.strip()
        ]

        self.assertEqual(
            [_normalise_create_table(statement) for statement in _runtime_schema_statements()],
            [_normalise_create_table(statement) for statement in bootstrap_statements],
        )

    def test_unused_sqlalchemy_draft_is_removed(self):
        self.assertFalse((PROJECT_ROOT / "db_setup.py").exists())


if __name__ == "__main__":
    unittest.main()
