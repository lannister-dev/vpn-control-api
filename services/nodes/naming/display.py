from __future__ import annotations


UNKNOWN_FLAG = "🌐"
_FLAG_OFFSET = 0x1F1E6
_A = ord("A")


def flag_emoji(country_code: str | None) -> str:
    if not country_code or len(country_code) != 2 or not country_code.isalpha():
        return UNKNOWN_FLAG
    code = country_code.upper()
    return chr(_FLAG_OFFSET + ord(code[0]) - _A) + chr(_FLAG_OFFSET + ord(code[1]) - _A)
