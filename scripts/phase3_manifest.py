"""Write a SHA-256 manifest of cached reads and generated outputs, with a load check per file.

Offline and read-only: nothing is downloaded or modified. Output (tracked):
reports/validation/phase3_file_manifest.json. The files themselves are git-ignored.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

ROOT = Path(__file__).resolve().parents[1]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(p: Path) -> str:
    """Return 'ok: <detail>' or 'FAILED: <reason>' after actually decoding the file."""
    try:
        if p.suffix == ".npz":
            z = np.load(p)
            return "ok: " + ", ".join(f"{k}{tuple(z[k].shape)}" for k in z.files)
        if p.suffix == ".npy":
            return f"ok: array{tuple(np.load(p).shape)}"
        if p.suffix == ".tif":
            with rasterio.open(p) as r:
                r.read()  # decode every block
                return f"ok: {r.count} bands {r.width}x{r.height} {r.crs}"
        if p.suffix == ".parquet":
            df = pd.read_parquet(p)
            return f"ok: {len(df)} rows x {df.shape[1]} cols"
        if p.suffix == ".geojson":
            n = len(json.loads(p.read_text(encoding="utf-8"))["features"])
            return f"ok: {n} features"
    except Exception as exc:  # noqa: BLE001 - reported in the manifest
        return f"FAILED: {type(exc).__name__}: {str(exc)[:100]}"
    return "not checked"


def main() -> None:
    files = sorted([*(ROOT / "data/raw").glob("*"), *(ROOT / "data/processed").glob("*")])
    rows = []
    for p in files:
        rows.append({"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size,
                     "sha256": sha256(p), "load_check": check(p)})
        print(rows[-1]["path"], rows[-1]["bytes"], rows[-1]["load_check"][:70])
    bad = [r["path"] for r in rows if r["load_check"].startswith("FAILED")]
    out = {"files": rows, "total_bytes": sum(r["bytes"] for r in rows), "failed": bad}
    (ROOT / "reports/validation/phase3_file_manifest.json").write_text(json.dumps(out, indent=2))
    print("failed:", bad)


if __name__ == "__main__":
    main()
