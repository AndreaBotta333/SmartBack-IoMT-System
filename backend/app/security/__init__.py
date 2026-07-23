"""Funzioni di sicurezza esposte dal pacchetto del backend."""

from app.security.passwords import hash_password

__all__ = ["hash_password"]
