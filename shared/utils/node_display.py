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
    "lv": "LV",
    "rig": "LV",
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
    "LV": "Latvia",
}


ZONE_EUROPE = "europe"
ZONE_ASIA = "asia"
ZONE_AMERICAS = "americas"
ZONE_OCEANIA = "oceania"
ZONE_AFRICA = "africa"
ZONE_UNKNOWN = "unknown"

COUNTRY_CODE_TO_ZONE: dict[str, str] = {
    "FI": ZONE_EUROPE, "DE": ZONE_EUROPE, "NL": ZONE_EUROPE, "PL": ZONE_EUROPE,
    "GB": ZONE_EUROPE, "FR": ZONE_EUROPE, "ES": ZONE_EUROPE, "IT": ZONE_EUROPE,
    "SE": ZONE_EUROPE, "NO": ZONE_EUROPE, "DK": ZONE_EUROPE, "CH": ZONE_EUROPE,
    "AT": ZONE_EUROPE, "CZ": ZONE_EUROPE, "UA": ZONE_EUROPE, "RU": ZONE_EUROPE,
    "KZ": ZONE_EUROPE, "LV": ZONE_EUROPE, "TR": ZONE_EUROPE,

    "SG": ZONE_ASIA, "JP": ZONE_ASIA, "KR": ZONE_ASIA, "HK": ZONE_ASIA,
    "IN": ZONE_ASIA, "AE": ZONE_ASIA, "IL": ZONE_ASIA,

    "US": ZONE_AMERICAS, "CA": ZONE_AMERICAS, "MX": ZONE_AMERICAS, "BR": ZONE_AMERICAS,

    "AU": ZONE_OCEANIA,
}

VALID_ZONES: frozenset[str] = frozenset([
    ZONE_EUROPE, ZONE_ASIA, ZONE_AMERICAS,
    ZONE_OCEANIA, ZONE_AFRICA, ZONE_UNKNOWN,
])


def zone_from_country_code(country_code: str | None) -> str | None:
    if not country_code:
        return None
    return COUNTRY_CODE_TO_ZONE.get(country_code.strip().upper())


def infer_zone_from_region(region: str | None) -> str | None:
    cc = country_code_from_region(region)
    return zone_from_country_code(cc)


def effective_zone(*, explicit_zone: str | None, region: str | None) -> str:
    if explicit_zone:
        candidate = explicit_zone.strip().lower()
        if candidate in VALID_ZONES:
            return candidate
    inferred = infer_zone_from_region(region)
    return inferred or ZONE_UNKNOWN


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
    if not country_code and safe_name:
        country_code = country_code_from_region(safe_name)
    if not country_code:
        return safe_name or "Node"

    country_name = COUNTRY_CODE_TO_NAME.get(country_code, country_code)
    flag = flag_emoji_from_country_code(country_code)
    if safe_name:
        return f"{flag} {country_name}"
    return f"{flag} {country_name}"
