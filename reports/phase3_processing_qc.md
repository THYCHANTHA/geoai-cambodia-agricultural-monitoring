# Phase 3 processing and quality-control report

Study area: Kampong Cham Province (geoBoundaries ADM1 KH-3). Imagery: Sentinel-2 L2A COGs via Element84
Earth Search, 2021-01-01 to 2021-03-31 (dry season). Labels: ESA WorldCover 2021 v200 (proxy labels, not
independently verified ground truth). All numbers come from `reports/validation/phase3_*.json` (executed runs).

## Windows and scenes
| Window | Centre (E, N) | Role | Scenes (processing baseline) | Observations per pixel 0 / 1 / 2 | Composite valid |
|---|---|---|---|---|---|
| W1 | 105.3000, 12.2000 | pilot; tree cover 75%, cropland 19% | 2021-02-19 (05.00, Phase 2 cache), 2021-01-05 (02.14) | 0.17 / 1.80 / 98.03 % | 99.83 % |
| W2 | 105.3805, 12.2761 | cropland-dominant (WorldCover 97%) | 2021-01-10 (02.14), 2021-02-19 (02.14) | 2.11 / 4.46 / 93.43 % | 97.89 % |
| W3 | 105.4306, 11.9550 | mixed: tree 31%, cropland 19%, water 24%, grassland 13%, wetland, built-up, bare | 2021-01-15 (02.14), 2021-02-19 (02.14) | 2.62 / 9.74 / 87.65 % | 97.38 % |

Selection: windows 2 and 3 were chosen from a 100 m WorldCover scan of the whole province (15,698 candidate 3 km
windows lying inside it), then re-measured at 10 m. They are at least 10 km from W1 and from each other. Scenes were
chosen by the AOI-level clear-pixel share of the SCL layer (not whole-tile cloud percentage); the second scene is at
least 5 days from the first. One item per (tile, date) was screened (lowest baseline). Six window-scene combinations
were used (limit 6).

## Method
- Reads: remote COG windows on a 10 m grid snapped to the Sentinel-2 grid. B02, B03, B04, B08 are native 10 m.
  B11 and SCL are native 20 m and were **replicated to 10 m by nearest neighbour, with no interpolation and no added detail**.
- Mask: SCL classes 4, 5, 6 are kept. Cloud shadow (3), medium/high cloud (8, 9) and cirrus (10) are dilated by 2 px
  (20 m). Dark, saturated, unclassified (7) and snow pixels are removed.
- Composite: per-pixel median of masked reflectance (with two observations this equals the mean; a single observation
  is used as is). Indices are computed from the composite reflectance.

## Reflectance offset verification
Earth Search metadata is contradictory for baseline 05.00 items: the asset lists `offset -0.1`, the item has
`boa_offset_applied: true`, and Element84 documentation says a non-zero asset offset should be applied. The decision
was therefore taken from evidence, not from NDVI plausibility:

1. **Paired-baseline test** (`reports/validation/offset_audit_pair_20210219.json`): the same acquisition (2021-02-19) in
   baseline 02.14 (no offset by ESA definition) and baseline 05.00, same W1 grid, red band, 90,000 pixels. Median DN
   difference (05.00 minus 02.14) is **-8**; an offset in the 05.00 values would give about +1000. Pearson r 0.965.
   The decision rule was written before the run.
2. **Per-scene DN audit** (`geoai.offset.audit_scene`, results in `phase3_build.json`): the 5th percentile of clear red DN is
   below 800 in all six scenes (range 151 to 771), so no +1000 offset is present. The metadata offset was applied to
   **none** of the scenes.
3. Five scenes are baseline 02.14 (ESA defines no offset; metadata offset is 0, consistent). Only the Phase 2 scene
   (W1, 2021-02-19) is baseline 05.00 and carries the metadata conflict (`metadata_conflict: true`).

Caveats: the paired test covers one window and one date. In W2 on 2021-02-19 the 5th percentile is 771, close to the 800
threshold (bright bare fields), so for the baseline 02.14 scenes the decision rests mainly on the ESA definition and the
consistent metadata, with the DN rule as a consistency check. The audit refuses to process a scene whose DN fit neither
pattern; this is covered by regression tests (`tests/test_offset.py`).

## Index results (composite value ranges, valid pixels)
| Window | NDVI | EVI | NDWI | NDBI |
|---|---|---|---|---|
| W1 | -0.126 to 0.892 | -0.039 to 0.735 | -0.792 to 0.186 | -0.464 to 0.402 |
| W2 | -0.047 to 0.789 | -0.030 to 0.635 | -0.701 to -0.026 | -0.499 to 0.407 |
| W3 | -0.589 to 0.840 | -0.138 to 0.783 | -0.750 to 0.718 | -0.690 to 0.645 |

All values lie within [-1, 1] (tested). The indices are not crop yield or rice measures, and NDBI is confounded by dry
bare soil in this season.

## Quality-control findings
- **Temporal consistency** (pixels clear on both dates), median absolute dNDVI: W1 0.064 (r 0.73), W2 0.026 (r 0.91),
  W3 0.049 (r 0.93). W1 is the weakest: large change between 2021-01-05 and 2021-02-19 (95th percentile 0.33) and two
  processing baselines are mixed there. A two-date composite there averages different land states.
- **Mask false positives:** in W2, large masked patches lie over plain dry fields with no visible cloud, which suggests
  the SCL flags bright bare soil as cloud. In W3 a thin masked line follows the river bank (water edge flagged as shadow).
  The cropland window is the most affected (2.1% unobserved), so masked pixels are not random.
- **Label and image alignment:** WorldCover water in W3 coincides with the dark channel in false colour and the NDWI
  maximum, and the test "water NDWI exceeds cropland and tree NDWI by 0.2" passes. WorldCover labels the exposed sandbar partly
  as water or bare ground, because its label year and season differ from the imagery. The labels are noisy proxies.
- **Alignment evidence:** grid origins are multiples of 10 m (the Sentinel-2 grid). The warped read was identical to a native
  window read for W1 (Phase 2). That exact-equality test was **not repeated for W2 and W3** because it needs extra downloads;
  there, alignment is supported structurally and by the label/NDWI consistency test only.
- **Class coverage** (`reports/validation/phase3_class_distribution.json`, `docs/validation_plan.md`): shrubland, bare/sparse,
  water and wetland cannot be evaluated under leave-one-window-out. Mangroves, moss/lichen and snow/ice are absent from all windows.

## Limitations
One season and year; at most two observations per pixel; three small windows (27 km2 in total) that do not represent the
province; WorldCover proxy labels; SCL masking not independently validated; processing baselines mixed in W1; SWIR is 20 m native.
