# Algorithm comparison — tele2025_07_09

Discovered 398 configs, generated 6960 per-(algorithm, cell) measurements.
Consensus tile selection uses cross-replicate median-gradient
(rejects moving content like cyclists/pedestrians).

## Stability per algorithm (replicate spread)

Per cell, CV = (top - min) / median * 100. Lower = the algorithm
returns consistent values across the burst of replicates.

| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |
|---|---|---|---|---|
| radial_cutoff | 3.2% | 10.4% | 1889 | (cells absent if algorithm returned NaN) |
| mtf50_slanted_edge | 25.4% | 200.7% | 1091 | (cells absent if algorithm returned NaN) |
| vol | 12.4% | 38.7% | 1990 | (cells absent if algorithm returned NaN) |
| brenner | 8.8% | 27.2% | 1990 | (cells absent if algorithm returned NaN) |

## Cross-algorithm rank agreement (Spearman ρ on `top`)

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.13 | 0.78 | 0.67 |
| mtf50_slanted_edge | 0.13 | 1.00 | 0.21 | 0.20 |
| vol | 0.78 | 0.21 | 1.00 | 0.97 |
| brenner | 0.67 | 0.20 | 0.97 | 1.00 |

## Pearson linear correlation

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.10 | 0.71 | 0.64 |
| mtf50_slanted_edge | 0.10 | 1.00 | 0.14 | 0.16 |
| vol | 0.71 | 0.14 | 1.00 | 0.96 |
| brenner | 0.64 | 0.16 | 0.96 | 1.00 |

## Lighting-robustness probe (one reference sharp tile)

Reference: Nikon AF-S VR Zoom-Nikkor 70-200mm f_2.8G IF-ED 135.0mm F8 x=0.34

| Transform | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| baseline | 0.294 (+0%) | — | 1899.824 (+0%) | 2030.145 (+0%) |
| brightness -0.5EV | 0.294 (-0%) | — | 949.625 (-50%) | 1014.766 (-50%) |
| brightness +0.5EV | 0.282 (-4%) | — | 3047.903 (+60%) | 3132.355 (+54%) |
| brightness -1.0EV | 0.294 (+0%) | — | 474.956 (-75%) | 507.536 (-75%) |
| brightness +1.0EV | 0.307 (+5%) | — | 1748.255 (-8%) | 1399.893 (-31%) |
| contrast x0.7 | 0.294 (+0%) | — | 930.914 (-51%) | 994.771 (-51%) |
| contrast x1.3 | 0.293 (-0%) | — | 3173.576 (+67%) | 3389.337 (+67%) |
| gamma 0.7 | 0.291 (-1%) | 0.361 (+nan%) | 1313.311 (-31%) | 1415.459 (-30%) |
| gamma 1.3 | 0.296 (+1%) | — | 2321.841 (+22%) | 2451.901 (+21%) |

## Movement detection (cross-replicate position-disagreement)

- 254 cells flagged as having moving content
  (replicate tile positions disagreed by > 2 search steps).
- Affected (lens, FL, aperture, position) — top 10:
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 135mm | F11 | x=0.34
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 180mm | F11 | x=0.18
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 70mm | F8 | x=0.34
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x | 100mm | F11 | x=0.34
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x | 100mm | F11 | x=0.66
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x | 150mm | F11 | x=0.34
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x | 190mm | F7.1 | x=0.66
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + Kenko Pro 300 DG 1.4x | 250mm | F11 | x=0.34
  - Nikon AF-S Nikkor 300mm f_4D IF-ED | 300mm | F11 | x=0.18
  - Nikon AF-S Nikkor 300mm f_4D IF-ED | 300mm | F4 | x=0.18
