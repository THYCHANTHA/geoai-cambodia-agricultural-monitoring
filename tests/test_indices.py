import numpy as np
import pytest

from geoai import indices


def test_ndvi_known_values():
    assert indices.ndvi(0.5, 0.1) == pytest.approx(0.4 / 0.6)
    assert indices.ndvi(0.1, 0.1) == 0.0


def test_evi_known_value():
    # 2.5 * (0.5-0.1) / (0.5 + 0.6 - 0.075 + 1)
    assert indices.evi(0.5, 0.1, 0.01) == pytest.approx(2.5 * 0.4 / (0.5 + 6 * 0.1 - 7.5 * 0.01 + 1))


def test_ndwi_sign_water_vs_vegetation():
    assert indices.ndwi(0.08, 0.02) > 0  # water: green > NIR
    assert indices.ndwi(0.06, 0.40) < 0  # vegetation: NIR > green


def test_ndbi_known_value():
    assert indices.ndbi(0.3, 0.2) == pytest.approx(0.1 / 0.5)


def test_nan_and_zero_denominator_give_nan_not_inf():
    nir = np.array([np.nan, 0.0, 0.4])
    red = np.array([0.1, 0.0, 0.1])
    out = indices.ndvi(nir, red)
    assert np.isnan(out[0]) and np.isnan(out[1])
    assert out[2] == pytest.approx(0.6)
    assert not np.isinf(out).any()


def test_range_of_ndvi_on_valid_reflectance():
    rng = np.random.default_rng(0)
    nir, red = rng.uniform(0.01, 0.6, 1000), rng.uniform(0.01, 0.6, 1000)
    v = indices.ndvi(nir, red)
    assert np.all(np.abs(v) <= 1)


def test_shape_preserved():
    a = np.full((4, 5), 0.3)
    assert indices.ndwi(a, a * 0.5).shape == (4, 5)


def test_dn_to_reflectance_scale_only():
    assert indices.dn_to_reflectance(np.array([500, 2500]))[1] == pytest.approx(0.25)


def test_offset_guard_detects_offset_scene_and_accepts_plain_scene():
    rng = np.random.default_rng(1)
    plain = rng.integers(300, 2500, 5000)
    indices.assert_no_boa_offset(plain)  # no error
    with pytest.raises(ValueError):
        indices.assert_no_boa_offset(plain + 1000)
