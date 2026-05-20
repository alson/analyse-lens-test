# Algorithm comparison — wide2026_01_24

Discovered 107 configs, generated 1812 per-(algorithm, cell) measurements.
Consensus tile selection uses cross-replicate median-gradient
(rejects moving content like cyclists/pedestrians).

## Stability per algorithm (replicate spread)

Per cell, CV = (top - min) / median * 100. Lower = the algorithm
returns consistent values across the burst of replicates.

| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |
|---|---|---|---|---|
| radial_cutoff | 0.0% | 5.5% | 535 | (cells absent if algorithm returned NaN) |
| mtf50_slanted_edge | 34.1% | 170.6% | 207 | (cells absent if algorithm returned NaN) |
| vol | 1.6% | 10.4% | 535 | (cells absent if algorithm returned NaN) |
| brenner | 1.1% | 9.7% | 535 | (cells absent if algorithm returned NaN) |

## Cross-algorithm rank agreement (Spearman ρ on `top`)

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.10 | 0.89 | 0.82 |
| mtf50_slanted_edge | 0.10 | 1.00 | 0.11 | 0.13 |
| vol | 0.89 | 0.11 | 1.00 | 0.98 |
| brenner | 0.82 | 0.13 | 0.98 | 1.00 |

## Pearson linear correlation

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.05 | 0.84 | 0.78 |
| mtf50_slanted_edge | 0.05 | 1.00 | 0.07 | 0.11 |
| vol | 0.84 | 0.07 | 1.00 | 0.97 |
| brenner | 0.78 | 0.11 | 0.97 | 1.00 |

## Lighting-robustness probe (one reference sharp tile)

Reference: NIKKOR Z 14-24mm f_2.8 S 24.0mm F4 x=0.5

| Transform | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| baseline | 0.324 (+0%) | — | 1092.736 (+0%) | 1062.698 (+0%) |
| brightness -0.5EV | 0.324 (+0%) | — | 546.203 (-50%) | 531.189 (-50%) |
| brightness +0.5EV | 0.324 (+0%) | — | 2184.601 (+100%) | 2124.466 (+100%) |
| brightness -1.0EV | 0.324 (+0%) | — | 273.184 (-75%) | 265.675 (-75%) |
| brightness +1.0EV | 0.324 (+0%) | — | 4072.782 (+273%) | 3856.984 (+263%) |
| contrast x0.7 | 0.324 (+0%) | — | 535.441 (-51%) | 520.722 (-51%) |
| contrast x1.3 | 0.324 (+0%) | — | 1846.663 (+69%) | 1795.390 (+69%) |
| gamma 0.7 | 0.324 (+0%) | — | 1051.293 (-4%) | 1026.410 (-3%) |
| gamma 1.3 | 0.324 (+0%) | — | 970.785 (-11%) | 937.035 (-12%) |

## Movement detection (cross-replicate position-disagreement)

- 39 cells flagged as having moving content
  (replicate tile positions disagreed by > 2 search steps).
- Affected (lens, FL, aperture, position) — top 10:
  - NIKKOR Z 14-24mm f_2.8 S | 14mm | F8 | x=0.5
  - NIKKOR Z 14-24mm f_2.8 S | 24mm | F11 | x=0.34
  - NIKKOR Z 14-24mm f_2.8 S | 24mm | F11 | x=0.5
  - NIKKOR Z 14-24mm f_2.8 S | 24mm | F16 | x=0.34
  - NIKKOR Z 14-24mm f_2.8 S | 24mm | F16 | x=0.66
  - NIKKOR Z 14-24mm f_2.8 S | 24mm | F2.8 | x=0.34
  - NIKKOR Z 14-24mm f_2.8 S | 24mm | F2.8 | x=0.5
  - NIKKOR Z 14-24mm f_2.8 S | 24mm | F2.8 | x=0.82
  - NIKKOR Z 14-24mm f_2.8 S | 24mm | F22 | x=0.34
  - NIKKOR Z 14-24mm f_2.8 S | 24mm | F4 | x=0.34
