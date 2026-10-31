"""Windowed reads from remote Cloud-Optimized GeoTIFFs onto a caller-defined grid."""
from __future__ import annotations

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT

GDAL_HTTP = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "AWS_NO_SIGN_REQUEST": "YES",
}

# Sentinel-2 SCL classes treated as clear land/water observations.
SCL_CLEAR = (4, 5, 6)  # vegetation, not vegetated, water


def read_on_grid(href: str, crs, transform: Affine, width: int, height: int,
                 resampling: Resampling = Resampling.nearest, scale: float = 1.0,
                 offset: float = 0.0, nodata: float | None = 0) -> np.ndarray:
    """Read `href` resampled onto the target grid; nodata -> NaN; applies scale/offset."""
    with (rasterio.Env(**GDAL_HTTP), rasterio.open(href) as src,
          WarpedVRT(src, crs=crs, transform=transform, width=width, height=height,
                    resampling=resampling, nodata=nodata) as vrt):
        arr = vrt.read(1)
    out = arr.astype("float64") * scale + offset
    if nodata is not None:
        out[arr == nodata] = np.nan
    return out


def read_native(href: str, window) -> tuple[np.ndarray, Affine, object]:
    with rasterio.Env(**GDAL_HTTP), rasterio.open(href) as src:
        arr = src.read(1, window=window)
        return arr, src.window_transform(window), src.crs
