"""Derivazione sicura delle password con PBKDF2 e salt casuale."""

import hashlib
import secrets


def hash_password(
    password: str,
    salt: bytes | None = None,
) -> tuple[str, str]:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        actual_salt,
        310_000,
    )
    return digest.hex(), actual_salt.hex()
