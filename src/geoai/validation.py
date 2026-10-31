"""Spatial validation helpers: block ids, leave-one-window-out folds, class availability.

Windows are geographically separate (>= 12 km apart), so holding out a whole window is a
spatial split. Neighbouring pixels are never split between train and test.
"""
from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pandas as pd

BLOCK_PX = 50  # 500 m blocks at 10 m, used only for grouping/diagnostics


def block_ids(window: str, rows, cols, block_px: int = BLOCK_PX) -> np.ndarray:
    r, c = np.asarray(rows) // block_px, np.asarray(cols) // block_px
    return np.array([f"{window}_r{a}_c{b}" for a, b in zip(r, c, strict=True)])


def leave_one_window_out(df: pd.DataFrame) -> Iterator[tuple[str, np.ndarray, np.ndarray]]:
    """Yield (held_out_window, train_index, test_index); asserts no window/block is shared."""
    wins = sorted(df["window"].unique())
    if len(wins) < 2:
        raise ValueError("need at least two windows")
    for w in wins:
        test = np.flatnonzero((df["window"] == w).to_numpy())
        train = np.flatnonzero((df["window"] != w).to_numpy())
        assert not set(df["block"].iloc[train]) & set(df["block"].iloc[test])
        assert not set(df["window"].iloc[train]) & set(df["window"].iloc[test])
        yield w, train, test


def class_availability(df: pd.DataFrame, min_pixels: int = 100) -> pd.DataFrame:
    """Per held-out window: classes that can be learned and evaluated (>= min_pixels in both)."""
    rows = []
    for w, tr, te in leave_one_window_out(df):
        n_tr = df["label_code"].iloc[tr].value_counts()
        n_te = df["label_code"].iloc[te].value_counts()
        for code in sorted(set(n_tr.index) | set(n_te.index)):
            a, b = int(n_tr.get(code, 0)), int(n_te.get(code, 0))
            rows.append({"held_out": w, "label_code": int(code), "train_pixels": a,
                         "test_pixels": b, "evaluable": a >= min_pixels and b >= min_pixels})
    return pd.DataFrame(rows)
