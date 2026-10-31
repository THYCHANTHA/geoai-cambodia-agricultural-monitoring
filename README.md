# GeoAI Cambodia: satellite-based agricultural and land-cover monitoring

**Status: IN PROGRESS, checkpointed and resumable (deferred, not cancelled); see `docs/PHASE3_RESUME.md`. Research pilot (Phase 3 of 6). A labelled, spatially separated dry-season dataset has been built and
quality-checked. No model has been trained, there is no dashboard yet, and no accuracy figure exists.**
GitHub Actions has never run for this repository (the account was billing-locked when it was published), so the CI
workflow is untested.

## Abstract
This project investigates how multispectral Sentinel-2 imagery and machine learning can support land-cover
classification and agricultural monitoring in Cambodia. The first stage builds a reproducible pipeline that reads small
windows from public Cloud-Optimized GeoTIFFs, audits the surface-reflectance scaling per scene, masks clouds, composites
two dry-season dates, computes NDVI, EVI, NDWI and NDBI, and aligns ESA WorldCover 2021 labels. Three 3 km x 3 km windows in
Kampong Cham Province (27 km2 in total) yield 265,593 labelled pixels. The ESA WorldCover labels are **reference (proxy)
labels, not independently verified ground truth**, so any later score will be agreement with WorldCover on held-out
windows.

## Research question and objectives
How can multispectral satellite imagery and machine-learning methods support land-cover classification and agricultural
monitoring in Cambodia? Objectives: acquire and process imagery; compute vegetation and water indices; build geospatial
feature datasets; classify land cover with spatially separated validation; analyse agricultural patterns; compare with
recognised land-cover products; document limitations. Done so far: the first three. The rest is future work.
The project is separate from rice-yield forecasting on survey data: it uses only public data and makes no rice or yield claims.

## Data
| Data | Source and access | Licence / terms (read from the publisher pages, 2026-10-31) |
|---|---|---|
| Sentinel-2 L2A COGs | Element84 Earth Search STAC (`sentinel-2-l2a`), public AWS bucket | "free, full and open" (Copernicus terms, as stated on the AWS Open Data registry) |
| ESA WorldCover 2021 v200 | public bucket | CC BY 4.0 |
| geoBoundaries KHM ADM1 | geoBoundaries API, gbOpen | ODbL 1.0 as reported by the API (source OpenStreetMap, 2017) |

Attribution: (c) ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA
WorldCover consortium. The province outline in `data/study_area.geojson` is a simplified derivative of geoBoundaries data (ODbL).
No imagery is stored in this repository; `docs/data_sources.md` has the details.

## Study area and windows
Kampong Cham Province (geoBoundaries ADM1, ISO KH-3, current boundary, so Tbong Khmum is excluded). A province-wide
comparison of Kampong Cham, Battambang and Prey Veng found complete dry-season Sentinel-2 coverage in all three
(`reports/validation/phase2_coverage.json`), so coverage did not decide the choice. Three windows were used:

| Window | Centre (E, N) | WorldCover composition | Scenes (processing baseline) |
|---|---|---|---|
| W1 | 105.3000, 12.2000 | tree cover 75%, cropland 19% | 2021-02-19 (05.00), 2021-01-05 (02.14) |
| W2 | 105.3805, 12.2761 | cropland 97% | 2021-01-10, 2021-02-19 (02.14) |
| W3 | 105.4306, 11.9550 | tree 31%, water 24%, cropland 19%, grassland 13%, wetland, built-up, bare | 2021-01-15, 2021-02-19 (02.14) |

W2 and W3 were chosen from a 100 m WorldCover scan of the province (15,698 candidate windows inside it) and re-measured at 10 m.
They are 12.1 to 35.9 km apart. Three small windows do not represent the province.

## Method
1. **Remote windowed reads** from COGs with HTTP range requests on a 10 m grid snapped to the Sentinel-2 grid.
   B02, B03, B04 and B08 are native 10 m; B11 and the scene-classification layer (SCL) are native 20 m and are replicated to
   10 m by nearest neighbour (no interpolation, no added detail).
2. **Reflectance offset audit per scene** (`src/geoai/offset.py`). Earth Search lists an asset offset of -0.1 on baseline 05.00
   items, but the values carry none. The paired test (same acquisition, baselines 02.14 and 05.00, 90,000 pixels) gave a
   median DN difference of -8, where an offset would give +1000. Each scene is audited from its raw digital numbers, the metadata
   offset is never applied blindly, and ambiguous scenes are refused. A blind -0.1 produced NDVI above 1 for 86% of pixels in the first run (kept as evidence in `reports/validation/superseded_*`).
