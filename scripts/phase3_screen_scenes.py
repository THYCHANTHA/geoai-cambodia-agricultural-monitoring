"""Phase 3: screen candidate scenes per window by AOI-level clear-pixel share.

Reads only the 20 m scene-classification layer (SCL) of each candidate over the window (a
small read, counted as a *screening* read, separate from the window-scene imagery reads).
One item per (tile, date) is screened (lowest processing baseline = original product).
Selection per window: scene 1 = highest AOI clear share; scene 2 = a different date,
>= 5 days from scene 1, maximising the share of pixels with >= 1 clear observation.
Window W1 keeps its Phase 2 scene as scene 1 when its AOI clear share is >= 95%.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import psutil
from pystac_client import Client
from rasterio.transform import from_origin
from shapely.geometry import box

from geoai.cog import SCL_CLEAR, read_on_grid

ROOT = Path(__file__).resolve().parents[1]
STAC_URL = "https://earth-search.aws.element84.com/v1"
MIN_GAP_DAYS = 5


def main() -> None:
    cfg = json.loads((ROOT / "configs/windows.json").read_text())
    cat = Client.open(STAC_URL)
    net0 = psutil.net_io_counters().bytes_recv
    out = {"stac": STAC_URL, "window": cfg["dry_season"], "windows": {}}
    for w in cfg["windows"]:
        x0, y1 = w["origin"]
        n = w["size_px"]
        grid = from_origin(x0, y1, 10, 10)
        import pyproj
        to_ll = pyproj.Transformer.from_crs(w["crs"], "EPSG:4326", always_xy=True).transform
        ring = [to_ll(x, y) for x, y in
                [(x0, y1), (x0 + 10 * n, y1), (x0 + 10 * n, y1 - 10 * n), (x0, y1 - 10 * n)]]
        poly = box(min(p[0] for p in ring), min(p[1] for p in ring),
                   max(p[0] for p in ring), max(p[1] for p in ring))
        items = list(cat.search(collections=["sentinel-2-l2a"], intersects=poly.__geo_interface__,
                                datetime=cfg["dry_season"]).items())
        by_key: dict = {}
        for it in items:  # keep the lowest baseline per (tile, date)
            k = (it.properties.get("grid:code"), it.datetime.date())
            bl = float(it.properties["s2:processing_baseline"])
            if k not in by_key or bl < float(by_key[k].properties["s2:processing_baseline"]):
                by_key[k] = it
        cand = sorted(by_key.values(), key=lambda i: i.datetime)
        print(w["id"], f"{len(items)} items, {len(cand)} (tile,date) candidates", flush=True)
        rows, masks = [], {}
        for k, it in enumerate(cand):
            t0 = time.time()
            try:
                scl = read_on_grid(it.assets["scl"].href, w["crs"], grid, n, n, nodata=None)
            except Exception as exc:  # noqa: BLE001 - recorded in the report
                rows.append({"id": it.id, "error": f"{type(exc).__name__}: {str(exc)[:80]}"})
                continue
            clear = np.isin(scl, SCL_CLEAR)
            masks[it.id] = clear
            rows.append({"id": it.id, "date": it.datetime.date().isoformat(),
                         "baseline": it.properties["s2:processing_baseline"],
                         "scene_cloud_pct": round(it.properties["eo:cloud_cover"], 2),
                         "aoi_clear_pct": round(100 * float(clear.mean()), 2),
                         "seconds": round(time.time() - t0, 1)})
            print(f"  {k + 1}/{len(cand)} {it.id} clear={rows[-1]['aoi_clear_pct']}% {rows[-1]['seconds']}s",
                  flush=True)
        ok = [r for r in rows if "aoi_clear_pct" in r]
        first = None
        if w.get("fixed_scene"):
            fixed = next((r for r in ok if r["date"] == "2021-02-19"), None)
            if fixed and fixed["aoi_clear_pct"] >= 95:
                first = {"id": w["fixed_scene"], "date": "2021-02-19", "baseline": "05.00",
                         "aoi_clear_pct": fixed["aoi_clear_pct"], "note": "Phase 2 scene reused (cached)"}
        if first is None:
            b = max(ok, key=lambda r: (r["aoi_clear_pct"], -float(r["baseline"])))
            first = {k: b[k] for k in ("id", "date", "baseline", "aoi_clear_pct")}
        d1 = np.datetime64(first["date"])
        base_mask = masks.get(next((r["id"] for r in ok if r["date"] == first["date"]), None))
        ranked = []
        for r in ok:
            if abs((np.datetime64(r["date"]) - d1).astype(int)) < MIN_GAP_DAYS:
                continue
            union = (base_mask | masks[r["id"]]) if base_mask is not None else masks[r["id"]]
            ranked.append((float(union.mean()), r["aoi_clear_pct"], r))
        ranked.sort(key=lambda t: (-t[0], -t[1], float(t[2]["baseline"])))
        second = ranked[0][2]
        out["windows"][w["id"]] = {
            "candidates": rows, "selected": [first, {k: second[k] for k in ("id", "date", "baseline", "aoi_clear_pct")}],
            "union_clear_pct_selected": round(100 * ranked[0][0], 2)}
        print(w["id"], "selected:", [s["id"] for s in out["windows"][w["id"]]["selected"]],
              "union clear %", out["windows"][w["id"]]["union_clear_pct_selected"], flush=True)
    out["network_bytes_received_during_screening"] = int(psutil.net_io_counters().bytes_recv - net0)
    (ROOT / "reports/validation/phase3_scene_screening.json").write_text(json.dumps(out, indent=2))
    print("done; net MB", round(out["network_bytes_received_during_screening"] / 1e6, 1), flush=True)


if __name__ == "__main__":
    main()
