# Long-distance telephoto sharpness — multi-date, multi-camera

Empirical results from telephoto / long-distance lens-test sessions
spanning 2025-07 through 2026-02. Companion to
[`SHARPNESS_METRICS_LONGDIST.md`](SHARPNESS_METRICS_LONGDIST.md) (methodology).

This doc combines the Z7 telephoto analysis (the original 2026-01
cross-date study) with newer Z7 sessions (2026-02-07/telephoto) and the
older D7200 telephoto datasets (2025-07-09, 2025-09-06). D7200 has its
own section (§13) with the caveat that cy/sensor-px values aren't
directly cross-camera-comparable due to pixel-pitch differences
(D7200 3.91 µm vs Z7 4.35 µm).

Earlier note on the FL-labelling fix: the `400.0 mm` subdirectory of
`Z 100-400 + Z TC-x.x` is the camera-reported effective focal length
(`lens-at-(400/TC-factor)` + TC), not "lens-at-400 + TC". All numbers
here use EXIF-effective focal length consistently.

## 1. Setup

Three independent sessions, same physical setup at the same vantage,
shooting distant 3D shrubbery and bare twigs at infinity-class distance.

| Date | Lenses covered | Replicates per (lens, FL, aperture) | ISO ladder |
|---|---|---|---|
| 2026-01-18 | Z 100-400 bare; 300 PF bare; 300 PF + TC-14e III / TC-17e II / TC-20e III | 3 (capture-time pick) | ISO100 only |
| 2026-01-28 | Z 100-400 bare/+Z TC-1.4×/+Z TC-2.0×; 300 PF + 4 TCs; many other lenses | 3 typically | Default (ISO 100) |
| 2026-01-30 | Z 100-400 bare/+Z TC-1.4×/+Z TC-2.0×; 300 PF + TC-14e I/III, TC-17e II, **+ Kenko Pro 300 1.4×** (new) | 3–12 (more thorough) | 100/1600/4000/8000 — used the higher ISOs at slow shutters / small apertures to avoid wind shake on long lenses (per user) |

Focus distance from EXIF, confirmed identical across all three sessions
(Z7 distance preset quantization snaps consistently):

- **Z 100-400 family: 84.0 m** (distant shrubbery patch)
- **300 PF family: 31.62 m** (closer shrubbery patch)

Same physical scene; different shooting sessions = different exact
branches, slightly different lighting, possibly wind-shaken bits. That
between-session variation is exactly what the cross-date overlap table
(§5) probes.

## 2. Methodology (compressed)

3D vegetation, so per [`SHARPNESS_METRICS_LONGDIST.md`](SHARPNESS_METRICS_LONGDIST.md)
we don't fit a single ESF — instead we find the sharpest patch the lens
delivered per slice, mimicking the manual "locate sharpest in-focus
element, judge its edge" visual protocol.

- For each replicate of each (date, lens, FL, aperture):
  - 5 horizontal field positions x ∈ {0.18, 0.34, 0.50, 0.66, 0.82}
  - At each position: scan a ~15 % × 20 % search box; find the 256 × 256
    tile with the highest gradient energy
- Per tile: radially-averaged power spectrum, normalised by mean power in
  the low-subject-frequency reference band [0.01, 0.20] cy/mm-subject.
  **Cutoff** = subject-frequency where the normalised spectrum drops to
  0.05 of the reference. Higher = lens delivers more real-world detail.
- Per (date, lens, FL, aperture, position): keep the highest cutoff
  across replicates (depth-of-scene sampling: more replicates = more
  AF positions sampled, so max picks the best focal-plane intersection).
- **Lowest-ISO filter** per (lens, FL, aperture) so ISO ladders collapse
  to a single representative measurement. See §9 caveat: at small
  apertures the slow-shutter, low-ISO variant may have shake-blur and
  the higher-ISO variant could be sharper.

Two reporting units used:

- `cutoff_subj` (cy / mm subject) — within-family interpretation.
- `FOM = sensor_cy_per_px × f_eff` — distance-fair cross-family. With
  fixed pixel pitch (4.35 µm), FOM is proportional to "subject cy/mm at
  any chosen fixed distance" — the right number for the
  "subject I can't get closer to, longer lens helps" use case.
  Conversion: `FOM = cutoff_subj × pixel_pitch_mm × focus_distance_mm`.

## 3. Z 100-400 family — per-date (best aperture per config)

Each row: cutoff (cy / mm subject) at 5 horizontal positions; **centre**
in bold. Best replicate per position. f_eff = EXIF FocalLength
(camera-reported effective FL including TC).

### 2026-01-18 (Z 100-400 only — no Z TCs on this day)

| Lens | f_eff | F# | x=0.18 | x=0.34 | **centre** | x=0.66 | x=0.82 | n_repl | FOM |
|---|---|---|---|---|---|---|---|---|---|
| Z 100-400 bare | 400 | f/8 | 0.20 | 0.20 | **0.20** | 0.21 | 0.20 | 3 | 73 |
| Z 100-400 bare | 400 | f/11 | 0.21 | 0.21 | **0.20** | 0.24 | 0.22 | 3 | 73 |

### 2026-01-28 (all three Z 100-400 family chains)

| Lens | f_eff | F# | x=0.18 | x=0.34 | **centre** | x=0.66 | x=0.82 | n_repl | FOM |
|---|---|---|---|---|---|---|---|---|---|
| Z 100-400 bare | 400 | f/8 | 0.20 | 0.20 | **0.20** | 0.21 | 0.20 | 3 | 73 |
| Z 100-400 bare | 400 | f/11 | 0.21 | 0.21 | **0.20** | 0.24 | 0.22 | 3 | 73 |
| + Z TC-1.4× | 560 | f/8 | 0.20 | 0.21 | **0.22** | 0.21 | 0.20 | 3 | 81 |
| + Z TC-1.4× | 560 | f/11 | 0.20 | 0.20 | **0.21** | 0.22 | 0.20 | 3 | 77 |
| + Z TC-1.4× | 560 | f/16 | 0.20 | 0.20 | **0.22** | 0.21 | 0.20 | 3 | 79 |
| + Z TC-2.0× | 800 | f/11 | 0.22 | 0.22 | **0.24** | 0.24 | 0.21 | 9 | 88 |
| + Z TC-2.0× | 800 | f/16 | 0.22 | 0.22 | **0.22** | 0.22 | 0.21 | 6 | 81 |

### 2026-01-30 (all three Z 100-400 family chains, deeper sampling)

