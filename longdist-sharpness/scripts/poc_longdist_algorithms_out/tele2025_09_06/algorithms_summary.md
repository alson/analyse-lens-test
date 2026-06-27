# Algorithm comparison — tele2025_09_06

Discovered 837 configs, generated 14007 per-(algorithm, cell) measurements.
Consensus tile selection uses cross-replicate median-gradient
(rejects moving content like cyclists/pedestrians).

## Stability per algorithm (replicate spread)

Per cell, CV = (top - min) / median * 100. Lower = the algorithm
returns consistent values across the burst of replicates.

| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |
|---|---|---|---|---|
| radial_cutoff | 2.7% | 7.6% | 3762 | (cells absent if algorithm returned NaN) |
| mtf50_slanted_edge | 35.4% | 201.1% | 1875 | (cells absent if algorithm returned NaN) |
| vol | 9.8% | 28.2% | 4185 | (cells absent if algorithm returned NaN) |
| brenner | 7.4% | 21.7% | 4185 | (cells absent if algorithm returned NaN) |

## Cross-algorithm rank agreement (Spearman ρ on `top`)

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.23 | 0.78 | 0.71 |
| mtf50_slanted_edge | 0.23 | 1.00 | 0.22 | 0.19 |
| vol | 0.78 | 0.22 | 1.00 | 0.98 |
| brenner | 0.71 | 0.19 | 0.98 | 1.00 |

## Pearson linear correlation

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.21 | 0.74 | 0.70 |
| mtf50_slanted_edge | 0.21 | 1.00 | 0.19 | 0.18 |
| vol | 0.74 | 0.19 | 1.00 | 0.97 |
| brenner | 0.70 | 0.18 | 0.97 | 1.00 |

## Lighting-robustness probe (one reference sharp tile)

Reference: Nikon AF Nikkor 50mm f_1.8 50.0mm F8 x=0.82

| Transform | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| baseline | 0.261 (+0%) | 0.099 (+0%) | 631.837 (+0%) | 858.829 (+0%) |
| brightness -0.5EV | 0.261 (+0%) | 0.099 (-0%) | 315.823 (-50%) | 429.285 (-50%) |
| brightness +0.5EV | 0.260 (-0%) | 0.099 (-0%) | 1259.386 (+99%) | 1708.950 (+99%) |
| brightness -1.0EV | 0.261 (+0%) | 0.099 (+0%) | 157.959 (-75%) | 214.707 (-75%) |
| brightness +1.0EV | 0.232 (-11%) | 0.035 (-64%) | 1639.124 (+159%) | 2212.958 (+158%) |
| contrast x0.7 | 0.261 (+0%) | 0.099 (-0%) | 309.600 (-51%) | 420.826 (-51%) |
| contrast x1.3 | 0.261 (-0%) | 0.099 (-0%) | 1067.804 (+69%) | 1451.420 (+69%) |
| gamma 0.7 | 0.254 (-3%) | 0.362 (+267%) | 515.262 (-18%) | 719.110 (-16%) |
| gamma 1.3 | 0.271 (+4%) | 0.326 (+231%) | 654.046 (+4%) | 863.798 (+1%) |

## Movement detection (cross-replicate position-disagreement)

- 368 cells flagged as having moving content
  (replicate tile positions disagreed by > 2 search steps).
- Affected (lens, FL, aperture, position) — top 10:
  - Nikon AF Micro-Nikkor 200mm f_4D IF-ED + Kenko Pro 300 DG 1.4x | 280mm | F11 | x=0.34
  - Nikon AF Micro-Nikkor 200mm f_4D IF-ED + Kenko Pro 300 DG 1.4x | 280mm | F11 | x=0.5
  - Nikon AF Micro-Nikkor 200mm f_4D IF-ED + Kenko Pro 300 DG 1.4x | 280mm | F5.6 | x=0.5
  - Nikon AF Micro-Nikkor 200mm f_4D IF-ED + Kenko Pro 300 DG 1.4x | 280mm | F8 | x=0.34
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 105mm | F16 | x=0.82
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 105mm | F8 | x=0.5
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 105mm | F8 | x=0.66
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 135mm | F16 | x=0.82
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 70mm | F11 | x=0.5
  - Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED | 70mm | F8 | x=0.5
