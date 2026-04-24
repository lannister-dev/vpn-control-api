from __future__ import annotations

from enum import Enum


class GeoZone(str, Enum):
    EU_CENTRAL = "eu-central"
    EU_WEST = "eu-west"
    EU_NORTH = "eu-north"
    EU_SOUTH = "eu-south"
    EU_EAST = "eu-east"
    NA_EAST = "na-east"
    NA_WEST = "na-west"
    AP_EAST = "ap-east"
    AP_SOUTH = "ap-south"
    ME = "me"
    OC = "oc"
    UNKNOWN = "unknown"


HIGH_LEVEL_ZONE_EUROPE = "europe"
HIGH_LEVEL_ZONE_AMERICAS = "americas"
HIGH_LEVEL_ZONE_ASIA = "asia"
HIGH_LEVEL_ZONE_OCEANIA = "oceania"
HIGH_LEVEL_ZONE_AFRICA = "africa"
HIGH_LEVEL_ZONE_UNKNOWN = "unknown"
