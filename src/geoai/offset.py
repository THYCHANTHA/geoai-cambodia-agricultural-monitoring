"""Per-scene audit of the Sentinel-2 L2A BOA offset in Earth Search COGs.

Metadata is ambiguous: baseline >= 04.00 products carry a +1000 DN offset in the original ESA
data, Earth Search lists `offset: -0.1` on those assets and sets `earthsearch:boa_offset_applied`,
and its docs say to apply a non-zero asset offset. Measured values disagree for the scenes we
checked (`reports/validation/offset_audit_pair_20210219.json`: same acquisition, baseline 02.14
vs 05.00, median DN difference -8, not +1000). So the decision is taken per scene from the
data, with the metadata kept as recorded evidence, and the audit refuses to guess.

Physical bound used (not a plausibility judgement): with a +1000 offset, DN < 1000 means
negative reflectance, which cannot hold for the majority of clear land pixels.
"""
from __future__ import annotations

import numpy as np

DN_OFFSET_ESA = 1000  # BOA_ADD_OFFSET magnitude for processing baseline >= 04.00


class AmbiguousOffsetError(ValueError):
    """The data do not support a unique offset decision; do not process the scene."""


def audit_scene(*, scene_id: str, baseline: str, boa_offset_applied, asset_offset: float,
                dn_clear_red) -> dict:
    """Return the per-scene decision record. `dn_clear_red`: raw red DN of clear pixels."""
    v = np.asarray(dn_clear_red, dtype="float64")
    v = v[np.isfinite(v)]
    if v.size < 100:
        raise AmbiguousOffsetError(f"{scene_id}: only {v.size} valid clear pixels to audit")
    frac_below = float((v < DN_OFFSET_ESA).mean())
    p01 = float(np.percentile(v, 1))
    if frac_below >= 0.5:
        dn_offset, basis = 0, "majority of clear red DN below 1000: no +1000 offset in values"
    elif p01 >= 0.9 * DN_OFFSET_ESA:
        dn_offset, basis = DN_OFFSET_ESA, "1st percentile of clear red DN >= 900: +1000 offset present"
    else:
        raise AmbiguousOffsetError(
            f"{scene_id}: fraction DN<1000 = {frac_below:.2f}, p01 = {p01:.0f}; neither pattern")
    return {
        "scene_id": scene_id, "processing_baseline": baseline,
        "earthsearch_boa_offset_applied": boa_offset_applied,
        "asset_offset_metadata": asset_offset,
        "dn_clear_red": {"n": int(v.size), "p01": p01, "p50": float(np.median(v)),
                         "fraction_below_1000": round(frac_below, 4)},
        "dn_offset_subtracted": dn_offset,
        "asset_offset_applied": False,  # never blindly apply the metadata offset
        "metadata_conflict": bool(asset_offset not in (0, 0.0)) and dn_offset == 0,
        "basis": basis,
    }


def to_reflectance(dn, decision: dict, scale: float = 1e-4) -> np.ndarray:
    """(DN - offset decided for this scene) * scale; the asset metadata offset is not used."""
    return (np.asarray(dn, dtype="float64") - decision["dn_offset_subtracted"]) * scale
