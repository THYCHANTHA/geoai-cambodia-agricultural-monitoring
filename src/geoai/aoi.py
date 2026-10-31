"""Administrative boundaries (geoBoundaries) and AOI helpers."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

import geopandas as gpd

GB_API = "https://www.geoboundaries.org/api/current/gbOpen/KHM/{level}/"


def fetch_geoboundaries(level: str, dest: Path) -> dict:
    """Download one geoBoundaries release file and return its API metadata."""
    with urlopen(GB_API.format(level=level), timeout=60) as r:
        meta = json.load(r)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(meta["gjDownloadURL"], timeout=120) as r:
        dest.write_bytes(r.read())
    return meta


def load_province(path: Path, name: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    sel = gdf[gdf["shapeName"] == name]
    if len(sel) != 1:
        raise ValueError(f"expected exactly one province named {name!r}, found {len(sel)}")
    sel = sel.copy()
    if not sel.geometry.is_valid.all():
        raise ValueError(f"invalid geometry for {name!r}")
    return sel
