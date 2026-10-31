"""Phase 2: pilot window test on one small AOI (network required).

1. STAC search, pick the least-cloudy Sentinel-2 L2A scene covering the AOI centre.
2. HTTP range request on the red-band COG (proves partial reads work).
3. Read a small window on a 10 m grid snapped to the Sentinel-2 grid; check that the
   warped read equals a direct native window read (alignment test).
4. Apply SCL cloud/shadow mask, scale + offset, compute NDVI/EVI/NDWI/NDBI.
5. Read ESA WorldCover 2021 v200 onto the same grid and cross-tabulate with the indices.
Outputs: reports/validation/phase2_window_<tag>.json, reports/figures/phase2_<tag>.png,
data/processed/pilot_<tag>.tif (git-ignored).
"""
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.request
from pathlib import Path

import numpy as np
import pyproj
import rasterio
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.windows import Window

from geoai import indices
from geoai.cog import SCL_CLEAR, read_native, read_on_grid

ROOT = Path(__file__).resolve().parents[1]
STAC_URL = "https://earth-search.aws.element84.com/v1"
WC_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
          "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif")
WC_CLASSES = {10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
              50: "Built-up", 60: "Bare/sparse vegetation", 70: "Snow and ice",
              80: "Permanent water bodies", 90: "Herbaceous wetland", 95: "Mangroves",
              100: "Moss and lichen"}


def wc_tile(lon: float, lat: float) -> str:
    la, lo = int(math.floor(lat / 3) * 3), int(math.floor(lon / 3) * 3)
    return f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}"


