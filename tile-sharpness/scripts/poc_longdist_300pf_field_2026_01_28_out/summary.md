# 300 PF + TC ladder — field-position cutoff sweep (2026-01-28)

FocusDistance = 31.62 m. 5 horizontal positions at x = [0.18, 0.34, 0.5, 0.66, 0.82].
Per-position search box ~ 15% wide x 20% tall, finding the highest-
gradient 256px tile inside. Radial-spectrum cutoff at 0.05 of the low-
subject-frequency band [0.01, 0.20] cy/mm. Higher cutoff = lens delivers
more real-world detail. Best replicate per (config, aperture, position).

## Field-position cutoff (cy / mm subject)

| Config | f_eff | F# | x=0.18 | x=0.34 | x=0.50 (center) | x=0.66 | x=0.82 | best |
|---|---|---|---|---|---|---|---|---|
| PF_300 | 300mm | F4 | 0.40 | 0.39 | 0.47 | 0.41 | 0.37 | 0.47 @ x=0.50 |
| PF_300 | 300mm | F5.6 | 0.36 | 0.49 | 0.52 | 0.43 | 0.31 | 0.52 @ x=0.50 |
| PF_300 | 300mm | F8 | 0.32 | 0.40 | 0.53 | 0.39 | 0.31 | 0.53 @ x=0.50 |
| PF_300 | 300mm | F11 | 0.39 | 0.45 | 0.43 | 0.40 | 0.33 | 0.45 @ x=0.34 |
| PF_300 | 300mm | F16 | 0.49 | 0.49 | 0.41 | 0.40 | 0.36 | 0.49 @ x=0.18 |
| PF_TC14eI | 420mm | F5.6 | 0.30 | 0.32 | 0.32 | 0.32 | 0.31 | 0.32 @ x=0.34 |
| PF_TC14eI | 420mm | F8 | 0.36 | 0.35 | 0.38 | 0.42 | 0.36 | 0.42 @ x=0.66 |
| PF_TC14eI | 420mm | F11 | 0.36 | 0.38 | 0.43 | 0.42 | 0.37 | 0.43 @ x=0.50 |
| PF_TC14eI | 420mm | F16 | 0.35 | 0.36 | 0.42 | 0.42 | 0.32 | 0.42 @ x=0.50 |
| PF_TC14eIII | 420mm | F5.6 | 0.27 | 0.31 | 0.35 | 0.42 | 0.36 | 0.42 @ x=0.66 |
| PF_TC14eIII | 420mm | F8 | 0.32 | 0.38 | 0.36 | 0.45 | 0.38 | 0.45 @ x=0.66 |
| PF_TC14eIII | 420mm | F11 | 0.32 | 0.41 | 0.43 | 0.47 | 0.42 | 0.47 @ x=0.66 |
| PF_TC14eIII | 420mm | F16 | 0.31 | 0.39 | 0.37 | 0.44 | 0.37 | 0.44 @ x=0.66 |
| PF_TC17eII | 500mm | F6.7 | 0.27 | 0.27 | 0.28 | 0.31 | 0.31 | 0.31 @ x=0.66 |
| PF_TC17eII | 500mm | F8 | 0.27 | 0.35 | 0.28 | 0.31 | 0.31 | 0.35 @ x=0.34 |
| PF_TC17eII | 500mm | F11 | 0.31 | 0.43 | 0.37 | 0.38 | 0.38 | 0.43 @ x=0.34 |
| PF_TC17eII | 500mm | F16 | 0.31 | 0.40 | 0.28 | 0.38 | 0.40 | 0.40 @ x=0.34 |
| PF_TC20eIII | 600mm | F8 | 0.32 | 0.46 | 0.43 | 0.32 | 0.37 | 0.46 @ x=0.34 |
| PF_TC20eIII | 600mm | F11 | 0.44 | 0.55 | 0.48 | 0.44 | 0.53 | 0.55 @ x=0.34 |
| PF_TC20eIII | 600mm | F16 | 0.44 | 0.55 | 0.41 | 0.49 | 0.55 | 0.55 @ x=0.34 |

## Centre (x=0.50) cutoff per (config, aperture)

| Config | F# wide | F# best | best cutoff (cy/mm subj) |
|---|---|---|---|
| PF_300 | F4 | **F8** | **0.53** |
| PF_TC14eI | F5.6 | **F11** | **0.43** |
| PF_TC14eIII | F5.6 | **F11** | **0.43** |
| PF_TC17eII | F6.7 | **F11** | **0.37** |
| PF_TC20eIII | F8 | **F11** | **0.48** |

## Interpretation

- The cutoff value scales with subject-space resolution. Within this same-
  distance, same-scene patch, comparing configs/apertures is meaningful.
- Look for the 'best aperture' per config (centre column). For a well-
  behaved long-tele on a planar-distant scene the optimum is usually 1-2
  stops down from wide-open; TC-bearing configs typically need MORE stop-
  down because the TC concentrates aberrations.
- Look across field positions. A flat row = good across the field. A row
  that droops at x=0.18 and x=0.82 = sharp centre, soft edges (typical
  long-tele behaviour). A row that droops only at one side suggests
  decentering or non-flat subject plane.
- Compare these cutoffs with the 100-400 family's centre numbers
  (bare 0.20, +TC14 0.25, +TC20 0.29 cy/mm-subject) BUT remember the 100-
  400 family is at 84 m on a different shrubbery patch — only the within-
  family rankings are strictly fair.

## Caveats

- Field-position curves are best-replicate per position; AF jitter is
  absorbed into the result (we report the sharpest the lens got at each
  position).
- The 0.20 cy/mm-subject floor is the same low-band reference shape we
  saw in the 100-400 analysis — the scene's underlying spectrum + JPEG
  processing dominate that band, which is exactly why we normalise to it.
- No NEFs on disk for 2026-01-28; JPEGs only. Within-day, same-camera
  comparisons are robust.
