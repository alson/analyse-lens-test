# Long-distance & wide-angle sharpness — session handover

State as of 2026-06-XX (handover written at the end of a multi-day
session covering long-distance telephoto and wide-angle / standard
lens-test analysis on both Z7 and D7200).

This doc is for the next chat session picking up the work. Read it first.
The detailed numbers and per-lens prose are in [`LONGDIST_TELE_RESULTS.md`](LONGDIST_TELE_RESULTS.md)
and [`WIDEANGLE_RESULTS.md`](WIDEANGLE_RESULTS.md); methodology is in
[`SHARPNESS_METRICS_LONGDIST.md`](SHARPNESS_METRICS_LONGDIST.md).

## 1. What was done this session

Telephoto and wide-angle / standard lens-test sessions analysed,
spanning 2025-07-05 through 2026-02-07, on two camera bodies:

- **Z7 (FX, 4.35 µm)**: 2026-01-18, 2026-01-24, 2026-01-26, 2026-01-28,
  2026-01-30, 2026-02-07/20mm, 2026-02-07/telephoto
- **D7200 (DX, 3.91 µm — separate sections in the docs)**: 2025-07-05
  (NEF-only, dt-demosaiced), 2025-07-09, 2025-09-06, 2025-09-10, 2025-09-11

Commits on `main` (tile-sharpness/analyse-lens-test):

```
f28bd2b — don't exclude below-Focal-min readings, just label them
3c9625f — Focal two-tier FL-ratio rule (20× for ≥300mm, 50× for <300mm)
75d617e — replace fixed-threshold distance validity with FL ratio (later refined)
ec98edc — NEF distance audit for 2025-07-09 + 2025-09-11
2afc009 — develop 2025-07-05 NEFs via darktable-cli (scene-limited result)
b34bf34 — extend long-distance to 2026-02 + D7200 datasets
fd949a3 — initial 2026-01 long-distance & wide-angle analysis
```

All analysis-related files committed; the unrelated `wafer-atlas/`
working tree changes are from another session/track — leave them
alone.

## 2. Core methodology (compressed)

### 2.1 Sharpness algorithms

Four algorithms run on identical tile selections by
`poc_longdist_algorithms.py`:

1. **`radial_cutoff`** — primary. Normalised radial-spectrum cutoff
   in cy/sensor-pixel. Hyper-stable (0 % median CV), full coverage,
   fully lighting-invariant.
2. **`mtf50_slanted_edge`** — ISO-12233-style auto-detect. 60–70 %
   NaN rate on real scenes; current auto-detect doesn't fire on the
   scene's visible edges (handrails / stair treads / wall horizon).
   **The user just asked for a CV-based edge ROI rewrite — see §5.1
   pending work.**
3. **`vol`** — variance of Laplacian, gradient-domain. Stable but
   tracks brightness quadratically (−50 % at −0.5 EV, +273 % at
   +1 EV). Same-lighting use only.
4. **`brenner`** — squared pixel diffs at lag 2. Interchangeable with
   `vol` (Spearman ρ ≥ 0.96).

For telephoto / 3D-shrubbery scenes use `radial_cutoff`; only
`mtf50_slanted_edge` becomes interesting if the planned CV-edge-ROI
upgrade lands and starts producing usable data on structured scenes.

### 2.2 Consensus tile selection (movement rejection)

