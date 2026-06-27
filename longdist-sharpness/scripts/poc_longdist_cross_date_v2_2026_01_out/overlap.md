# Cross-date overlap (v2 — sharpest-of-ISO + replicate spread)

For each (lens, f_eff, F#) shot on 2+ dates: centre top cutoff per
date (now max across all ISO variants AND all replicates), plus the
cross-date stdev of those tops as a percent of the mean.
**top_vs_median** per-date column flags whether each day's top was a
flier (≥1.10) or consistent (≈1.00).
**dist class** is the Reikan two-tier distance bucket (20×FL min for FL≥300mm, 50×FL otherwise; 100×FL = infinity-class).

| Lens | f_eff | F# | dist class | 2026-01-18 top (med, n, tvm, ISO) | 2026-01-28 top (med, n, tvm, ISO) | 2026-01-30 top (med, n, tvm, ISO) | mean | **stdev%** | min..max |
|---|---|---|---|---|---|---|---|---|---|
| 300 PF + TC-14e I | 420 | F5.6 | meets Focal min, <100×FL | — | 0.28 (med 0.27, n 3, tvm 1.03, ISO0) | 0.36 (med 0.28, n 13, tvm 1.28, ISO100) | 0.32 | **18.0%** | 0.28..0.36 |
| 300 PF + TC-14e I | 420 | F8 | meets Focal min, <100×FL | — | 0.33 (med 0.32, n 3, tvm 1.03, ISO0) | 0.40 (med 0.34, n 10, tvm 1.16, ISO1600) | 0.36 | **12.7%** | 0.33..0.40 |
| 300 PF + TC-14e I | 420 | F11 | meets Focal min, <100×FL | — | 0.33 (med 0.33, n 3, tvm 1.00, ISO0) | 0.42 (med 0.36, n 10, tvm 1.16, ISO1600) | 0.38 | **16.2%** | 0.33..0.42 |
| 300 PF + TC-14e I | 420 | F16 | meets Focal min, <100×FL | — | 0.34 (med 0.33, n 3, tvm 1.02, ISO0) | 0.41 (med 0.38, n 10, tvm 1.08, ISO1600) | 0.37 | **14.1%** | 0.34..0.41 |
| 300 PF + TC-14e III | 420 | F5.6 | meets Focal min, <100×FL | 0.28 (med 0.19, n 6, tvm 1.48, ISO100) | 0.26 (med 0.25, n 3, tvm 1.01, ISO0) | 0.31 (med 0.27, n 11, tvm 1.14, ISO1600) | 0.28 | **9.2%** | 0.26..0.31 |
| 300 PF + TC-14e III | 420 | F8 | meets Focal min, <100×FL | 0.38 (med 0.30, n 6, tvm 1.28, ISO100) | 0.30 (med 0.29, n 3, tvm 1.05, ISO0) | 0.36 (med 0.34, n 11, tvm 1.05, ISO1600) | 0.35 | **11.6%** | 0.30..0.38 |
| 300 PF + TC-14e III | 420 | F11 | meets Focal min, <100×FL | 0.34 (med 0.33, n 6, tvm 1.03, ISO100) | 0.34 (med 0.32, n 3, tvm 1.04, ISO0) | 0.39 (med 0.38, n 14, tvm 1.02, ISO1600) | 0.35 | **7.8%** | 0.34..0.39 |
| 300 PF + TC-14e III | 420 | F16 | meets Focal min, <100×FL | 0.16 (med 0.16, n 6, tvm 1.01, ISO100) | 0.30 (med 0.29, n 3, tvm 1.04, ISO0) | 0.41 (med 0.36, n 12, tvm 1.15, ISO1600) | 0.29 | **44.3%** | 0.16..0.41 |
| 300 PF + TC-17e II | 500 | F6.7 | meets Focal min, <100×FL | 0.25 (med 0.24, n 6, tvm 1.03, ISO100) | 0.24 (med 0.23, n 3, tvm 1.06, ISO0) | 0.29 (med 0.28, n 10, tvm 1.07, ISO8000) | 0.26 | **11.2%** | 0.24..0.29 |
| 300 PF + TC-17e II | 500 | F8 | meets Focal min, <100×FL | 0.38 (med 0.34, n 6, tvm 1.12, ISO100) | 0.24 (med 0.24, n 3, tvm 1.00, ISO0) | 0.34 (med 0.31, n 10, tvm 1.11, ISO8000) | 0.32 | **23.0%** | 0.24..0.38 |
| 300 PF + TC-17e II | 500 | F11 | meets Focal min, <100×FL | 0.41 (med 0.36, n 6, tvm 1.13, ISO100) | 0.41 (med 0.38, n 3, tvm 1.07, ISO0) | 0.39 (med 0.38, n 9, tvm 1.04, ISO8000) | 0.40 | **2.3%** | 0.39..0.41 |
| 300 PF + TC-17e II | 500 | F16 | meets Focal min, <100×FL | 0.32 (med 0.29, n 6, tvm 1.09, ISO100) | 0.24 (med 0.22, n 3, tvm 1.08, ISO0) | 0.40 (med 0.37, n 14, tvm 1.08, ISO1600) | 0.32 | **24.7%** | 0.24..0.40 |
| 300 PF + TC-20e III | 600 | F8 | meets Focal min, <100×FL | 0.26 (med 0.22, n 9, tvm 1.19, ISO100) | 0.29 (med 0.25, n 6, tvm 1.16, ISO0) | — | 0.28 | **8.9%** | 0.26..0.29 |
| 300 PF + TC-20e III | 600 | F11 | meets Focal min, <100×FL | 0.29 (med 0.28, n 9, tvm 1.03, ISO100) | 0.38 (med 0.29, n 6, tvm 1.28, ISO0) | — | 0.33 | **19.0%** | 0.29..0.38 |
| 300 PF + TC-20e III | 600 | F16 | meets Focal min, <100×FL | 0.30 (med 0.28, n 9, tvm 1.09, ISO100) | 0.33 (med 0.26, n 6, tvm 1.26, ISO0) | — | 0.31 | **6.1%** | 0.30..0.33 |
| 300 PF bare | 300 | F4 | infinity-class | 0.25 (med 0.25, n 3, tvm 1.00, ISO100) | 0.36 (med 0.30, n 9, tvm 1.22, ISO0) | 0.25 (med 0.25, n 10, tvm 1.01, ISO1600) | 0.29 | **22.5%** | 0.25..0.36 |
| 300 PF bare | 300 | F5.6 | infinity-class | 0.34 (med 0.32, n 6, tvm 1.05, ISO100) | 0.44 (med 0.39, n 6, tvm 1.15, ISO0) | 0.40 (med 0.38, n 15, tvm 1.05, ISO8000) | 0.39 | **14.0%** | 0.34..0.44 |
| 300 PF bare | 300 | F8 | infinity-class | 0.33 (med 0.31, n 6, tvm 1.09, ISO100) | 0.43 (med 0.38, n 6, tvm 1.12, ISO0) | 0.39 (med 0.37, n 13, tvm 1.07, ISO1600) | 0.39 | **12.5%** | 0.33..0.43 |
| 300 PF bare | 300 | F11 | infinity-class | 0.34 (med 0.31, n 9, tvm 1.10, ISO100) | 0.37 (med 0.35, n 6, tvm 1.04, ISO0) | 0.39 (med 0.34, n 13, tvm 1.15, ISO1600) | 0.36 | **6.3%** | 0.34..0.39 |
| 300 PF bare | 300 | F16 | infinity-class | 0.32 (med 0.30, n 9, tvm 1.08, ISO100) | 0.34 (med 0.34, n 6, tvm 1.01, ISO0) | 0.37 (med 0.34, n 10, tvm 1.09, ISO1600) | 0.34 | **6.2%** | 0.32..0.37 |
| Z 100-400 + Z TC-1.4x | 400 | F7.6 | infinity-class | — | 0.16 (med 0.16, n 6, tvm 1.00, ISO0) | 0.18 (med 0.18, n 6, tvm 1.02, ISO8000) | 0.17 | **8.3%** | 0.16..0.18 |
| Z 100-400 + Z TC-1.4x | 400 | F8 | infinity-class | — | 0.17 (med 0.16, n 6, tvm 1.04, ISO0) | 0.18 (med 0.18, n 6, tvm 1.02, ISO1600) | 0.18 | **6.6%** | 0.17..0.18 |
| Z 100-400 + Z TC-1.4x | 400 | F11 | infinity-class | — | 0.17 (med 0.16, n 6, tvm 1.03, ISO0) | 0.18 (med 0.18, n 6, tvm 1.02, ISO8000) | 0.17 | **5.1%** | 0.17..0.18 |
| Z 100-400 + Z TC-1.4x | 400 | F16 | infinity-class | — | 0.17 (med 0.16, n 6, tvm 1.04, ISO0) | 0.18 (med 0.17, n 6, tvm 1.04, ISO1600) | 0.17 | **5.3%** | 0.17..0.18 |
| Z 100-400 + Z TC-1.4x | 420 | F7.6 | infinity-class | — | 0.17 (med 0.17, n 3, tvm 1.00, ISO0) | 0.18 (med 0.18, n 6, tvm 1.03, ISO1600) | 0.17 | **6.8%** | 0.17..0.18 |
| Z 100-400 + Z TC-1.4x | 420 | F8 | infinity-class | — | 0.17 (med 0.17, n 3, tvm 1.01, ISO0) | 0.19 (med 0.18, n 6, tvm 1.05, ISO1600) | 0.18 | **7.0%** | 0.17..0.19 |
| Z 100-400 + Z TC-1.4x | 420 | F11 | infinity-class | — | 0.18 (med 0.17, n 3, tvm 1.03, ISO0) | 0.19 (med 0.18, n 6, tvm 1.05, ISO8000) | 0.18 | **4.1%** | 0.18..0.19 |
| Z 100-400 + Z TC-1.4x | 420 | F16 | infinity-class | — | 0.17 (med 0.16, n 3, tvm 1.05, ISO0) | 0.18 (med 0.18, n 9, tvm 1.02, ISO1600) | 0.18 | **5.5%** | 0.17..0.18 |
| Z 100-400 + Z TC-1.4x | 490 | F7.6 | infinity-class | — | 0.18 (med 0.18, n 3, tvm 1.02, ISO0) | 0.19 (med 0.17, n 6, tvm 1.13, ISO8000) | 0.18 | **3.7%** | 0.18..0.19 |
| Z 100-400 + Z TC-1.4x | 490 | F8 | infinity-class | — | 0.18 (med 0.17, n 3, tvm 1.03, ISO0) | 0.19 (med 0.17, n 6, tvm 1.11, ISO8000) | 0.18 | **2.6%** | 0.18..0.19 |
| Z 100-400 + Z TC-1.4x | 490 | F11 | infinity-class | — | 0.19 (med 0.19, n 3, tvm 1.01, ISO0) | 0.19 (med 0.18, n 6, tvm 1.06, ISO1600) | 0.19 | **0.1%** | 0.19..0.19 |
| Z 100-400 + Z TC-1.4x | 490 | F16 | infinity-class | — | 0.20 (med 0.19, n 3, tvm 1.07, ISO0) | 0.20 (med 0.18, n 6, tvm 1.08, ISO1600) | 0.20 | **1.5%** | 0.20..0.20 |
| Z 100-400 + Z TC-1.4x | 560 | F8 | infinity-class | — | 0.18 (med 0.18, n 3, tvm 1.00, ISO0) | 0.18 (med 0.17, n 10, tvm 1.06, ISO1600) | 0.18 | **1.7%** | 0.18..0.18 |
| Z 100-400 + Z TC-1.4x | 560 | F11 | infinity-class | — | 0.18 (med 0.18, n 3, tvm 1.00, ISO0) | 0.20 (med 0.19, n 6, tvm 1.05, ISO1600) | 0.19 | **8.3%** | 0.18..0.20 |
| Z 100-400 + Z TC-1.4x | 560 | F16 | infinity-class | — | 0.18 (med 0.18, n 3, tvm 1.02, ISO0) | 0.21 (med 0.18, n 7, tvm 1.15, ISO1600) | 0.19 | **8.1%** | 0.18..0.21 |
| Z 100-400 + Z TC-2.0x | 400 | F10 | infinity-class | — | 0.16 (med 0.15, n 3, tvm 1.02, ISO0) | 0.17 (med 0.17, n 6, tvm 1.04, ISO1600) | 0.16 | **5.6%** | 0.16..0.17 |
| Z 100-400 + Z TC-2.0x | 400 | F11 | infinity-class | — | 0.16 (med 0.16, n 3, tvm 1.01, ISO0) | 0.17 (med 0.16, n 9, tvm 1.04, ISO1600) | 0.17 | **3.1%** | 0.16..0.17 |
| Z 100-400 + Z TC-2.0x | 400 | F16 | infinity-class | — | 0.16 (med 0.15, n 3, tvm 1.01, ISO0) | 0.17 (med 0.16, n 7, tvm 1.08, ISO1600) | 0.16 | **5.7%** | 0.16..0.17 |
| Z 100-400 + Z TC-2.0x | 600 | F11 | infinity-class | — | 0.19 (med 0.18, n 3, tvm 1.05, ISO0) | 0.21 (med 0.18, n 14, tvm 1.13, ISO1600) | 0.20 | **5.7%** | 0.19..0.21 |
| Z 100-400 + Z TC-2.0x | 600 | F16 | infinity-class | — | 0.20 (med 0.18, n 3, tvm 1.10, ISO0) | 0.20 (med 0.19, n 15, tvm 1.07, ISO8000) | 0.20 | **0.2%** | 0.20..0.20 |
| Z 100-400 + Z TC-2.0x | 700 | F11 | infinity-class | — | 0.19 (med 0.19, n 3, tvm 1.01, ISO0) | 0.18 (med 0.17, n 14, tvm 1.08, ISO1600) | 0.19 | **6.2%** | 0.18..0.19 |
| Z 100-400 + Z TC-2.0x | 700 | F16 | infinity-class | — | 0.19 (med 0.18, n 3, tvm 1.03, ISO0) | 0.19 (med 0.16, n 12, tvm 1.15, ISO8000) | 0.19 | **0.2%** | 0.19..0.19 |
| Z 100-400 + Z TC-2.0x | 800 | F11 | infinity-class | — | 0.20 (med 0.19, n 9, tvm 1.05, ISO0) | 0.19 (med 0.17, n 20, tvm 1.10, ISO1600) | 0.19 | **6.0%** | 0.19..0.20 |
| Z 100-400 + Z TC-2.0x | 800 | F16 | infinity-class | — | 0.20 (med 0.18, n 6, tvm 1.08, ISO0) | 0.18 (med 0.17, n 13, tvm 1.10, ISO8000) | 0.19 | **5.7%** | 0.18..0.20 |
| Z 100-400 bare | 200 | F5 | well past infinity | 0.14 (med 0.14, n 3, tvm 1.00, ISO100) | 0.15 (med 0.15, n 3, tvm 1.01, ISO0) | — | 0.15 | **4.2%** | 0.14..0.15 |
| Z 100-400 bare | 200 | F5.6 | well past infinity | 0.14 (med 0.14, n 3, tvm 1.00, ISO100) | 0.15 (med 0.15, n 3, tvm 1.05, ISO0) | — | 0.15 | **5.3%** | 0.14..0.15 |
| Z 100-400 bare | 200 | F8 | well past infinity | 0.14 (med 0.13, n 4, tvm 1.02, ISO100) | 0.15 (med 0.15, n 3, tvm 1.05, ISO0) | — | 0.14 | **7.1%** | 0.14..0.15 |
| Z 100-400 bare | 200 | F11 | well past infinity | 0.14 (med 0.14, n 3, tvm 1.00, ISO100) | 0.15 (med 0.15, n 3, tvm 1.00, ISO0) | — | 0.14 | **5.0%** | 0.14..0.15 |
| Z 100-400 bare | 200 | F16 | well past infinity | 0.13 (med 0.13, n 3, tvm 1.01, ISO100) | 0.15 (med 0.15, n 3, tvm 1.02, ISO0) | — | 0.14 | **8.8%** | 0.13..0.15 |
| Z 100-400 bare | 300 | F5.3 | infinity-class | 0.19 (med 0.19, n 3, tvm 1.01, ISO100) | 0.18 (med 0.18, n 3, tvm 1.00, ISO0) | — | 0.18 | **4.2%** | 0.18..0.19 |
| Z 100-400 bare | 300 | F5.6 | infinity-class | 0.17 (med 0.17, n 3, tvm 1.00, ISO100) | 0.18 (med 0.17, n 3, tvm 1.02, ISO0) | — | 0.17 | **2.4%** | 0.17..0.18 |
| Z 100-400 bare | 300 | F8 | infinity-class | 0.15 (med 0.15, n 3, tvm 1.01, ISO100) | 0.17 (med 0.16, n 3, tvm 1.02, ISO0) | — | 0.16 | **7.3%** | 0.15..0.17 |
| Z 100-400 bare | 300 | F11 | infinity-class | 0.15 (med 0.15, n 3, tvm 1.01, ISO100) | 0.17 (med 0.17, n 3, tvm 1.02, ISO0) | — | 0.16 | **6.6%** | 0.15..0.17 |
| Z 100-400 bare | 300 | F16 | infinity-class | 0.15 (med 0.15, n 3, tvm 1.00, ISO100) | 0.16 (med 0.16, n 3, tvm 1.04, ISO0) | — | 0.16 | **4.5%** | 0.15..0.16 |
| Z 100-400 bare | 350 | F5.3 | infinity-class | 0.17 (med 0.16, n 3, tvm 1.01, ISO100) | 0.17 (med 0.16, n 3, tvm 1.07, ISO0) | 0.18 (med 0.17, n 6, tvm 1.06, ISO1600) | 0.17 | **3.6%** | 0.17..0.18 |
| Z 100-400 bare | 350 | F5.6 | infinity-class | 0.18 (med 0.18, n 3, tvm 1.01, ISO100) | 0.17 (med 0.16, n 3, tvm 1.08, ISO0) | 0.17 (med 0.17, n 6, tvm 1.02, ISO8000) | 0.17 | **3.4%** | 0.17..0.18 |
| Z 100-400 bare | 350 | F8 | infinity-class | 0.16 (med 0.16, n 3, tvm 1.01, ISO100) | 0.17 (med 0.17, n 3, tvm 1.01, ISO0) | 0.17 (med 0.17, n 6, tvm 1.01, ISO1600) | 0.17 | **2.5%** | 0.16..0.17 |
| Z 100-400 bare | 350 | F11 | infinity-class | 0.17 (med 0.17, n 3, tvm 1.01, ISO100) | 0.17 (med 0.16, n 2, tvm 1.02, ISO0) | 0.17 (med 0.17, n 6, tvm 1.03, ISO1600) | 0.17 | **2.1%** | 0.17..0.17 |
| Z 100-400 bare | 350 | F16 | infinity-class | 0.17 (med 0.17, n 3, tvm 1.00, ISO100) | 0.16 (med 0.16, n 3, tvm 1.03, ISO0) | 0.17 (med 0.16, n 6, tvm 1.04, ISO1600) | 0.17 | **1.4%** | 0.16..0.17 |
| Z 100-400 bare | 400 | F5.6 | infinity-class | 0.16 (med 0.16, n 3, tvm 1.01, ISO100) | 0.17 (med 0.17, n 3, tvm 1.02, ISO0) | 0.18 (med 0.18, n 6, tvm 1.05, ISO8000) | 0.17 | **6.0%** | 0.16..0.18 |
| Z 100-400 bare | 400 | F8 | infinity-class | 0.16 (med 0.15, n 3, tvm 1.05, ISO100) | 0.17 (med 0.17, n 3, tvm 1.01, ISO0) | 0.19 (med 0.18, n 6, tvm 1.01, ISO8000) | 0.17 | **7.4%** | 0.16..0.19 |
| Z 100-400 bare | 400 | F11 | infinity-class | 0.15 (med 0.15, n 3, tvm 1.01, ISO100) | 0.17 (med 0.16, n 3, tvm 1.08, ISO0) | 0.18 (med 0.17, n 6, tvm 1.06, ISO8000) | 0.17 | **8.0%** | 0.15..0.18 |
| Z 100-400 bare | 400 | F16 | infinity-class | 0.16 (med 0.16, n 3, tvm 1.00, ISO100) | 0.16 (med 0.16, n 3, tvm 1.01, ISO0) | 0.17 (med 0.17, n 6, tvm 1.03, ISO8000) | 0.17 | **5.2%** | 0.16..0.17 |
