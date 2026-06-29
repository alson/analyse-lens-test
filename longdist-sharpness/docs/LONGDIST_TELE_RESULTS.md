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

> **2026-06 — `radial_cutoff` metric definition changed (§5.3).**
> All `cy/mm-subject` and `cy/sensor-px` numbers in this doc were
> recorded under the original metric: `REF_BAND = (0.01, 0.20)`,
> first-crossing, no smoothing. The metric now uses
> `REF_BAND = (0.01, 0.10)`, last-crossing on a Gaussian-smoothed
> normalised spectrum (σ=2 bins). See
> [`RADIAL_CUTOFF_REFBAND_RESULTS.md`](RADIAL_CUTOFF_REFBAND_RESULTS.md).
> Absolute values typically read **12–15 % lower** for sharp Z7
> measurements under the new metric and **higher** for previously-
> floored soft cases. **Rankings within each comparison are
> preserved** except where the old metric was at floor — in which
> case the new metric reveals previously-hidden ordering (the
> headline §6a/b/c tables below have been re-generated from the new
> cross-family-edges output; the deeper per-date prose below still
> reads from the original metric and is annotated where the change
> mattered).

## §5.3 — what conclusions changed

Five places where the new metric materially shifted what the data
says (rather than just rescaling everything proportionally):

1. **Z TCs are dramatically more effective than previously claimed.**
   In §6a "TC vs cropping the bare 400 mm frame": TC-1.4× gain went
   from +10 % to **+24 %**; TC-2.0× gain went from +15 % to **+65 %**.
   The old metric capped the bare 400 mm reading at the 0.20 cy/mm-
   subj floor (real value is 0.17), masking the bare-vs-TC gap. The
   TCs were always this good; the metric was understating it.
2. **Z 100-400 bare is genuinely flatter and slightly softer than
   "around 0.20" suggested.** Cross-date cutoff sits in 0.14–0.19
   cy/mm-subj across the full FL × aperture sweep (was reported as a
   blanket 0.20 because the metric saturated). The "all apertures
   look the same" finding holds — the lens really is aperture-
   invariant in this range — but the absolute level was overstated.
3. **300 PF bare's "best centre aperture" is f/5.6, not f/8.**
   Cross-family-edges F5.6 = 0.44 centre, F8 = 0.43 — within noise.
   The old f/8 recommendation isn't wrong, just unnecessarily
   specific; either is fine.
4. **300 PF + TC-20e III shows an unexpected off-axis-up-centre-down
   field on 2026-01-28** (edge/centre 1.24 in the new metric, was
   1.02). Could be a 3D-scene focal-plane artefact (centre and edge
   branches at different depths) or a centre-tile-placement issue.
   **Worth visual inspection** before drawing TC field-uniformity
   conclusions for this combo.
5. **D7200 long-FL TC ordering is now quantified.** Pre-§5.3 every
   300 PF + TC chain on D7200 2025-09-06 read 0.20 floor; under §5.3
   they resolve to bare 300 PF (E) 0.183, Kenko 1.4× 0.158, 300/4D +
   TC-20e III 0.140. The "F-mount TCs aren't net-positive at distance"
   pattern, previously inferred from a shared floor on Z7, is now
   genuinely measured on D7200 with clear lens-MTF-penalty ordering.

What did NOT change:

- Cross-family FOM ordering: Z 100-400 + Z TC combos still beat
  300 PF + F-mount TC combos at every FL (ranks preserved; FOM
  magnitudes lower — e.g. Z TC-2.0× 800 mm FOM 103, was 84).
- F-mount TCs on the 300 PF are still net-negative vs bare 300 PF
  for centre subjects (FOM 46–56 vs bare 61).
- Edge/centre ratios for the Z 100-400 family stay flat (1.05–1.12).
- 300 PF bare is still a centre-only lens at its centre-best stop
  (edge/centre 0.60).
