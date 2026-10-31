"""Phase 3: choose windows 2 and 3 from WorldCover composition, separation and province cover.

Coarse scan: WorldCover 2021 v200 sampled at 100 m (nearest) over Kampong Cham; candidate 3 km
windows must lie >= 98% inside the province polygon. Top candidates are then re-measured from
the 10 m product. Network: WorldCover COG overview/windows only.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pyproj
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.ops import transform as shp_transform

from geoai.aoi import load_province
from geoai.cog import read_on_grid
from geoai.worldcover import WC_CLASSES, WC_URL, wc_tiles_for_bounds

ROOT = Path(__file__).resolve().parents[1]
CRS = "EPSG:32648"
CELL, WIN = 100.0, 30  # 3 km windows
MIN_SEP_M = 10000.0
W1 = {"id": "W1", "lon": 105.30, "lat": 12.20}


def read_wc(tr, w, h):
    to_ll = pyproj.Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform
    x0, y1 = tr.c, tr.f
    xs, ys = [x0, x0 + w * tr.a], [y1, y1 + h * tr.e]
    lons, lats = zip(*[to_ll(x, y) for x in xs for y in ys], strict=True)
    out = np.full((h, w), np.nan)
    for t in wc_tiles_for_bounds(min(lons), min(lats), max(lons), max(lats)):
        out = np.where(np.isfinite(out), out, read_on_grid(WC_URL.format(tile=t), CRS, tr, w, h, nodata=0))
    return out


def fractions(arr):
    v = arr[np.isfinite(arr)].astype(int)
    return {WC_CLASSES.get(int(c), str(c)): round(float((v == c).mean()), 4) for c in np.unique(v)}, v.size


def main() -> None:
    prov = load_province(ROOT / "data/raw/geoBoundaries-KHM-ADM1.geojson", "Kampong Cham")
    to_utm = pyproj.Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform
    g = shp_transform(to_utm, prov.geometry.iloc[0])
    x0, y0, x1, y1 = g.bounds
    w, h = int((x1 - x0) // CELL) + 1, int((y1 - y0) // CELL) + 1
    tr = from_origin(x0, y1, CELL, CELL)
    inside = rasterize([(g, 1)], out_shape=(h, w), transform=tr, fill=0, dtype="uint8").astype(bool)
    t0 = time.time()
    wc = read_wc(tr, w, h)
    print(f"coarse WorldCover read {w}x{h} in {time.time() - t0:.0f}s", flush=True)
    np.save(ROOT / "data/raw/wc_coarse_100m.npy", wc)
    cx1, cy1 = to_utm(W1["lon"], W1["lat"])
    cands = []
    for r in range(0, h - WIN, 5):
        for c in range(0, w - WIN, 5):
            if inside[r:r + WIN, c:c + WIN].mean() < 0.98:
                continue
            sub = wc[r:r + WIN, c:c + WIN]
            if np.isnan(sub).mean() > 0.01:
                continue
            fr, _ = fractions(sub)
            cx, cy = x0 + (c + WIN / 2) * CELL, y1 - (r + WIN / 2) * CELL
            p = np.array(list(fr.values()))
            cands.append({"row": r, "col": c, "cx": cx, "cy": cy, "frac": fr,
                          "entropy": float(-(p[p > 0] * np.log(p[p > 0])).sum()),
                          "dist_w1_km": float(np.hypot(cx - cx1, cy - cy1) / 1000)})
    print(len(cands), "candidate windows fully inside the province", flush=True)
    # cropland-dominant (75-97%) yet not single-class: >= 2 other classes of >= 1% each
    crop = [c for c in cands if c["dist_w1_km"] >= MIN_SEP_M / 1000
            and 0.75 <= c["frac"].get("Cropland", 0) <= 0.97
            and sum(v >= 0.01 for k, v in c["frac"].items() if k != "Cropland") >= 2]
    crop.sort(key=lambda c: -c["frac"].get("Cropland", 0))
    w2c = crop[:6]
    sel = {"W2_candidates": w2c}
    best2 = w2c[0]
    mixed = []
    for c in cands:
        if c["dist_w1_km"] < MIN_SEP_M / 1000:
            continue
        if np.hypot(c["cx"] - best2["cx"], c["cy"] - best2["cy"]) < MIN_SEP_M:
            continue
        f = c["frac"]
        other = sum(v for k, v in f.items() if k not in ("Cropland", "Tree cover"))
        if f.get("Cropland", 0) >= 0.10 and f.get("Tree cover", 0) >= 0.10 and other >= 0.10:
            mixed.append(c)
    mixed.sort(key=lambda c: -c["entropy"])
    sel["W3_candidates"] = mixed[:6]
    print("W2 top:", [(round(c["frac"].get("Cropland", 0), 3), round(c["dist_w1_km"], 1)) for c in w2c])
    print("W3 top:", [(round(c["entropy"], 2), {k: v for k, v in c["frac"].items() if v >= 0.05}) for c in mixed[:3]])
    # verify the first candidate of each list at 10 m
    for key in ("W2_candidates", "W3_candidates"):
        for c in sel[key][:3]:
            n = 300
            ox = round((c["cx"] - 1500) / 10) * 10
            oy = round((c["cy"] + 1500) / 10) * 10
            fine = read_wc(from_origin(ox, oy, 10, 10), n, n)
            c["fine_10m_frac"], _ = fractions(fine)
            c["fine_origin"] = [ox, oy]
            c["fine_unlabelled_pct"] = round(100 * float(np.isnan(fine).mean()), 3)
    (ROOT / "reports/validation/phase3_window_selection.json").write_text(json.dumps(sel, indent=2))
    print("done", flush=True)


if __name__ == "__main__":
    main()
