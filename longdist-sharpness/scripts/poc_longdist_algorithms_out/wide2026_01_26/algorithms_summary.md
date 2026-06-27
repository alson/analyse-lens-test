# Algorithm comparison — wide2026_01_26

Discovered 111 configs, generated 1793 per-(algorithm, cell) measurements.
Consensus tile selection uses cross-replicate median-gradient
(rejects moving content like cyclists/pedestrians).

## Stability per algorithm (replicate spread)

Per cell, CV = (top - min) / median * 100. Lower = the algorithm
returns consistent values across the burst of replicates.

| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |
|---|---|---|---|---|
| radial_cutoff | 0.7% | 3.0% | 525 | (cells absent if algorithm returned NaN) |
| mtf50_slanted_edge | 37.5% | 127.1% | 158 | (cells absent if algorithm returned NaN) |
| vol | 2.5% | 11.3% | 555 | (cells absent if algorithm returned NaN) |
| brenner | 1.9% | 9.6% | 555 | (cells absent if algorithm returned NaN) |

## Cross-algorithm rank agreement (Spearman ρ on `top`)

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | -0.06 | 0.60 | 0.49 |
| mtf50_slanted_edge | -0.06 | 1.00 | 0.20 | 0.14 |
| vol | 0.60 | 0.20 | 1.00 | 0.96 |
| brenner | 0.49 | 0.14 | 0.96 | 1.00 |

## Pearson linear correlation

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | -0.10 | 0.51 | 0.44 |
| mtf50_slanted_edge | -0.10 | 1.00 | 0.22 | 0.20 |
| vol | 0.51 | 0.22 | 1.00 | 0.96 |
| brenner | 0.44 | 0.20 | 0.96 | 1.00 |

## Lighting-robustness probe (one reference sharp tile)

Reference: Viltrox AF 50_2.0 Z 50.0mm F4 x=0.66

| Transform | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| baseline | 0.303 (+0%) | — | 1541.545 (+0%) | 1660.007 (+0%) |
| brightness -0.5EV | 0.303 (-0%) | — | 770.540 (-50%) | 829.753 (-50%) |
| brightness +0.5EV | 0.303 (+0%) | — | 3062.811 (+99%) | 3274.209 (+97%) |
| brightness -1.0EV | 0.303 (+0%) | — | 385.386 (-75%) | 415.002 (-75%) |
| brightness +1.0EV | 0.304 (+0%) | — | 4153.420 (+169%) | 3807.665 (+129%) |
| contrast x0.7 | 0.303 (+0%) | — | 755.357 (-51%) | 813.403 (-51%) |
| contrast x1.3 | 0.303 (+0%) | — | 2604.758 (+69%) | 2803.449 (+69%) |
| gamma 0.7 | 0.302 (-0%) | — | 1255.575 (-19%) | 1355.355 (-18%) |
| gamma 1.3 | 0.304 (+0%) | — | 1604.506 (+4%) | 1718.218 (+4%) |

## Movement detection (cross-replicate position-disagreement)

- 5 cells flagged as having moving content
  (replicate tile positions disagreed by > 2 search steps).
- Affected (lens, FL, aperture, position) — top 10:
  - NIKKOR Z 14-24mm f_2.8 S AF for every pic | 16mm | F2.8 | x=0.82
  - NIKKOR Z 14-24mm f_2.8 S AF for every pic | 16mm | F4 | x=0.18
  - NIKKOR Z 24-120mm f_4 S | 60mm | F4 | x=0.66
  - Nikon AF Nikkor 50mm f_1.8 N | 50mm | F11 | x=0.66
  - Nikon AF Nikkor 50mm f_1.8 N | 50mm | F8 | x=0.82
