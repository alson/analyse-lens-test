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
| wide2026_01_24 | 4332 | 0.145 | 0.613 | 0.108 | 0.141 | 131.133 | 0.372 | 0.271 | 0.52 | -0.013 | 99 |
| wide2026_01_26 | 4719 | 0.107 | 0.715 | 0.054 | 0.113 | 167.853 | 0.398 | 0.28 | 0.509 | 0.287 | 100 |
| wide2026_02_07 | 2139 | 0.094 | 0.477 | 0.111 | 0.153 | 72.736 | 0.422 | 0.018 | 0.425 | -0.112 | 52 |
| wide2025_09_10 | 6951 | 0.096 | 0.481 | 0.102 | 0.148 | 75.028 | 0.399 | 0.093 | 0.373 | 0.088 | 231 |
| mid2025_09_11 | 10338 | 0.192 | 0.381 | 0.143 | 0.182 | 120.608 | 0.363 | 0.093 | 0.338 | 0.071 | 231 |
