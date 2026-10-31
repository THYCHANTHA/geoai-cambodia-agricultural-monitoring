"""Independent offset test: same acquisition, two processing baselines, same pixels.

Baseline 02.14 has no BOA offset by ESA definition (asset offset 0). If the baseline-05.00
COG (asset offset -0.1, boa_offset_applied=True) had a +1000 offset in its values, its DN would
exceed the 02.14 DN by ~1000. Reads one band over the cached pilot grid (network required).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from pystac_client import Client
from rasterio.transform import from_origin

from geoai.cog import read_on_grid

ROOT = Path(__file__).resolve().parents[1]
ITEMS = {"old_0214": "S2A_48PWU_20210219_0_L2A", "new_0500": "S2A_48PWU_20210219_1_L2A"}


def main() -> None:
    rep = json.loads((ROOT / "reports/validation/phase2_window_kc_b.json").read_text())
    x0, y1 = rep["grid"]["origin"]
    n = rep["grid"]["size_px"][0]
    grid = from_origin(x0, y1, 10, 10)
    cat = Client.open("https://earth-search.aws.element84.com/v1")
    out: dict = {"window_origin": [x0, y1], "size_px": n, "band": "red (B04)", "items": {}}
    dn = {}
    for tag, iid in ITEMS.items():
        it = next(cat.search(collections=["sentinel-2-l2a"], ids=[iid]).items())
        t0 = time.time()
        if tag == "new_0500":  # already cached by the Phase 2 run for this exact grid
            dn[tag] = np.load(next((ROOT / "data/raw").glob(f"cache_kc_b_{iid}.npz")))["red"]
        else:
            dn[tag] = read_on_grid(it.assets["red"].href, f"EPSG:{rep['scene']['epsg']}", grid, n, n)
        rb = it.assets["red"].extra_fields["raster:bands"][0]
        out["items"][tag] = {"id": iid, "baseline": it.properties["s2:processing_baseline"],
                             "boa_offset_applied": it.properties.get("earthsearch:boa_offset_applied"),
                             "asset_scale": rb.get("scale"), "asset_offset": rb.get("offset"),
                             "dn_p01_p50_p99": [float(np.nanpercentile(dn[tag], q)) for q in (1, 50, 99)],
                             "seconds": round(time.time() - t0, 1)}
    a, b = dn["old_0214"], dn["new_0500"]
    m = np.isfinite(a) & np.isfinite(b)
    d = b[m] - a[m]
    out["pixels_compared"] = int(m.sum())
    out["median_dn_new_minus_old"] = float(np.median(d))
    out["p05_p95_dn_new_minus_old"] = [float(np.percentile(d, 5)), float(np.percentile(d, 95))]
    out["pearson_r"] = float(np.corrcoef(a[m], b[m])[0, 1])
    out["median_ratio_new_over_old"] = float(np.median(b[m] / a[m]))
    out["conclusion_rule"] = ("offset present in new COG iff median(new-old) is within 200 DN of +1000; "
                              "absent iff within 200 DN of 0; else ambiguous")
    md = out["median_dn_new_minus_old"]
    out["conclusion"] = ("OFFSET_PRESENT" if abs(md - 1000) < 200 else
                         "NO_OFFSET_IN_VALUES" if abs(md) < 200 else "AMBIGUOUS")
    (ROOT / "reports/validation/offset_audit_pair_20210219.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
