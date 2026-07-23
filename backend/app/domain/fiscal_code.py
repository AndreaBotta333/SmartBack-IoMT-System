"""Validazione del codice fiscale italiano."""

import re


def is_valid_fiscal_code(value: str) -> bool:
    code = value.upper().replace(" ", "")
    pattern = (
        r"^[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}"
        r"[A-Z][0-9LMNPQRSTUV]{3}[A-Z]$"
    )
    if not re.fullmatch(pattern, code):
        return False
    odd_values = {
        **dict(zip("0123456789", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21])),
        **dict(
            zip(
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                [
                    1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18,
                    20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23,
                ],
            )
        ),
    }
    even_values = {
        **{str(index): index for index in range(10)},
        **{
            letter: index
            for index, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        },
    }
    total = sum(
        odd_values[char] if index % 2 == 0 else even_values[char]
        for index, char in enumerate(code[:15])
    )
    return code[15] == chr(ord("A") + total % 26)
