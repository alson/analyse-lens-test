# Cross-family edge comparison — best centre-aperture per combo (2026-01-28)

Each row: cutoff at x=0.18 (far left), x=0.50 (centre), x=0.82 (far right).
`cy/mm-subj` reflects each family's own shooting distance (84m vs 31.62m).
`FOM = sensor cy/px * f_eff` is the distance-invariant figure of merit:
proportional to subject cy/mm at any fixed distance, so the right number
for the 'bird across the inlet' use case.

## cy/mm-subject (within-family interpretation)

| Combo | f_eff | F# | x=0.18 | centre | x=0.82 | edge / centre |
|---|---|---|---|---|---|---|
| Z 100-400 bare 400mm | 400mm | F11 | 0.21 | **0.20** | 0.22 | 1.06 |
| Z 100-400 + Z TC1.4x (560mm) | 560mm | F16 | 0.25 | **0.26** | 0.29 | 1.05 |
| Z 100-400 + Z TC2.0x (800mm) | 800mm | F11 | 0.32 | **0.32** | 0.38 | 1.08 |
| 300 PF bare 300mm | 300mm | F8 | 0.32 | **0.53** | 0.31 | 0.60 |
| 300 PF + TC-14e I (420mm) | 420mm | F11 | 0.36 | **0.43** | 0.37 | 0.85 |
| 300 PF + TC-14e III (420mm) | 420mm | F11 | 0.32 | **0.43** | 0.42 | 0.86 |
| 300 PF + TC-17e II (500mm) | 500mm | F11 | 0.31 | **0.37** | 0.38 | 0.94 |
| 300 PF + TC-20e III (600mm) | 600mm | F11 | 0.44 | **0.48** | 0.53 | 1.02 |

## FOM = sensor cy/px × f_eff (cross-family, distance-fair)

Distance-normalised: this is what you actually get at the subject when
the distance is fixed (more = more subject detail per mm).

| Combo | f_eff | F# | x=0.18 | centre | x=0.82 | edge / centre |
|---|---|---|---|---|---|---|
| Z 100-400 bare 400mm | 400mm | F11 | 75 | **73** | 81 | 1.06 |
| Z 100-400 + Z TC1.4x (560mm) | 560mm | F16 | 92 | **94** | 105 | 1.05 |
| Z 100-400 + Z TC2.0x (800mm) | 800mm | F11 | 116 | **119** | 141 | 1.08 |
| 300 PF bare 300mm | 300mm | F8 | 45 | **73** | 42 | 0.60 |
| 300 PF + TC-14e I (420mm) | 420mm | F11 | 49 | **59** | 51 | 0.85 |
| 300 PF + TC-14e III (420mm) | 420mm | F11 | 44 | **59** | 57 | 0.86 |
| 300 PF + TC-17e II (500mm) | 500mm | F11 | 43 | **51** | 53 | 0.94 |
| 300 PF + TC-20e III (600mm) | 600mm | F11 | 61 | **66** | 73 | 1.02 |

## Reading the edge / centre column

- 1.00 = edges as sharp as centre. Long-tele on planar distant scene rarely
  achieves this (off-axis aberrations + slight field curvature).
- 0.70-0.90 is typical for a good long-tele on a flat-ish distant subject.
- < 0.60 = soft edges -- avoid leaving important detail there.
- > 1.00 can happen on 3D scenes because the sharpest tile in an edge slice
  may sit on a branch that happens to be closer to the focal plane than
  whatever the centre tile landed on. This is a known artefact of the 'pick
  the sharpest tile per slice' protocol on 3D subjects. Treat such cases
  as 'edge is at least as sharp as centre, possibly more'.

## Caveats

- Field positions are picked by gradient-energy maximum in a per-position
  search box: they correspond to wherever the lens's focal plane hit a
  sharp subject element in that slice. Not a controlled flat target.
- Different shooting distance per family (84m vs 31.62m) -- the FOM column
  normalises that on the lens-MTF side; residual scene-statistics bias may
  remain in the cy/mm-subj column.
