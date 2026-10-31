"""Data-quality checks on the generated Phase 3 outputs (skipped if data/processed is absent).

These run on local, git-ignored products; they validate structure, alignment and consistency,
not model accuracy or the correctness of the WorldCover labels.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "configs/windows.json").read_text())["windows"]
PROC = ROOT / "data/processed"
pytestmark = pytest.mark.skipif(not (PROC / "features_all.parquet").exists(), reason="outputs not built")
NAMES = ["B02", "B03", "B04", "B08", "B11", "NDVI", "EVI", "NDWI", "NDBI", "n_obs", "worldcover"]
VALID_WC = {10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100}


@pytest.fixture(scope="module")
def table():
    return pd.read_parquet(PROC / "features_all.parquet")


@pytest.mark.parametrize("w", CFG, ids=[w["id"] for w in CFG])
class TestWindowRaster:
    def _open(self, w):
        return rasterio.open(PROC / f"features_{w['id']}.tif")

    def test_grid_crs_and_dimensions(self, w):
        with self._open(w) as r:
            assert r.crs.to_string() == "EPSG:32648"
            assert (r.width, r.height) == (300, 300)
            assert (r.transform.a, r.transform.e) == (10, -10)
            assert [r.transform.c, r.transform.f] == w["origin"]
            assert list(r.descriptions) == NAMES

    def test_grid_snapped_to_sentinel2_10m_grid(self, w):
        assert w["origin"][0] % 10 == 0 and w["origin"][1] % 10 == 0  # S2 tile origins are x10 m

    def test_indices_in_physical_range(self, w):
        with self._open(w) as r:
            a = dict(zip(NAMES, r.read(), strict=True))
        for k in ("NDVI", "NDWI", "NDBI", "EVI"):
            v = a[k][np.isfinite(a[k])]
            assert v.size > 0.9 * a[k].size
            assert np.abs(v).max() <= 1.0, k
        for k in ("B02", "B03", "B04", "B08", "B11"):
            v = a[k][np.isfinite(a[k])]
            assert 0.0 < v.min() and v.max() < 1.0, k  # no negative reflectance (offset fix)

    def test_nobs_consistent_with_masks(self, w):
        with self._open(w) as r:
            a = dict(zip(NAMES, r.read(), strict=True))
        assert set(np.unique(a["n_obs"])) <= {0.0, 1.0, 2.0}
        assert np.all(np.isnan(a["B04"][a["n_obs"] == 0]))
        assert np.all(np.isfinite(a["B04"][a["n_obs"] > 0]))

    def test_worldcover_labels_aligned_and_valid(self, w):
        with self._open(w) as r:
            lab = r.read(NAMES.index("worldcover") + 1)
        codes = set(np.unique(lab[np.isfinite(lab)]).astype(int))
        assert codes <= VALID_WC
        assert np.isfinite(lab).mean() > 0.999  # fully inside WorldCover coverage
        assert len(codes) >= 2

    def test_water_labels_have_higher_ndwi_than_cropland_and_tree(self, w):
        # internal-consistency check of label/imagery alignment (not an accuracy claim)
        with self._open(w) as r:
            a = dict(zip(NAMES, r.read(), strict=True))
        lab = a["worldcover"]
        if (lab == 80).sum() < 500:
            pytest.skip("no water class in this window")
        ndwi = a["NDWI"]
        assert np.nanmedian(ndwi[lab == 80]) > np.nanmedian(ndwi[lab == 40]) + 0.2
        assert np.nanmedian(ndwi[lab == 80]) > np.nanmedian(ndwi[lab == 10]) + 0.2


def test_table_matches_rasters_pixel_for_pixel(table):
    for w in CFG:
        sub = table[table.window == w["id"]]
        with rasterio.open(PROC / f"features_{w['id']}.tif") as r:
            a = dict(zip(NAMES, r.read(), strict=True))
        rr, cc = sub["row"].to_numpy(), sub["col"].to_numpy()
        assert np.allclose(sub["ndvi"], a["NDVI"][rr, cc], atol=1e-6)
        assert np.array_equal(sub["label_code"], a["worldcover"][rr, cc].astype(int))
        x, y = r.xy(rr[:50], cc[:50])
        assert np.allclose(sub["x_utm"].to_numpy()[:50], x) and np.allclose(sub["y_utm"].to_numpy()[:50], y)


def test_table_schema_no_duplicates_no_nans(table):
    feats = ["b02", "b03", "b04", "b08", "b11", "ndvi", "evi", "ndwi", "ndbi", "n_obs"]
    assert not table.duplicated(["window", "row", "col"]).any()
    assert not table[feats + ["label_code"]].isna().any().any()
    assert set(table.label_code) <= VALID_WC
    assert set(table.window) == {w["id"] for w in CFG}


def test_blocks_are_nested_in_one_window(table):
    assert table.groupby("block")["window"].nunique().max() == 1


def test_windows_are_geographically_separate():
    cs = np.array([w["origin"] for w in CFG], dtype=float)
    d = np.hypot(cs[:, None, 0] - cs[None, :, 0], cs[:, None, 1] - cs[None, :, 1])
    assert d[np.triu_indices(3, 1)].min() >= 10000


def test_offset_decisions_recorded_for_every_scene_and_none_applied_blindly():
    b = json.loads((ROOT / "reports/validation/phase3_build.json").read_text())
    n = 0
    for w in b["windows"].values():
        for d in w["offset_decisions"]:
            n += 1
            assert d["asset_offset_applied"] is False
            assert d["dn_offset_subtracted"] in (0, 1000)
            assert d["basis"]
    assert n == 6


def test_budget_respected():
    b = json.loads((ROOT / "reports/validation/phase3_build.json").read_text())
    assert b["reads_used"] <= 6
    assert b["d_free_gb_after"] >= 4
    assert b["processed_outputs_mb"] < 1000
