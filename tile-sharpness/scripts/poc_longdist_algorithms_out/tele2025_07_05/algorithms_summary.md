# Algorithm comparison — tele2025_07_05

Discovered 0 configs, generated 0 per-(algorithm, cell) measurements.
Consensus tile selection uses cross-replicate median-gradient
(rejects moving content like cyclists/pedestrians).

## Stability per algorithm (replicate spread)

Per cell, CV = (top - min) / median * 100. Lower = the algorithm
returns consistent values across the burst of replicates.

| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |
|---|---|---|---|---|
| radial_cutoff | — | — | 0 | — |
| mtf50_slanted_edge | — | — | 0 | — |
| vol | — | — | 0 | — |
| brenner | — | — | 0 | — |

## Cross-algorithm rank agreement (Spearman ρ on `top`)

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | — | — | — | — |
| mtf50_slanted_edge | — | — | — | — |
| vol | — | — | — | — |
| brenner | — | — | — | — |

## Pearson linear correlation

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | — | — | — | — |
| mtf50_slanted_edge | — | — | — | — |
| vol | — | — | — | — |
| brenner | — | — | — | — |

## Movement detection (cross-replicate position-disagreement)

- 0 cells flagged as having moving content
  (replicate tile positions disagreed by > 2 search steps).
