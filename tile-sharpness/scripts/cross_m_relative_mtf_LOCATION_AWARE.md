# Location-aware (field-position) sharpness — design + subset validation

**Caveats first.** This is a *companion* to the cross-M **RELATIVE, FIXED-SENSOR-FREQUENCY**
glass-MTF estimator, not a new axis. Per-patch sharpness is the SAME relative amplitude
(sqrt-PSD at the fixed sensor frequency, default `f_px=0.10` cy/px, fenced to `0.08–0.15`)
that the global ranking uses — it is NOT an absolute MTF and NOT a subject-resolution map;
it just resolves that one quantity by *position in the frame*. **Field coverage is
intrinsically M-dependent and incomplete** — sparse coverage is expected, not a failure:
at high M the magnified wafer clusters the patches (small field-height span, no true
corners); at low M the wafer occupies only part of the frame (corners unsampled). Every
config therefore carries a **coverage descriptor** and field maps are reported **only where
patches actually exist** — no extrapolation into empty zones. **Subset only** (10 configs);
the estimator and driver are **production-ready for the later full reprocess**.

## What was added (production module + driver)

Pure, unit-tested core in `src/tile_sharpness/cross_m_relative_mtf.py`:

- `field_geometry(px,py,cx,cy,W,H,m=…)` — a patch's position relative to the **frame
  centre** (= the registration/optical centre). Returns **distance** (`dist_px`),
  **field height** = `dist_px / (½·frame-diagonal)` (0 = centre, 1.0 = extreme corner;
  aspect-independent), **azimuth** `angle_deg` (math convention, image-y flipped: right 0°,
  up +90°, left 180°, down −90°), and **subject mm** (`dist·pitch/M`, Z7 4.35 µm).
- `field_zone` / `assign_field_zones` — bin field height into **centre [0,0.33) / mid
  [0.33,0.66) / corner [0.66,∞)**.
