# Z 100-400 family — clean RAW slanted-edge MTF, 2026-06-28 brick (f/11 + f/16, ceiling-gated)

rawpy demosaic-only, gamma(1,1), no sharpening / no lens corrections; MTF in linear light. Brick-mortar edges. In-focus AF frames only; per-edge MEDIAN across AF frames, then median across edges. LSF profile = centroid_hann (§5.6e fix). MTF50 in cy/sensor-px.

## 1. Per (config, aperture)

| config | aperture | ISO | n edges | n AF frames | median MTF50 | p90 MTF50 | median MTF@Nyq | ceiling MTF50 | below ceiling? |
|---|---|---|---|---|---|---|---|---|---|
| bare | F5.6 | 100 | 394 | 3 | 0.252 | 0.493 | 0.312 | 0.571 | yes (glass-limited) |
| bare | F8 | 100 | 214 | 3 | 0.199 | 0.273 | 0.154 | 0.399 | yes (glass-limited) |
| bare | F11 | 100 | 716 | 3 | 0.209 | 0.320 | 0.138 | 0.290 | yes (glass-limited) |
| bare | F16 | 100 | 791 | 3 | 0.196 | 0.277 | 0.102 | 0.200 | yes (glass-limited) |
| tc14 | F8 | 100 | 527 | 3 | 0.162 | 0.234 | 0.144 | 0.399 | yes (glass-limited) |
| tc14 | F11 | 100 | 771 | 3 | 0.173 | 0.246 | 0.226 | 0.290 | yes (glass-limited) |
| tc14 | F16 | 100 | 331 | 3 | 0.196 | 0.375 | 0.294 | 0.200 | yes (glass-limited) |
| tc20 | F11 | 100 | 1057 | 3 | 0.145 | 0.229 | 0.148 | 0.290 | yes (glass-limited) |
| tc20 | F16 | 100 | 92 | 3 | 0.139 | 0.209 | 0.147 | 0.200 | yes (glass-limited) |

## 1b. Bare 400 mm aperture sweep (fixed analysis)

Full bare sweep re-measured with the centroid_hann fix + ceiling gate. f/5.6 is wide-open/glass-limited (ceiling above Nyquist).

| aperture | median MTF50 | median MTF@Nyq | ceiling MTF50 | below ceiling? |
|---|---|---|---|---|
| F5.6 | 0.252 | 0.312 | 0.571 | yes |
| F8 | 0.199 | 0.154 | 0.399 | yes |
| F11 | 0.209 | 0.138 | 0.290 | yes |
| F16 | 0.196 | 0.102 | 0.200 | yes |

- Peak bare aperture by MTF50: **F5.6** (0.252). Bare MTF50 is flat ~0.20-0.25 across f/5.6-f/16 (gust-limited / atmosphere on a 45 m subject), not the textbook f/8 peak; all stops sit well below the 0.49 Nyquist cap, so MTF50 is **not** saturated here.

## 2. Matched-aperture physical ordering (cy/sensor-px)

Physically must be **bare >= tc14 >= tc20** (more TC = more MTF loss). **MTF50 is the primary channel here**: on this clean RAW data bare MTF50 ~0.20 sits far below the 0.49 cap (no saturation), and it is robust. **MTF@Nyq is CONFOUNDED on this dataset** — each config detects an independent edge population on its own reference and the noise-sensitive Nyquist tail amplifies that mismatch, yielding impossible orderings (tc14 > bare). Reported below for completeness but it does NOT drive the verdict.


### F11

- MTF50 **(primary)**: bare 0.209  tc14 0.173  tc20 0.145  -> HOLDS
- MTF@Nyq (secondary, confounded): bare 0.138  tc14 0.226  tc20 0.148  -> VIOLATED (expected — confounded channel)

### F16

- MTF50 **(primary)**: bare 0.196  tc14 0.196  tc20 0.139  -> HOLDS
- MTF@Nyq (secondary, confounded): bare 0.102  tc14 0.294  tc20 0.147  -> VIOLATED (expected — confounded channel)

## 3. Retention at matched aperture (vs bare, same f-stop)

**MTF50 primary** (it is sub-cap here, ~0.20, so not saturated). MTF@Nyq shown secondary but is confounded (impossible >1 ratios) and is not used for the verdict.

- tc14 @ F11: **MTF50 retention 0.831**  (MTF@Nyq retention 1.636 — confounded)
- tc20 @ F11: **MTF50 retention 0.696**  (MTF@Nyq retention 1.077 — confounded)
- tc14 @ F16: **MTF50 retention 0.998**  (MTF@Nyq retention 2.891 — confounded)
- tc20 @ F16: **MTF50 retention 0.709**  (MTF@Nyq retention 1.450 — confounded)

## 4. FOM over cropping the bare 400 mm frame

**MTF50** ratio (primary). Best TC aperture = highest median MTF50 among ceiling-passing cells. Bare reference = f/8 (the frame you would crop to the TC framing). FOM = retention x (f_eff/400) - 1; the **ratio is more robust than absolutes** (common-mode over-read cancels). Break-even retention = 0.714 (TC-1.4x) / 0.500 (TC-2.0x).

Bare cropping reference: **F8** (MTF50 0.199).

- **tc14 @ F16** (f_eff 560): MTF50 retention **0.986** (break-even 0.714) -> **FOM +38%** (BEATS cropping)
- **tc20 @ F11** (f_eff 800): MTF50 retention **0.731** (break-even 0.500) -> **FOM +46%** (BEATS cropping)

## 5. TC-2.0x verdict

- TC-2.0x best at **F11** (MTF50 0.145), MTF50 retention vs bare-F8 = **0.731** (break-even 0.500).
- **CLEARS the 0.500 break-even -> BEATS cropping the bare 400 frame** (MTF50 FOM +46%).
- Ceiling gate (tc20): F11 PASS, F16 PASS — no over-read; readings are glass-limited.
- Physical ordering bare >= tc14 >= tc20 HOLDS on MTF50 at both f/11 and f/16 -> the data is NOT confounded on the primary channel.
- vs 2026-01 foliage: that gave TC-2.0x ~0% FOM, but it was scene-floor-limited (the whole Z 100-400 family floored at 0.20-0.25 cy/px on shrubbery; CAPTURE doc). This brick wall still has its own ceiling (bare MTF50 only ~0.20, gust/atmo-limited at 45 m), but the TCs separate cleanly from bare on MTF50, so this is a real positive TC-2.0x FOM rather than the floor-pinned ~0%.

## Ceiling-gate pass/fail per (config, aperture)

- bare F5.6: median MTF50 0.252 vs ceiling 0.571 -> PASS (glass-limited)
- bare F8: median MTF50 0.199 vs ceiling 0.399 -> PASS (glass-limited)
- bare F11: median MTF50 0.209 vs ceiling 0.290 -> PASS (glass-limited)
- bare F16: median MTF50 0.196 vs ceiling 0.200 -> PASS (glass-limited)
- tc14 F8: median MTF50 0.162 vs ceiling 0.399 -> PASS (glass-limited)
- tc14 F11: median MTF50 0.173 vs ceiling 0.290 -> PASS (glass-limited)
- tc14 F16: median MTF50 0.196 vs ceiling 0.200 -> PASS (glass-limited)
- tc20 F11: median MTF50 0.145 vs ceiling 0.290 -> PASS (glass-limited)
- tc20 F16: median MTF50 0.139 vs ceiling 0.200 -> PASS (glass-limited)

_Wall-clock 222s on 8 workers; 27 develop+measure jobs._