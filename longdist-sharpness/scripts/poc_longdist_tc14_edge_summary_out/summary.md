# TC-1.4x revalidation — EDGE-MTF50 (primary metric), 2026-06-28 wall

Slanted-edge MTF50 on chalk/placard edges; per edge = best-focus (max over focus-shift frames). MTF@Nyquist is the un-saturated sharpness index.

## Per-config — best aperture (median over edges; n edges)

| config | f_eff | best F | n_edges | median MTF50 | p90 MTF50 | median MTF@Nyq | p90 MTF@Nyq |
|---|---|---|---|---|---|---|---|
| bare | 400 | F5.6 | 24 | 0.493 | 0.493 | **0.768** | 1.289 |
| tc14 | 560 | F11 | 24 | 0.368 | 0.493 | **0.417** | 0.742 |
| tc20 | 800 | F16 | 24 | 0.400 | 0.493 | **0.556** | 1.275 |

## Check 1 — adds real detail vs cropping (MTF@Nyquist, FOM)

| TC | retention (Nyq) | retention (MTF50) | break-even | FOM gain | verdict |
|---|---|---|---|---|---|
| tc14 | 0.54 | 0.75 | 0.714 | -24% | FAIL (crop as good) |
| tc20 | 0.72 | 0.81 | 0.500 | +45% | PASS (adds detail) |

> retention should order bare > tc14 > tc20 in cy/sensor-px (more TC = more MTF loss). If tc14 < tc20 the data is still confounded.

## Check 2 — decentering / tilt (best-focus edges by position)

| config | n L / R | median L | median R | L/R | n T / B | median T | median B | T/B |
|---|---|---|---|---|---|---|---|---|
| bare | 15/9 | 0.777 | 0.759 | 0.98 | 9/10 | 1.024 | 0.552 | 0.54 |
| tc14 | 5/12 | 0.446 | 0.451 | 0.99 | 6/12 | 0.417 | 0.409 | 0.98 |
| tc20 | 7/7 | 0.633 | 0.561 | 0.89 | 5/13 | 0.386 | 0.633 | 0.61 |

> L/R or T/B << 1.0 (with enough edges each side) ⇒ decentering/tilt. Few edges per side ⇒ low confidence (edges cluster where chalk is).