def so(asset) -> tuple[float, float]:
    rb = asset.extra_fields["raster:bands"][0]
    return rb.get("scale", 1.0), rb.get("offset", 0.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--window", default="2021-01-01/2021-03-31")
    ap.add_argument("--size-m", type=int, default=5000)
    ap.add_argument("--offset-mode", choices=["metadata", "none"], default="none")
    a = ap.parse_args()
    rep: dict = {"tag": a.tag, "lon": a.lon, "lat": a.lat, "window": a.window}

    items = list(Client.open(STAC_URL).search(
        collections=["sentinel-2-l2a"], intersects={"type": "Point", "coordinates": [a.lon, a.lat]},
        datetime=a.window).items())
    items.sort(key=lambda i: i.properties["eo:cloud_cover"])
    it = items[0]
    pr = it.properties
    epsg = pr.get("proj:epsg") or int(pr["proj:code"].split(":")[1])  # pystac may migrate the key
    rep["scenes_covering_point"] = len(items)
    rep["scene"] = {"id": it.id, "date": it.datetime.isoformat(),
                    "scene_cloud_cover_pct": it.properties["eo:cloud_cover"],
                    "processing_baseline": it.properties["s2:processing_baseline"],
                    "boa_offset_applied": it.properties.get("earthsearch:boa_offset_applied"),
                    "epsg": epsg}
    A = it.assets

    print('stage: scene chosen', it.id, flush=True)
    # 2. HTTP range request
    url = A["red"].href
    head = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60)
    size = int(head.headers["Content-Length"])
    req = urllib.request.Request(url, headers={"Range": "bytes=0-4095"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        rep["range_request"] = {"file_bytes": size, "status": r.status, "bytes_returned": len(body),
                                "content_range": r.headers.get("Content-Range"),
                                "tiff_magic_ok": body[:4] in (b"II*\x00", b"MM\x00*")}

    print('stage: range request done', rep['range_request'], flush=True)
    # 3. grid snapped to the Sentinel-2 10 m grid
    crs = f"EPSG:{epsg}"
    tx = A["red"].extra_fields["proj:transform"]
    gx0, gy0 = tx[2], tx[5]
    cx, cy = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(a.lon, a.lat)
    n = a.size_m // 10
    x0 = gx0 + 10 * round((cx - a.size_m / 2 - gx0) / 10)
    y1 = gy0 - 10 * round((gy0 - (cy + a.size_m / 2)) / 10)
    grid = from_origin(x0, y1, 10, 10)
    rep["grid"] = {"crs": crs, "size_px": [n, n], "origin": [x0, y1], "pixel_m": 10}

    t0 = time.time()
    cache = ROOT / f"data/raw/cache_{a.tag}_{it.id}.npz"
    so_ = {k: so(A[k]) for k in ("blue", "green", "red", "nir", "swir16")}
    if cache.exists():
        z = np.load(cache)
        dn = {k: z[k] for k in so_}
        scl = z["scl"]
        rep["s2_read_from_cache"] = True
    else:
        # nearest: 20 m SWIR/SCL are block-replicated to 10 m, not interpolated or "enhanced"
        dn = {k: read_on_grid(A[k].href, crs, grid, n, n, resampling=Resampling.nearest)
              for k in so_}
        scl = read_on_grid(A["scl"].href, crs, grid, n, n, nodata=None)
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, scl=scl, **dn)
    rep["seconds_read_s2"] = round(time.time() - t0, 1)
    rep["dn_red"] = {"p01_p50_p99": [float(np.nanpercentile(dn["red"], q)) for q in (1, 50, 99)],
                     "pct_below_1000": round(100 * float(np.nanmean(dn["red"] < 1000)), 2),
                     "asset_scale_offset": list(so_["red"])}
    rep["offset_mode"] = a.offset_mode
    if a.offset_mode == "none":
        for k in so_:
            indices.assert_no_boa_offset(dn[k])
        refl = {k: indices.dn_to_reflectance(dn[k], so_[k][0]) for k in so_}
    else:  # diagnostic only: reproduces the metadata-offset defect
        refl = {k: dn[k] * so_[k][0] + so_[k][1] for k in so_}

    win = Window(round((x0 - gx0) / 10), round((gy0 - y1) / 10), n, n)
    direct, _, _ = read_native(A["red"].href, win)
    direct_f = np.where(direct == 0, np.nan, direct.astype("float64"))
    both = np.isfinite(direct_f) & np.isfinite(dn["red"])
    rep["alignment_test"] = {
        "warped_equals_native_window": bool(np.array_equal(direct_f[both], dn["red"][both])),
        "max_abs_diff_dn": float(np.abs(direct_f[both] - dn["red"][both]).max()) if both.any() else None,
        "native_window_offset_px": [int(win.col_off), int(win.row_off)]}

    clear = np.isin(scl, SCL_CLEAR)
    scl_hist = {int(k): int(v) for k, v in zip(*np.unique(scl, return_counts=True), strict=True)}
    rep["scl_pixel_counts"] = scl_hist
    rep["clear_pixel_pct"] = round(100 * float(clear.mean()), 2)
    m = {k: np.where(clear, v, np.nan) for k, v in refl.items()}
    idx = {"ndvi": indices.ndvi(m["nir"], m["red"]),
           "evi": indices.evi(m["nir"], m["red"], m["blue"]),
           "ndwi": indices.ndwi(m["green"], m["nir"]),
           "ndbi": indices.ndbi(m["swir16"], m["nir"])}
    rep["reflectance_range_masked"] = {k: [round(float(np.nanmin(v)), 4), round(float(np.nanmax(v)), 4)]
                                       for k, v in m.items() if np.isfinite(v).any()}
    rep["indices"] = {}
    for k, v in idx.items():
        f = v[np.isfinite(v)]
        rep["indices"][k] = {"valid_pct": round(100 * f.size / v.size, 2),
                             "p01_p50_p99": [round(float(np.percentile(f, q)), 3) for q in (1, 50, 99)],
                             "outside_pm1_pct": round(100 * float((np.abs(f) > 1).mean()), 3)}

    print('stage: S2 read done', rep['seconds_read_s2'], flush=True)
    # 5. WorldCover on the same grid
    t0 = time.time()
    to_ll = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    xs = [x0, x0 + 10 * n]
    ys = [y1, y1 - 10 * n]
    corners = [to_ll(x, y) for x in xs for y in ys]
    tiles = sorted({wc_tile(lo, la) for lo, la in corners})
    wc = np.full((n, n), np.nan)
    for t in tiles:
        part = read_on_grid(WC_URL.format(tile=t), crs, grid, n, n, nodata=0)
        wc = np.where(np.isfinite(wc), wc, part)
    rep["worldcover"] = {"tiles": tiles, "seconds": round(time.time() - t0, 1),
                         "pct_unlabelled_nodata": round(100 * float(np.isnan(wc).mean()), 3)}
    wc_i = np.where(np.isfinite(wc), wc, 0).astype(int)
    cls = {}
    for c in np.unique(wc_i):
        sel = (wc_i == c) & clear
        cls[WC_CLASSES.get(int(c), str(c))] = {
            "pixels": int((wc_i == c).sum()), "pct_of_aoi": round(100 * float((wc_i == c).mean()), 2),
            "clear_pixels": int(sel.sum()),
            "mean_ndvi": round(float(np.nanmean(idx["ndvi"][sel])), 3) if sel.any() else None,
            "mean_ndwi": round(float(np.nanmean(idx["ndwi"][sel])), 3) if sel.any() else None,
            "mean_ndbi": round(float(np.nanmean(idx["ndbi"][sel])), 3) if sel.any() else None}
    rep["worldcover"]["classes_in_aoi"] = cls

    # outputs
    out_t = ROOT / f"data/processed/pilot_{a.tag}.tif"
    out_t.parent.mkdir(parents=True, exist_ok=True)
    stack = np.stack([idx[k] for k in ("ndvi", "evi", "ndwi", "ndbi")] + [wc_i.astype("float32")])
    with rasterio.open(out_t, "w", driver="GTiff", height=n, width=n, count=5, dtype="float32",
                       crs=crs, transform=grid, compress="deflate", nodata=np.nan) as dst:
        dst.write(stack.astype("float32"))
        dst.descriptions = ("ndvi", "evi", "ndwi", "ndbi", "worldcover2021")
    rep["output_tif_bytes"] = out_t.stat().st_size

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rgb = np.dstack([np.nan_to_num(refl[k], nan=0.0) for k in ("red", "green", "blue")])
    fig, ax = plt.subplots(1, 3, figsize=(15, 5))
    ax[0].imshow(np.clip(rgb / 0.3, 0, 1)); ax[0].set_title("True colour (all pixels, unmasked)")
    ax[1].imshow(idx["ndvi"], cmap="RdYlGn", vmin=-0.2, vmax=0.9); ax[1].set_title("NDVI (cloud-masked)")
    ax[2].imshow(wc_i, cmap="tab20", interpolation="nearest"); ax[2].set_title("WorldCover 2021 v200")
    for x in ax:
        x.axis("off")
    fig.suptitle(f"{it.id}  {it.datetime.date()}  (pilot {a.tag}; (c) ESA WorldCover project 2021 / "
                 "Contains modified Copernicus Sentinel data)", fontsize=8)
    figp = ROOT / f"reports/figures/phase2_{a.tag}.png"
    figp.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figp, dpi=90, bbox_inches="tight")

    p = ROOT / f"reports/validation/phase2_window_{a.tag}.json"
    p.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
