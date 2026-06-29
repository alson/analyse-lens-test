# §6a / §6b / §6c — CLEAN re-derivation (old→new)

Old numbers were all from 2026-01-28 (now excluded as session-wide
ISO-8000 low-SNR). New numbers re-derived within a single clean date.

## §6a — TC vs cropping the bare 400 mm frame (Z 100-400 family, 2026-01-30)

Bare-400 centre cutoff is the cropping ceiling (crop+upsample adds no
information). Compared against the Z TCs at their native effective FL.

| Comparison (84 m) | bare-cropped ceiling | TC chain centre | gain |
|---|---|---|---|
| 560 mm effective | 0.19 (bare 400 F8) | 0.21 (TC-1.4× F16) | **+11%** |
| 800 mm effective | 0.19 (bare 400 F8) | 0.19 (TC-2.0× F11) | **-0%** |

OLD (2026-01-28): TC-1.4× **+24%**, TC-2.0× **+65%**.

## §6b — FOM ranking at each combo's best-centre aperture

Sorted by FOM (= sensor cy/px × f_eff). Within-date only; the Z 100-400
family + F-mount-TC families are all on 2026-01-30; TC-20e III is on
2026-01-18 (kept on its own date, distances differ so FOM is the fair
cross-family number but absolute level is not cross-date-comparable).

| FOM | Combo | f_eff | F# | date |
|---|---|---|---|---|
| 75 | Z 100-400 + Z TC-1.4x 560mm | 560mm | F16 | 2026-01-30 |
| 68 | Z 100-400 bare 400mm | 400mm | F8 | 2026-01-30 |
| 68 | Z 100-400 + Z TC-2.0x 800mm | 800mm | F11 | 2026-01-30 |
| 61 | 300 PF + Kenko Pro 300 1.4x 420mm | 420mm | F11 | 2026-01-30 |
| 60 | Z 100-400 bare 400mm | 400mm | F5.6 | 2026-01-18 |
| 58 | 300 PF + TC-14e I 420mm | 420mm | F11 | 2026-01-30 |
| 57 | 300 PF + TC-14e III 420mm | 420mm | F16 | 2026-01-30 |
| 56 | 300 PF + TC-17e II 500mm | 500mm | F11 | 2026-01-18 |
| 55 | 300 PF bare 300mm | 300mm | F5.6 | 2026-01-30 |
| 55 | 300 PF + TC-17e II 500mm | 500mm | F16 | 2026-01-30 |
| 52 | 300 PF + TC-14e III 420mm | 420mm | F8 | 2026-01-18 |
| 47 | 300 PF bare 300mm | 300mm | F11 | 2026-01-18 |
| 41 | 300 PF + TC-20e III 600mm | 600mm | F22 | 2026-01-18 |

OLD (2026-01-28): Z 100-400 + Z TC-2.0× @ 800 f/11 dominated (FOM 103);
every F-mount TC on the 300 PF net-negative vs bare; Kenko competitive.

## §6c — edge / centre per combo (best-centre aperture)

| Combo | date | F# | edge/centre (cy/mm) | edge/centre (FOM) |
|---|---|---|---|---|
| Z 100-400 bare 400mm | 2026-01-30 | F8 | 0.90 | 0.90 |
| Z 100-400 + Z TC-1.4x 560mm | 2026-01-30 | F16 | 0.95 | 0.95 |
| Z 100-400 + Z TC-2.0x 800mm | 2026-01-30 | F11 | 1.00 | 1.00 |
| 300 PF bare 300mm | 2026-01-30 | F5.6 | 0.76 | 0.76 |
| 300 PF + TC-14e I 420mm | 2026-01-30 | F11 | 0.79 | 0.79 |
| 300 PF + TC-14e III 420mm | 2026-01-30 | F16 | 0.83 | 0.83 |
| 300 PF + TC-17e II 500mm | 2026-01-30 | F16 | 0.78 | 0.78 |
| 300 PF + Kenko Pro 300 1.4x 420mm | 2026-01-30 | F11 | 0.76 | 0.76 |
| 300 PF bare 300mm | 2026-01-18 | F11 | 0.96 | 0.96 |
| 300 PF + TC-14e III 420mm | 2026-01-18 | F8 | 0.83 | 0.83 |
| 300 PF + TC-17e II 500mm | 2026-01-18 | F11 | 0.80 | 0.80 |
| 300 PF + TC-20e III 600mm | 2026-01-18 | F22 | 1.18 | 1.18 |
| Z 100-400 bare 400mm | 2026-01-18 | F5.6 | 0.94 | 0.94 |

OLD (2026-01-28): Z family flat 1.05–1.12; 300 PF bare 0.60;
**300 PF + TC-20e III = 1.24** (the anomaly).

NOTE on the TC-20e III anomaly: it is sourced clean from 2026-01-18
ISO 100 here (TC-20e III was sold before 2026-01-30). The edge>centre
pattern PERSISTS on clean data (see table) — so it is NOT a 2026-01-28
low-SNR artefact. It is the 'pick-the-sharpest-tile on a 3D scene'
protocol artefact combined with the TC-20e III's genuinely soft on-axis
delivery: the centre cutoff is consistently the lowest of the 5 slices.