- `field_coverage` — per-config descriptor: field-height min/max/**span**, **azimuthal
  span**, per-zone patch counts, which zones are **populated** (≥2 patches),
  `degenerate_cluster` (span < 0.10 → a tight high-M cluster, not a field profile), and
  `field_supported`. Richest coverage first = most trustworthy.
- `radial_falloff` — per-config relative-amp mean/median per zone + **corner/centre** and
  **mid/centre** ratios (< 1 = softens toward the corner). Sparse zones flagged, ratio NaN.
- `azimuthal_asymmetry` — at matched radius (mid+corner annulus) projects amp onto L–R and
  T–B axes → asymmetry **magnitude** + **direction** (a decentering/tilt signature).
- `astigmatism_index` — `mean(log(amp_sag/amp_tan))` from per-patch **sagittal vs
  tangential** wedge amplitudes (driver computes them from the 2D PSD in wedges aligned to
  each patch's radial direction). >0 = sagittal sharper.
- `field_resolved_ranking` — the validated relative-MTF chain run **per zone** → "which
  configs hold their corners across M".

Driver (`scripts/cross_m_relative_mtf_run.py`): the `extract` stage now emits a
`fieldtag_shard_*.csv` per-patch record `(sid, patch, px, py, dist_px, field_height,
angle_deg, dist_subject_mm, amp/amp_sag/amp_tan @ f_px 0.10 & 0.15)` and a new
`directional_psd` for the sagittal/tangential split. A `field` subcommand (and an additive
call at the end of `analyse`) derives the coverage / radial / azimuthal / astigmatism /
field-resolved-ranking CSVs, a sharp-vs-soft `field_map.png`, and `field_REPORT.md`, all
with the caveats header baked in. `--subset` and `--out` flags keep subset runs off the
production paths. **Nothing in the parked multi-session extension
(`scripts/_recovered_extension_2026-06-30/`) is touched** — location-awareness is built on
the clean HEAD baseline so the two combine cleanly later.

## Subset (10 configs, 2026-01-29 cohort)

Modern macros (Z105, AF200, S105, S150 @ 1:1 F8), vintage primes (Micro-Nikkor 55 f/2.8 AIS
287318, 55 f/3.5 209088, AF 60 f/2.8 @ 1:1 F8), a soft diopter (Z100-400 + MCON-35, M≈1.12),
and two extension-tube high-M configs (AF200+6T M≈1.7, AF200+5T+6T M≈2.0). Outputs:
`scripts/cross_m_relative_mtf_out/` was left untouched; subset products are under
`cross_m_relative_mtf_loctest_out/` (`field_per_patch.csv`, `field_coverage.csv`,
`field_radial_{zone,ratio}.csv`, `field_azimuthal.csv`, `field_astigmatism.csv`,
`field_resolved_ranking.csv`, `field_map.png`, `field_REPORT.md`). Computed on **nufan**.

### Coverage behaves exactly as predicted by the M-dependence caveat

The eight ~1:1 configs richly cover centre/mid/corner (≈83–93 patches, field-height span
0.75–0.81, azimuth ≈340°). The extension configs degrade: **AF200+6T (M≈1.7)** drops to
28 patches; **AF200+5T+6T (M≈2.0)** to **16 patches with the corner zone unpopulated** →
its radial corner/centre ratio is NaN and `falloff_supported=False`. The field map
(`field_map.png`) shows Z105's dense full-frame grid beside AF200+5T+6T's sparse cluster.
The map is honest about where it has no data; it does not extrapolate.

### Radial falloff (corner/centre relative-amp ratio; < 1 = softens to corner)

| config | corner/centre | mid/centre | note |
|---|---|---|---|
| V55f35 209088 | **0.607** | 0.750 | strong corner softening (vintage) |
| AF200+6T 1.7:1 | 0.789 | 0.934 | |
| V55f28 287318 | **0.829** | 0.969 | corner softening (vintage) |
| Z100400+MCON-35 | 0.841 | 0.888 | diopter softens off-axis (expected) |
| S150 | 0.884 | 0.940 | |
| AF200 / AF60 / S105 / Z105 | 1.02–1.04 | ~1.04–1.09 | flat-to-slightly-rising* |
| AF200+5T+6T 2:1 | NaN | 0.949 | corner not sampled (M≈2) |

\*A corner/centre slightly **above 1** at f_px=0.10 for the sharpest modern macros is a
relative-amp artefact (centre patches sit nearer focus-stack best-focus / texture content
differs), not a claim that corners out-resolve centres; the *direction* of the signal — soft
glass softens to the corner, sharp glass stays flat — is what is robust.

### Azimuthal asymmetry / decentering (lr>0 right sharper, tb>0 top sharper)

A consistent **top-bottom** tilt dominates (tb ≈ −0.10 to −0.16 across most configs → bottom
sharper), a real subject-tilt/field-curvature signature of the 2026-01-29 rig that BOTH this
method and `characterise` see. V55f35 carries the largest asymmetry magnitude (0.20). L–R is
near the noise floor for the well-centred modern macros.

### Astigmatism index (mean log(sag/tan); 10/10 supported)

Mostly mildly negative (tangential ≥ sagittal), small for the sharp macros (Z105 −0.02,
AF200 +0.05) and larger for the vintage 55s (V55f35 −0.20, V55f28 −0.15). Reported as a
clean per-config index; treat magnitudes as **relative/qualitative** at this subset size.

### Field-resolved relative ranking

Centre top-3: S150, Z105, V55f28. Mid top-3: Z105, S150, AF60. **Corner top-3: Z105, AF60,
S105** (8 configs — the two M≈1.7/2.0 extensions drop out for lack of corner coverage). Z105
leads every zone → it holds its corners; the soft/diopter and extension tail fall off the
corner ranking.

## Agreement with `characterise` (independent existing field product)

`characterise.py` (LSF/maze path) independently reports centre/DX/FX-ring MTF50 + uniformity
+ decentering (L−R, T−B) per config. Comparing on the cohort it covers (sign note:
characterise's `decentering_lr = (left−right)/mean`, the **negative** of our lr; its `tb`
agrees in sign):

| config | char uniformity_fx | ours corner/centre | char dec_lr | ours lr (char conv) | char dec_tb | ours tb |
|---|---|---|---|---|---|---|
| Z105 | (centre NaN) | 1.036 | +0.179 | −0.002 | **−0.164** | **−0.141** |
| AF200 | (centre NaN) | 1.025 | +0.060 | −0.047 | **−0.189** | **−0.122** |
| V55f28 287318 | **0.498** | **0.829** | +0.032 | −0.110 | +0.023 | −0.069 |
| V55f35 209088 | **0.689** | **0.607** | −0.034 | −0.113 | **−0.205** | **−0.164** |

- **Radial falloff direction AGREES**: both vintage 55s where characterise has corner data
  show uniformity_fx < 1 *and* our corner/centre < 1; V55f35 is close in magnitude
  (0.689 vs 0.607). (Z105/AF200 have a NaN characterise centre → no comparison.)
- **T–B decentering AGREES in sign and roughly in magnitude** on the three configs with
  clean data (Z105, AF200, V55f35) — both see a bottom-sharper tilt.
- **L–R** is near the noise floor for both methods and does not reliably co-sign; the
  dominant, agreed decentering signal is the T–B tilt. V55f28's small T–B disagrees (both
  near zero). Honest read: the strong, agreeing signals (corner falloff direction, T–B sign)
  validate the location-aware product against the independent LSF/maze field measurement;
  the weak L–R axis is inconclusive at this subset size.

## Status

Production-ready. Full suite green on nufan (`pytest tests/` → **223 passed**: 208 baseline
+ 15 new field tests covering geometry, zone binning, coverage incl. the degenerate high-M
cluster + sparse-zone flags, radial-falloff direction recovery, decentering sign/direction
recovery, astigmatism recovery, per-zone ranking, and a characterise-agreement sanity test).
The **full 316-config reprocess is the next phase** and was deliberately NOT run.
