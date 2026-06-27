# Algorithm comparison — tele2026_02_07

Discovered 162 configs, generated 2883 per-(algorithm, cell) measurements.
Consensus tile selection uses cross-replicate median-gradient
(rejects moving content like cyclists/pedestrians).

## Stability per algorithm (replicate spread)

Per cell, CV = (top - min) / median * 100. Lower = the algorithm
returns consistent values across the burst of replicates.

| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |
|---|---|---|---|---|
| radial_cutoff | 2.4% | 8.9% | 803 | (cells absent if algorithm returned NaN) |
| mtf50_slanted_edge | 47.2% | 287.0% | 460 | (cells absent if algorithm returned NaN) |
| vol | 9.3% | 58.3% | 810 | (cells absent if algorithm returned NaN) |
| brenner | 6.0% | 39.1% | 810 | (cells absent if algorithm returned NaN) |

## Cross-algorithm rank agreement (Spearman ρ on `top`)

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.16 | 0.61 | 0.43 |
| mtf50_slanted_edge | 0.16 | 1.00 | 0.08 | 0.06 |
| vol | 0.61 | 0.08 | 1.00 | 0.95 |
| brenner | 0.43 | 0.06 | 0.95 | 1.00 |

## Pearson linear correlation

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.08 | 0.64 | 0.51 |
| mtf50_slanted_edge | 0.08 | 1.00 | 0.02 | 0.00 |
| vol | 0.64 | 0.02 | 1.00 | 0.95 |
| brenner | 0.51 | 0.00 | 0.95 | 1.00 |

## Lighting-robustness probe (one reference sharp tile)

Reference: Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED ISO500 70.0mm F8 x=0.5

| Transform | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| baseline | 0.285 (+0%) | — | 1419.620 (+0%) | 1692.533 (+0%) |
| brightness -0.5EV | 0.285 (-0%) | — | 709.596 (-50%) | 846.011 (-50%) |
| brightness +0.5EV | 0.285 (-0%) | — | 2837.812 (+100%) | 3382.957 (+100%) |
| brightness -1.0EV | 0.285 (+0%) | — | 354.905 (-75%) | 423.133 (-75%) |
| brightness +1.0EV | 0.281 (-1%) | — | 4913.962 (+246%) | 5418.035 (+220%) |
| contrast x0.7 | 0.285 (+0%) | — | 695.614 (-51%) | 829.341 (-51%) |
| contrast x1.3 | 0.285 (+0%) | — | 2399.158 (+69%) | 2860.381 (+69%) |
| gamma 0.7 | 0.282 (-1%) | — | 1247.259 (-12%) | 1502.958 (-11%) |
| gamma 1.3 | 0.288 (+1%) | — | 1369.535 (-4%) | 1609.623 (-5%) |

## Movement detection (cross-replicate position-disagreement)

- 163 cells flagged as having moving content
  (replicate tile positions disagreed by > 2 search steps).
- Affected (lens, FL, aperture, position) — top 10:
  - NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO800 | 100mm | F16 | x=0.82
  - NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO800 | 100mm | F4.5 | x=0.5
  - NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO800 | 100mm | F8 | x=0.82
  - NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO800 | 105mm | F11 | x=0.34
  - NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO800 | 105mm | F11 | x=0.82
  - NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO800 | 105mm | F8 | x=0.82
  - NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO800 | 120mm | F11 | x=0.34
  - NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO800 | 120mm | F4.5 | x=0.66
  - NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO800 | 120mm | F5.6 | x=0.5
  - NIKKOR Z 100-400mm f_4.5-5.6 VR S ISO800 | 120mm | F8 | x=0.34
