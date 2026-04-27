from __future__ import annotations

from dataclasses import dataclass

from services.nodes.naming.geo import (
    HIGH_LEVEL_ZONE_AMERICAS,
    HIGH_LEVEL_ZONE_ASIA,
    HIGH_LEVEL_ZONE_EUROPE,
    HIGH_LEVEL_ZONE_OCEANIA,
    GeoZone,
)


@dataclass(frozen=True)
class CityInfo:
    iata: str
    city: str
    country: str
    country_name: str
    zone: GeoZone
    high_level_zone: str


CITIES: tuple[CityInfo, ...] = (
    CityInfo("fra", "Frankfurt", "DE", "Germany", GeoZone.EU_CENTRAL, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("ber", "Berlin", "DE", "Germany", GeoZone.EU_CENTRAL, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("muc", "Munich", "DE", "Germany", GeoZone.EU_CENTRAL, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("waw", "Warsaw", "PL", "Poland", GeoZone.EU_CENTRAL, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("prg", "Prague", "CZ", "Czechia", GeoZone.EU_CENTRAL, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("vie", "Vienna", "AT", "Austria", GeoZone.EU_CENTRAL, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("zrh", "Zurich", "CH", "Switzerland", GeoZone.EU_CENTRAL, HIGH_LEVEL_ZONE_EUROPE),

    CityInfo("par", "Paris", "FR", "France", GeoZone.EU_WEST, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("ams", "Amsterdam", "NL", "Netherlands", GeoZone.EU_WEST, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("lon", "London", "GB", "United Kingdom", GeoZone.EU_WEST, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("dub", "Dublin", "IE", "Ireland", GeoZone.EU_WEST, HIGH_LEVEL_ZONE_EUROPE),

    CityInfo("hel", "Helsinki", "FI", "Finland", GeoZone.EU_NORTH, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("sto", "Stockholm", "SE", "Sweden", GeoZone.EU_NORTH, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("osl", "Oslo", "NO", "Norway", GeoZone.EU_NORTH, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("cph", "Copenhagen", "DK", "Denmark", GeoZone.EU_NORTH, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("rix", "Riga", "LV", "Latvia", GeoZone.EU_NORTH, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("tll", "Tallinn", "EE", "Estonia", GeoZone.EU_NORTH, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("vno", "Vilnius", "LT", "Lithuania", GeoZone.EU_NORTH, HIGH_LEVEL_ZONE_EUROPE),

    CityInfo("mad", "Madrid", "ES", "Spain", GeoZone.EU_SOUTH, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("rom", "Rome", "IT", "Italy", GeoZone.EU_SOUTH, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("mil", "Milan", "IT", "Italy", GeoZone.EU_SOUTH, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("lis", "Lisbon", "PT", "Portugal", GeoZone.EU_SOUTH, HIGH_LEVEL_ZONE_EUROPE),

    CityInfo("mow", "Moscow", "RU", "Russia", GeoZone.EU_EAST, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("spb", "Saint Petersburg", "RU", "Russia", GeoZone.EU_EAST, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("kiv", "Kyiv", "UA", "Ukraine", GeoZone.EU_EAST, HIGH_LEVEL_ZONE_EUROPE),
    CityInfo("ist", "Istanbul", "TR", "Turkey", GeoZone.EU_EAST, HIGH_LEVEL_ZONE_EUROPE),

    CityInfo("nyc", "New York", "US", "United States", GeoZone.NA_EAST, HIGH_LEVEL_ZONE_AMERICAS),
    CityInfo("mia", "Miami", "US", "United States", GeoZone.NA_EAST, HIGH_LEVEL_ZONE_AMERICAS),
    CityInfo("chi", "Chicago", "US", "United States", GeoZone.NA_EAST, HIGH_LEVEL_ZONE_AMERICAS),
    CityInfo("lax", "Los Angeles", "US", "United States", GeoZone.NA_WEST, HIGH_LEVEL_ZONE_AMERICAS),
    CityInfo("sfo", "San Francisco", "US", "United States", GeoZone.NA_WEST, HIGH_LEVEL_ZONE_AMERICAS),
    CityInfo("sea", "Seattle", "US", "United States", GeoZone.NA_WEST, HIGH_LEVEL_ZONE_AMERICAS),
    CityInfo("tor", "Toronto", "CA", "Canada", GeoZone.NA_EAST, HIGH_LEVEL_ZONE_AMERICAS),

    CityInfo("sgp", "Singapore", "SG", "Singapore", GeoZone.AP_EAST, HIGH_LEVEL_ZONE_ASIA),
    CityInfo("tok", "Tokyo", "JP", "Japan", GeoZone.AP_EAST, HIGH_LEVEL_ZONE_ASIA),
    CityInfo("hkg", "Hong Kong", "HK", "Hong Kong", GeoZone.AP_EAST, HIGH_LEVEL_ZONE_ASIA),
    CityInfo("sel", "Seoul", "KR", "South Korea", GeoZone.AP_EAST, HIGH_LEVEL_ZONE_ASIA),
    CityInfo("bom", "Mumbai", "IN", "India", GeoZone.AP_SOUTH, HIGH_LEVEL_ZONE_ASIA),

    CityInfo("dxb", "Dubai", "AE", "United Arab Emirates", GeoZone.ME, HIGH_LEVEL_ZONE_ASIA),
    CityInfo("tlv", "Tel Aviv", "IL", "Israel", GeoZone.ME, HIGH_LEVEL_ZONE_ASIA),

    CityInfo("syd", "Sydney", "AU", "Australia", GeoZone.OC, HIGH_LEVEL_ZONE_OCEANIA),
)
