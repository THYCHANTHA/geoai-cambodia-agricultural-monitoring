"""Phase 3: read selected window-scenes, audit offsets, mask, composite, index, label, tabulate.

Budget guards: at most 6 window-scene imagery reads (cache hits count), D: free >= 4 GB,
generated rasters < 1 GB. Network bytes are measured with psutil (all traffic of the machine
during the read, so an upper bound). Outputs (git-ignored): data/processed/features_<W>.tif,
data/processed/features_all.parquet. Evidence (tracked): reports/validation/phase3_*.json.
"""
from __future__ import annotations

import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
import pyproj
import rasterio
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from scipy.ndimage import binary_dilation

from geoai import indices
from geoai.cog import SCL_CLEAR, read_on_grid
from geoai.offset import audit_scene, to_reflectance
from geoai.validation import block_ids
from geoai.worldcover import WC_CLASSES, WC_URL, wc_tiles_for_bounds

ROOT = Path(__file__).resolve().parents[1]
STAC_URL = "https://earth-search.aws.element84.com/v1"
BANDS = {"B02": "blue", "B03": "green", "B04": "red", "B08": "nir", "B11": "swir16"}
SCL_BAD_CORE = (3, 8, 9, 10)  # cloud shadow, medium/high-probability cloud, thin cirrus
DILATE_PX = 2  # 20 m: SCL cloud edges are known to be ragged
MAX_READS, MIN_FREE_GB, MAX_OUT_GB = 6, 4.0, 1.0


def free_gb() -> float:
    return shutil.disk_usage("D:/").free / 1e9


def read_scene(cat, wid: str, scene_id: str, grid, crs: str, n: int, origin) -> tuple[dict, dict]:
    legacy = ROOT / "data/raw/cache_kc_b_S2A_48PWU_20210219_1_L2A.npz"
    cache = ROOT / f"data/raw/cache_{wid}_{scene_id}.npz"
    it = next(cat.search(collections=["sentinel-2-l2a"], ids=[scene_id]).items())
    meta = {"scene_id": scene_id, "date": it.datetime.date().isoformat(),
            "baseline": it.properties["s2:processing_baseline"],
            "boa_offset_applied": it.properties.get("earthsearch:boa_offset_applied"),
            "asset_offset": it.assets["red"].extra_fields["raster:bands"][0].get("offset", 0),
            "scene_cloud_pct": it.properties["eo:cloud_cover"]}
    src = legacy if (wid == "W1" and scene_id == "S2A_48PWU_20210219_1_L2A" and legacy.exists()) else cache
    if src.exists():
        z = np.load(src)
        if "origin" in z.files:
            assert list(z["origin"]) == list(origin), "cached grid differs from window grid"
        meta.update({"from_cache": True, "seconds": 0.0, "net_mb_upper_bound": 0.0,
                     "cache_file": src.name})
        return meta, {k: z[k] for k in (*BANDS, "scl")} if all(k in z.files for k in BANDS) else \
            {"B02": z["blue"], "B03": z["green"], "B04": z["red"], "B08": z["nir"],
             "B11": z["swir16"], "scl": z["scl"]}
    net0, t0 = psutil.net_io_counters().bytes_recv, time.time()
    def _one(item):
        key, asset, nodata = item
        return key, read_on_grid(it.assets[asset].href, crs, grid, n, n,
                                 resampling=Resampling.nearest, nodata=nodata)

    jobs = [(b, a, 0) for b, a in BANDS.items()] + [("scl", "scl", None)]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:  # latency-bound: separate connections
        arrs = dict(pool.map(_one, jobs))
    np.savez_compressed(cache, origin=np.array(origin), **arrs)
    meta.update({"from_cache": False, "seconds": round(time.time() - t0, 1),
                 "net_mb_upper_bound": round((psutil.net_io_counters().bytes_recv - net0) / 1e6, 2)})
    return meta, arrs