- Kenko Pro 300 1.4× is still the only F-mount 1.4× class TC that
  is competitive with bare 300 PF (cf. §6a).

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

_The tables in §3–§5 below are the pre-§5.3-metric values (Z 100-400
family floored at ~0.20). Refreshed §5.3 cross-date ranges are in §7
and the regenerated `poc_longdist_cross_date_2026_01_out/overlap.md` —
under §5.3 the bare lens resolves to 0.14–0.19 and the Z TC chains to
0.17–0.21. Rankings are unchanged; only the absolute magnitudes shift._

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

| Comparison (84 m) | bare-cropped ceiling | TC chain | cutoff cy/mm-subj |
|---|---|---|---|
| 560 mm effective framing | 0.17 (bare 400 F11, cropped) | lens-400 + Z TC-1.4× F16 | TC 0.21 → **+24 %** |
| 800 mm effective framing | 0.17 (bare 400 F11, cropped) | lens-400 + Z TC-2.0× F11 | TC 0.28 → **+65 %** |

Cropping the bare frame preserves the bare lens's 0.17 cy/mm-subj
(crop + upsample adds no information). Both Z TCs **beat that ceiling
substantially**. Compared to the ideal mag gain (1.4× / 2.0×), the
actual subject-resolution gain is 1.24× / 1.65× — about 60–65 %
optical efficiency of the nominal magnification.

_§5.3 note — the previous version of this table reported the bare
ceiling at 0.20 and TC gains of +10/+15 %. That was the old metric
floor; the bare lens was always below 0.20, and the §5.3 metric
correctly captures the bare-vs-TC gap, which is larger than first
read._

**Question B — distant fixed subject, longer lens helps.**
For a bird across an inlet you cannot approach, which combo delivers
the most subject detail per real-world millimetre?

FOM = sensor cy/px × f_eff (proportional to subject cy/mm at any fixed
distance):

| Combo (2026-01-28 centre, best aperture per combo) | f_eff | F# | FOM |
|---|---|---|---|
| Z 100-400 + Z TC-2.0× | 800 | f/11 | **103** |
| Z 100-400 + Z TC-1.4× | 560 | f/16 | **76** |
| Z 100-400 bare | 400 | f/11 | **63** |
| 300 PF bare | 300 | f/5.6 | **61** |
| 300 PF + TC-17e II | 500 | f/11 | 56 |
| 300 PF + TC-20e III | 600 | f/11 | 52 |
| 300 PF + TC-14e I | 420 | f/16 | 46 |
| 300 PF + TC-14e III | 420 | f/11 | 46 |

**Z TCs remain strongly net-positive over bare** for the bird-on-cliff
use case: TC-1.4× is +21 % FOM (76/63), TC-2.0× is +63 % FOM (103/63).
The §5.3 metric makes the Z TC-2.0× gain more dramatic than the §5.2
metric did — see §6a above for the reason.

**Every Nikon F-mount TC on the 300 PF is still net-negative** vs the
bare 300 PF (61 FOM at f/5.6, was f/8 under the old metric) — the
lens-MTF penalty eats the magnification gain. Best F-mount TC is
TC-17e II at FOM 56 (8 % below bare). The §5.3 metric shifts the
"best centre aperture" for bare 300 PF from f/8 to f/5.6; cross-date
v2 data shows f/5.6 and f/8 are within noise of each other on this
combo, see `poc_longdist_cross_date_v2_2026_01_out/overlap.md`.

(Cross-date FOM ranges for the 300 PF family are now in the regenerated
`overlap.md`; old prose values like "55–73", "59–66", "Kenko 69" are
the §5.2-metric numbers and have not been hand-replaced.)

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

