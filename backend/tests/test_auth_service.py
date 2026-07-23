import unittest
from unittest.mock import Mock

from app.services.auth_service import (
    AuthService,
    InvalidCurrentPassword,
    ProtectedAccount,
)


class AuthServiceTest(unittest.TestCase):
    def setUp(self):
        self.repository = Mock()

        def hasher(password, salt=None):
            if salt is not None:
                return f"digest:{password}:{salt.hex()}", salt.hex()
            return f"digest:{password}:new", "6e6577"

        self.service = AuthService(self.repository, hasher)

    def test_logout_delegates_session_removal(self):
        self.service.logout("session-token")
        self.repository.delete_session.assert_called_once_with("session-token")

    def test_change_password_checks_current_password_and_persists_new_one(self):
        user = {
            "id": "usr_1",
            "password_salt": "6f6c64",
            "password_hash": "digest:current:6f6c64",
        }
        self.service.change_password(user, "current", "new-password")
        self.repository.update_password.assert_called_once_with(
            "usr_1", "digest:new-password:new", "6e6577"
        )

        with self.assertRaises(InvalidCurrentPassword):
            self.service.change_password(user, "wrong", "new-password")

    def test_administrator_account_is_protected(self):
        with self.assertRaises(ProtectedAccount):
            self.service.deactivate_account({"id": "usr_grafana_admin"})
        self.repository.deactivate_account.assert_not_called()

    def test_avatar_update_is_delegated(self):
        updated = {"id": "usr_1", "avatar_data": "data:image/png;base64,AA"}
        self.repository.update_avatar.return_value = updated
        self.assertIs(
            self.service.change_avatar("usr_1", updated["avatar_data"]),
            updated,
        )


if __name__ == "__main__":
    unittest.main()
