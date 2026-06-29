# `mtf50_known_edge` vs `mtf50_slanted_edge` (auto-detect) comparison

Per-dataset summary of the §5.1 known-edge MTF50 follow-up.

- `*_nan_rate`: fraction of attempted measurements that returned NaN.
- `ke_cv_median`: median coefficient of variation across replicates per
  (lens, FL, aperture, edge). Lower = more stable.
- `auto_range_pct_mean`: mean (max-min)/median × 100 across replicates.
  Approximately 2×CV for n=3 replicates.
- `spearman_*_vs_radial`: ranking agreement with `radial_cutoff` over
  (lens, FL, aperture). Higher = the new metric ranks lenses similarly.

| dataset | ke_rows | ke_nan_rate | auto_nan_rate | ke_cv_median | ke_cv_mean | auto_range_pct_mean | ke_median_mtf50 | auto_median_mtf50 | spearman_ke_vs_radial | spearman_auto_vs_radial | compared_configs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| wide2026_01_24 | 4476 | 0.145 | 0.6 | 0.027 | 0.053 | 131.133 | 0.306 | 0.271 | 0.82 | 0.014 | 99 |
| wide2026_01_26 | 4683 | 0.134 | 0.699 | 0.022 | 0.046 | 167.853 | 0.314 | 0.28 | 0.693 | 0.3 | 100 |
| wide2026_02_07 | 2160 | 0.118 | 0.393 | 0.05 | 0.075 | 72.736 | 0.346 | 0.018 | 0.622 | -0.145 | 52 |
| wide2025_09_10 | 6616 | 0.085 | 0.339 | 0.045 | 0.073 | 75.028 | 0.273 | 0.093 | 0.496 | 0.229 | 231 |
| mid2025_09_11 | 10332 | 0.162 | 0.193 | 0.062 | 0.094 | 120.608 | 0.273 | 0.093 | 0.543 | 0.043 | 227 |
