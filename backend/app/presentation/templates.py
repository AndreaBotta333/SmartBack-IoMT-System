"""Caricamento sicuro e rendering dei template HTML del portale medico."""

from functools import lru_cache
from pathlib import Path
from string import Template


_TEMPLATE_DIRECTORY = Path(__file__).with_name("templates")


@lru_cache(maxsize=32)
def _read_template(name: str) -> Template:
    path = (_TEMPLATE_DIRECTORY / name).resolve()
    if path.parent != _TEMPLATE_DIRECTORY.resolve():
        raise ValueError("Nome del template non valido")
    return Template(path.read_text(encoding="utf-8"))


def render_template(name: str, **context: str) -> str:
    """Renderizza un template HTML affidabile.

    I valori dinamici devono essere già sottoposti all'escaping adatto al
    contesto di destinazione.
    """

    return _read_template(name).substitute(context)
