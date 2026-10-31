import numpy as np
import pandas as pd
import pytest

from geoai.validation import block_ids, class_availability, leave_one_window_out


def _df():
    rows = []
    for w, classes in {"W1": [10, 40], "W2": [40], "W3": [10, 40, 80]}.items():
        for c in classes:
            for i in range(150):
                r, col = i // 15, i % 15
                rows.append({"window": w, "row": r * 10, "col": col * 10, "label_code": c})
    df = pd.DataFrame(rows)
    df["block"] = block_ids("x", df["row"], df["col"])
    df["block"] = df["window"] + "_" + df["block"]
    return df


def test_block_ids_group_neighbours_and_separate_far_pixels():
    b = block_ids("W1", [0, 49, 50], [0, 49, 0])
    assert b[0] == b[1] and b[0] != b[2]


def test_lowo_never_shares_a_window_or_block():
    df = _df()
    folds = list(leave_one_window_out(df))
    assert [f[0] for f in folds] == ["W1", "W2", "W3"]
    for _, tr, te in folds:
        assert not set(tr) & set(te)
        assert set(df["window"].iloc[tr]).isdisjoint(set(df["window"].iloc[te]))
        assert len(tr) + len(te) == len(df)


def test_class_availability_flags_absent_classes():
    av = class_availability(_df(), min_pixels=100)
    water = av[(av.label_code == 80)]
    assert not water["evaluable"].any()  # only W3 has water: cannot be both learned and tested
    crop_w2 = av[(av.held_out == "W2") & (av.label_code == 40)].iloc[0]
    assert crop_w2["evaluable"] and crop_w2["test_pixels"] == 150


def test_single_window_rejected():
    df = _df()
    with pytest.raises(ValueError):
        list(leave_one_window_out(df[df.window == "W1"]))


def test_index_returns_are_numpy():
    tr = next(leave_one_window_out(_df()))[1]
    assert isinstance(tr, np.ndarray)
