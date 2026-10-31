# Phase 3 checkpoint and resume guide

Checkpoint date: 2026-10-31. Project status: **IN PROGRESS - CHECKPOINTED / RESUMABLE** (deferred, not cancelled; not complete).

## 1. Status in one paragraph
Phase 3 *data processing is complete*: all six planned window-scene reads finished, the three windows were processed,
masked, composited, indexed, labelled and checked, and no process is running. Nothing is half-written. What remains is
**not satellite processing** but the later project phases (models, dashboard, research report) and three owner decisions
(section 9). Nothing marked "done" below was left incomplete; failures and aborted attempts are listed in section 8.

Repository: https://github.com/THYCHANTHA/geoai-cambodia-agricultural-monitoring (public, branch `main`).

## 2. Windows and scenes
All windows: 300 x 300 px, 10 m, EPSG:32648 (WGS 84 / UTM 48N), origin = upper-left corner (easting, northing).

| Window | Centre (E, N) | Origin (x, y) | Role |
|---|---|---|---|
| W1 | 105.29997, 12.20002 | 531130, 1350190 | pilot (Phase 2); tree cover 75%, cropland 19% |
| W2 | 105.38051, 12.27607 | 539880, 1358610 | cropland 97% (WorldCover) |
| W3 | 105.43057, 11.95496 | 545380, 1323110 | mixed, 7 classes, 24% water |

| Window | Scene identifier | Date | Baseline | Read time | Source of the data |
|---|---|---|---|---|---|
| W1 | S2A_48PWU_20210219_1_L2A | 2021-02-19 | 05.00 | (Phase 2) | cache `cache_kc_b_S2A_48PWU_20210219_1_L2A.npz` |
| W1 | S2B_48PWU_20210105_0_L2A | 2021-01-05 | 02.14 | first build run | cache `cache_W1_S2B_48PWU_20210105_0_L2A.npz` |
| W2 | S2A_48PWU_20210110_0_L2A | 2021-01-10 | 02.14 | 203.1 s | cache `cache_W2_...` |
| W2 | S2A_48PWU_20210219_0_L2A | 2021-02-19 | 02.14 | 183.6 s | cache `cache_W2_...` |
| W3 | S2B_48PWU_20210115_0_L2A | 2021-01-15 | 02.14 | 175.2 s | cache `cache_W3_...` |
| W3 | S2A_48PWU_20210219_0_L2A | 2021-02-19 | 02.14 | 163.3 s | cache `cache_W3_...` |

**Pending satellite scenes: none.** The read budget agreed for this stage (six window-scene combinations) is used up.
Candidate scenes per window are listed in `reports/validation/phase3_scene_screening.json`.

## 3. Reflectance scaling and offset decisions (per scene)
Only the 0.0001 scale is applied. The metadata offset (-0.1 on baseline 05.00 items) is **not** applied to any scene.
Evidence: paired-baseline test `reports/validation/offset_audit_pair_20210219.json` (median DN difference -8, not +1000),
and a per-scene audit (`src/geoai/offset.py`, results in `reports/validation/phase3_build.json`).

| Scene | Window | 5th percentile clear red DN | Decision | Metadata conflict |
|---|---|---|---|---|
| S2A_48PWU_20210219_1 (05.00) | W1 | 337 | no offset in values | yes (metadata says -0.1) |
| S2B_48PWU_20210105_0 (02.14) | W1 | 151 | no offset | no |
| S2A_48PWU_20210110_0 (02.14) | W2 | 642 | no offset | no |
| S2A_48PWU_20210219_0 (02.14) | W2 | 771 (close to the 800 limit) | no offset | no |
| S2B_48PWU_20210115_0 (02.14) | W3 | 475 | no offset | no |
| S2A_48PWU_20210219_0 (02.14) | W3 | 390 | no offset | no |

## 4. Completed products (all verified to decode; SHA-256 in `reports/validation/phase3_file_manifest.json`)
| File (git-ignored, local only) | Size (bytes) | Check |
|---|---|---|
| `data/processed/features_W1.tif`, `_W2.tif`, `_W3.tif` | 2,838,523 / 2,788,289 / 2,826,139 | 11 bands, 300x300, EPSG:32648 |
| `data/processed/features_all.parquet` | 13,256,849 | 265,593 rows x 20 columns |
| `data/processed/pilot_kc_a.tif`, `pilot_kc_b.tif` | 1,404,890 / 1,406,198 | Phase 2 pilot outputs (kc_a is superseded evidence) |
| `data/raw/cache_W1_..., cache_W2_x2, cache_W3_x2, cache_kc_b_...` (6 files) | 674,885 to 743,857 each | all arrays decode |
| `data/raw/geoBoundaries-KHM-ADM1.geojson` | 2,313,831 | 25 features |
| `data/raw/wc_coarse_100m.npy` | 7,072,128 | array 850 x 1040 |

