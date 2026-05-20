# Algorithm comparison — wide2026_02_07

Discovered 52 configs, generated 916 per-(algorithm, cell) measurements.
Consensus tile selection uses cross-replicate median-gradient
(rejects moving content like cyclists/pedestrians).

## Stability per algorithm (replicate spread)

Per cell, CV = (top - min) / median * 100. Lower = the algorithm
returns consistent values across the burst of replicates.

| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |
|---|---|---|---|---|
| radial_cutoff | 0.0% | 4.7% | 260 | (cells absent if algorithm returned NaN) |
| mtf50_slanted_edge | 4.0% | 87.3% | 136 | (cells absent if algorithm returned NaN) |
| vol | 1.7% | 6.9% | 260 | (cells absent if algorithm returned NaN) |
| brenner | 1.6% | 6.0% | 260 | (cells absent if algorithm returned NaN) |

## Cross-algorithm rank agreement (Spearman ρ on `top`)

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.55 | 0.25 | -0.03 |
| mtf50_slanted_edge | 0.55 | 1.00 | -0.52 | -0.60 |
| vol | 0.25 | -0.52 | 1.00 | 0.94 |
| brenner | -0.03 | -0.60 | 0.94 | 1.00 |

## Pearson linear correlation

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.45 | 0.18 | -0.09 |
| mtf50_slanted_edge | 0.45 | 1.00 | -0.43 | -0.54 |
| vol | 0.18 | -0.43 | 1.00 | 0.94 |
| brenner | -0.09 | -0.54 | 0.94 | 1.00 |

## Lighting-robustness probe (one reference sharp tile)

Reference: NIKKOR Z 14-24mm f_2.8 S ISO100 20.0mm F4 x=0.34

| Transform | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| baseline | 0.336 (+0%) | — | 866.916 (+0%) | 880.128 (+0%) |
| brightness -0.5EV | 0.336 (+0%) | — | 433.327 (-50%) | 439.931 (-50%) |
| brightness +0.5EV | 0.336 (+0%) | — | 1733.308 (+100%) | 1759.724 (+100%) |
| brightness -1.0EV | 0.336 (+0%) | — | 216.729 (-75%) | 220.032 (-75%) |
| brightness +1.0EV | 0.336 (+0%) | — | 3462.293 (+299%) | 3510.926 (+299%) |
| contrast x0.7 | 0.336 (+0%) | — | 424.789 (-51%) | 431.263 (-51%) |
| contrast x1.3 | 0.336 (+0%) | — | 1464.697 (+69%) | 1485.008 (+69%) |
| gamma 0.7 | 0.332 (-1%) | — | 1035.679 (+19%) | 1060.270 (+20%) |
| gamma 1.3 | 0.340 (+1%) | — | 625.973 (-28%) | 625.437 (-29%) |

## Movement detection (cross-replicate position-disagreement)

- 8 cells flagged as having moving content
  (replicate tile positions disagreed by > 2 search steps).
- Affected (lens, FL, aperture, position) — top 10:
  - NIKKOR Z 14-24mm f_2.8 S ISO800 | 20mm | F2.8 | x=0.18
  - NIKKOR Z 14-24mm f_2.8 S ISO800 | 20mm | F4 | x=0.18
  - NIKKOR Z 14-24mm f_2.8 S ISO800 | 20mm | F8 | x=0.18
  - NIKKOR Z 20mm f_1.8 S ISO100 | 20mm | F16 | x=0.5
  - NIKKOR Z 20mm f_1.8 S ISO400 | 20mm | F4 | x=0.34
  - Nikon AF Nikkor 20mm f_2.8 ISO100 | 20mm | F5.6 | x=0.34
  - Nikon AF Nikkor 20mm f_2.8 ISO400 | 20mm | F8 | x=0.34
  - Viltrox AF 20_2.8 Z ISO100 | 20mm | F4 | x=0.18
