# Algorithm comparison — mid2025_09_11

Discovered 248 configs, generated 4487 per-(algorithm, cell) measurements.
Consensus tile selection uses cross-replicate median-gradient
(rejects moving content like cyclists/pedestrians).

## Stability per algorithm (replicate spread)

Per cell, CV = (top - min) / median * 100. Lower = the algorithm
returns consistent values across the burst of replicates.

| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |
|---|---|---|---|---|
| radial_cutoff | 0.0% | 5.3% | 1240 | (cells absent if algorithm returned NaN) |
| mtf50_slanted_edge | 25.9% | 193.1% | 767 | (cells absent if algorithm returned NaN) |
| vol | 5.3% | 25.0% | 1240 | (cells absent if algorithm returned NaN) |
| brenner | 4.3% | 21.2% | 1240 | (cells absent if algorithm returned NaN) |

## Cross-algorithm rank agreement (Spearman ρ on `top`)

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | -0.02 | 0.68 | 0.59 |
| mtf50_slanted_edge | -0.02 | 1.00 | -0.00 | -0.03 |
| vol | 0.68 | -0.00 | 1.00 | 0.96 |
| brenner | 0.59 | -0.03 | 0.96 | 1.00 |

## Pearson linear correlation

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.11 | 0.69 | 0.59 |
| mtf50_slanted_edge | 0.11 | 1.00 | 0.07 | 0.02 |
| vol | 0.69 | 0.07 | 1.00 | 0.97 |
| brenner | 0.59 | 0.02 | 0.97 | 1.00 |

## Lighting-robustness probe (one reference sharp tile)

Reference: Nikon AF-S DX Zoom-Nikkor 18-70mm f_3.5-4.5G IF-ED 27.0mm F8 x=0.82

| Transform | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| baseline | 0.301 (+0%) | — | 1793.662 (+0%) | 2079.145 (+0%) |
| brightness -0.5EV | 0.301 (+0%) | — | 896.560 (-50%) | 1039.259 (-50%) |
| brightness +0.5EV | 0.332 (+10%) | 0.393 (+nan%) | 1366.753 (-24%) | 1223.585 (-41%) |
| brightness -1.0EV | 0.301 (+0%) | — | 448.415 (-75%) | 519.786 (-75%) |
| brightness +1.0EV | 0.371 (+23%) | — | 142.968 (-92%) | 106.624 (-95%) |
| contrast x0.7 | 0.301 (+0%) | — | 878.894 (-51%) | 1018.781 (-51%) |
| contrast x1.3 | 0.309 (+3%) | 0.425 (+nan%) | 2987.890 (+67%) | 3410.560 (+64%) |
| gamma 0.7 | 0.301 (+0%) | 0.255 (+nan%) | 1075.142 (-40%) | 1251.654 (-40%) |
| gamma 1.3 | 0.309 (+3%) | — | 2500.523 (+39%) | 2882.925 (+39%) |

## Movement detection (cross-replicate position-disagreement)

- 70 cells flagged as having moving content
  (replicate tile positions disagreed by > 2 search steps).
- Affected (lens, FL, aperture, position) — top 10:
  - Nikon AF Nikkor 35mm f_2 | 35mm | F11 | x=0.18
  - Nikon AF Nikkor 35mm f_2 | 35mm | F11 | x=0.34
  - Nikon AF Nikkor 35mm f_2 | 35mm | F16 | x=0.18
  - Nikon AF Nikkor 35mm f_2 | 35mm | F16 | x=0.34
  - Nikon AF Nikkor 35mm f_2 | 35mm | F4 | x=0.82
  - Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR | 50mm | F3.5 | x=0.34
  - Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR | 55mm | F16 | x=0.34
  - Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR | 55mm | F4 | x=0.82
  - Nikon AF-S DX Nikkor 35mm f_1.8G | 35mm | F5.6 | x=0.18
  - Nikon AF-S DX VR Zoom-Nikkor 16-85mm f_3.5-5.6G ED | 24mm | F11 | x=0.5
