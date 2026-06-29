# TC-1.4x revalidation — 2026-06-28 wall (within-session)

Centre = Pinpoint-AF (closed-loop, accurate under the point). Field/corners = focus-shift best-of-stack (each region at its own peak focus). Metric: radial_cutoff (cy/sensor-px).

## Per-config — best aperture (sharpest-of-ISO)

| config | f_eff | best F | ISO | AF centre top | AF centre med | stack centre | n_af/n_stk |
|---|---|---|---|---|---|---|---|
| bare | 400 | F5.6 | 500 | **0.156** | 0.158 | 0.364 | 3/80 |
| tc14 | 560 | F11 | 500 | **0.178** | 0.183 | 0.229 | 3/60 |
| tc20 | 800 | F11 | 500 | **0.117** | 0.118 | 0.328 | 3/160 |

> ⚠ AF-vs-stack: the AF centre reads LOWER than the stack centre here (af median 0.143 vs stack 0.190 across all cells). The 3 AF frames used the mechanical shutter + remote in gusty wind and are shake-softened; the focus-shift stacks are electronic-shutter, best-of-60+, so they're the cleaner centre (at step 1 the focus-quantisation worry is moot). **Checks below use the stack centre**; AF centre is shown above only as a (shake-flagged) cross-check.

> ⚠ radial_cutoff is partly compressed for this lens (stack range 0.10–0.46, much near the 2026-01 saturation band) — bare-vs-TC separation is muddy. The brick mortar lines make this an ideal scene for the edge-based MTF50 (poc_known_edge_mtf50.py); that is the discriminating follow-up metric, not radial_cutoff.

## Check 1 — adds real detail vs cropping the bare frame (stack centre, FOM)

| TC | retention=c_TC/c_bare | break-even | FOM gain vs bare-crop | verdict |
|---|---|---|---|---|
| tc14 | 0.63 | 0.714 | -12% | FAIL (crop as good) |
| tc20 | 0.90 | 0.500 | +80% | PASS (adds detail) |

## Check 2 — decentering / tilt (focus-shift corners, best aperture)

| config | TL | TR | BL | BR | corner min/max | diag (TL+BR)/(TR+BL) | centre/cornersᵐ |
|---|---|---|---|---|---|---|---|
| bare | 0.366 | 0.218 | 0.357 | 0.424 | 0.52  ⚠ | 1.37 | 1.07 |
| tc14 | 0.165 | 0.126 | 0.191 | 0.187 | 0.66  ⚠ | 1.11 | 1.37 |
| tc20 | 0.355 | 0.393 | 0.347 | 0.345 | 0.88  ⚠ | 0.95 | 0.91 |

> corner min/max < 0.90 ⇒ decentering suspect; diag far from 1.00 ⇒ tilt; centre/corners > 1 ⇒ residual field falloff even at each corner's own focus.

## Check 3 — retention vs the old (lost) copy [cross-series anchor]

Compare to the **re-run** 2026-01 ratios, not raw cutoffs. Old §6b: 1.4x ~0.80, 2.0x ~0.60.

| TC | retention now | expected | role |
|---|---|---|---|
| tc14 | 0.63 | ~0.80 | THE TEST |
| tc20 | 0.90 | ~0.60 | validity anchor (unchanged hw) |
