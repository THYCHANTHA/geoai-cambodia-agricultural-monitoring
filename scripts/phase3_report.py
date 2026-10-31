"""Phase 3: class distribution/coverage report, leave-one-window-out plan, figures.

Reads data/processed (features_all.parquet, features_<W>.tif) and writes
reports/validation/phase3_class_distribution.json and reports/figures/phase3_*.png.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import rasterio

from geoai.validation import class_availability
from geoai.worldcover import WC_CLASSES

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap

ROOT = Path(__file__).resolve().parents[1]
WC_COLOURS = {10: "#006400", 20: "#ffbb22", 30: "#ffff4c", 40: "#f096ff", 50: "#fa0000",
              60: "#b4b4b4", 80: "#0064c8", 90: "#0096a0", 95: "#00cf75"}
ATTR = "(c) ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data"


def label_cmap():
    codes = sorted(WC_COLOURS)
    cmap = ListedColormap([WC_COLOURS[c] for c in codes])
    norm = BoundaryNorm([c - 5 for c in codes] + [codes[-1] + 5], cmap.N)
    return cmap, norm


def main() -> None:
    df = pd.read_parquet(ROOT / "data/processed/features_all.parquet")
    cfg = json.loads((ROOT / "configs/windows.json").read_text())
    build = json.loads((ROOT / "reports/validation/phase3_build.json").read_text())
    # class distribution
    ct = df.groupby(["window", "label_code"]).size().unstack(fill_value=0)
    dist = {w: {WC_CLASSES[int(c)]: int(v) for c, v in ct.loc[w].items() if v > 0} for w in ct.index}
    absent = {w: sorted(WC_CLASSES[int(c)] for c in ct.columns if ct.loc[w, c] == 0) for w in ct.index}
    allc = df["label_code"].value_counts().sort_index()
    av = class_availability(df, min_pixels=100)
    ev = {h: sorted(WC_CLASSES[int(c)] for c in g.loc[g.evaluable, "label_code"])
          for h, g in av.groupby("held_out")}
    never = sorted(WC_CLASSES[c] for c in WC_CLASSES if c not in set(df["label_code"]))
    rep = {"rows_total": len(df), "rows_by_window": df["window"].value_counts().sort_index().to_dict(),
           "pixels_by_class_and_window": dist,
           "pixels_by_class_total": {WC_CLASSES[int(c)]: int(v) for c, v in allc.items()},
           "classes_absent_in_window_valid_pixels": absent,
           "worldcover_classes_absent_from_all_windows": never,
           "blocks_500m_per_window": df.groupby("window")["block"].nunique().to_dict(),
           "leave_one_window_out_evaluable_classes_min100": ev,
           "availability_table": av.to_dict(orient="records"),
           "composite_valid_pct": {w: build["windows"][w]["composite_valid_pct"] for w in build["windows"]}}
    (ROOT / "reports/validation/phase3_class_distribution.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps({k: rep[k] for k in ("rows_by_window", "pixels_by_class_total",
                                          "leave_one_window_out_evaluable_classes_min100")}, indent=1))

    cmap, norm = label_cmap()
    figdir = ROOT / "reports/figures"
    figdir.mkdir(parents=True, exist_ok=True)
    for w in cfg["windows"]:
        with rasterio.open(ROOT / f"data/processed/features_{w['id']}.tif") as src:
            a = src.read()
            names = list(src.descriptions)
            tags = src.tags()
        g = dict(zip(names, a, strict=True))
        rgb = np.dstack([g["B04"], g["B03"], g["B02"]])
        fcc = np.dstack([g["B08"], g["B04"], g["B03"]])
        fig, ax = plt.subplots(2, 4, figsize=(18, 9.4))
        panels = [("True colour (composite)", np.clip(np.nan_to_num(rgb, nan=1.0) / 0.25, 0, 1), None),
                  ("False colour (NIR-R-G)", np.clip(np.nan_to_num(fcc, nan=1.0) / 0.5, 0, 1), None),
                  ("NDVI", g["NDVI"], ("RdYlGn", -0.2, 0.9)), ("EVI", g["EVI"], ("RdYlGn", 0.0, 0.8)),
                  ("NDWI", g["NDWI"], ("BrBG", -0.8, 0.3)), ("NDBI", g["NDBI"], ("PuOr_r", -0.5, 0.4)),
                  ("Observations per pixel", g["n_obs"], ("viridis", 0, 2)),
                  ("WorldCover 2021 v200 (proxy labels)", g["worldcover"], "wc")]
        for x, (title, arr, st) in zip(ax.ravel(), panels, strict=True):
            if st == "wc":
                x.imshow(np.where(np.isfinite(arr), arr, 0), cmap=cmap, norm=norm, interpolation="nearest")
            elif st:
                im = x.imshow(arr, cmap=st[0], vmin=st[1], vmax=st[2], interpolation="nearest")
                fig.colorbar(im, ax=x, fraction=0.046, pad=0.02)
            else:
                x.imshow(arr, interpolation="nearest")
            x.set_title(title, fontsize=10)
            x.axis("off")
        sc = tags.get("scenes", "").replace(",", ", ")
        fig.suptitle(f"{w['id']} - {w['role']}\ncentre {w['centre_lon_lat'][0]:.4f}E {w['centre_lon_lat'][1]:.4f}N, "
                     f"3 km x 3 km, EPSG:32648. Scenes: {sc}\n{ATTR}", fontsize=9, color="#0b1f4a")
        fig.tight_layout()
        fig.savefig(figdir / f"phase3_{w['id']}.png", dpi=80)
        plt.close(fig)
    # class distribution chart
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ws = list(ct.index)
    bottom = np.zeros(len(ws))
    for c in ct.columns:
        v = ct[c].to_numpy() / ct.sum(axis=1).to_numpy() * 100
        ax.bar(ws, v, bottom=bottom, color=WC_COLOURS[int(c)], label=WC_CLASSES[int(c)])
        bottom += v
    ax.set_ylabel("% of valid labelled pixels")
    ax.set_title("WorldCover proxy-label composition per window", fontsize=11, color="#0b1f4a")
    ax.legend(fontsize=7, loc="center left", bbox_to_anchor=(1, 0.5))
    fig.tight_layout()
    fig.savefig(figdir / "phase3_class_distribution.png", dpi=90)
    print("figures written")


if __name__ == "__main__":
    main()
