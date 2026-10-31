"""Regression tests for the BOA-offset decision (Phase 2 defect: blind -0.1 produced NDVI > 1)."""
import numpy as np
import pytest

from geoai import indices
from geoai.offset import AmbiguousOffsetError, audit_scene, to_reflectance

RNG = np.random.default_rng(7)


def _kw(dn, **over):
    base = {"scene_id": "S", "baseline": "05.00", "boa_offset_applied": True,
            "asset_offset": -0.1, "dn_clear_red": dn}
    return base | over


def test_scene_without_offset_in_values_despite_metadata_minus_0p1():
    dn = RNG.integers(250, 2500, 20000)  # vegetation/soil red, no offset
    d = audit_scene(**_kw(dn))
    assert d["dn_offset_subtracted"] == 0
    assert d["asset_offset_applied"] is False
    assert d["metadata_conflict"] is True  # metadata says -0.1, data say none
    assert to_reflectance(dn, d).min() > 0


def test_blind_metadata_offset_would_give_impossible_negative_reflectance():
    dn = RNG.integers(250, 2500, 20000)
    blind = dn * 1e-4 - 0.1
    assert np.median(blind) < 0  # the Phase 2 failure mode
    assert np.median(to_reflectance(dn, audit_scene(**_kw(dn)))) > 0


def test_scene_with_true_plus_1000_offset_is_corrected():
    rho = RNG.uniform(0.02, 0.25, 20000)
    dn = np.round(rho * 1e4) + 1000
    d = audit_scene(**_kw(dn))
    assert d["dn_offset_subtracted"] == 1000
    assert d["metadata_conflict"] is False
    assert np.allclose(to_reflectance(dn, d), rho, atol=1e-4)


def test_old_baseline_with_consistent_zero_metadata():
    dn = RNG.integers(250, 2500, 20000)
    d = audit_scene(**_kw(dn, baseline="02.14", boa_offset_applied=False, asset_offset=0))
    assert d["dn_offset_subtracted"] == 0 and d["metadata_conflict"] is False


def test_ambiguous_scene_is_refused():
    dn = np.concatenate([RNG.integers(600, 900, 3000), RNG.integers(1100, 2500, 7000)])
    with pytest.raises(AmbiguousOffsetError):
        audit_scene(**_kw(dn))


def test_too_few_pixels_is_refused():
    with pytest.raises(AmbiguousOffsetError):
        audit_scene(**_kw(np.array([500.0] * 10)))


def test_nan_pixels_ignored():
    dn = np.concatenate([RNG.integers(250, 2500, 5000).astype(float), np.full(500, np.nan)])
    assert audit_scene(**_kw(dn))["dn_clear_red"]["n"] == 5000


def test_ndvi_of_audited_reflectance_stays_in_range():
    red = RNG.integers(250, 2500, 5000)
    nir = RNG.integers(500, 5000, 5000)
    d = audit_scene(**_kw(red))
    v = indices.ndvi(to_reflectance(nir, d), to_reflectance(red, d))
    assert np.all(np.abs(v) <= 1)
