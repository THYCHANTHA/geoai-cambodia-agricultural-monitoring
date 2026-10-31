"""Spectral indices on surface reflectance (0-1 scale, float arrays).

Invalid pixels (NaN, or zero denominator) yield NaN. No clipping is applied, so values
outside [-1, 1] stay visible as a data-quality signal.
"""
from __future__ import annotations

import numpy as np


def _ratio(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    num = np.asarray(num, dtype="float64")
    den = np.asarray(den, dtype="float64")
    out = np.full(np.broadcast(num, den).shape, np.nan)
    ok = np.isfinite(num) & np.isfinite(den) & (den != 0)
    np.divide(num, den, out=out, where=ok)
    return out


def ndvi(nir, red):
    """(NIR - Red) / (NIR + Red); Sentinel-2 B8, B4."""
    return _ratio(np.subtract(nir, red), np.add(nir, red))


def evi(nir, red, blue):
    """2.5 (NIR - Red) / (NIR + 6 Red - 7.5 Blue + 1); B8, B4, B2 as reflectance."""
    nir, red, blue = (np.asarray(x, dtype="float64") for x in (nir, red, blue))
    return 2.5 * _ratio(nir - red, nir + 6.0 * red - 7.5 * blue + 1.0)


def ndwi(green, nir):
    """(Green - NIR) / (Green + NIR) (McFeeters); B3, B8."""
    return _ratio(np.subtract(green, nir), np.add(green, nir))


def ndbi(swir, nir):
    """(SWIR - NIR) / (SWIR + NIR); B11, B8 (B11 must be on the same grid as B8)."""
    return _ratio(np.subtract(swir, nir), np.add(swir, nir))


def dn_to_reflectance(dn, scale: float = 1e-4):
    """Digital numbers -> reflectance for Earth Search Sentinel-2 L2A COGs.

    The asset metadata advertises offset -0.1, but measured DN of the two scenes inspected
    (baselines 05.00 and 05.09) carry no +1000 offset, so only the scale is applied. The
    guard `assert_no_boa_offset` fails loudly if a scene disagrees.
    """
    return np.asarray(dn, dtype="float64") * scale


def assert_no_boa_offset(dn_valid, floor: float = 900.0) -> None:
    """Heuristic: with a +1000 offset, the 1st percentile of valid DN would be >= ~900."""
    v = np.asarray(dn_valid, dtype="float64")
    v = v[np.isfinite(v)]
    if v.size and np.percentile(v, 1) >= floor:
        raise ValueError("DN look offset by +1000; subtract the offset before scaling")
