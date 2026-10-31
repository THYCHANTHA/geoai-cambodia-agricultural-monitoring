"""Phase 2: compare usable Sentinel-2 coverage for candidate provinces (dry season).

For each province: STAC search, then read the 20 m scene-classification layer (SCL) at a
coarse 200 m grid (GDAL picks a COG overview, so only a small part of each file is fetched),
and report the share of province pixels with >= N clear observations.
Writes reports/validation/phase2_coverage.json. Network required.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pyproj
from pystac_client import Client
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import mapping
from shapely.ops import transform as shp_transform

from geoai.aoi import fetch_geoboundaries, load_province
from geoai.cog import SCL_CLEAR, read_on_grid

ROOT = Path(__file__).resolve().parents[1]
STAC_URL = "https://earth-search.aws.element84.com/v1"
PROVINCES = ["Kampong Cham", "Battambang", "Prey Veng"]
WINDOW = "2021-01-01/2021-03-31"  # dry season, same year as WorldCover 2021
MAX_ITEM_CLOUD = 70  # metadata filter only to bound reads; masking happens per pixel
CELL = 200.0
CRS = "EPSG:32648"


def _pct_ge(counts: np.ndarray, inside: np.ndarray, k: int) -> float:
    return round(100 * float((counts[inside] >= k).sum()) / int(inside.sum()), 1)


def main() -> None:
    adm1 = ROOT / "data/raw/geoBoundaries-KHM-ADM1.geojson"
    meta = fetch_geoboundaries("ADM1", adm1) if not adm1.exists() else None
    cat = Client.open(STAC_URL)
    to_utm = pyproj.Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform
    results = {"stac": STAC_URL, "window": WINDOW, "grid_cell_m": CELL, "crs": CRS,
               "scl_clear_classes": list(SCL_CLEAR), "provinces": {}}
    for name in PROVINCES:
        t0 = time.time()
        geom = load_province(adm1, name).geometry.iloc[0]
        search = cat.search(collections=["sentinel-2-l2a"],
                            intersects=mapping(geom.simplify(0.01)), datetime=WINDOW,
                            query={"eo:cloud_cover": {"lt": MAX_ITEM_CLOUD}})
        items = list(search.items())
        g_utm = shp_transform(to_utm, geom)
        x0, y0, x1, y1 = g_utm.bounds
        w, h = int((x1 - x0) // CELL) + 1, int((y1 - y0) // CELL) + 1
        tr = from_origin(x0, y1, CELL, CELL)
        inside = rasterize([(g_utm, 1)], out_shape=(h, w), transform=tr, fill=0,
                           dtype="uint8").astype(bool)
        clear_n = np.zeros((h, w), dtype="int16")
        seen_n = np.zeros((h, w), dtype="int16")
        failures = 0
        dates = set()
        tiles = set()
        print(f'{name}: {len(items)} items', flush=True)
        for k, it in enumerate(items):
            t1 = time.time()
            try:
                scl = read_on_grid(it.assets["scl"].href, CRS, tr, w, h, nodata=0)
            except Exception as exc:  # noqa: BLE001 - recorded in the report, not hidden
                failures += 1
                print("  read failed:", it.id, type(exc).__name__, str(exc)[:80], file=sys.stderr)
                continue
            valid = np.isfinite(scl)
            clear = valid & np.isin(scl, SCL_CLEAR)
            clear_n += clear
            seen_n += valid
            print(f'  {k + 1}/{len(items)} {it.id} {time.time() - t1:.1f}s', flush=True)
            dates.add(it.datetime.date().isoformat())
            tiles.add(it.properties.get("grid:code"))
        n_in = int(inside.sum())
        results["provinces"][name] = {
            "area_km2": round(g_utm.area / 1e6, 1),
            "items_searched_cloud_lt_70": len(items),
            "read_failures": failures,
            "acquisition_dates": len(dates),
            "mgrs_tiles": sorted(t for t in tiles if t),
            "pct_pixels_observed_by_any_scene": round(100 * float((seen_n[inside] > 0).sum()) / n_in, 1),
            "pct_pixels_with_ge1_clear": _pct_ge(clear_n, inside, 1),
            "pct_pixels_with_ge3_clear": _pct_ge(clear_n, inside, 3),
            "pct_pixels_with_ge5_clear": _pct_ge(clear_n, inside, 5),
            "median_clear_obs_per_pixel": float(np.median(clear_n[inside])),
            "seconds": round(time.time() - t0, 1),
        }
        print(name, json.dumps(results["provinces"][name]))
    if meta:
        results["geoboundaries_adm1"] = {k: meta.get(k) for k in (
            "boundaryYearRepresented", "boundaryLicense", "boundarySource", "admUnitCount")}
    out = ROOT / "reports/validation/phase2_coverage.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
