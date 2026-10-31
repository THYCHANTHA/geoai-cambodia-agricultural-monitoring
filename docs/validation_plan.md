# Spatial validation plan (prepared in Phase 3; no model has been trained)

Labels are ESA WorldCover 2021 v200 proxy labels. Any later score is **agreement with WorldCover on
held-out windows**, not independently verified land-cover accuracy.

## Design
- Three windows (3 km x 3 km, EPSG:32648) in Kampong Cham, 12.1 / 30.6 / 35.9 km apart: W1 (pilot, tree-cover
  dominant), W2 (cropland-dominant), W3 (mixed, 7 WorldCover classes). They are far apart relative to the
  3 km window size, so a held-out window shares no neighbouring pixels with the training data.
- **Primary scheme: leave-one-window-out (LOWO)**, implemented in `geoai.validation.leave_one_window_out`
  (asserts that no window or 500 m block is shared between train and test).
- 500 m blocks (`block` column, 36 per window) are for diagnostics and for any later within-window block
  cross-validation, which must use whole blocks with a buffer. Random pixel splits must not be reported as
  spatial validation.

## What LOWO can evaluate
A class is "evaluable" when it has at least 100 pixels both in the held-out window and in the other two windows.

| Class | W1 held out | W2 held out | W3 held out |
|---|---|---|---|
| Tree cover, Grassland, Cropland, Built-up | yes | yes | yes |
| Shrubland (24 px, W1 only) | no | no | no |
| Bare/sparse vegetation (39 / 6 / 4,438 px in W1 / W2 / W3) | no | no | no (training side has 45) |
| Permanent water bodies (W3 only, 21,010 px) | no | no | no |
| Herbaceous wetland (W3 only, 2,071 px) | no | no | no |
| Mangroves, Moss and lichen, Snow and ice | absent from all windows | | |

Consequences: water, wetland, bare/sparse vegetation and shrubland cannot be learned from one window and
tested on another with the present sample. They must be reported as "not evaluable" and never imputed or
synthesised. A fourth window containing water, wetland and bare ground would change this; it needs approval
because the agreed limit is three windows.

## Metrics to report later
Macro F1 (over evaluable classes only), per-class precision and recall, balanced accuracy, confusion matrix,
IoU and Cohen's kappa, per fold and pooled, together with the class-imbalance table. Fold scores are expected
to differ strongly (W2 is 97% cropland), so report them individually, not only their mean.

## Known risks
- Label noise: WorldCover has its own 10 m classification errors, and its compositing period differs from the
  January to March 2021 imagery.
- Only three folds, so no meaningful confidence intervals across folds. Pixel counts overstate the effective
  sample size because neighbouring pixels are strongly autocorrelated.
