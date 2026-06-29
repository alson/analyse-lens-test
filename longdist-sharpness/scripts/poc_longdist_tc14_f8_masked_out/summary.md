# TC-1.4x retention — bare vs tc14 at F8, placards masked

Brick/chalk edges only (green+purple masked), central overlap, best-focus per edge.

| config | f_eff | n edges | median MTF50 | p75 MTF50 | max MTF50 | sub-Nyquist |
|---|---|---|---|---|---|---|
| bare | 400 | 3 | 0.493 | 0.493 | 0.493 | 1/3 |
| tc14 | 560 | 21 | 0.427 | 0.493 | 0.493 | 15/21 |

## Retention (median MTF50, cy/sensor-px)

- tc14/bare median MTF50 = **0.87**  (break-even 0.714; FOM gain +21%) → PASS (adds detail)
- physical sanity: bare (0.493) ≥ tc14 (0.427)

> If most edges are sub-Nyquist AND bare ≥ tc14, this is a trustworthy retention. If edges still saturate (max=0.49, few sub-Nyquist), f/8 didn't escape the cap either.