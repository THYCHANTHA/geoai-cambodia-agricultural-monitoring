"""ESA WorldCover 2021 v200 (10 m, 3 x 3 degree COG tiles on a public bucket)."""
from __future__ import annotations

import math

WC_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
          "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif")
WC_CLASSES = {10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
              50: "Built-up", 60: "Bare/sparse vegetation", 70: "Snow and ice",
              80: "Permanent water bodies", 90: "Herbaceous wetland", 95: "Mangroves",
              100: "Moss and lichen"}


def wc_tile(lon: float, lat: float) -> str:
    la, lo = int(math.floor(lat / 3) * 3), int(math.floor(lon / 3) * 3)
    return f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}"


def wc_tiles_for_bounds(west: float, south: float, east: float, north: float) -> list[str]:
    """All tiles touched by a lon/lat box (box edges on a tile boundary touch both)."""
    return sorted({wc_tile(lo, la) for lo in (west, east) for la in (south, north)})