def build_window(cat, w: dict, scene_ids: list[str], reads_used: int) -> tuple[dict, pd.DataFrame, int]:
    wid, crs, n = w["id"], w["crs"], w["size_px"]
    x0, y1 = w["origin"]
    grid = from_origin(x0, y1, 10, 10)
    refl, clears, decisions, metas = [], [], [], []
    for sid in scene_ids:
        if reads_used >= MAX_READS:
            raise RuntimeError("imagery read budget (6 window-scenes) exhausted")
        reads_used += 1
        assert free_gb() >= MIN_FREE_GB, "D: free space below 4 GB: stopping"
        meta, a = read_scene(cat, wid, sid, grid, crs, n, w["origin"])
        scl = a["scl"]
        base_clear = np.isin(scl, SCL_CLEAR)
        red_clear = a["B04"][base_clear & np.isfinite(a["B04"])]
        dec = audit_scene(scene_id=sid, baseline=meta["baseline"],
                          boa_offset_applied=meta["boa_offset_applied"],
                          asset_offset=meta["asset_offset"], dn_clear_red=red_clear)
        decisions.append(dec)
        bad = binary_dilation(np.isin(scl, SCL_BAD_CORE), iterations=DILATE_PX)
        finite = np.all([np.isfinite(a[b]) for b in BANDS], axis=0)
        clear = base_clear & ~bad & finite
        stack = np.stack([np.where(clear, to_reflectance(a[b], dec), np.nan) for b in BANDS])
        refl.append(stack)
        clears.append(clear)
        meta.update({"aoi_clear_pct_after_mask": round(100 * float(clear.mean()), 2),
                     "scl_class_pct": {int(k): round(100 * float(v) / scl.size, 3) for k, v in
                                       zip(*np.unique(scl, return_counts=True), strict=True)}})
        metas.append(meta)
    R = np.stack(refl)  # (scenes, bands, H, W)
    nobs = np.sum(clears, axis=0).astype("float32")
    with np.errstate(all="ignore"):
        comp = np.nanmedian(R, axis=0)  # masked per-pixel median over the available observations
    comp[:, nobs == 0] = np.nan
    b02, b03, b04, b08, b11 = comp
    idx = {"NDVI": indices.ndvi(b08, b04), "EVI": indices.evi(b08, b04, b02),
           "NDWI": indices.ndwi(b03, b08), "NDBI": indices.ndbi(b11, b08)}
    # labels on the same grid (all WorldCover tiles the window touches)
    to_ll = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    cs = [to_ll(x, y) for x in (x0, x0 + 10 * n) for y in (y1, y1 - 10 * n)]
    tiles = wc_tiles_for_bounds(min(c[0] for c in cs), min(c[1] for c in cs),
                                max(c[0] for c in cs), max(c[1] for c in cs))
    lab = np.full((n, n), np.nan)
    for t in tiles:
        lab = np.where(np.isfinite(lab), lab, read_on_grid(WC_URL.format(tile=t), crs, grid, n, n, nodata=0))
    # temporal-consistency QC where two dates are both clear
    qc = {}
    if len(refl) == 2:
        nd = [indices.ndvi(r[3], r[2]) for r in refl]
        both = np.isfinite(nd[0]) & np.isfinite(nd[1])
        d = np.abs(nd[0][both] - nd[1][both])
        qc = {"pixels_clear_in_both": int(both.sum()), "median_abs_ndvi_diff": round(float(np.median(d)), 4),
              "p95_abs_ndvi_diff": round(float(np.percentile(d, 95)), 4),
              "ndvi_pearson_r": round(float(np.corrcoef(nd[0][both], nd[1][both])[0, 1]), 4)}
    names = ["B02", "B03", "B04", "B08", "B11", "NDVI", "EVI", "NDWI", "NDBI", "n_obs", "worldcover"]
    data = np.concatenate([comp, np.stack(list(idx.values())), nobs[None], lab[None]]).astype("float32")
    out = ROOT / f"data/processed/features_{wid}.tif"
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", driver="GTiff", height=n, width=n, count=data.shape[0], dtype="float32",
                       crs=crs, transform=grid, compress="deflate", nodata=np.nan) as dst:
        dst.write(data)
        dst.descriptions = tuple(names)
        dst.update_tags(scenes=",".join(scene_ids), composite="masked per-pixel median",
                        label_source="ESA WorldCover 2021 v200 (proxy labels, not ground truth)")
    # feature table: composite valid + labelled pixels
    valid = np.isfinite(data[:9]).all(axis=0) & np.isfinite(lab) & (lab > 0)
    rr, cc = np.nonzero(valid)
    xs, ys = x0 + (cc + 0.5) * 10, y1 - (rr + 0.5) * 10
    lon, lat = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(xs, ys)
    df = pd.DataFrame({"window": wid, "row": rr, "col": cc, "x_utm": xs, "y_utm": ys, "lon": lon, "lat": lat,
                       "block": [f"{wid}_{b}" for b in block_ids(wid, rr, cc)],
                       "label_code": lab[valid].astype(int)})
    df["label_name"] = df["label_code"].map(WC_CLASSES)
    for k, nme in enumerate(names[:10]):
        df[nme.lower()] = data[k][valid]
    rep = {"window": wid, "scenes": metas, "offset_decisions": decisions, "composite_method":
           f"per-pixel median of masked reflectance (2 scenes -> mean); SCL clear={SCL_CLEAR}; "
           f"cloud/shadow/cirrus {SCL_BAD_CORE} dilated {DILATE_PX} px (10 m)",
           "n_obs_pct": {str(k): round(100 * float((nobs == k).mean()), 3) for k in range(len(scene_ids) + 1)},
           "composite_valid_pct": round(100 * float((nobs > 0).mean()), 3),
           "worldcover_tiles": tiles, "worldcover_unlabelled_pct": round(100 * float(np.isnan(lab).mean()), 3),
           "temporal_consistency": qc, "feature_table_rows": int(valid.sum()),
           "raster_bytes": out.stat().st_size,
           "index_ranges": {k: [round(float(np.nanmin(v)), 3), round(float(np.nanmax(v)), 3)] for k, v in idx.items()}}
    return rep, df, reads_used