Total 38.2 MB. A verified backup zip of `data/raw`, `data/processed`, `data/study_area.geojson` and `configs` was created
outside the repository (SHA-256 `1fac93b63da1ae8b17e4292307f7571bd99e1405018ab1fc77c7326a4ff02706`). These files exist
only on the owner's machine, because they are git-ignored.

Feature stack band order: B02, B03, B04, B08, B11, NDVI, EVI, NDWI, NDBI, n_obs, WorldCover.

## 5. Indices and labels
NDVI, EVI, NDWI and NDBI are computed for all three windows (ranges in `reports/phase3_processing_qc.md`) and are within
[-1, 1] (tested). WorldCover 2021 v200 labels are aligned on the same grid with 0% unlabelled pixels. They are proxy labels,
not independently verified ground truth. Exact warped-versus-native alignment was tested for W1 only.

## 6. Processing times and resources
Final build run: 741.9 s; at most 107.3 MB received (machine-wide upper bound); scene screening 4.3 MB. Some earlier reads
were not measured (see `BUILD_STATUS.md` section 7c). D: free space at checkpoint: 7.58 GB (4 GB minimum was kept).

## 7. Tests at the checkpoint
`pytest`: 53 passed, 2 skipped; `ruff` clean (output in `reports/validation/phase3_tests.txt`). GitHub Actions has never run
for this repository (the account was billing-locked), so CI is untested.

## 8. Errors, aborted attempts and known limitations
- The first build run was stopped after about 15 minutes on W2 scene 1 (reads at about 14 kB/s because of GDAL's 16 KB range
  chunks). No data from that attempt was kept; the read was repeated after the fix (1 MB chunks, six parallel connections).
- Two small single-band reads outside the six were used for the offset audit.
- The SCL mask appears to flag bright dry bare fields as cloud (W2, 2.1% unobserved) and a river bank as shadow (W3).
- W1 mixes processing baselines 05.00 and 02.14; its two dates differ strongly (NDVI correlation 0.73).
- Under leave-one-window-out only tree cover, grassland, cropland and built-up are evaluable; water, wetland, bare/sparse and
  shrubland are not (`docs/validation_plan.md`).
- One season, at most two observations per pixel, 27 km2 in total: not representative of Kampong Cham or Cambodia.

## 9. Open decisions before Phase 4
1. Add a fourth window containing water, wetland and bare ground (needs approval; the agreed limit is three), or accept those classes as not evaluable.
2. Keep W1's mixed-baseline composite, or re-read W1 2021-02-19 as baseline 02.14 (`S2A_48PWU_20210219_0_L2A`) and rebuild.
3. Add a mask rule for the SCL false positives, or accept them and document the bias.

## 10. Exact commands to resume
Run from the repository root (Windows, PowerShell). Do not delete `data/raw`: it holds the only copy of the cached reads.
```
.venv\Scripts\python.exe -m pytest -q                         # expect 53 passed, 2 skipped
.venv\Scripts\python.exe scripts\phase3_manifest.py           # verify caches against reports\validation\phase3_file_manifest.json (compare sha256)
.venv\Scripts\python.exe scripts\phase3_build_features.py     # OPTIONAL: regenerates the validated outputs (overwrites them; the backup zip covers this); reuses all six caches (no scene download)
.venv\Scripts\python.exe scripts\phase3_report.py             # class report and figures
```
If the virtual environment is missing: `python -m venv --system-site-packages .venv` then
`.venv\Scripts\python.exe -m pip install -e . pytest ruff` (use `python -m pip`; `pip.exe` is blocked on the owner's machine).
If the caches are missing, restore them from the backup zip; only if that is impossible re-run `scripts\phase3_build_features.py`,
which re-reads the six window-scenes (about 12 minutes, about 100 MB).
Note: the rebuild still makes small STAC metadata requests and reads the WorldCover windows (a few MB), but not the Sentinel-2 scenes.
Do not start new scene reads or a fourth window without approval. After the decisions in section 9, continue with Phase 4
(Random Forest, then XGBoost, under leave-one-window-out; XGBoost is not installed yet).
