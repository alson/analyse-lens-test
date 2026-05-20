# Algorithm comparison — tele2025_07_05

Discovered 35 configs, generated 667 per-(algorithm, cell) measurements.
Consensus tile selection uses cross-replicate median-gradient
(rejects moving content like cyclists/pedestrians).

## Stability per algorithm (replicate spread)

Per cell, CV = (top - min) / median * 100. Lower = the algorithm
returns consistent values across the burst of replicates.

| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |
|---|---|---|---|---|
| radial_cutoff | 0.0% | 0.0% | 175 | (cells absent if algorithm returned NaN) |
| mtf50_slanted_edge | 79.1% | 394.2% | 142 | (cells absent if algorithm returned NaN) |
| vol | 33.5% | 81.6% | 175 | (cells absent if algorithm returned NaN) |
| brenner | 41.3% | 84.1% | 175 | (cells absent if algorithm returned NaN) |

## Cross-algorithm rank agreement (Spearman ρ on `top`)

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | — | — | — | — |
| mtf50_slanted_edge | — | 1.00 | 0.21 | 0.16 |
| vol | — | 0.21 | 1.00 | 0.94 |
| brenner | — | 0.16 | 0.94 | 1.00 |

## Pearson linear correlation

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | — | — | — | — |
| mtf50_slanted_edge | — | 1.00 | 0.15 | 0.17 |
| vol | — | 0.15 | 1.00 | 0.89 |
| brenner | — | 0.17 | 0.89 | 1.00 |

## Lighting-robustness probe (one reference sharp tile)

Reference: Nikon AF-S 300mm f_4D + Kenko Pro 300 DG 1.4x inf 420.0mm F11 x=0.18

| Transform | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| baseline | 0.203 (+0%) | 0.094 (+0%) | 7.859 (+0%) | 19.606 (+0%) |
| brightness -0.5EV | 0.203 (+0%) | 0.094 (+0%) | 3.928 (-50%) | 9.800 (-50%) |
| brightness +0.5EV | 0.203 (+0%) | 0.094 (+0%) | 15.713 (+100%) | 39.199 (+100%) |
| brightness -1.0EV | 0.203 (+0%) | 0.094 (+0%) | 1.965 (-75%) | 4.901 (-75%) |
| brightness +1.0EV | 0.203 (+0%) | 0.092 (-2%) | 30.531 (+288%) | 75.242 (+284%) |
| contrast x0.7 | 0.203 (+0%) | 0.094 (+0%) | 3.851 (-51%) | 9.607 (-51%) |
| contrast x1.3 | 0.203 (+0%) | 0.094 (-0%) | 13.282 (+69%) | 33.133 (+69%) |
| gamma 0.7 | 0.203 (+0%) | 0.094 (+1%) | 6.917 (-12%) | 17.303 (-12%) |
| gamma 1.3 | 0.203 (+0%) | 0.074 (-21%) | 7.489 (-5%) | 18.614 (-5%) |

## Movement detection (cross-replicate position-disagreement)

- 33 cells flagged as having moving content
  (replicate tile positions disagreed by > 2 search steps).
- Affected (lens, FL, aperture, position) — top 10:
  - Nikon AF-S 300mm f_4D + Kenko Pro 300 DG 1.4x inf | 420mm | F11 | x=0.18
  - Nikon AF-S 300mm f_4D + Kenko Pro 300 DG 1.4x inf | 420mm | F11 | x=0.34
  - Nikon AF-S 300mm f_4D + Kenko Pro 300 DG 1.4x inf | 420mm | F11 | x=0.5
  - Nikon AF-S 300mm f_4D + Kenko Pro 300 DG 1.4x inf | 420mm | F5.6 | x=0.5
  - Nikon AF-S 300mm f_4D + Kenko Pro 300 DG 1.4x inf | 420mm | F8 | x=0.5
  - Nikon AF-S 300mm f_4D + Nikon TC-14e I inf | 420mm | F11 | x=0.5
  - Nikon AF-S 300mm f_4D + Nikon TC-14e I inf | 420mm | F5.6 | x=0.5
  - Nikon AF-S 300mm f_4D + Nikon TC-14e I inf | 420mm | F8 | x=0.18
  - Nikon AF-S 300mm f_4D + Nikon TC-14e I inf | 420mm | F8 | x=0.5
  - Nikon AF-S 300mm f_4D + Nikon TC-14e III inf | 420mm | F5.6 | x=0.18
