# Algorithm comparison — tele2025_07_05

Discovered 35 configs, generated 585 per-(algorithm, cell) measurements.
Consensus tile selection uses cross-replicate median-gradient
(rejects moving content like cyclists/pedestrians).

## Stability per algorithm (replicate spread)

Per cell, CV = (top - min) / median * 100. Lower = the algorithm
returns consistent values across the burst of replicates.

| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |
|---|---|---|---|---|
| radial_cutoff | 4.9% | 17.4% | 93 | (cells absent if algorithm returned NaN) |
| mtf50_slanted_edge | 79.1% | 394.2% | 142 | (cells absent if algorithm returned NaN) |
| vol | 33.5% | 81.6% | 175 | (cells absent if algorithm returned NaN) |
| brenner | 41.3% | 84.1% | 175 | (cells absent if algorithm returned NaN) |

## Cross-algorithm rank agreement (Spearman ρ on `top`)

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.07 | 0.60 | 0.47 |
| mtf50_slanted_edge | 0.07 | 1.00 | 0.21 | 0.16 |
| vol | 0.60 | 0.21 | 1.00 | 0.94 |
| brenner | 0.47 | 0.16 | 0.94 | 1.00 |

## Pearson linear correlation

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.09 | 0.73 | 0.56 |
| mtf50_slanted_edge | 0.09 | 1.00 | 0.15 | 0.17 |
| vol | 0.73 | 0.15 | 1.00 | 0.89 |
| brenner | 0.56 | 0.17 | 0.89 | 1.00 |

## Lighting-robustness probe (one reference sharp tile)

Reference: Tamron 90mm Di Macro VC USD F017 + Kenko Pro 300 DG 1.4x inf 90.0mm F2.8 x=0.5

| Transform | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| baseline | 0.168 (+0%) | — | 272.525 (+0%) | 509.356 (+0%) |
| brightness -0.5EV | 0.168 (+0%) | — | 136.221 (-50%) | 254.601 (-50%) |
| brightness +0.5EV | 0.168 (-0%) | — | 544.792 (+100%) | 1018.198 (+100%) |
| brightness -1.0EV | 0.168 (+0%) | — | 68.131 (-75%) | 127.339 (-75%) |
| brightness +1.0EV | 0.166 (-1%) | — | 953.063 (+250%) | 1666.645 (+227%) |
| contrast x0.7 | 0.168 (-0%) | — | 133.537 (-51%) | 249.585 (-51%) |
| contrast x1.3 | 0.168 (+0%) | — | 460.568 (+69%) | 860.812 (+69%) |
| gamma 0.7 | 0.167 (-1%) | — | 236.047 (-13%) | 445.102 (-13%) |
| gamma 1.3 | 0.169 (+1%) | — | 266.612 (-2%) | 492.180 (-3%) |

## Movement detection (cross-replicate position-disagreement)

- 18 cells flagged as having moving content
  (replicate tile positions disagreed by > 2 search steps).
- Affected (lens, FL, aperture, position) — top 10:
  - Nikon AF-S 300mm f_4D + Kenko Pro 300 DG 1.4x inf | 420mm | F11 | x=0.5
  - Nikon AF-S 300mm f_4D + Kenko Pro 300 DG 1.4x inf | 420mm | F8 | x=0.5
  - Nikon AF-S 300mm f_4D + Nikon TC-14e I inf | 420mm | F8 | x=0.5
  - Nikon AF-S 300mm f_4D + Nikon TC-14e III inf | 420mm | F5.6 | x=0.34
  - Nikon AF-S 300mm f_4D + Nikon TC-14e III inf | 420mm | F5.6 | x=0.5
  - Nikon AF-S 300mm f_4D + Nikon TC-14e III inf | 420mm | F5.6 | x=0.66
  - Nikon AF-S 300mm f_4D inf | 300mm | F4 | x=0.5
  - Nikon AF-S 300mm f_4D inf | 300mm | F5.6 | x=0.5
  - Nikon AF-S 300mm f_4D inf | 300mm | F5.6 | x=0.82
  - Nikon AF-S 300mm f_4D inf | 300mm | F8 | x=0.5