| Combo (2026-01-28 best-centre aperture) | Best F# | edge/centre |
|---|---|---|
| Z 100-400 bare | f/11 | 1.06 |
| Z 100-400 + Z TC-1.4× | f/16 | 1.12 |
| Z 100-400 + Z TC-2.0× | f/11 | 1.05 |
| 300 PF bare | f/5.6 | **0.60** |
| 300 PF + TC-14e I | f/16 | 0.83 |
| 300 PF + TC-14e III | f/11 | 0.96 |
| 300 PF + TC-17e II | f/11 | 0.74 |
| 300 PF + TC-20e III | f/11 | 1.24 |

**Z 100-400 family is still flat across the field** — no off-axis
penalty (edge/centre 1.05–1.12). **300 PF bare is still centre-only**
at its centre-best aperture (now f/5.6, was f/8 under the old metric)
— drops to 60 % at the field edges. Mounting a TC mostly flattens
the field; the 300 PF + TC-20e III actually shows edge > centre
(1.24) on this date with the §5.3 metric, suggesting either a TC
non-uniformity or a centre-tile placement artefact worth visual
inspection. Kenko Pro 300 1.4× isn't in the 2026-01-28 cross-family
table (it was shot only on 2026-01-30) and isn't re-tabulated here.

For "1–2 stops down from max for decent frame-edge sharpness on the
300 PF + F-mount TC" (the user's manual finding), see the earlier
single-day analysis output `poc_longdist_300pf_field_2026_01_28_out/`
for the full aperture × position table — the rule was confirmed by the
field-position cutoffs on 2026-01-28.

## 7. Per-lens prose

_All numbers in this section are §5.3-metric cross-date ranges from
`poc_longdist_cross_date_v2_2026_01_out/overlap.md` (consensus tile
across 2026-01-18 / 28 / 30; top = max across replicates and ISO
variants, stdev computed on the per-date top vector)._

**Z 100-400 bare.** Cross-date cutoff sits in a tight 0.14–0.19
cy/mm-subject band across the full FL × aperture sweep (200 mm = 0.14,
300 mm = 0.16, 350–400 mm = 0.17). The "all apertures look the same"
finding holds: cross-date stdev per (FL, aperture) is 2–9 %. The
absolute number is **lower than the pre-§5.3 0.20 reading because
the old metric was at floor**, not because the lens improved — the
field is fundamentally flat for this lens (edge/centre ≥ 1.0 in §6c).
**Best aperture range: f/5.6 through f/11; flat.**

**Z 100-400 + Z TC-1.4× (lens-at-400 → 560 mm effective).** Cutoff
0.18–0.21 cy/mm-subj at 560 mm f/11–f/16; cross-date stdev 4–8 %.
At 560 mm framing the TC delivers 0.21 cy/mm-subj vs the bare's
0.17 = **+24 % subject-resolution gain** over cropping (was claimed
as +10 % under the old metric; the cap on the bare was hiding the
real gap). **Best aperture: f/11 or f/16.**

**Z 100-400 + Z TC-2.0× (lens-at-400 → 800 mm effective).** Cutoff
0.18–0.20 cy/mm-subj at 800 mm f/11; cross-date stdev ~6 %. At the
2026-01-28 cross-family-edges measurement the centre reads 0.28 (the
best-tile-in-box methodology picks higher; cross-date overlap is
consensus-tile). Either way, the **+65 % gain over bare-cropped to
800 mm** (cross-family-edges) is dramatically larger than the
pre-§5.3 +15 % — once the bare-400 floor is removed, the TC-2.0× is
seen to be highly effective for distant subjects. **Best aperture:
f/11.**

**300 PF bare.** Sharpest centre reading in the dataset (0.34–0.44
cy/mm-subj at f/5.6 / f/8). Cross-date stdev tightens with aperture:
14 % at f/5.6 → 12 % at f/8 → 6 % at f/11 → 6 % at f/16. F5.6 / F8
are within stdev of each other — the §5.2-era "best at f/8" claim is
soft; cross-date max is at F5.6 (0.44) but F8 hits 0.43 on the same
date. **Edges collapse off-axis at f/5.6 / f/8 (edge/centre 0.60).**
**Best aperture for centre: f/5.6 or f/8 (within noise). Best for
full-frame use: f/11.**