def main() -> None:
    cfg = json.loads((ROOT / "configs/windows.json").read_text())
    sel = json.loads((ROOT / "reports/validation/phase3_scene_screening.json").read_text())["windows"]
    cat = Client.open(STAC_URL)
    t_start, net_start = time.time(), psutil.net_io_counters().bytes_recv
    free0, reads, reports, frames = free_gb(), 0, {}, []
    for w in cfg["windows"]:
        ids = [s["id"] for s in sel[w["id"]]["selected"]]
        print(w["id"], "scenes:", ids, flush=True)
        rep, df, reads = build_window(cat, w, ids, reads)
        reports[w["id"]] = rep
        frames.append(df)
        print(w["id"], "rows", len(df), "valid%", rep["composite_valid_pct"], flush=True)
    table = pd.concat(frames, ignore_index=True)
    table.to_parquet(ROOT / "data/processed/features_all.parquet", index=False)
    out_gb = sum(p.stat().st_size for p in (ROOT / "data/processed").glob("*")) / 1e9
    assert out_gb < MAX_OUT_GB, "local raster outputs exceed 1 GB"
    summary = {"reads_used": reads, "read_budget": MAX_READS, "runtime_s": round(time.time() - t_start, 1),
               "network_mb_upper_bound": round((psutil.net_io_counters().bytes_recv - net_start) / 1e6, 1),
               "d_free_gb_before": round(free0, 2), "d_free_gb_after": round(free_gb(), 2),
               "processed_outputs_mb": round(out_gb * 1e3, 2), "windows": reports}
    (ROOT / "reports/validation/phase3_build.json").write_text(json.dumps(summary, indent=2))
    print("done", json.dumps({k: v for k, v in summary.items() if k != "windows"}), flush=True)


if __name__ == "__main__":
    main()
