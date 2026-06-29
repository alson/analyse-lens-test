# Cross-family edge comparison — best centre-aperture per combo (2026-01-30, CLEAN)

Re-derivation of the old 2026-01-28 §6 tables on a clean date. 2026-01-28 is excluded (session-wide ISO 8000, low-SNR — see `LONGDIST_TELE_RESULTS.md` §3). Field-position cutoffs sourced from `poc_longdist_cross_date_v2_2026_01_out/per_date_2026-01-30.csv` (`top` statistic = max across pooled replicates / ISO variants).

Each row: cutoff at x=0.18 / centre (x=0.50) / x=0.82, at the aperture that maximises the centre cutoff. `cy/mm-subj` shares this date's shooting distance per family; `FOM = sensor cy/px × f_eff = cutoff_subj × pitch × distance` is the distance-fair figure of merit.

## cy/mm-subject (within-family interpretation)

| Combo | f_eff | F# | x=0.18 | centre | x=0.82 | edge / centre |
|---|---|---|---|---|---|---|
| Z 100-400 bare 400mm | 400mm | F8 | 0.16 | **0.19** | 0.17 | 0.90 |
| Z 100-400 + Z TC-1.4x 560mm | 560mm | F16 | 0.19 | **0.21** | 0.20 | 0.95 |
| Z 100-400 + Z TC-2.0x 800mm | 800mm | F11 | 0.19 | **0.19** | 0.17 | 1.00 |
| 300 PF bare 300mm | 300mm | F5.6 | 0.28 | **0.40** | 0.33 | 0.76 |
| 300 PF + TC-14e I 420mm | 420mm | F11 | 0.41 | **0.42** | 0.26 | 0.79 |
| 300 PF + TC-14e III 420mm | 420mm | F16 | 0.41 | **0.41** | 0.28 | 0.83 |
| 300 PF + TC-17e II 500mm | 500mm | F16 | 0.35 | **0.40** | 0.27 | 0.78 |
| 300 PF + Kenko Pro 300 1.4x 420mm | 420mm | F11 | 0.41 | **0.44** | 0.27 | 0.76 |

## FOM = sensor cy/px × f_eff (cross-family, distance-fair)

| Combo | f_eff | F# | x=0.18 | centre | x=0.82 | edge / centre |
|---|---|---|---|---|---|---|
| Z 100-400 bare 400mm | 400mm | F8 | 59 | **68** | 63 | 0.90 |
| Z 100-400 + Z TC-1.4x 560mm | 560mm | F16 | 69 | **75** | 74 | 0.95 |
| Z 100-400 + Z TC-2.0x 800mm | 800mm | F11 | 71 | **68** | 64 | 1.00 |
| 300 PF bare 300mm | 300mm | F5.6 | 39 | **55** | 45 | 0.76 |
| 300 PF + TC-14e I 420mm | 420mm | F11 | 56 | **58** | 36 | 0.79 |
| 300 PF + TC-14e III 420mm | 420mm | F16 | 57 | **57** | 38 | 0.83 |
| 300 PF + TC-17e II 500mm | 500mm | F16 | 48 | **55** | 38 | 0.78 |
| 300 PF + Kenko Pro 300 1.4x 420mm | 420mm | F11 | 56 | **61** | 37 | 0.76 |
