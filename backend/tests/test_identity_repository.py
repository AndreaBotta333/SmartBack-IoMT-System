"""Test della persistenza di identità e sessioni."""

import tempfile
import unittest
from pathlib import Path

from app.infrastructure.database import init_database
from app.repositories.identity_repository import IdentityRepository


class IdentityRepositoryTests(unittest.TestCase):
    def test_session_lookup_survives_shared_connection_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "smartback.db")
            database = init_database(database_path)
            database.execute(
                "INSERT INTO users("
                "id,name,email,password_hash,password_salt,role,created_at"
                ") VALUES (?,?,?,?,?,?,?)",
                (
                    "doctor-1",
                    "Medico Test",
                    "medico@example.test",
                    "digest",
                    "salt",
                    "doctor",
                    "now",
                ),
            )
            database.execute(
                "INSERT INTO sessions(token,user_id,created_at) VALUES (?,?,?)",
                ("token-1", "doctor-1", "now"),
            )
            database.commit()
            repository = IdentityRepository(database, database_path)
            database.close()

            user = repository.user_for_session("token-1")

            self.assertIsNotNone(user)
            self.assertEqual(user["id"], "doctor-1")


if __name__ == "__main__":
    unittest.main()