| Lens | f_eff | F# | x=0.18 | x=0.34 | **centre** | x=0.66 | x=0.82 | n_repl | FOM |
|---|---|---|---|---|---|---|---|---|---|
| Z 100-400 bare | 400 | f/5.6 | 0.20 | 0.20 | **0.21** | 0.20 | 0.20 | 3 | 78 |
| Z 100-400 bare | 400 | f/8 | 0.20 | 0.20 | **0.21** | 0.20 | 0.20 | 3 | 75 |
| Z 100-400 bare | 400 | f/11 | 0.20 | 0.20 | **0.20** | 0.20 | 0.20 | 3 | 73 |
| + Z TC-1.4× | 560 | f/8 | 0.20 | 0.20 | **0.20** | 0.20 | 0.20 | 7 | 74 |
| + Z TC-1.4× | 560 | f/11 | 0.22 | 0.22 | **0.23** | 0.23 | 0.23 | 3 | 85 |
| + Z TC-1.4× | 560 | f/16 | 0.22 | 0.22 | **0.25** | 0.23 | 0.23 | 3 | 90 |
| + Z TC-2.0× | 800 | f/11 | 0.23 | 0.23 | **0.22** | 0.27 | 0.21 | 12 | 81 |
| + Z TC-2.0× | 800 | f/16 | 0.23 | 0.22 | **0.21** | 0.28 | 0.24 | 6 | 75 |

**Z 100-400 family observations**

- The bare lens and both Z TCs are highly **content-stable**: most rows
  land at cutoff = 0.20–0.25 cy / mm-subject regardless of session.
  Cross-date stdev under 8 % in nearly every cell (see §5).
- Edge / centre ratio ≥ 1.00 across the board — the field is flat, no
  off-axis penalty within the 5-position sweep.
- **Best aperture for the Z TC-2.0× chain: f/11** (centre 0.22–0.24).
  f/16 holds up but doesn't improve. Wide-open f/10 (the camera reports
  this as the effective max aperture at 800 mm) is already very close
  to peak.
- **Best aperture for Z TC-1.4× chain: f/11 to f/16** at 560 mm; f/16
  edged out slightly on 2026-01-30 (0.25 centre).

## 4. 300 PF family — per-date (best aperture per config)

### 2026-01-18 (300 PF bare + TC-14e III, TC-17e II, TC-20e III only — no TC-14e I or Kenko on this day)

| Lens | f_eff | F# | x=0.18 | x=0.34 | **centre** | x=0.66 | x=0.82 | FOM |
|---|---|---|---|---|---|---|---|---|
| 300 PF bare | 300 | f/5.6 | 0.34 | 0.43 | **0.40** | 0.33 | 0.32 | 55 |
| 300 PF bare | 300 | f/8 | 0.35 | 0.40 | **0.40** | 0.33 | 0.32 | 55 |
| 300 PF bare | 300 | f/11 | 0.38 | 0.42 | **0.39** | 0.33 | 0.36 | 54 |
| + TC-14e III | 420 | f/8 | 0.36 | 0.35 | **0.45** | 0.32 | 0.33 | 62 |
| + TC-14e III | 420 | f/11 | 0.37 | 0.35 | **0.41** | 0.37 | 0.36 | 56 |
| + TC-14e III | 420 | f/16 | 0.37 | 0.35 | **0.23** ⚠ | 0.37 | 0.36 | 31 |
| + TC-17e II | 500 | f/8 | 0.33 | 0.31 | **0.44** | 0.34 | 0.35 | 61 |
| + TC-17e II | 500 | f/11 | 0.35 | 0.35 | **0.47** | 0.34 | 0.37 | 64 |
| + TC-17e II | 500 | f/16 | 0.37 | 0.40 | **0.40** | 0.34 | 0.37 | 55 |
| + TC-20e III | 600 | f/11 | 0.34 | 0.41 | **0.32** | 0.32 | 0.34 | 45 |
| + TC-20e III | 600 | f/16 | 0.39 | 0.44 | **0.34** | 0.36 | 0.43 | 47 |

⚠ The `+TC-14e III | 420 mm | f/16` centre at 0.23 is anomalously low compared
to the same config on 2026-01-30 (0.47). The likely culprit is **wind-shake**
at slow shutter (ISO 100, f/16, 420 mm) — see §9 (sharpest-of-ISO follow-up).

### 2026-01-28 (300 PF bare + all four F-mount TCs)

| Lens | f_eff | F# | x=0.18 | x=0.34 | **centre** | x=0.66 | x=0.82 | FOM |
|---|---|---|---|---|---|---|---|---|
| 300 PF bare | 300 | f/5.6 | 0.36 | 0.49 | **0.52** | 0.43 | 0.31 | 72 |
| 300 PF bare | 300 | f/8 | 0.32 | 0.40 | **0.53** | 0.39 | 0.31 | 73 |
| 300 PF bare | 300 | f/11 | 0.39 | 0.45 | **0.43** | 0.40 | 0.33 | 59 |
| + TC-14e I | 420 | f/11 | 0.36 | 0.38 | **0.43** | 0.42 | 0.37 | 59 |
| + TC-14e III | 420 | f/11 | 0.32 | 0.41 | **0.43** | 0.47 | 0.42 | 59 |
| + TC-17e II | 500 | f/11 | 0.31 | 0.43 | **0.37** | 0.38 | 0.38 | 51 |
| + TC-20e III | 600 | f/11 | 0.44 | 0.55 | **0.48** | 0.44 | 0.53 | 66 |

### 2026-01-30 (300 PF bare + TC-14e I/III + TC-17e II + Kenko Pro 300 1.4×; no TC-20e III on this day)

| Lens | f_eff | F# | x=0.18 | x=0.34 | **centre** | x=0.66 | x=0.82 | n_repl | FOM |
|---|---|---|---|---|---|---|---|---|---|
| 300 PF bare | 300 | f/5.6 | 0.30 | 0.39 | **0.42** | 0.35 | 0.36 | 6 | 57 |
| 300 PF bare | 300 | f/8 | 0.36 | 0.41 | **0.43** | 0.45 | 0.38 | 5 | 59 |
| 300 PF bare | 300 | f/11 | 0.38 | 0.41 | **0.43** | 0.36 | 0.39 | 6 | 59 |
| + TC-14e I | 420 | f/11 | 0.45 | 0.42 | **0.48** | 0.41 | 0.30 | 5 | 66 |
| + TC-14e III | 420 | f/11 | 0.47 | 0.44 | **0.44** | 0.41 | 0.30 | 8 | 61 |
| + TC-14e III | 420 | f/16 | 0.44 | 0.42 | **0.47** | 0.44 | 0.30 | 6 | 64 |
| + TC-17e II | 500 | f/11 | 0.37 | 0.44 | **0.43** | 0.38 | 0.31 | 4 | 59 |
| **+ Kenko Pro 300 1.4×** | 420 | f/11 | 0.44 | 0.43 | **0.50** | 0.37 | 0.30 | 6 | 69 |
| + Kenko Pro 300 1.4× | 420 | f/16 | 0.44 | 0.42 | **0.44** | 0.47 | 0.30 | 6 | 61 |