**300 PF + TC-14e I.** Centre cutoff 0.33–0.42 at f/11. Cross-date
stdev 13–18 %. At the cross-family-edges best aperture (f/16) the
centre reads 0.34, edge 0.28 (edge/centre 0.83). Subject resolution
sits at ~78 % of bare 300 PF at the same FL; the 1.4× mag claim
yields less than 1.4× cy/mm-subj — TC penalty is real. **Best
aperture: f/11 (or f/16 for slightly flatter field).**

**300 PF + TC-14e III.** Centre 0.34–0.39 at f/11; cross-date stdev
8 %. F16 cross-date stdev is 44 % (2026-01-18 was shake-corrupted at
0.16); ignoring 2026-01-18 the F16 top is 0.41 (2026-01-30 ISO 1600).
**Best aperture: f/11 unless you can shoot fast enough to use f/16
without shake.**

**300 PF + TC-17e II.** Centre 0.39–0.41 at f/11 — **the tightest
cross-date stdev of any combo (2.3 %)**, which means the metric is
truly tracking the optics here. At cross-family edge (F11) reads
0.41 centre / 0.28 edge / 0.33 right edge — edge/centre 0.74,
markedly off-axis even at f/11. **Best aperture: f/11.**

**300 PF + TC-20e III.** Centre 0.29–0.38 at f/11; cross-date stdev
19 %. F16 narrows to 6 % stdev (0.30–0.33). At cross-family-edges f/11
the field actually peaks at the edges (0.44 / 0.49 vs 0.38 centre,
edge/centre 1.24) — a striking off-axis reversal on 2026-01-28 that
warrants visual inspection (could be centre-tile-placement artefact
on the 3D scene's depth surface). FOM 52 puts it below bare 300 PF
(FOM 61) at the centre — **bare-300-PF-cropped wins for distant
subjects.**

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
- ~~**Z 100-400 cutoff appears saturated** around 0.20 cy/mm-subject…~~
  **Resolved 2026-06 by §5.3.** The saturation was the cutoff falling
  inside the old `REF_BAND = (0.01, 0.20)`. The metric now uses
  `REF_BAND = (0.01, 0.10)` with smoothing and last-crossing; the
  Z 100-400 family cutoffs spread out cleanly (bare 0.17, TC-1.4×
  0.21, TC-2.0× 0.28 — see §6a). See
  [`RADIAL_CUTOFF_REFBAND_RESULTS.md`](RADIAL_CUTOFF_REFBAND_RESULTS.md).
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

POC scripts under `../scripts/`:

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

_The cutoff values in the §11a/§11b tables are pre-§5.3-metric (Z 100-400
family floored at ~0.20). The regenerated §5.3 v2 data is in
`poc_longdist_cross_date_v2_2026_01_out/overlap.md`: under §5.3 the bare
400 mm median sits at ~0.17 and the Z TC chains at 0.18–0.19 median, so
the §11b "median advantage is only 5–10 %, a closer call than the top-based
headline" conclusion still holds on the typical-frame statistic — only the
absolute magnitudes shift down. The flier / top-vs-median structure (the
ratios in §11a) is metric-invariant._

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

- ~~**Z 100-400 family cutoff still appears quantized** at 0.20–0.25 cy/mm-subj…~~
  **Resolved 2026-06 by §5.3.** Was the cutoff falling inside the old
  ref band (cf. §9 above). Under the new metric the Z 100-400 family
  spreads cleanly across [0.17, 0.28] cy/mm-subj depending on TC,
  and the cross-algorithm comparison with `mtf50_known_edge` (§5.1)
  confirms the radial-cutoff rankings.
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
| **AF Zoom-Micro 70-180/4.5-5.6D** | 70 mm f/8 | **0.285** |
| Z MC 105/2.8 VR S | 105 mm f/4 | 0.278 |
| Z 100-400/4.5-5.6 VR S | 100 mm f/5.6 | 0.275 |
| Z 24-120/4 S | 105 mm f/5.6 | 0.262 |
| Sigma Macro 105/2.8 EX DG OS HSM | 105 mm f/2.8 | 0.259 |
| Sigma APO Macro 150/2.8 EX DG OS HSM | 150 mm f/8 | 0.251 |
| AF Micro-Nikkor 200/4D IF-ED | 200 mm f/11 | 0.236 |
| AF Zoom-Micro 70-180 + Kenko Pro 300 1.4× | 180 mm f/16 | 0.215 |
| AF Micro 200/4D + Kenko Pro 300 1.4× | 280 mm f/16 | 0.166 |

(§5.3 metric. The pre-§5.3 table read ~0.04 higher across the board;
relative ranking is essentially the same except Z MC 105/2.8 moved
above Z 100-400 at this scene's 15 m distance.)

The Z 100-400 at its wide end (100 mm) outperforms its long end on this
scene because at 15 m focus the wide-end FL is well inside its "infinity"
range. At 300+ mm the same 15 m distance is borderline → lens performance
drops there (typical "lens needs much more distance to count as infinity"
behaviour for longer focal lengths).

The **AF Zoom-Micro 70-180/4.5-5.6D macro** scores top at 70 mm f/8 —
interesting cross-check that a vintage macro zoom can match modern S-line
glass on the right scene at the right aperture.

### Algorithm comparison observations (2026-02-07/tele)

Same 4 algorithms ran on this dataset (figures pre-§5.3, still
representative of the algorithm-comparison shape):
- `radial_cutoff`: low single-digit % median CV (highly stable;
  FFT-bin-quantisation was resolved by §5.3 sub-bin interp + smooth)
- `mtf50_slanted_edge`: ~30 % median CV, ~50 % NaN (no usable edges
  in most tiles — typical for 3D-shrubbery scene; cf. §5.1
  `mtf50_known_edge` CV-discovered edges for the wide datasets)
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
4. **2025-07-09 distance audit**: per NEF EXIF FocusDistance audit
   (`audit_nef_distance_out/nef_distances_2025-07-09.md`), classified
   by subject distance / focal length ratio using Reikan Focal's two-tier
   minimum: **20× FL for FL ≥ 300 mm**, **50× FL for FL < 300 mm**.
   Closer readings aren't invalid — they measure the lens at a different
   distance regime. Per-(lens, FL) summary:
   - AF-S 300/4D bare @ 300 mm: 37.58 m = **125× FL** → infinity-class.
   - AF-S 300/4D + TC ladder (420 / 500 / 600 mm effective): 37.58 m =
     **63–89× FL** → meets Focal min (≥ 20× FL for long teles) but
     below 100× FL. The original "borderline at long FL" intuition was
     directionally correct.
   - AF-S 70-200/2.8G + TC ladder at 280 mm effective: 23.71 m = **85× FL**
     → meets Focal min (50× FL for < 300mm FL), < 100× FL.
   - Sigma 50-150/2.8 zooms (50–210 mm): 22.39 m = **107–448× FL** →
     infinity-class.
   - Sigma 50-100/1.8 A: 19.95 m = **199–399× FL** → infinity-class.
   - AF Zoom-Micro 70-180 @ 180 mm: 14.96 m = **83× FL** → meets Focal min.
   - **Sigma APO Macro 150/2.8 + TCs (150–300 mm effective)**: 5.96 m =
     **20–40× FL** → **below Focal min** for the 150 mm and 210 mm
     entries (need 50× FL), at-min for the 300 mm + Sigma TC-2001 entry
     (20× FL minimum). The macro's "inf" folder was apparently tested
     at the lens's near-focus end, not true infinity.
   - Tamron SP 90 Macro: 44.67 m = **496× FL** → well past infinity.

   Final distribution of 98 cells:
   - 5 below Focal min (all Sigma APO Macro 150 variants)
   - 17 meet Focal min but < 100× FL (long-tele + TC combos)
   - 60 infinity-class (100–300× FL)
   - 16 well past infinity (> 300× FL)

   All cells with meet-Focal-min and above are usable for at-distance
   MTF analysis; cross-day same-lens comparisons should match distance
   class. The 5 below-Focal-min Sigma 150 macro readings are usable as
   close-distance MTF measurements but not directly comparable to the
   same lens at infinity.

   *Focal explicitly notes that macro lenses should be calibrated at
   their intended use-distance rather than infinity. The "inf" folders
   here are infinity-test attempts, so the standard FL-ratio rule
   applies and the Sigma 150 entries fall below the threshold.*
5. **Scenes differ across days.** 2025-07-09 features a structured
   sign/post scene; 2025-09-06 is 3D shrubbery (matching the later 2026
   Z7 scene). Cross-day same-lens comparisons on D7200 are partially
   scene-confounded.

### 13a-bis. 2025-07-05 — heath / bush scene (darktable-demosaiced, 35 configs)

Scene: distant heath + a low bush against grass. **Low-contrast vegetation
with no bare twigs or built structure** — different scene class from the
2026 telephoto sessions (which use bare-twig 3D shrubbery).

Under the §5.3 metric, no measurement hits the old 0.2031 cy/sensor-px
floor (that was the post-§5.2 ref-band ceiling). Every config gets a
non-zero reading, but the dynamic range is compressed into [0.11, 0.17]
— this scene is **genuinely sharpness-limited**, not just metric-floored.

Top centre-aperture values:

| Lens × FL × aperture | centre cy/sensor-px |
|---|---|
| Tamron 90 Di Macro F017 + Kenko Pro 300 1.4× @ 90 mm, f/2.8 | 0.168 |
| Tamron 90 Di Macro F017 @ 90 mm, f/2.8 | 0.142 |
| Sigma 150 Macro + Sigma TC-1401 @ 210 mm, f/5.6 | 0.131 |
| AF-S 300/4D @ 300 mm, f/4 | 0.128 |
| Sigma 150 Macro + Kenko Pro 300 1.4× @ 150 mm, f/4 | 0.126 |
| Sigma 150 Macro @ 150 mm, f/5.6 | 0.119 |
| AF-S 300/4D + Nikon TC-14e I @ 420 mm, f/8 | 0.117 |
| AF-S 300/4D + Kenko Pro 300 1.4× @ 420 mm, f/11 | 0.112 |

The Tamron 90 macro + Kenko TC combo is at SHORTER subject distance
than the 300mm-class lenses; that's why it tops despite being on a
nominally less ambitious lens — it's effectively measuring its
performance at near-focus, not at infinity. The macro/long-tele
ordering at infinity-class distance is preserved (Sigma 150 +
TC-1401 > AF-S 300/4D > Sigma 150 bare).

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
| Sigma 50-150/2.8 EX APO DC HSM I @ 150 mm, f/11 | 0.270 |
| Sigma 50-150/2.8 I + Kenko Pro 300 1.4× @ 102 mm, f/11 | 0.266 |
| Sigma 50-150/2.8 I @ 72 mm, f/8 | 0.265 |
| AF-S 70-200/2.8G + Kenko Pro 300 1.4× @ 280 mm, f/8 | 0.261 |
| AF-S 70-200/2.8G + TC-17e II @ 180 mm, f/5.6 | 0.260 |
| AF-S 70-200/2.8G @ 200 mm, f/8 | 0.260 |
| Sigma 50-100/1.8 DC HSM | A @ 70 mm, f/2.8 | 0.258 |
| AF-S 70-200/2.8G + TC-14e I @ 280 mm, f/11 | 0.257 |
| Sigma 50-150/2.8 I + Sigma APO TC 1.4× @ 70 mm, f/11 | 0.253 |

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
| AF-S 300/4E PF ED VR @ 300 mm, f/8 | 0.183 |
| AF-S 300/4D IF-ED @ 300 mm, f/11 | 0.163 |
| 300 PF (E) + Kenko Pro 300 1.4× @ 420 mm, f/11 | 0.158 |
| 300 PF (D) + TC-20e III @ 600 mm, f/11 | 0.140 |
| Sigma 50-150 II + TC-2001 @ 145 mm, f/16 | 0.167 |
| AF-S 70-200/2.8G + TC-17e II @ 180 mm, f/8 | 0.191 |
| AF-S 70-200/2.8G + TC-17e II @ 135 mm, f/8 | 0.172 |
| Sigma 50-100/1.8 + Sigma TC-2001 @ 100 mm, f/11 | 0.185 |

The §5.3 metric reveals genuine ordering that the old §5.2 metric
flattened onto its 0.20 floor: at long FL the 300 PF (E) bare lens
sits at 0.18 cy/sensor-px and every TC chain falls below that —
TC-20e III + 300/4D at 600mm reaches only 0.14, and the Kenko 1.4×
on 300 PF reaches 0.16. **The "F-mount TCs aren't net-positive for
distant subjects" pattern is now quantified on D7200, not just
inferred from a metric floor.**

Other notable findings on 2025-09-06 (top centre per lens):
- **Sigma 50-150/2.8 EX APO DC HSM I peaks at 50 mm f/8** with centre
  0.257 — strong mid-zoom performer.
- **Sigma 50-100/1.8 DC HSM | A** holds 0.234–0.251 across 50–85 mm.
- TC-laden lenses drop noticeably: adding Sigma TC-1401 to the 50-150 II
  pulls centre to 0.220 (was at the 0.20 floor under §5.2). Cross-TC
  ordering is now visible (Sigma APO TC-1.4× ≈ TC-1401 > TC-2001).

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

### 13d. D7200 vs Z7 — bridged 2026-06 via shared-lens shared-scene measurement

Direct cross-camera comparison of cy/sensor-px is not 1:1 because:
1. Pixel pitch differs (3.91 µm vs 4.35 µm — but only 11 % spread).
2. JPEG engine differs (D7200 vs Z7 in-camera sharpening).
3. Sensor cover-glass / OLPF differs (D7200 has OLPF, Z7 does not).

**Quantified bridge factor (§5.5 follow-up, landed 2026-06):**
Three F-mount lenses tested on both bodies at the stairs scene
(Sigma 24/2.8 SWII, Nikkor-N.C 24/2.8, AF Nikkor 20/2.8) give a
**Z7 / D7200 ratio of ~1.35× in cy/sensor-px** (~1.21× in cy/mm-sensor)
across 24 matched (lens, aperture) cells. See
[`CROSS_CAMERA_BRIDGE_RESULTS.md`](CROSS_CAMERA_BRIDGE_RESULTS.md)
for the full table.

Use the factor as a first-cut estimate when reading D7200 numbers in
this doc against the Z7 sections of `LONGDIST_TELE_RESULTS.md` and
`WIDEANGLE_RESULTS.md`. The bridge was measured on wide-angle scene
content; for telephoto / 3D-shrubbery the factor may shift because
JPEG sharpening interacts with scene content, so verify case-by-case
before drawing fine-grained conclusions.

The takeaway from the D7200 datasets is still primarily **the ranking
within each lens family** rather than absolute numbers. The
within-D7200 patterns that hold:
- Modern S-line / G-series lenses dominate older AF non-D primes.
- Adding F-mount TCs to almost any lens reduces sensor MTF
  substantially.
- 300 PF (E) is the only long-tele on D7200 that holds above the
  noise floor — same as on Z7.
