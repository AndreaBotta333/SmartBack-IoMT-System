"""Dipendenze di autenticazione HTTP.

Questo modulo conosce soltanto il modo in cui una sessione viene trasportata
via HTTP. La ricerca dell'utente rimane responsabilità del servizio di
autenticazione, ricevuto come funzione.
"""

import sqlite3
from collections.abc import Callable

from fastapi import Header, HTTPException


SessionUserLookup = Callable[[str], sqlite3.Row | None]


def build_current_user_dependency(
    session_user_lookup: SessionUserLookup,
) -> Callable[..., sqlite3.Row]:
    """Crea la dipendenza Bearer senza accoppiarla al database applicativo."""

    def current_user(
        authorization: str | None = Header(default=None),
    ) -> sqlite3.Row:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Autenticazione richiesta")
        token = authorization.removeprefix("Bearer ").strip()
        user = session_user_lookup(token)
        if user is None:
            raise HTTPException(status_code=401, detail="Sessione non valida")
        return user

    return current_user


def require_grafana_user(
    token: str | None,
    session_user_lookup: SessionUserLookup,
) -> sqlite3.Row:
    """Valida una sessione cookie riservata a un medico verificato."""

    if not token:
        raise HTTPException(status_code=401, detail="Sessione Grafana richiesta")
    user = session_user_lookup(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Sessione Grafana non valida")
    if user["role"] != "doctor" or not bool(user["professional_verified"]):
        raise HTTPException(
            status_code=403,
            detail="Accesso riservato ai medici verificati",
        )
    return user