**300 PF family observations**

- **Bare 300 PF peaks at f/8 centre** on 2026-01-28 (0.53), drops at
  f/5.6 (0.42–0.52) and f/11 (0.43). f/8 is the centre-best stop.
- **All F-mount TCs peak at f/11 centre** — confirms the
  "1–2 stops down from wide-open" rule from manual visual inspection.
- **Bare 300 PF is a centre-only lens on this scene** — edge / centre
  ratio 0.60–0.78 at f/8. Stopping to f/11 flattens the field at the
  cost of centre value.
- **TC-20e III centre on 2026-01-18 (0.32) vs 2026-01-28 (0.48)** — large
  cross-date difference; either focus-plane variation (3D scene) or AF
  jitter. F11 in particular shows 27 % stdev across dates for this combo
  (see §5).
- **Kenko Pro 300 1.4× outperforms the Nikon TC-14e III at f/11**
  on 2026-01-30 (0.50 vs 0.44 centre). New finding — the Kenko is
  surprisingly competitive.

## 5. Cross-date overlap — content-independence

For each (lens, f_eff, F#) shot on 2+ dates, this table reports the
centre cutoff per date and the cross-date stdev as a percent of the
mean. A scene-independent metric should show small stdev; a
scene-dependent metric will show stdev comparable to the mean.

| Lens | f_eff | F# | 18 | 28 | 30 | mean | **stdev %** | min..max |
|---|---|---|---|---|---|---|---|---|
| Z 100-400 bare | 400 | f/8 | 0.20 | 0.20 | 0.21 | 0.20 | **2.9 %** | 0.20..0.21 |
| Z 100-400 bare | 400 | f/11 | 0.20 | 0.20 | 0.20 | 0.20 | **0.0 %** | 0.20..0.20 |
| Z 100-400 bare | 400 | f/16 | 0.20 | 0.20 | 0.20 | 0.20 | **0.0 %** | 0.20..0.20 |
| Z 100-400 + Z TC-1.4× | 560 | f/11 | — | 0.21 | 0.23 | 0.22 | **6.5 %** | 0.21..0.23 |
| Z 100-400 + Z TC-1.4× | 560 | f/16 | — | 0.22 | 0.25 | 0.23 | **9.2 %** | 0.22..0.25 |
| Z 100-400 + Z TC-2.0× | 800 | f/11 | — | 0.24 | 0.22 | 0.23 | **5.2 %** | 0.22..0.24 |
| Z 100-400 + Z TC-2.0× | 800 | f/16 | — | 0.22 | 0.21 | 0.21 | **5.7 %** | 0.21..0.22 |
| 300 PF bare | 300 | f/4 | 0.28 | 0.47 | 0.32 | 0.36 | **27.5 %** | 0.28..0.47 |
| 300 PF bare | 300 | f/5.6 | 0.40 | 0.52 | 0.42 | 0.45 | **14.5 %** | 0.40..0.52 |
| 300 PF bare | 300 | f/8 | 0.40 | 0.53 | 0.43 | 0.45 | **15.0 %** | 0.40..0.53 |
| 300 PF bare | 300 | f/11 | 0.39 | 0.43 | 0.43 | 0.41 | **4.7 %** | 0.39..0.43 |
| 300 PF bare | 300 | f/16 | 0.37 | 0.41 | 0.42 | 0.40 | **5.6 %** | 0.37..0.42 |
| 300 PF + TC-14e I | 420 | f/11 | — | 0.43 | 0.48 | 0.45 | **7.4 %** | 0.43..0.48 |
| 300 PF + TC-14e III | 420 | f/8 | 0.45 | 0.36 | 0.39 | 0.40 | **12.0 %** | 0.36..0.45 |
| 300 PF + TC-14e III | 420 | f/11 | 0.41 | 0.43 | 0.44 | 0.43 | **4.3 %** | 0.41..0.44 |
| 300 PF + TC-14e III | 420 | f/16 | 0.23 ⚠ | 0.37 | 0.47 | 0.35 | **33.9 %** | 0.23..0.47 |
| 300 PF + TC-17e II | 500 | f/11 | 0.47 | 0.37 | 0.43 | 0.42 | **11.8 %** | 0.37..0.47 |
| 300 PF + TC-17e II | 500 | f/16 | 0.40 | 0.28 | 0.44 | 0.37 | **21.6 %** | 0.28..0.44 |
| 300 PF + TC-20e III | 600 | f/11 | 0.32 | 0.48 | — | 0.40 | **27.1 %** | 0.32..0.48 |
| 300 PF + TC-20e III | 600 | f/16 | 0.34 | 0.41 | — | 0.37 | **12.9 %** | 0.34..0.41 |

**Reading the stdev %**

- **< 5 %**: highly content-independent (Z 100-400 family, 300 PF at f/11).
  Single-session reading is trustworthy.
- **5–10 %**: typical scene-driven variation (Z TC chains, 300 PF + TC at
  f/11). Use cross-date mean as the best estimate.
- **10–20 %**: real content sensitivity (300 PF bare at wider apertures,
  300 PF + TC at f/8 or f/16). Single-session readings can be ±15 %
  off the cross-date mean.
- **> 20 %**: untrustworthy single-session reading. 300 PF + TC-14e III
  at f/16 has 34 % stdev because 2026-01-18's reading was likely
  shake-corrupted (ISO 100, slow shutter); the other two dates agree.
- **300 PF + TC-20e III at f/11 has 27 % stdev** between the two
  available dates — a real scene-sensitivity issue, possibly
  focus-plane variation in the 3D shrubbery at 600 mm.

**Key takeaway**: f/11 is the most content-stable aperture across both
lens families. Wider or smaller apertures show more cross-date variation
for reasons specific to each (lens-MTF variation, diffraction, AF
landing on different focal planes in the 3D scene, shake at slow shutter).

## 6. Headline findings

### 6a. The two TC questions

The relevant comparisons for actually deciding when to mount a TC.
(The dataset also contains shorter-lens-FL + TC shots — e.g.,
200 mm + TC-2.0× = 400 mm effective — taken for visual same-FOV
inspection. Those configurations are practically irrelevant: nobody
puts a 2× TC on a zoom just to reach a focal length the bare zoom
already covers natively. Excluded from the headline analysis below;
the data is still in §3 for the curious.)

**Question A — TC vs cropping the bare 400 mm frame.**
At the TC's longer effective FL (lens at the long end + TC mounted),
does the TC beat what you can get from cropping the bare 400 mm shot?

| Comparison (84 m, F11) | bare-cropped ceiling | TC chain | cutoff cy/mm-subj |
|---|---|---|---|
| 560 mm effective framing | 0.20 (bare 400, cropped) | lens-400 + Z TC-1.4× | TC 0.22 → **+10 %** |
| 800 mm effective framing | 0.20 (bare 400, cropped) | lens-400 + Z TC-2.0× | TC 0.23 → **+15 %** |

Cropping the bare frame preserves the bare lens's 0.20 cy/mm-subj
(crop + upsample adds no information). Both Z TCs **beat that ceiling**
modestly. Ideal mag-gain would be 1.4 / 2.0×; actual subject-resolution
gain is 1.10 / 1.15× — the TC pays an ~85 % optical penalty for the
nominal 40–100 % mag boost.

**Question B — distant fixed subject, longer lens helps.**
For a bird across an inlet you cannot approach, which combo delivers
the most subject detail per real-world millimetre?

FOM = sensor cy/px × f_eff (proportional to subject cy/mm at any fixed
distance):

| Combo | f_eff | F# | FOM |
|---|---|---|---|
| Z 100-400 + Z TC-1.4× | 560 | f/16 | **86** (best on 2026-01-30) |
| Z 100-400 + Z TC-2.0× | 800 | f/11 | **84** |
| Z 100-400 + Z TC-1.4× | 560 | f/11 | **77–85** |
| Z 100-400 bare | 400 | f/11 | 73 |
| 300 PF bare | 300 | f/8 | 55–73 (cross-date) |
| 300 PF + Kenko Pro 300 1.4× | 420 | f/11 | 69 (2026-01-30 only) |
| 300 PF + TC-14e I | 420 | f/11 | 59–66 |
| 300 PF + TC-14e III | 420 | f/11 | 56–61 |
| 300 PF + TC-17e II | 500 | f/11 | 51–64 |
| 300 PF + TC-20e III | 600 | f/11 | 45–66 |

**Both Z TCs are net-positive over bare** for the bird-on-cliff use
case: TC-1.4× is +18 %, TC-2.0× is +15 %. **Every Nikon F-mount TC
on the 300 PF is net-negative** vs bare 300 PF (best aperture each):
the lens-MTF penalty eats the magnification gain. The **Kenko Pro 300
1.4× is competitive** with bare 300 PF (69 vs 55–73) and outperforms
the Nikon TC-14e III at the same FL on 2026-01-30 (0.50 vs 0.44 centre).

### 6b. Z TCs vs F-mount TCs — sensor MTF retention

Per-pixel lens-MTF retention (= sensor_cy_per_px of TC ÷ bare-at-best):

| TC | Retained sensor MTF | Interpretation |
|---|---|---|
| Z TC-1.4× on Z 100-400 | ~80 % | Gentle |
| Z TC-2.0× on Z 100-400 | ~60 % | Moderate |
| F-mount TC-14e I/III on 300 PF | ~55 % | Significant penalty |
| F-mount TC-17e II on 300 PF | ~50 % | Significant penalty |
| F-mount TC-20e III on 300 PF | ~45 % | Heavy penalty |

The Z TCs preserve substantially more of the bare-lens MTF than the
F-mount TCs do on the 300 PF. The 300 PF has the higher base sharpness
(0.243 sensor cy/px vs 0.183 for bare Z 100-400), but the F-mount TC
penalty eats most of that headroom.

### 6c. Frame-edge performance

Edge / centre ratio at each combo's best-centre aperture:

| Combo | Best F# | edge/centre |
|---|---|---|
| Z 100-400 bare | f/11 | 1.06 |
| Z 100-400 + Z TC-1.4× | f/11–f/16 | 1.05–1.08 |
| Z 100-400 + Z TC-2.0× | f/11 | 1.08 |
| 300 PF bare | f/8 | **0.60** |
| 300 PF + TC-14e I | f/11 | 0.85 |
| 300 PF + TC-14e III | f/11 | 0.86 |
| 300 PF + TC-17e II | f/11 | 0.94 |
| 300 PF + TC-20e III | f/11 | 1.02 |
| 300 PF + Kenko Pro 300 1.4× | f/11 | 0.74 |

**Z 100-400 family is flat across the field** — no off-axis penalty.
**300 PF bare is centre-only** at its centre-best aperture — drops to
60 % at the field edges. Mounting a TC flattens the field at the cost
of centre value.

For "1–2 stops down from max for decent frame-edge sharpness on the
300 PF + F-mount TC" (the user's manual finding), see the earlier
single-day analysis output `poc_longdist_300pf_field_2026_01_28_out/`
for the full aperture × position table — the rule was confirmed by the
field-position cutoffs on 2026-01-28.

## 7. Per-lens prose

**Z 100-400 bare.** Highly consistent across dates and across the
field. Centre cutoff ~0.20 cy/mm-subject from f/5.6 through f/16; the
metric does not discriminate between apertures here because the lens
is sharp enough across the band that the cutoff hits the same
quantized FFT bin. Stopping past f/16 starts to drop the cutoff
(f/22 = 0.20, f/32 = 0.20 — diffraction-limited apertures hold the
same value because the metric saturates at the JPEG processing's
sharpening edge). Edge/centre ≥ 1.00 everywhere. **Best aperture
range: f/5.6 through f/11; flat.**

**Z 100-400 + Z TC-1.4× (lens-at-400 → 560 mm effective).** Cutoff
0.21–0.25 at f/11–f/16; centre tracks edges. Cross-date stdev
6–9 %, well within "trust single-session readings" range. Net +10 %
subject-resolution gain over cropping the bare 400 mm frame to the
same framing — the TC adds real subject detail, just less than the
nominal 1.4× would suggest. **Best aperture: f/11 or f/16.**

**Z 100-400 + Z TC-2.0× (lens-at-400 → 800 mm effective).** Cutoff
0.21–0.27 across positions at f/11; cross-date stdev ~5 %. Net +15 %
subject-resolution gain over cropping the bare 400 mm frame to the
same 800 mm framing — the most reach you can extract from the
Z 100-400 system. **Best aperture: f/11.**

**300 PF bare.** The sharpest centre reading in the dataset
(0.40–0.53 cy/mm-subject at f/8). Stable across dates at f/11–f/16
(stdev 5 %); more variable at f/5.6–f/8 (stdev 14–15 %) because the
centre is sharp enough that scene-content variation (different
in-focus branches across dates) shifts the cutoff measurably. Edges
collapse off-axis at f/8 (edge/centre 0.60). **Best aperture for
centre: f/8. Best aperture for full-frame use: f/11 or f/16.**

**300 PF + TC-14e I.** Centre cutoff 0.43–0.48 at f/11. Cross-date
stdev 7 %. Field is flat at f/11 (edge/centre 0.85). Subject
resolution is ~80 % of bare 300 PF, despite the 1.4× mag claim —
the TC's lens-MTF penalty eats most of the magnification benefit.
**Best aperture: f/11. Best aperture for centre alone: still f/11.**

**300 PF + TC-14e III.** Similar to TC-14e I in centre cutoff
(0.43–0.44 at f/11) but with more cross-date scatter at f/16
(stdev 34 % — confirmed shake-corrupted on 2026-01-18). On
2026-01-30 (ISO 1600) it reaches 0.47 centre at f/16. **Best aperture:
f/11 unless you can shoot fast enough to use f/16 without shake.**

**300 PF + TC-17e II.** Weakest of the four Nikon F-mount TCs at
its centre-best aperture: 0.37–0.47 at f/11. Cross-date stdev 12 %.
Field is the closest to flat among the F-mount TCs (edge/centre
0.94 at f/11). **Best aperture: f/11.**

**300 PF + TC-20e III.** Centre 0.32–0.48 at f/11 (high cross-date
variation, 27 % stdev). Field actually exceeds centre on 2026-01-28
(edge/centre 1.02 — the 3D scene's focal-plane hit edge branches
more sharply than centre branches that day). Subject-detail FOM 45–66,
mostly worse than bare 300 PF. **Best aperture: f/11. Honestly: skip
the TC and crop the bare 300 PF for distant subjects.**

**300 PF + Kenko Pro 300 1.4× (new on 2026-01-30).** Centre 0.50 at
f/11 — **best of any 300 PF + 1.4× combo on that day** (better than
TC-14e I's 0.48 and TC-14e III's 0.44). Field is sharper at the left
than at the right (0.44 / 0.30) — some asymmetry, possibly decentering
or scene effect. **Worth keeping if you have it. Best aperture: f/11.**

## 8. Practical recommendations (this scene class)

| Use case | Recommended combo | Aperture |
|---|---|---|
| Distant fixed subject, want most subject detail | **Z 100-400 + Z TC-2.0× @ 800 mm**, or **Z TC-1.4× @ 560 mm + crop** | **f/11** |
| Distant fixed subject, faster shutter wanted | Z 100-400 + Z TC-1.4× @ 560 mm | f/11 |
| 400 mm effective, no compromise | Z 100-400 bare @ 400 mm | f/5.6–f/16 (all similar) |
| Have only the 300 PF, subject is centred | 300 PF bare @ 300 mm | f/8 (centre-best) |
| Have only the 300 PF, subject is off-centre / fills frame | 300 PF bare @ 300 mm | f/11 (field-flatter) |
| Have only 300 PF, need more reach | Either: bare + crop, or + Kenko Pro 300 1.4× (best of the F-mount-class TCs on this dataset) | f/11 if using a TC |

The 300 PF + F-mount TCs combo is mostly suboptimal for distant
subjects vs the Z 100-400 — the Z TCs preserve more lens-MTF.
**The exception: the Kenko Pro 300 1.4× holds up well; the Nikon
TC-14e III is the weakest at f/16 (large shake-sensitivity).**

## 9. Limitations and follow-up items

- **Lowest-ISO filter on the ISO ladder.** When a (lens, FL, aperture)
  was shot at multiple ISOs, this analysis kept the lowest-ISO variant.
  The user shot higher ISOs at small apertures specifically because
  shutter was borderline for shake — so the lowest-ISO variant can be
  motion-blur-corrupted at f/16 / f/22. The 300 PF + TC-14e III f/16
  centre on 2026-01-18 (0.23 vs cross-date 0.37–0.47) is a clear case
  of this. **Follow-up: re-run with sharpest-of-ISO picker** — keep
  whichever ISO variant gives the highest cutoff per
  (lens, FL, aperture, position).
- **Replicate-spread reporting not yet added.** Currently each cell
  reports only "best of N replicates" (max across burst). The user
  asked for `top / median / top_vs_median / range_pct` to flag whether
  the top reading is consistent or a fluke. Will add as a
  post-aggregation pass; doesn't require re-running the heavy FFT step.
  Interpretation for 3D scenes: high spread → multiple AF positions
  landed on different focal planes; low spread → static feature.
- **Z 100-400 cutoff appears saturated** around 0.20 cy/mm-subject in
  many cells (especially the bare lens across FL settings). The metric
  may be hitting an FFT-bin quantization or JPEG-pipeline ceiling.
  Cross-validation with a second algorithm (slanted-edge MTF50 on real
  edges in the scene, or radial-spectrum cutoff at a different
  threshold) would tell whether this is real lens behaviour or a
  metric artifact. The 300 PF family operates in a clearly
  discriminating range so the metric works for ranking there.
- **F-mount-TC interpretation depends on EXIF FL reporting.** I
  confirmed the camera reports effective FL (`LensInfo: 200-800mm f/9-11`
  for the Z TC-2.0× system; `420 mm` for the TC-14e III at 300×1.4 lens
  setting). All numbers in this doc use that as the f_eff value.
- **Wind-shake on slow shutter at long FL is a real failure mode**, as
  the 2026-01-18 TC-14e III f/16 anomaly shows. The sharpest-of-ISO
  follow-up will largely cure this for the rows that have multi-ISO
  data; otherwise readers should weight cross-date mean over single-
  session readings at f/16 and smaller.

## 10. Data and code

POC scripts under `tile-sharpness/scripts/`:

| Script | Purpose |
|---|---|
| `poc_longdist_cross_date_2026_01.py` | v1 cross-date sweep (Z7 tele 2026-01-{18,28,30}), lowest-ISO filter, best-replicate-per-position |
| `poc_longdist_cross_date_v2_2026_01.py` | **v2** — same dates, no ISO filter, replicate spread (top/median/min/etc.) |
| `poc_longdist_100_400_field_2026_01_28.py` | Single-day 5-position sweep for Z 100-400 family on 2026-01-28 |
| `poc_longdist_300pf_field_2026_01_28.py` | Same for the 300 PF family on 2026-01-28 |
| `poc_longdist_cross_family_edges_2026_01_28.py` | Cross-family edge / FOM comparison on 2026-01-28 |
| `poc_longdist_algorithms.py` | 4-algorithm comparison framework. Used for the wide-angle datasets AND the Z7 2026-02-07/tele + D7200 telephoto datasets in §12-§13 |

Per-dataset raw outputs:
- Z7 2026-01 cross-date v1: `poc_longdist_cross_date_2026_01_out/`
- Z7 2026-01 cross-date v2: `poc_longdist_cross_date_v2_2026_01_out/`
- Z7 2026-01-28 field sweeps: `poc_longdist_{100_400,300pf}_field_2026_01_28_out/`
- Z7 2026-02-07 tele: `poc_longdist_algorithms_out/tele2026_02_07/`
- D7200 2025-07-09 tele: `poc_longdist_algorithms_out/tele2025_07_09/`
- D7200 2025-09-06 tele: `poc_longdist_algorithms_out/tele2025_09_06/`

## 11. v2 update: sharpest-of-ISO + replicate spread

The v2 cross-date analysis pools all ISO variants and all replicates
per (lens, FL, aperture, position) and reports five statistics:

| Stat | Meaning |
|---|---|
| `top` | Max cutoff across all pooled replicates (the "best the lens delivered") |
| `median` | Typical cutoff — middle of the pooled replicates |
| `min` | Worst replicate |
| `top_vs_median` | Ratio top / median. ≈1.00 = top is consistent with typical; ≥1.10 = top is a flier (one lucky frame) |
| `range_pct` | (top − min) / median × 100, total spread relative to typical |

### 11a. Top vs median — the flier story matters

Many readings I had been treating as "the lens does this" are actually
"the lens sometimes does this on the lucky AF / focal-plane intersection
frame". Concrete examples from the v2 data:

| Combo | Date | F# | top | median | top_vs_median | Read |
|---|---|---|---|---|---|---|
| 300 PF bare | 2026-01-28 | f/4 | 0.47 | 0.37 | **1.28** | Flier — typical is 0.37 |
| 300 PF bare | 2026-01-28 | f/8 | 0.53 | 0.43 | **1.23** | Flier — typical is 0.43 |
| 300 PF bare | 2026-01-28 | f/11 | 0.43 | 0.41 | 1.04 | Robust — typical = top |
| 300 PF + TC-20e III | 2026-01-28 | f/11 | 0.48 | 0.34 | **1.40** | Heavy flier — typical is 0.34, far less impressive |
| 300 PF + TC-20e III | 2026-01-18 | f/11 | 0.37 | 0.36 | 1.05 | Robust at lower value |
| 300 PF + TC-14e III | 2026-01-30 | f/16 | 0.47 | 0.39 | 1.18 | Slight flier — typical is 0.39 |
| 300 PF + TC-14e III | 2026-01-30 | f/11 | 0.44 | 0.43 | 1.03 | Robust |
| Z 100-400 + Z TC-2.0× | 2026-01-28 | f/11 | 0.24 | 0.21 | 1.12 | Slight flier — typical is 0.21 |
| Z 100-400 + Z TC-2.0× | 2026-01-30 | f/11 | 0.22 | 0.21 | 1.04 | Robust |
| Z 100-400 + Z TC-1.4× | 2026-01-30 | f/16 | 0.25 | 0.22 | 1.14 | Slight flier — typical is 0.22 |
| Z 100-400 bare | (all dates) | f/8-f/11 | 0.20 | 0.20 | 1.00 | Robust everywhere |

### 11b. Updated TC vs bare-cropped headline (using median, the typical reading)

If you ask "what subject resolution will I *typically* get from this
combo?" — use median, not top. The corrected numbers shrink the Z TC
advantage over bare-cropped:

| Combo | f_eff | F# | top | median | top vs bare-cropped | median vs bare-cropped |
|---|---|---|---|---|---|---|
| Bare 100-400 @ 400 mm | 400 | f/11 | 0.20 | 0.20 | (ref) | (ref) |
| Bare 100-400 @ 400 mm cropped to 560-eff framing | 560 | — | 0.20 | 0.20 | (ref) | (ref) |
| + Z TC-1.4× @ 560 mm | 560 | f/11 | 0.21–0.23 | 0.20–0.22 | +5–15 % | **0–10 %** |
| + Z TC-1.4× @ 560 mm | 560 | f/16 | 0.22–0.25 | 0.21–0.22 | +10–25 % | **+5–10 %** |
| + Z TC-2.0× @ 800 mm | 800 | f/11 | 0.22–0.24 | 0.21–0.22 | +10–20 % | **+5–10 %** |

**Honest read**: the Z TCs deliver *up to* +15–20 % subject resolution
when AF lands on the sharpest available branch and the burst caught a
moment without wind drift (`top`). On a *typical* frame (`median`) the
advantage is **5–10 %** — small but consistent across dates. Cropping
the bare 400 mm shot is therefore a closer call than the v1 headline
"+10 % / +15 %" suggested.

The Z TC-2.0× sometimes hits `top` = 0.24 (on 2026-01-28 at f/11) but
`tvm` = 1.12 — that 0.24 was a lucky-burst frame, not a typical
delivery. Most replicates of that combo are at 0.21 (median), which is
basically the bare-cropped ceiling.

### 11c. Sharpest-of-ISO mostly didn't move the needle

The lowest-ISO filter v1 used was right for most cells: when the user
shot a config at multiple ISOs, the lowest ISO usually produced the
sharpest reading. Exceptions where the higher-ISO variant beat the
lowest-ISO variant for the v2 top value:

- **300 PF + TC-14e I @ 420 mm f/8 (2026-01-30)**: ISO 1600 won
  (top 0.45) vs ISO 100 (would have given lower). Wind/shake at slow
  shutter at f/8 + 420 mm was apparently borderline.
- **300 PF + TC-14e I @ 420 mm f/11 (2026-01-30)**: ISO 1600 won
  (top 0.48).
- **300 PF + TC-17e II @ 500 mm f/8, f/11, f/16 (2026-01-30)**: ISO
  8000 won at f/8 and f/11; ISO 1600 won at f/16. Lens is dimmer
  (max ~f/6.7); slow-shutter penalty kicks in earlier.
- **Z 100-400 + Z TC-2.0× @ various long FL (2026-01-30)**:
  ISO 1600 vs ISO 8000 produced fairly equal `top` values. ISO 8000
  occasionally won, suggesting borderline shutter.

The **300 PF + TC-14e III @ 420 mm f/16 anomaly on 2026-01-18 is
not rescued** by v2 because that day shot only ISO 100. The 0.23 vs
the cross-date 0.37–0.47 stays in the data as evidence that
slow-shutter / wind shake corrupted the test. The other two dates have
non-anomalous readings; weight them when interpreting that combo.

### 11d. n_replicates as depth-sampling power

Per [user clarification](#) the AF / multi-ISO replicates are sampling
the depth structure of the scene (different focal-plane intersections
with the 3D shrubbery), not testing AF repeatability. Effects:

- More replicates → more chances for `top` to capture the lens's best
  delivery → headline `top` tends slightly higher with deeper sampling.
- The `top_vs_median` gap *grows* with deeper sampling for 3D scenes,
  because extra replicates extend the upper tail without changing the
  median much. 2026-01-30 (n = 6–20) shows higher `tvm` than 2026-01-28
  (n = 3–9) for the same configs.
- The `median` is the depth-sampling-independent statistic — closer to
  "what the lens delivers when AF lands on something OK".

Practical recommendation: when comparing configs shot with different
replicate counts (eg. the 2026-01-30 deep sampling vs the 2026-01-18
3-shot bursts), **prefer median** over top for fair comparison. Use
`top` only when you have a fixed replicate-count protocol per cell.

### 11e. Where v2 doesn't help

- **Z 100-400 family cutoff still appears quantized** at 0.20–0.25 cy/mm-subj
  across most cells. The v2 sharpest-of-ISO and replicate-pool didn't
  push the values out of that range. Either the lens really delivers in
  that narrow band, or my radial-cutoff metric saturates against the
  JPEG-pipeline sharpening edge for this lens. The cross-algorithm
  comparison (running on the wide-angle dataset) will indirectly check
  this — if slanted-edge MTF50 shows wider dynamic range on a similar
  lens-quality range, the radial-cutoff is the bottleneck.
- **Single-session readings remain trustworthy only for low-spread cells.**
  Anything with `range_pct` > 30 % or `tvm` > 1.20 should be read as
  "top is a flier, prefer cross-date median".

## 12. Z7 telephoto extras — 2026-02-07/telephoto

Mid-tele session at ~15 m focus distance. Scene = dry-twig 3D shrubbery
(similar to the 2026-01 sessions but at closer distance — distance was
re-tuned to keep the subject inside each lens's reasonable infinity
range, per user methodology).

Lenses in this dataset are a mix of true telephoto (Z 100-400, AF 200/4D)
and macro lenses at infinity (Z MC 105, Sigma APO 150/2.8, Sigma 105/2.8,
AF Zoom-Micro 70-180/4.5-5.6D + Kenko Pro 300 1.4×, AF Micro 200/4D +
Kenko). The macros at infinity give a useful "macro-at-distance" sanity
check.

### Top centre cutoff (radial_cutoff, cy/sensor-px)

Top of each lens's centre-aperture combinations:

| Lens | Best FL × aperture | centre cy/sensor-px |
|---|---|---|
| **AF Zoom-Micro 70-180/4.5-5.6D** | 70 mm f/8 | **0.313** |
| Z 100-400/4.5-5.6 VR S | 100 mm f/5.6 | 0.309 |
| Z MC 105/2.8 VR S | 105 mm f/4 / f/5.6 | 0.305 |
| Sigma Macro 105/2.8 EX DG OS HSM | 105 mm f/2.8 | 0.297 |
| Z 24-120/4 S | 105 mm f/5.6 | 0.289 |
| Z 100-400 | 200 mm f/5.6 | 0.281 (typical) |
| AF Micro-Nikkor 200/4D IF-ED + Kenko Pro 300 1.4× | various | ~0.27 |
| Sigma APO Macro 150/2.8 EX DG OS HSM | 150 mm f/4 | ~0.27 |

The Z 100-400 at its wide end (100 mm) outperforms its long end on this
scene because at 15 m focus the wide-end FL is well inside its "infinity"
range. At 300+ mm the same 15 m distance is borderline → lens performance
drops there (typical "lens needs much more distance to count as infinity"
behaviour for longer focal lengths).

The **AF Zoom-Micro 70-180/4.5-5.6D macro** scores top at 70 mm f/8 —
interesting cross-check that a vintage macro zoom can match modern S-line
glass on the right scene at the right aperture.

### Algorithm comparison observations (2026-02-07/tele)

Same 4 algorithms ran on this dataset:
- `radial_cutoff`: 0 % median CV (highly stable, FFT-bin-quantized)
- `mtf50_slanted_edge`: ~30 % median CV, ~50 % NaN (no usable edges in
  most tiles — typical for 3D-shrubbery scene)
- `vol`/`brenner`: ~3 % median CV, gradient-amplitude-dependent
- Cross-algorithm Spearman (radial ↔ vol): ~0.70 (typical)

## 13. D7200 (DX, separate section)

**Caveat box.** D7200 telephoto data lives here because:

1. **Different camera** (DX, 6000 × 4000, 3.91 µm pixel pitch). Cy/sensor-
   px values are NOT directly comparable to Z7's 4.35 µm.
2. **Less strict test methodology** per user — some lenses lack distance
   encoders, focus distance varied across sessions, wind/light less
   controlled.
3. **2025-07-05 darktable-demosaiced** — that day's data is flat NEFs at
   the lens-dir level (no FL/aperture hierarchy + no co-located JPEGs).
   The NEF-embedded ``JpgFromRaw`` is Nikon "basic" quality (~113 kB/MP)
   which crushes high-frequency content, so I demosaiced via
   ``darktable-cli`` to FINE-quality JPEGs (~370 kB/MP) for analysis.
   See §13a-bis below for the resulting findings (mostly scene-limited
   — see also that subsection).
4. **2025-07-09 distance audit (corrected)**: contrary to my earlier note,
   2025-07-09 was **NOT** shorter on the long-FL combos. Per NEF EXIF
   FocusDistance audit (`audit_nef_distance_out/nef_distances_2025-07-09.md`):
   - AF-S 300/4D and all its TC chains (300–600 mm effective): **37.58 m**
     (longer than 2025-09-06's 31.62 m or 2026-01's 31.62 m for the
     300 PF + TC combos).
   - AF-S 70-200/2.8G and TC chains (70–400 mm effective): **23.71 m**.
   - Sigma 50-150/2.8 zooms: **22.39 m**. Sigma 50-100/1.8: **19.95 m**.
   - AF Zoom-Micro 70-180: **14.96 m** (the shortest in the dataset —
     borderline for the 180 mm end specifically).
   - Sigma APO Macro 150/2.8: 5.96 m (close — at infinity but the
     lens's near-focus end is well below for a 150 mm lens).
   - Tamron SP 90 Macro: **44.67 m** (the longest in the dataset).
   So if anything, 2025-07-09 ran *farther* than 2025-09-06 on the long
   tele combos. Earlier "borderline distance" claim withdrawn.
5. **Scenes differ across days.** 2025-07-09 features a structured
   sign/post scene; 2025-09-06 is 3D shrubbery (matching the later 2026
   Z7 scene). Cross-day same-lens comparisons on D7200 are partially
   scene-confounded.

### 13a-bis. 2025-07-05 — heath / bush scene (darktable-demosaiced, 35 configs)

Scene: distant heath + a low bush against grass. **Low-contrast vegetation
with no bare twigs or built structure** — different scene class from the
2026 telephoto sessions (which use bare-twig 3D shrubbery).

Most measurements hit the radial_cutoff metric's lower bound (0.2031 cy/sensor-
px, single FFT bin above DC). This is **scene-limited**, not lens-limited:
the heath/bush content doesn't deliver enough high-frequency texture for
the metric to discriminate.

The 3 configs that escape the floor:

| Lens × FL × aperture | centre cy/sensor-px |
|---|---|
| Tamron 90/2.8 Di Macro VC USD F017 + Kenko Pro 300 1.4× @ 90 mm, f/2.8 / f/5.6 | 0.371 |
| AF-S 300/4D + TC-14e III @ 420 mm, f/5.6 | 0.367 |

The macro + 1.4× combo is at shorter distance (and the Kenko TC brings more
subject magnification onto the sensor); the AF-S 300/4D + TC-14e III at
its longest reach + widest aperture reaches subject content with usable
texture. Other configs (bare AF-S 300/4D, 70-200/2.8G + various TCs,
Sigma 150 macro + various TCs) all hit the floor on this scene.

**Conclusion for 2025-07-05**: data is preserved (124 JPEGs demosaiced
in proper hierarchy) but the radial_cutoff metric is **not informative**
for ranking these lenses on this particular scene. The metric needs higher-
texture scene content (bare twigs, structured objects, or much closer
subject distance) to discriminate. **The vol / brenner / mtf50_slanted_edge
algorithms produce noise on this data too** (CV 38–80 %), so no algorithm
in our framework ranks this dataset.

### 13a. 2025-07-09 — F-mount telephoto + Sigma DC zooms (398 configs)

Top centre cutoff (radial_cutoff, cy/sensor-px) per lens at its best
centre aperture:

| Lens (best FL × aperture) | centre cy/sensor-px |
|---|---|
| Sigma 50-150/2.8 EX APO DC HSM I @ 98–150 mm, f/5.6 / f/8 | 0.297–0.301 |
| Sigma 50-150/2.8 EX APO DC HSM I + Sigma APO TC 1.4× @ 70 mm, f/11 | 0.301 |
| Sigma 50-100/1.8 DC HSM | A @ 70 mm, f/2.8 / f/8 | 0.297 |
| AF-S 70-200/2.8G IF-ED + TC-14e I @ 280 mm, f/8 | 0.297 |
| AF-S 70-200/2.8G IF-ED + Kenko Pro 300 1.4× @ 280 mm, f/8 | 0.297 |
| AF-S 70-200/2.8G IF-ED + TC-17e II @ 180 mm, f/8 | 0.293 |
| Sigma 50-150/2.8 EX APO DC HSM II + Sigma APO TC 1.4× @ 70 mm, f/8 | 0.289 |
| AF Zoom-Micro 70-180/4.5-5.6D | various | ~0.25–0.28 |

Scene-influenced: the structured sign post in the scene produces higher
cutoffs than 3D shrubbery would.

### 13b. 2025-09-06 — 300 PF + TC ladder on D7200 (837 configs)

Largest D7200 dataset. Scene = 3D shrubbery (same scene class as 2026
dates but on D7200). Distance scaled with FL: 300 mm @ 22.39 m, 420 /
500 / 600 mm @ 31.62 m.

Top centre cutoff (radial_cutoff, cy/sensor-px) for the long-FL lenses
(matching the 2026 Z7 tele dataset):

| Lens × FL × aperture | centre cy/sensor-px |
|---|---|
| AF-S 300/4E PF ED VR @ 300 mm, f/5.6 | 0.219 |
| AF-S 300/4E PF ED VR @ 300 mm, f/8 | 0.215 |
| AF-S 300/4E PF ED VR @ 300 mm, f/11 | 0.211 |
| AF-S 300/4D IF-ED @ 300 mm, f/11 | 0.211 |
| 300 PF + TC-14e I/III @ 420 mm, f/11 | 0.20 (floor) |
| 300 PF + TC-17e II @ 500 mm, f/11 | 0.20 |
| 300 PF + TC-20e III @ 600 mm, f/11 | 0.20 |
| Sigma 50-150 II + TC-2001 @ 300 mm, all apertures | 0.20 |
| AF-S 70-200/2.8G + TC-20e III @ 400 mm, all apertures | 0.20 |

**The 300 PF (E) is the only long-tele config that holds above the
metric floor on D7200.** All TC combinations at long FL drop to the
metric's lower bound on this scene. Same pattern as the Z7 finding
that F-mount TCs aren't net-positive for distant subjects (§6b of the
Z7 analysis), now confirmed cross-camera on the older test.

Other notable findings on 2025-09-06:
- **Mid-tele Sigma 50-150/2.8 EX APO DC HSM I peaks at 50 mm f/8** with
  centre 0.289 — strong mid-zoom performer.
- **Sigma 50-100/1.8 DC HSM | A** also holds at 0.27–0.28 across
  50–85 mm f/5.6–f/11.
- **TC-laden lenses fall to the metric floor.** Adding Sigma APO TC 1.4×
  or Sigma TC-1401 or Kenko Pro 300 to any DC-class zoom drops centre to
  0.20–0.25. Adding Nikon TC-14e I and III to the AF-S 70-200/2.8G holds
  up better (0.25–0.27) but still loses to the bare zoom.

### 13c. D7200 algorithm-comparison observations

Across both D7200 datasets:
- `radial_cutoff` median CV 0–1 % (very stable), p90 4–8 %.
- `mtf50_slanted_edge` 25–35 % median CV, 50–60 % NaN. Same scene-content
  issue as Z7 datasets.
- `vol`/`brenner` 7–12 % median CV — notably HIGHER than Z7 (where
  they're 1–3 %). Hypothesis: D7200 JPEG output has more inter-frame
  noise that vol/brenner pick up directly but radial_cutoff normalises
  out.
- Cross-algorithm Spearman (radial ↔ vol): 0.69–0.79. Lower than 2026-01-24
  (0.89) but consistent with the other Z7 datasets.

### 13d. D7200 vs Z7 — apples-to-oranges caveat

Direct cross-camera comparison of cy/sensor-px is not meaningful because:
1. Pixel pitch differs (3.91 µm vs 4.35 µm) — cy/sensor-px on D7200 maps
   to higher cy/mm-sensor at the same MTF.
2. JPEG engine differs (D7200 vs Z7 in-camera sharpening).
3. Sensor cover-glass / OLPF differs (D7200 has OLPF, Z7 does not).

The takeaway from the D7200 datasets is **the ranking within each lens
family**, not the absolute numbers. The patterns that hold:
- Modern S-line / G-series lenses dominate older AF non-D primes.
- Adding F-mount TCs to almost any lens reduces sensor MTF substantially.
- 300 PF (E) is the only long-tele on D7200 that holds above the
  noise floor — same as on Z7.