3. **Masking and compositing:** SCL classes 4, 5, 6 kept; cloud shadow, cloud and cirrus dilated by 2 px; per-pixel median of the
   masked observations (two dates, so effectively the mean).
4. **Indices** from composite reflectance: NDVI = (NIR-Red)/(NIR+Red); EVI = 2.5 (NIR-Red)/(NIR+6 Red-7.5 Blue+1) (Huete et al. 2002);
   NDWI = (Green-NIR)/(Green+NIR) (McFeeters 1996); NDBI = (SWIR-NIR)/(SWIR+NIR). They are indicators, not measurements of crop yield or rice.
5. **Labels:** WorldCover 2021 v200 on the same grid.
6. **Spatial validation plan:** leave-one-window-out (`docs/validation_plan.md`). Random pixel splits are not used.

## Results so far (all from executed runs; see `reports/phase3_processing_qc.md`)
- 6 window-scene reads, 741.9 s for the final run, at most 107.3 MB received (machine-wide upper bound); composite valid 99.83 / 97.89 / 97.38%.
- All indices within [-1, 1]; per-window ranges are in the QC report.
- Labelled pixels: cropland 119,646; tree cover 96,251; water 21,010 (W3 only); grassland 17,710; bare/sparse 4,483; built-up 4,398; herbaceous wetland 2,071 (W3 only); shrubland 24.
- Under leave-one-window-out only tree cover, grassland, cropland and built-up have at least 100 pixels on both sides. Water, wetland, bare/sparse and shrubland are **not evaluable** with these windows.
- Tests: 53 passed and 2 skipped (offline unit tests plus checks on the generated outputs; the output checks need local data and skip otherwise); ruff clean.

## Limitations
- One season and year, at most two observations per pixel, three small windows. Not representative of the province or of Cambodia.
- WorldCover is a reference product with its own errors, and its global validation does not establish accuracy in Cambodia. Model agreement with it is not independent accuracy.
- The SCL mask appears to flag bright dry bare fields as cloud (W2, 2.1% of pixels unobserved) and a river bank as shadow (W3); it is not independently validated.
- W1 mixes processing baselines 05.00 and 02.14 and its two dates differ strongly (NDVI correlation 0.73).
- The offset decision for baseline 02.14 scenes rests mainly on the ESA definition and consistent metadata; the paired test covers one window and date.
- The exact warped-versus-native read test was done for W1 only.
- Cropland is not rice. No rice classification or yield estimate is made or implied.
- Phase 2 and 3 network figures: only part of the transferred data was measured.

## Reproduce
```
python -m venv .venv && .venv/Scripts/python -m pip install -e . pytest ruff
.venv/Scripts/python -m pytest -q            # offline tests; output checks skip without local data
python scripts/phase2_coverage.py            # network; slow
python scripts/phase3_select_windows.py      # network
python scripts/phase3_screen_scenes.py       # network
python scripts/phase3_build_features.py      # network; caches reads under data/raw (git-ignored)
python scripts/phase3_report.py              # class report and figures
```
Imagery and generated rasters are not committed. Scene identifiers are recorded in `reports/validation/phase3_scene_screening.json`.

## Repository layout
`src/geoai/` (cog reads, indices, offset audit, validation, WorldCover), `scripts/` (phase pipelines), `tests/`,
`configs/` (windows, study area), `docs/` (data sources, validation plan), `reports/` (QC report, validation evidence, figures).

## Roadmap
Phase 4: Random Forest then XGBoost under leave-one-window-out (a fourth window with water/wetland/bare ground needs approval);
Phase 5: agricultural-monitoring module and Streamlit dashboard; Phase 6: research report and full review.

## References
- Zanaga, D. et al. (2022). ESA WorldCover 10 m 2021 v200. Zenodo. doi:10.5281/zenodo.7254221 (CC BY 4.0).
- Runfola, D. et al. (2020). geoBoundaries: A global database of political administrative boundaries. PLOS ONE 15(4): e0231866. doi:10.1371/journal.pone.0231866.
- McFeeters, S. K. (1996). The use of the Normalized Difference Water Index (NDWI) in the delineation of open water features. International Journal of Remote Sensing 17: 1425-1432. doi:10.1080/01431169608948714.
- Huete, A. et al. (2002). Overview of the radiometric and biophysical performance of the MODIS vegetation indices. Remote Sensing of Environment 83: 195-213. doi:10.1016/S0034-4257(02)00096-2.
- Copernicus Sentinel-2 data via the Element84 Earth Search STAC API (https://earth-search.aws.element84.com/v1).

Code licence: MIT (`LICENSE`). External datasets keep their own licences (table above).