Per (search-box, replicate) compute gradient-energy map → median
across replicates → highest-median position is "the static feature"
in this slice. Rejects cyclists / pedestrians (which only contribute
to one replicate's gradient).

Movement-flag column in per_measurement.csv marks cells where
replicate gradient-max positions disagreed.

### 2.3 Replicate spread reporting

v2 cross-date analysis (`poc_longdist_cross_date_v2_2026_01.py`) pools
all replicates and ISO variants per (lens, FL, aperture, position) and
reports:
- `top` — max cutoff (the "best the lens delivered")
- `median` — typical cutoff
- `min` — worst replicate
- `top_vs_median` — flier indicator (≥ 1.10 = top is a lucky frame)
- `range_pct` — total spread relative to median

### 2.4 Distance class (Focal two-tier rule)

Per [Reikan Focal docs](https://blog.reikanfocal.com/faq/ideal-distance-for-afma-auto-focus-calibration/):
- **FL ≥ 300 mm**: 20× FL minimum (curve stabilises earlier for long teles)
- **FL < 300 mm**: 50× FL minimum

Distance / FL classification:
- `below Focal min` — under per-FL minimum. NOT excluded from analysis;
  just labelled. Useful as close-distance MTF measurement, not directly
  comparable to infinity-class readings of the same lens.
- `meets Focal min, < 100× FL`
- `infinity-class (100–300× FL)`
- `well past infinity (> 300× FL)`

Macros: Focal explicitly says calibrate at intended use-distance
rather than infinity. "inf" folders here are infinity tests so the
standard rule applies.

### 2.5 Lens-encoder lookup (derivable from slug)

- D / G / E aperture suffix: encoded (e.g., `AF Micro-Nikkor 60mm f_2.8D`,
  `AF-S 50/1.8G`, `AF-S 300mm f_4E PF`).
- Z-mount native: encoded.
- AIS / Nikkor-N.C / PC-Nikkor / Sigma 24/2.8 SWM / AF non-D-G-E:
  no encoder. EXIF FocusDistance reports a default ~0.01–0.06 m.

For non-encoder lenses, distance inferred from the temporally-nearest
encoder-equipped frame (the tripod was not moved between lenses in
the same sub-session, per user methodology).

Encoder presence check is hardcoded in `audit_nef_distance.py`'s
`lens_has_encoder()`.

## 3. Per-dataset state

| Date | Camera | Scope | Distance class | Notes |
|---|---|---|---|---|
| 2026-01-18 | Z7 tele | Z 100-400, 300 PF + TC ladder, ISO 100 only | infinity-class | Cross-date v1 + v2 analysed |
| 2026-01-24 | Z7 wide | 14-60 mm primes / zooms | mostly infinity-class | 4-algorithm comparison done |
| 2026-01-26 | Z7 wide | Same + Viltrox 16/1.8 + AF-every-pic variants | mostly infinity-class | 4-algorithm comparison done |
| 2026-01-28 | Z7 tele | Full TC ladder both families | infinity-class | Field-position sweeps + cross-family edge |
| 2026-01-30 | Z7 tele | Deeper sampling, ISO ladder, **Kenko Pro 300 (new)** | infinity-class | Cross-date v1 + v2 analysed |
| 2026-02-07/20mm | Z7 wide | 4 lenses at 20 mm | infinity-class | New scene-content note: grass-dominated centre, less structural |
| 2026-02-07/tele | Z7 tele | Mid-tele + macros at infinity | infinity-class | 4-algorithm done |
| 2025-07-05 | D7200 tele | Macros + 300/4D + 70-200 + Tamron 90 | mostly infinity-class | **Scene-limited result**: heath + bush, 32/35 cells at metric floor |
| 2025-07-09 | D7200 tele | Sigma DC zooms + 300/4D ladder + 70-200 ladder | mixed (5 below-min Sigma 150 macro variants, 17 long-tele near-infinity) | NEF distance audit done; original "borderline at long FL" intuition confirmed for the long-tele TC combos at 63–89× FL |
| 2025-09-06 | D7200 tele | 300 PF + TC ladder + DC zooms | infinity-class | Big dataset (837 configs) |
| 2025-09-10 | D7200 wide | UWA + DX zooms + Sigma 18-35/1.8 | infinity-class | Same stairs scene as Z7 wide-angle dates |
| 2025-09-11 | D7200 mid | 18 lenses incl. AIS, Nikkor-N.C, PC-Nikkor | mixed (5 below-min cells in the DX 18-70 + DX 35/1.8G close-distance sub-session, 35 infinity-class) | NEF→JPEG fallback in audit (no NEFs on disk for this day) |

## 4. Key findings carried into the docs

These are the surprising / non-obvious takeaways:

1. **TC vs cropping the bare 400 mm frame** (`LONGDIST_TELE_RESULTS.md` §6a):
   bare-cropped + upsampled cannot exceed the bare-lens cutoff (info
   theory). Z TC-1.4× delivers +10 %, Z TC-2.0× +15 % over bare-cropped
   ceiling (top numbers; median numbers are smaller: +5–10 %).

2. **Z 100-400 bare-vs-TC effective focal length labelling fix**: the
   directory `Z 100-400 + Z TC-2.0× / 400.0 mm` is `lens-at-200mm + TC`
   = 400 mm effective, NOT `lens-at-400mm + TC` = 800 mm. The earlier
   `LONGDIST_TELE_RESULTS_2026-01-28.md` had this wrong; superseded by
   `LONGDIST_TELE_RESULTS.md` which uses EXIF-effective FL consistently.

3. **Distant fixed subject FOM ranking** (FOM = sensor cy/px × f_eff):
   Z 100-400 + Z TC-2.0× at 800 mm f/11 dominates. Every Nikon F-mount
   TC on the 300 PF is net-NEGATIVE vs bare 300 PF. Kenko Pro 300 1.4×
   is competitive with bare 300 PF (new finding from 2026-01-30 deep
   sampling).

4. **Z 100-400 family edge/centre ≈ 1.0–1.08** (flat field at all FLs,
   bare or with Z TCs). **300 PF bare at f/8 edge/centre = 0.60**
   (centre-only lens at its centre-best stop). Stop down for edges
   on the F-mount + TC combos: best is consistently f/11.

5. **Algorithm comparison** (`WIDEANGLE_RESULTS.md` §3): radial_cutoff
   wins. mtf50_slanted_edge auto-detect fails on real edges
   (60–70 % NaN). vol/brenner same-family.

6. **Wide-angle centre cluster vs edges**: Z 14-24/2.8 S leads centre
   (0.348 cy/sensor-px at 24 mm f/4); Viltrox AF 50/2 Z best 50 mm;
   AF-S DX 35/1.8G best 35 mm. **But centres are FFT-bin quantized**
   so differences within 0.30–0.35 cluster aren't reliable. **Edges
   open up a wider spread**: F-mount primes drop right edge to 0.20
   floor at centre-best aperture; Z/Viltrox AF lenses hold edges close
   to centre. Viltrox 16/1.8 has strong right-edge asymmetry wide-open
   through f/2.8 (right edge stuck at 0.20).

7. **Visual confirmation of "stop down for edges"** on legacy primes
   matches the user's manual notes (AF 20/2.8 fuzzy edges until f/5.6,
   Z 14-24 slightly less sharp than Z 20/1.8 at edges until f/5.6,
   Viltrox 20mm Air good centre from f/2.8 but edges need f/5.6, Z
   20/1.8 best wide-open). All these match the F-mount-drops-right-
   edge-to-0.20-floor pattern in the data.

8. **2025-07-05 scene-limited**: heath/bush content has too little
   high-frequency texture for radial_cutoff to discriminate. 32 of
   35 cells at metric floor. Vol/brenner produce noise too. No
   algorithm in the current framework ranks this dataset.

## 5. Open follow-ups (priority order)

### 5.1 CV-based edge ROI for `mtf50_slanted_edge` — LANDED 2026-06

**Status: landed. See [`MTF50_KNOWN_EDGE_RESULTS.md`](MTF50_KNOWN_EDGE_RESULTS.md).**

Implementation: `scripts/poc_known_edge_mtf50.py` (discover + dataset
modes) and `scripts/poc_known_edge_mtf50_compare.py`. Output under
`scripts/poc_known_edge_mtf50_out/<dataset>/`. NaN rate dropped from
38–71 % (auto-detect) to 9–19 %; replicate CV from ~35–85 % to
single-digit medians; Spearman ρ vs `radial_cutoff` went from
essentially zero to 0.34–0.52 across all five wide-angle datasets.

The original "planned" notes below are kept for context. Open
follow-up: §5.2 sub-bin interpolation is now the next bottleneck —
many sharp edges saturate the new metric at the ≈0.49 cy/px Nyquist
cap. Telephoto / 3D-shrubbery scenes still don't benefit from this
algorithm (no usable structural edges).

User specifically asked for a computer-vision approach since we know
which structural objects are in each scene-class. Auto-detect currently
misses them. Plan:

1. Per scene-class (stairs scene on 2026-01-24/26, 2025-09-10/11,
   2026-02-07/wide; sloped-stair scene; 2025-07-09 sign-post scene),
   pick one reference sharp image and use Read to confirm scene content.
2. Canny edge → Hough lines on the reference. Filter by length (≥ 200 px)
   and orientation (avoid near-horizontal/vertical for ISO 12233 aliasing).
3. Score candidate edges by gradient strength and contrast on both
   sides; keep top-K.
4. For each tested image of that scene-class: re-detect lines OR
   template-match the reference's strong edges to find corresponding
   location (small framing differences across days).
5. Extract 256×128 ROI around each detected edge → modified
   slanted-edge MTF50 that uses the **given** dominant direction
   rather than auto-detecting it.
6. Add as new algorithm `mtf50_known_edge` alongside the existing
   `mtf50_slanted_edge` (don't replace — comparison value).
7. Re-run on wide-angle datasets; expect NaN rate to drop from
   60–70 % to ~20 %, CV from 34 % to single digits.

Telephoto / 3D shrubbery scenes have no usable edges — keep skipping
mtf50 there. 2025-07-09 D7200 has the sign-post scene which would
benefit.

Suggested entry-point script: `../scripts/poc_known_edge_mtf50.py`.
Dependencies: opencv-contrib-python is already in `tile-sharpness/pyproject.toml`.

### 5.2 Sub-bin interpolation on radial_cutoff — LANDED 2026-06

**Status: landed. See [`RADIAL_CUTOFF_SUBBIN_RESULTS.md`](RADIAL_CUTOFF_SUBBIN_RESULTS.md).**

`alg_radial_cutoff` in `poc_longdist_algorithms.py` now linearly
interpolates between bracketing FFT bins at the `CUTOFF_THRESHOLD =
0.05` crossing. Three datasets (wide2026_01_24, wide2026_02_07,
mid2025_09_11) see 5–15× more distinct measurement values with
Spearman ≈ 1.0 to the pre-fix output (rankings preserved).

Two datasets (wide2025_09_10 D7200, wide2026_01_26 Z7) show no
improvement — their actual cutoff falls *inside* the ref band, so
they sit at the metric's floor regardless. That's a metric issue,
not an interpolation issue. Addressed in §5.3 below.

### 5.3 `radial_cutoff` ref-band + smoothing — LANDED 2026-06

**Status: landed. See [`RADIAL_CUTOFF_REFBAND_RESULTS.md`](RADIAL_CUTOFF_REFBAND_RESULTS.md).**

`alg_radial_cutoff` now uses `REF_BAND = (0.01, 0.10)` (was 0.20),
Gaussian-smooths the normalised spectrum (σ=2 bins), and locates the
last-crossing rather than the first. The two previously-stuck
datasets gain 10–23× more distinct centre values; the three already-
good datasets keep their rankings (Spearman 0.97–0.98 vs §5.2).

**Downstream impact — same units, different scale.** Absolute
`radial_cutoff` numbers in `LONGDIST_TELE_RESULTS.md` and
`WIDEANGLE_RESULTS.md` are now ~12 % lower for sharp Z7 measurements
and higher for soft cases that were previously floored. Rankings
within each comparison are preserved (except where the old metric
was at floor, in which case the new metric reveals previously-hidden
ordering). The cross-date analysis scripts have NOT been re-run yet
— left as deliberate follow-up so the headline analysis docs can be
edited with the new numbers.

### 5.3 Apply distance-class labelling to existing plots

The cross-day comparison plots (e.g., `combined_field_curves.png` in
`poc_longdist_cross_family_edges_2026_01_28_out/`) silently mix readings
that are now classified as different distance classes. Adding distance-
class markers (or filtering to one class per plot) would prevent
misreading. Low-priority polish — the per-measurement CSVs preserve
the data; only plots need re-emitting.

### 5.4 2026-02-07/wide scene-content confound

The Z 14-24 at 20 mm vs Z 20/1.8 S centre ranking on 2026-02-07 is
suspicious — the consensus tile picker landed on grass texture
(different scene content than 2026-01-24's stairs centre). User's
visual finding "Z 20/1.8 best" contradicts the data, likely due to
the scene-content issue. Either:
- (a) Re-frame the analysis to pick a different ROI (the edge of
  the frame where structural content is) — needs the §5.1 CV work
  to land first
- (b) Drop the centre-only comparison for this dataset and report
  edge values instead

### 5.5 D7200 cross-camera bridge factor — LANDED 2026-06

**Status: landed. See [`CROSS_CAMERA_BRIDGE_RESULTS.md`](CROSS_CAMERA_BRIDGE_RESULTS.md).**

Three F-mount lenses (Sigma 24/2.8 SWII, Nikkor-N.C 24/2.8, AF
Nikkor 20/2.8) appear in both D7200 (2025-09-10) and Z7 (2026-01-24
or 2026-02-07) wide datasets at the stairs scene. Cross-camera
ratio at matched (lens, FL, aperture, best position):

- **Z7 / D7200 in cy/sensor-px: ~1.35×** (median across 24 ratios)
- **Z7 / D7200 in cy/mm-sensor: ~1.21×** (factors out the small
  pitch difference — D7200 3.91 µm vs Z7 4.35 µm is only an 11 %
  spread, so the cy/mm conversion barely moves the ratio).

Multiply D7200 `radial_cutoff` by ~1.35 to compare against a Z7
reading in cy/sensor-px (or 1.21 if working in cy/mm-sensor). The
factor captures Z7's no-OLPF + JPEG-pipeline advantage net of the
pitch difference.

## 6. Gotchas the next session should know about

### 6.1 EXIF FocusDistance stripped from JPEG MakerNotes on some days

2025-07-09 JPEGs have FocusDistance stripped (it's in MakerNotes,
which Nikon's JPEG path apparently doesn't preserve sometimes). 2025-09-11
has no NEFs at all on disk but its JPEGs preserve distance.

`audit_nef_distance.py` handles this: tries NEFs first, falls back to
JPEGs.

### 6.2 NEF-embedded JpgFromRaw is Nikon "basic" quality

For 2025-07-05 (flat NEFs at lens-dir level, no co-located JPEGs):
the NEF-embedded `JpgFromRaw` is Nikon basic quality (~113 kB/MP)
which crushes high-frequency content. The first pass collapsed all
35 configs to the radial_cutoff metric floor.

**Workaround in `extract_2025_07_05_jpegs.py`**: use `darktable-cli`
to demosaic NEFs at full FINE quality (~370 kB/MP at jpeg quality 92).
Yields valid (if scene-limited) JPEGs.

Race-condition gotcha during extraction: if you parallel-launch the
extraction script accidentally, you can end up with truncated JPEGs.
Run only once or check for truncated files afterwards (PIL.Image.load
will raise on truncated).

### 6.3 Z 100-400 + Z TC focal-length labelling

Directory names use **EXIF effective FL** not lens-setting FL. E.g.
`Z 100-400 + Z TC-2.0× / 400.0 mm /` contains shots of the *lens at
200 mm* with the TC making them 400 mm effective. NOT the lens at
400 mm. EXIF FocalLength confirms: `200-800mm f/9-11` for TC-2.0×
system, with FocalLength = 400 mm for these shots.

For "TC at lens-long-end" data, look in `/ 560.0 mm /` (TC-1.4× system,
lens at 400 mm) or `/ 800.0 mm /` (TC-2.0× system, lens at 400 mm).

### 6.4 Cross-replicate position scatter ≠ AF jitter

For "AF for every pic" folders: the user re-triggered AF between
replicates **to sample multiple focal-plane positions in 3D scenes**,
not to test AF repeatability. Treat replicate-count as statistical
power of the best-pick metric, not as an AF measurement.

### 6.5 ISO ladder is shake-avoidance not noise-comparison

On 2026-01-30 specifically, the user shot multiple ISO variants at
small apertures specifically because shutter was borderline for shake
on long lenses in wind. Pick the SHARPEST-of-ISO (which v2 cross-date
does), not the lowest-ISO. The lowest-ISO can be shake-corrupted at
f/16 / f/22.

### 6.6 Scene content varies across sessions even at same location

Same physical scene (the stair / handrail location near user's home)
is reused across years and dates, but the **framing differs**:
- 2026-01-24/26 — wide framing, stairs+handrails in centre
- 2026-02-07/wide — lower framing, grass in centre, stairs at edges
- 2025-09-10/11 — different sub-positions per session

Cross-day same-lens comparisons need to consider this. The consensus
tile picker locks onto whatever has the highest gradient in the
search box, which differs across dates.

### 6.7 The 1_1 / 1_3 magnification subdirs

D7200 datasets occasionally have `inf` / `1_1` / `1_3` sub-folders per
lens for the macro lenses (testing at infinity, 1:1 macro, 1:3 macro).
For long-distance analysis use **`inf` only**. The algorithm script's
`_skip_macro_mag` filter handles this.

## 7. Quick-start commands

```bash
# Re-run any analysis script
cd /home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness
direnv exec . uv run python -u scripts/poc_longdist_algorithms.py wide2026_01_24

# Re-run the distance audit
direnv exec . uv run python -u scripts/audit_nef_distance.py

# Re-extract 2025-07-05 NEFs (if you delete the existing JPEGs)
direnv exec . uv run python -u scripts/extract_2025_07_05_jpegs.py

# Run a cross-date analysis
direnv exec . uv run python -u scripts/poc_longdist_cross_date_v2_2026_01.py

# Inventory of all dataset keys recognised by the algorithm script
grep '^    "' scripts/poc_longdist_algorithms.py | grep ':' | head -20
```

Output dirs are alongside the scripts (suffix `_out/`). Run-time per
dataset: 2–15 min depending on config count.

## 8. Files map

- **Methodology**: `SHARPNESS_METRICS_LONGDIST.md` (root)
- **Results**:
  - `LONGDIST_TELE_RESULTS.md` — Z7 + D7200 telephoto findings
  - `WIDEANGLE_RESULTS.md` — Z7 + D7200 wide-angle findings
- **Scripts** in `../scripts/`:
  - `poc_longdist_algorithms.py` — algorithm comparison, all 4 algos
  - `poc_longdist_cross_date_2026_01.py` — v1 cross-date (lowest-ISO)
  - `poc_longdist_cross_date_v2_2026_01.py` — v2 cross-date (replicate spread)
  - `poc_longdist_{100_400,300pf}_field_2026_01_28.py` — single-day field sweeps
  - `poc_longdist_cross_family_edges_2026_01_28.py` — cross-family edge comparison
  - `audit_nef_distance.py` — EXIF distance audit
  - `extract_2025_07_05_jpegs.py` — NEF→JPEG via darktable
- **Output dirs** (CSVs, MDs, PNGs):
  - `poc_longdist_algorithms_out/{wide,tele,mid}<dataset_key>/`
  - `poc_longdist_cross_date_2026_01_out/`
  - `poc_longdist_cross_date_v2_2026_01_out/`
  - `poc_longdist_{100_400,300pf}_field_2026_01_28_out/`
  - `poc_longdist_cross_family_edges_2026_01_28_out/`
  - `audit_nef_distance_out/`

## 9. Hard-won facts kept in memory but not always in docs

- D7200 has sensor cover glass + OLPF; Z7 does not. Cross-camera
  cy/sensor-px values are not directly comparable for this reason
  alone (pixel pitch is the secondary factor).
- Reikan Focal's [target-distance recommendation](https://blog.reikanfocal.com/faq/ideal-distance-for-afma-auto-focus-calibration/)
  is the two-tier rule used here: 20× FL for ≥ 300 mm, 50× FL
  otherwise. Macros: calibrate at intended-use distance.
- Lens-encoder presence: aperture-suffix D/G/E or Z-mount → encoded;
  AF non-D, AIS, manual focus → no encoder.
- The user's "AF for every pic" variants are *depth-sampling*, not
  AF-repeatability tests.

## 10. The bigger picture

These sessions established a working analysis pipeline for the user's
multi-year multi-camera lens-test dataset. The radial_cutoff metric
is the workhorse; the other three algorithms exist mainly to validate
that the rankings are not metric-specific.

The next big step is the CV-based edge ROI rewrite (§5.1) which should
unlock the slanted-edge MTF50 algorithm and provide a physical-units
cross-check. If that lands and the rankings agree with radial_cutoff,
the metric's FFT-bin quantization (§5.2) becomes the next bottleneck.

The user's photographic workflow informs the design: shoots multiple
distances per lens-FL on purpose, doesn't move the tripod within a
sub-session, prefers JPEG comparisons over RAW where reasonable (the
2025-07-05 case was the exception where RAW was necessary).
