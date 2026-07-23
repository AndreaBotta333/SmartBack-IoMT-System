import unittest

from fastapi import HTTPException

from app.api.dependencies import (
    build_current_user_dependency,
    require_grafana_user,
)


class AuthDependenciesTest(unittest.TestCase):
    def test_bearer_session_returns_current_user(self):
        expected = {"id": "usr_1", "role": "patient"}
        dependency = build_current_user_dependency(
            lambda token: expected if token == "valid-token" else None
        )

        self.assertIs(dependency("Bearer valid-token"), expected)

    def test_missing_or_invalid_bearer_session_is_rejected(self):
        dependency = build_current_user_dependency(lambda _token: None)

        with self.assertRaises(HTTPException) as missing:
            dependency(None)
        self.assertEqual(missing.exception.status_code, 401)
        self.assertEqual(missing.exception.detail, "Autenticazione richiesta")

        with self.assertRaises(HTTPException) as invalid:
            dependency("Bearer expired-token")
        self.assertEqual(invalid.exception.status_code, 401)
        self.assertEqual(invalid.exception.detail, "Sessione non valida")

    def test_grafana_session_requires_verified_doctor(self):
        verified_doctor = {
            "id": "usr_doctor",
            "role": "doctor",
            "professional_verified": 1,
        }
        self.assertIs(
            require_grafana_user("valid", lambda _token: verified_doctor),
            verified_doctor,
        )

        with self.assertRaises(HTTPException) as forbidden:
            require_grafana_user(
                "patient-session",
                lambda _token: {
                    "role": "patient",
                    "professional_verified": 0,
                },
            )
        self.assertEqual(forbidden.exception.status_code, 403)
        self.assertEqual(
            forbidden.exception.detail,
            "Accesso riservato ai medici verificati",
        )


if __name__ == "__main__":
    unittest.main()
