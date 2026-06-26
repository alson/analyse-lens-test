# Algorithm comparison — wide2025_09_10

Discovered 237 configs, generated 4170 per-(algorithm, cell) measurements.
Consensus tile selection uses cross-replicate median-gradient
(rejects moving content like cyclists/pedestrians).

## Stability per algorithm (replicate spread)

Per cell, CV = (top - min) / median * 100. Lower = the algorithm
returns consistent values across the burst of replicates.

| Algorithm | median CV% | p90 CV% | n_cells | NaN rate |
|---|---|---|---|---|
| radial_cutoff | 0.0% | 3.1% | 1185 | (cells absent if algorithm returned NaN) |
| mtf50_slanted_edge | 14.7% | 120.8% | 615 | (cells absent if algorithm returned NaN) |
| vol | 4.1% | 21.3% | 1185 | (cells absent if algorithm returned NaN) |
| brenner | 3.6% | 18.4% | 1185 | (cells absent if algorithm returned NaN) |

## Cross-algorithm rank agreement (Spearman ρ on `top`)

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.04 | 0.43 | 0.23 |
| mtf50_slanted_edge | 0.04 | 1.00 | 0.07 | 0.08 |
| vol | 0.43 | 0.07 | 1.00 | 0.94 |
| brenner | 0.23 | 0.08 | 0.94 | 1.00 |

## Pearson linear correlation

|  | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| radial_cutoff | 1.00 | 0.12 | 0.40 | 0.22 |
| mtf50_slanted_edge | 0.12 | 1.00 | 0.09 | 0.09 |
| vol | 0.40 | 0.09 | 1.00 | 0.95 |
| brenner | 0.22 | 0.09 | 0.95 | 1.00 |

## Lighting-robustness probe (one reference sharp tile)

Reference: Nikon AF-S DX Zoom-Nikkor 18-70mm f_3.5-4.5G IF-ED 24.0mm F8 x=0.34

| Transform | radial_cutoff | mtf50_slanted_edge | vol | brenner |
|---|---|---|---|---|
| baseline | 0.285 (+0%) | — | 618.486 (+0%) | 757.164 (+0%) |
| brightness -0.5EV | 0.285 (+0%) | — | 309.150 (-50%) | 378.468 (-50%) |
| brightness +0.5EV | 0.285 (+0%) | — | 1219.087 (+97%) | 1486.038 (+96%) |
| brightness -1.0EV | 0.285 (+0%) | — | 154.622 (-75%) | 189.291 (-75%) |
| brightness +1.0EV | 0.281 (-1%) | — | 1054.623 (+71%) | 1070.789 (+41%) |
| contrast x0.7 | 0.285 (+0%) | — | 303.058 (-51%) | 371.010 (-51%) |
| contrast x1.3 | 0.285 (+0%) | — | 1045.242 (+69%) | 1279.607 (+69%) |
| gamma 0.7 | 0.285 (+0%) | — | 458.544 (-26%) | 566.965 (-25%) |
| gamma 1.3 | 0.285 (+0%) | — | 699.440 (+13%) | 846.111 (+12%) |

## Movement detection (cross-replicate position-disagreement)

- 38 cells flagged as having moving content
  (replicate tile positions disagreed by > 2 search steps).
- Affected (lens, FL, aperture, position) — top 10:
  - Nikon AF DX Fisheye-Nikkor 10.5mm f_2.8G ED | 10mm | F2.8 | x=0.18
  - Nikon AF DX Fisheye-Nikkor 10.5mm f_2.8G ED | 10mm | F8 | x=0.18
  - Nikon AF Nikkor 20mm f_2.8 | 20mm | F4 | x=0.34
  - Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR | 20mm | F2.8 | x=0.82
  - Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR | 20mm | F8 | x=0.82
  - Nikon AF-S DX Nikkor 16-80mm f_2.8-4E ED VR | 24mm | F11 | x=0.82
  - Nikon AF-S DX VR Zoom-Nikkor 16-85mm f_3.5-5.6G ED | 20mm | F11 | x=0.34
  - Nikon AF-S DX VR Zoom-Nikkor 16-85mm f_3.5-5.6G ED | 24mm | F4 | x=0.34
  - Nikon AF-S DX Zoom-Nikkor 17-55mm f_2.8G IF-ED | 20mm | F16 | x=0.18
  - Nikon AF-S DX Zoom-Nikkor 17-55mm f_2.8G IF-ED | 22mm | F8 | x=0.66
