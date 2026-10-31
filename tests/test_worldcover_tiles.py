import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "wt", Path(__file__).resolve().parents[1] / "scripts" / "phase2_window_test.py")
wt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wt)


def test_tile_naming_matches_3_degree_grid():
    assert wt.wc_tile(105.2, 12.0) == "N12E105"
    assert wt.wc_tile(104.9, 11.7) == "N09E102"
    assert wt.wc_tile(102.5, 13.0) == "N12E102"
