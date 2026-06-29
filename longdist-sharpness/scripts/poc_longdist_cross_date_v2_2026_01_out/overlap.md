# Cross-date overlap (v2 — sharpest-of-ISO + replicate spread)

For each (lens, f_eff, F#) shot on 2+ dates: centre top cutoff per
date (now max across all ISO variants AND all replicates), plus the
cross-date stdev of those tops as a percent of the mean.
**top_vs_median** per-date column flags whether each day's top was a
flier (≥1.10) or consistent (≈1.00).
**dist class** is the Reikan two-tier distance bucket (20×FL min for FL≥300mm, 50×FL otherwise; 100×FL = infinity-class).

| Lens | f_eff | F# | dist class | 2026-01-18 top (med, n, tvm, ISO) | 2026-01-30 top (med, n, tvm, ISO) | mean | **stdev%** | min..max |
|---|---|---|---|---|---|---|---|---|
| 300 PF + TC-14e III | 420 | F5.6 | meets Focal min, <100×FL | 0.28 (med 0.19, n 6, tvm 1.48, ISO100) | 0.31 (med 0.27, n 11, tvm 1.14, ISO1600) | 0.29 | **7.5%** | 0.28..0.31 |
| 300 PF + TC-14e III | 420 | F8 | meets Focal min, <100×FL | 0.38 (med 0.30, n 6, tvm 1.28, ISO100) | 0.36 (med 0.34, n 11, tvm 1.05, ISO1600) | 0.37 | **3.8%** | 0.36..0.38 |
| 300 PF + TC-14e III | 420 | F11 | meets Focal min, <100×FL | 0.34 (med 0.33, n 6, tvm 1.03, ISO100) | 0.39 (med 0.38, n 14, tvm 1.02, ISO1600) | 0.36 | **8.9%** | 0.34..0.39 |
| 300 PF + TC-14e III | 420 | F16 | meets Focal min, <100×FL | 0.16 (med 0.16, n 6, tvm 1.01, ISO100) | 0.41 (med 0.36, n 12, tvm 1.15, ISO1600) | 0.29 | **63.4%** | 0.16..0.41 |
| 300 PF + TC-17e II | 500 | F6.7 | meets Focal min, <100×FL | 0.25 (med 0.24, n 6, tvm 1.03, ISO100) | 0.29 (med 0.28, n 10, tvm 1.07, ISO8000) | 0.27 | **11.7%** | 0.25..0.29 |
| 300 PF + TC-17e II | 500 | F8 | meets Focal min, <100×FL | 0.38 (med 0.34, n 6, tvm 1.12, ISO100) | 0.34 (med 0.31, n 10, tvm 1.11, ISO8000) | 0.36 | **7.7%** | 0.34..0.38 |
| 300 PF + TC-17e II | 500 | F11 | meets Focal min, <100×FL | 0.41 (med 0.36, n 6, tvm 1.13, ISO100) | 0.39 (med 0.38, n 9, tvm 1.04, ISO8000) | 0.40 | **2.3%** | 0.39..0.41 |
| 300 PF + TC-17e II | 500 | F16 | meets Focal min, <100×FL | 0.32 (med 0.29, n 6, tvm 1.09, ISO100) | 0.40 (med 0.37, n 14, tvm 1.08, ISO1600) | 0.36 | **15.3%** | 0.32..0.40 |
| 300 PF bare | 300 | F4 | infinity-class | 0.25 (med 0.25, n 3, tvm 1.00, ISO100) | 0.25 (med 0.25, n 10, tvm 1.01, ISO1600) | 0.25 | **1.7%** | 0.25..0.25 |
| 300 PF bare | 300 | F5.6 | infinity-class | 0.34 (med 0.32, n 6, tvm 1.05, ISO100) | 0.40 (med 0.38, n 15, tvm 1.05, ISO8000) | 0.37 | **12.6%** | 0.34..0.40 |
| 300 PF bare | 300 | F8 | infinity-class | 0.33 (med 0.31, n 6, tvm 1.09, ISO100) | 0.39 (med 0.37, n 13, tvm 1.07, ISO1600) | 0.36 | **11.6%** | 0.33..0.39 |
| 300 PF bare | 300 | F11 | infinity-class | 0.34 (med 0.31, n 9, tvm 1.10, ISO100) | 0.39 (med 0.34, n 13, tvm 1.15, ISO1600) | 0.36 | **8.9%** | 0.34..0.39 |
| 300 PF bare | 300 | F16 | infinity-class | 0.32 (med 0.30, n 9, tvm 1.08, ISO100) | 0.37 (med 0.34, n 10, tvm 1.09, ISO1600) | 0.34 | **8.7%** | 0.32..0.37 |
| Z 100-400 bare | 350 | F5.3 | infinity-class | 0.17 (med 0.16, n 3, tvm 1.01, ISO100) | 0.18 (med 0.17, n 6, tvm 1.06, ISO1600) | 0.17 | **5.1%** | 0.17..0.18 |
| Z 100-400 bare | 350 | F5.6 | infinity-class | 0.18 (med 0.18, n 3, tvm 1.01, ISO100) | 0.17 (med 0.17, n 6, tvm 1.02, ISO8000) | 0.18 | **4.4%** | 0.17..0.18 |
| Z 100-400 bare | 350 | F8 | infinity-class | 0.16 (med 0.16, n 3, tvm 1.01, ISO100) | 0.17 (med 0.17, n 6, tvm 1.01, ISO1600) | 0.17 | **3.4%** | 0.16..0.17 |
| Z 100-400 bare | 350 | F11 | infinity-class | 0.17 (med 0.17, n 3, tvm 1.01, ISO100) | 0.17 (med 0.17, n 6, tvm 1.03, ISO1600) | 0.17 | **2.1%** | 0.17..0.17 |
| Z 100-400 bare | 350 | F16 | infinity-class | 0.17 (med 0.17, n 3, tvm 1.00, ISO100) | 0.17 (med 0.16, n 6, tvm 1.04, ISO1600) | 0.17 | **0.5%** | 0.17..0.17 |
| Z 100-400 bare | 400 | F5.6 | infinity-class | 0.16 (med 0.16, n 3, tvm 1.01, ISO100) | 0.18 (med 0.18, n 6, tvm 1.05, ISO8000) | 0.17 | **8.2%** | 0.16..0.18 |
| Z 100-400 bare | 400 | F8 | infinity-class | 0.16 (med 0.15, n 3, tvm 1.05, ISO100) | 0.19 (med 0.18, n 6, tvm 1.01, ISO8000) | 0.17 | **9.9%** | 0.16..0.19 |
| Z 100-400 bare | 400 | F11 | infinity-class | 0.15 (med 0.15, n 3, tvm 1.01, ISO100) | 0.18 (med 0.17, n 6, tvm 1.06, ISO8000) | 0.17 | **10.8%** | 0.15..0.18 |
| Z 100-400 bare | 400 | F16 | infinity-class | 0.16 (med 0.16, n 3, tvm 1.00, ISO100) | 0.17 (med 0.17, n 6, tvm 1.03, ISO8000) | 0.17 | **7.1%** | 0.16..0.17 |
