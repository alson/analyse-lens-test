# Algorithm comparison — wide2026_01_26

Discovered 111 configs, generated 1823 per-(algorithm, cell) measurements.
Consensus tile selection uses cross-replicate median-gradient
(rejects moving content like cyclists/pedestrians).

## Stability per algorithm (replicate spread)

Per cell, CV = (top - min) / median * 100. Lower = the algorithm
returns consistent values across the burst of replicates.

| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |
|---|---|---|---|---|
| radial_cutoff | 0.0% | 2.9% | 555 | (cells absent if algorithm returned NaN) |
| mtf50_slanted_edge | 37.5% | 127.1% | 158 | (cells absent if algorithm returned NaN) |
| vol | 2.5% | 11.3% | 555 | (cells absent if algorithm returned NaN) |
| brenner | 1.9% | 9.6% | 555 | (cells absent if algorithm returned NaN) |

## Cross-algorithm rank agreement (Spearman ρ on `top`)

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | -0.05 | 0.67 | 0.56 |
| mtf50_slanted_edge | -0.05 | 1.00 | 0.20 | 0.14 |
| vol | 0.67 | 0.20 | 1.00 | 0.96 |
| brenner | 0.56 | 0.14 | 0.96 | 1.00 |

## Pearson linear correlation

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | -0.08 | 0.62 | 0.51 |
| mtf50_slanted_edge | -0.08 | 1.00 | 0.22 | 0.20 |
| vol | 0.62 | 0.22 | 1.00 | 0.96 |
| brenner | 0.51 | 0.20 | 0.96 | 1.00 |

## Lighting-robustness probe (one reference sharp tile)

Reference: NIKKOR Z 14-24mm f_2.8 S AF for every pic 16.0mm F4 x=0.34

| Transform | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| baseline | 0.328 (+0%) | — | 1460.857 (+0%) | 1501.408 (+0%) |
| brightness -0.5EV | 0.328 (+0%) | — | 730.208 (-50%) | 750.477 (-50%) |
| brightness +0.5EV | 0.328 (+0%) | — | 2920.542 (+100%) | 3001.509 (+100%) |
| brightness -1.0EV | 0.328 (+0%) | — | 365.214 (-75%) | 375.352 (-75%) |
| brightness +1.0EV | 0.328 (+0%) | — | 5609.370 (+284%) | 5638.258 (+276%) |
| contrast x0.7 | 0.328 (+0%) | — | 715.820 (-51%) | 735.690 (-51%) |
| contrast x1.3 | 0.328 (+0%) | — | 2468.183 (+69%) | 2533.071 (+69%) |
| gamma 0.7 | 0.328 (+0%) | — | 1424.486 (-2%) | 1473.211 (-2%) |
| gamma 1.3 | 0.332 (+1%) | — | 1281.213 (-12%) | 1302.399 (-13%) |

## Movement detection (cross-replicate position-disagreement)

- 5 cells flagged as having moving content
  (replicate tile positions disagreed by > 2 search steps).
- Affected (lens, FL, aperture, position) — top 10:
  - NIKKOR Z 14-24mm f_2.8 S AF for every pic | 16mm | F2.8 | x=0.82
  - NIKKOR Z 14-24mm f_2.8 S AF for every pic | 16mm | F4 | x=0.18
  - NIKKOR Z 24-120mm f_4 S | 60mm | F4 | x=0.66
  - Nikon AF Nikkor 50mm f_1.8 N | 50mm | F11 | x=0.66
  - Nikon AF Nikkor 50mm f_1.8 N | 50mm | F8 | x=0.82
