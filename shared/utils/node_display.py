from __future__ import annotations

import re

UNKNOWN_FLAG = "🌐"

# Region aliases used in infrastructure naming -> ISO 3166-1 alpha-2.
REGION_TO_COUNTRY_CODE: dict[str, str] = {
    "fi": "FI",
    "hel": "FI",
    "de": "DE",
    "fra": "DE",
    "nl": "NL",
    "ams": "NL",
    "pl": "PL",
    "waw": "PL",
    "gb": "GB",
    "uk": "GB",
    "lon": "GB",
    "fr": "FR",
    "par": "FR",
    "es": "ES",
    "mad": "ES",
    "it": "IT",
    "rom": "IT",
    "mil": "IT",
    "se": "SE",
    "sto": "SE",
    "no": "NO",
    "osl": "NO",
    "dk": "DK",
    "cph": "DK",
    "ch": "CH",
    "zrh": "CH",
    "at": "AT",
    "vie": "AT",
    "cz": "CZ",
    "prg": "CZ",
    "us": "US",
    "nyc": "US",
    "lax": "US",
    "ca": "CA",
    "tor": "CA",
    "sg": "SG",
    "jp": "JP",
    "tok": "JP",
    "kr": "KR",
    "sel": "KR",
    "hk": "HK",
    "au": "AU",
    "syd": "AU",
    "in": "IN",
    "tr": "TR",
    "ua": "UA",
    "ru": "RU",
    "kz": "KZ",
    "ae": "AE",
    "dxb": "AE",
    "br": "BR",
    "mx": "MX",
    "il": "IL",
}

COUNTRY_CODE_TO_NAME: dict[str, str] = {
    "FI": "Finland",
    "DE": "Germany",
    "NL": "Netherlands",
    "PL": "Poland",
    "GB": "United Kingdom",
    "FR": "France",
    "ES": "Spain",
    "IT": "Italy",
    "SE": "Sweden",
    "NO": "Norway",
    "DK": "Denmark",
    "CH": "Switzerland",
    "AT": "Austria",
    "CZ": "Czechia",
    "US": "United States",
    "CA": "Canada",
    "SG": "Singapore",
    "JP": "Japan",
    "KR": "South Korea",
    "HK": "Hong Kong",
    "AU": "Australia",
    "IN": "India",
    "TR": "Turkey",
    "UA": "Ukraine",
    "RU": "Russia",
    "KZ": "Kazakhstan",
    "AE": "United Arab Emirates",
    "BR": "Brazil",
    "MX": "Mexico",
    "IL": "Israel",
}


def _extract_region_tokens(region: str) -> list[str]:
    return [token for token in re.split(r"[^a-zA-Z]+", region.lower()) if token]


def country_code_from_region(region: str | None) -> str | None:
    if region is None:
        return None
    region_clean = region.strip().lower()
    if not region_clean:
        return None

    tokens = _extract_region_tokens(region_clean)
    for token in tokens:
        mapped = REGION_TO_COUNTRY_CODE.get(token)
        if mapped:
            return mapped

    for token in tokens:
        if len(token) == 2 and token.isalpha():
            return token.upper()

    return None


def flag_emoji_from_country_code(country_code: str | None) -> str:
    if not country_code:
        return UNKNOWN_FLAG
    code = country_code.strip().upper()
    if len(code) != 2 or not code.isalpha():
        return UNKNOWN_FLAG
    base = ord("A")
    return chr(0x1F1E6 + ord(code[0]) - base) + chr(0x1F1E6 + ord(code[1]) - base)


def format_node_display_name(*, node_name: str, region: str | None) -> str:
    safe_name = node_name.strip() if isinstance(node_name, str) else ""
    country_code = country_code_from_region(region)
    if not country_code:
        return safe_name or "Node"

    country_name = COUNTRY_CODE_TO_NAME.get(country_code, country_code)
    flag = flag_emoji_from_country_code(country_code)
    if safe_name:
        return f"{flag} {country_name}"
    return f"{flag} {country_name}"
