# Cross-family edge comparison — best centre-aperture per combo (2026-01-18, CLEAN)

Re-derivation of the old 2026-01-28 §6 tables on a clean date. 2026-01-28 is excluded (session-wide ISO 8000, low-SNR — see `LONGDIST_TELE_RESULTS.md` §3). Field-position cutoffs sourced from `poc_longdist_cross_date_v2_2026_01_out/per_date_2026-01-18.csv` (`top` statistic = max across pooled replicates / ISO variants).

Each row: cutoff at x=0.18 / centre (x=0.50) / x=0.82, at the aperture that maximises the centre cutoff. `cy/mm-subj` shares this date's shooting distance per family; `FOM = sensor cy/px × f_eff = cutoff_subj × pitch × distance` is the distance-fair figure of merit.

## cy/mm-subject (within-family interpretation)

| Combo | f_eff | F# | x=0.18 | centre | x=0.82 | edge / centre |
|---|---|---|---|---|---|---|
| 300 PF bare 300mm | 300mm | F11 | 0.35 | **0.34** | 0.31 | 0.96 |
| 300 PF + TC-14e III 420mm | 420mm | F8 | 0.34 | **0.38** | 0.29 | 0.83 |
| 300 PF + TC-17e II 500mm | 500mm | F11 | 0.31 | **0.41** | 0.33 | 0.80 |
| 300 PF + TC-20e III 600mm | 600mm | F22 | 0.34 | **0.30** | 0.38 | 1.18 |
| Z 100-400 bare 400mm | 400mm | F5.6 | 0.15 | **0.16** | 0.15 | 0.94 |

## FOM = sensor cy/px × f_eff (cross-family, distance-fair)

| Combo | f_eff | F# | x=0.18 | centre | x=0.82 | edge / centre |
|---|---|---|---|---|---|---|
| 300 PF bare 300mm | 300mm | F11 | 48 | **47** | 42 | 0.96 |
| 300 PF + TC-14e III 420mm | 420mm | F8 | 47 | **52** | 40 | 0.83 |
| 300 PF + TC-17e II 500mm | 500mm | F11 | 43 | **56** | 45 | 0.80 |
| 300 PF + TC-20e III 600mm | 600mm | F22 | 46 | **41** | 52 | 1.18 |
| Z 100-400 bare 400mm | 400mm | F5.6 | 56 | **60** | 56 | 0.94 |
