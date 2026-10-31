# Data sources and licences (read from the publishers' pages on 2026-10-31)

| Data | Access used | Licence / terms as stated by the publisher | Required attribution |
|---|---|---|---|
| Sentinel-2 L2A COGs | Element84 Earth Search STAC v1 (`sentinel-cogs` public bucket) | AWS Open Data registry: "Access to Sentinel data is free, full and open" (Copernicus terms) | "Contains modified Copernicus Sentinel data [year]" |
| ESA WorldCover 2021 v200 | public bucket (HTTPS) | Publisher (esa-worldcover.org/en/data-access) and AWS registry: CC BY 4.0; "free of charge, without restriction of use" | "(c) ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium"; cite Zanaga et al. 2022, doi:10.5281/zenodo.7254221 (Zenodo record, v200, CC BY 4.0) |
| geoBoundaries KHM ADM1 / ADM2 | geoBoundaries API (gbOpen) | API reports ODbL 1.0 for ADM1 (source OpenStreetMap, year 2017) and CC BY 4.0 for ADM2 (year 2014) | geoBoundaries + source credits |
| Copernicus Data Space STAC | search tested only | not used for data yet | n/a |

Notes
- The Copernicus legal notice page was fetched but no licence sentence could be extracted automatically; the Sentinel wording above is taken from the AWS registry page. Re-read it before publication.
- WorldCover is a reference product. Its global validation figures do not establish accuracy in Cambodia. Model agreement with it is not independent accuracy.
- Not used: Google Earth Engine, Dynamic World (owner decision, 2026-10-31).
- Earth Search COGs: the asset metadata lists scale 0.0001 and offset -0.1, but the DN of the two scenes inspected contain no +1000 offset (see `reports/validation/superseded_phase2_window_kc_b_metadata_offset_applied.json`). Only the scale is applied, with a runtime guard.
