"""Alignment, scale/offset and nodata handling on a small synthetic GeoTIFF (no network)."""
import numpy as np
import pytest
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin

from geoai.cog import SCL_CLEAR, read_native, read_on_grid

CRS = "EPSG:32648"


@pytest.fixture()
def tif(tmp_path):
    arr = (np.arange(64 * 64, dtype="uint16").reshape(64, 64) % 5000) + 1  # no zeros
    arr[0, :4] = 0  # nodata
    p = tmp_path / "band.tif"
    with rasterio.open(p, "w", driver="GTiff", height=64, width=64, count=1, dtype="uint16",
                       crs=CRS, transform=from_origin(500000, 1400000, 10, 10), nodata=0) as d:
        d.write(arr, 1)
    return p, arr


def test_aligned_read_equals_native_window(tif):
    p, arr = tif
    grid = from_origin(500000 + 10 * 8, 1400000 - 10 * 8, 10, 10)
    got = read_on_grid(str(p), CRS, grid, 16, 16, scale=1.0, offset=0.0)
    assert np.array_equal(got, arr[8:24, 8:24].astype("float64"))


def test_scale_offset_and_nodata_to_nan(tif):
    p, arr = tif
    grid = from_origin(500000, 1400000, 10, 10)
    got = read_on_grid(str(p), CRS, grid, 64, 64, scale=0.0001, offset=-0.1)
    assert np.isnan(got[0, :4]).all()
    assert got[1, 0] == pytest.approx(arr[1, 0] * 0.0001 - 0.1)


def test_coarser_grid_nearest_does_not_invent_values(tif):
    p, arr = tif
    grid = from_origin(500000, 1400000, 20, 20)
    got = read_on_grid(str(p), CRS, grid, 32, 32, resampling=Resampling.nearest)
    assert set(np.unique(got[np.isfinite(got)])) <= set(arr.ravel().astype("float64"))


def test_read_native_returns_expected_transform(tif):
    p, _ = tif
    from rasterio.windows import Window
    _, tr, crs = read_native(str(p), Window(4, 2, 8, 8))
    assert (tr.c, tr.f) == (500040, 1399980)
    assert str(crs) == CRS


def test_scl_clear_classes_exclude_cloud_shadow_and_snow():
    for bad in (0, 1, 2, 3, 7, 8, 9, 10, 11):
        assert bad not in SCL_CLEAR
    assert set(SCL_CLEAR) == {4, 5, 6}
