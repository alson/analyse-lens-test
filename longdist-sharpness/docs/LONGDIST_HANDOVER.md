# Long-distance & wide-angle sharpness — session handover

State as of **2026-06-29** (handover updated at the end of a
2026-06 session that landed §5.1–§5.5 follow-ups, added MTF@Nyquist
+ MTF10 to the §5.1 algorithm, computed the D7200↔Z7 bridge, and
**landed the §5.6e slanted-edge MTF over-read fix** — centroid-Hann LSF
windowing, diffraction-ceiling validated; see §5.6e. Downstream
`mtf50_known_edge` dataset re-run under the fix is the new top
follow-up, §5.6f).

This doc is for the next chat session picking up the work. Read it first.
The detailed numbers and per-lens prose are in [`LONGDIST_TELE_RESULTS.md`](LONGDIST_TELE_RESULTS.md)
and [`WIDEANGLE_RESULTS.md`](WIDEANGLE_RESULTS.md); methodology is in
[`SHARPNESS_METRICS_LONGDIST.md`](SHARPNESS_METRICS_LONGDIST.md);
metric-change reasoning is in
[`MTF50_KNOWN_EDGE_RESULTS.md`](MTF50_KNOWN_EDGE_RESULTS.md),
[`RADIAL_CUTOFF_SUBBIN_RESULTS.md`](RADIAL_CUTOFF_SUBBIN_RESULTS.md),
[`RADIAL_CUTOFF_REFBAND_RESULTS.md`](RADIAL_CUTOFF_REFBAND_RESULTS.md),
[`CROSS_CAMERA_BRIDGE_RESULTS.md`](CROSS_CAMERA_BRIDGE_RESULTS.md).

## 2026-06 session — what landed

14 commits covering the §5 follow-up list plus enhancements:

| Commit | Topic |
|---|---|
| `85c15e5` | §5.1 CV-discovered slanted-edge MTF50 |
| `1a8b2f1` | §5.2 sub-bin interpolation on radial_cutoff |
| `bd914fe` | §5.3 ref-band + smoothing + last-crossing |
| `4656373` | Cross-date analyses refreshed under §5.3 |
| `31c53fa` | Result-doc §5.3 banners + §6 headline refresh |
| `bc73d41` | Tele datasets refreshed + LONGDIST_TELE §12/§13 prose |
| `5aa5652` | §7 per-lens prose + conclusions-changed summary |
| `ba09716` | §5.5 D7200 ↔ Z7 cross-camera bridge factor |
| `73d9aa7` | mtf50_known_edge: MTF@Nyquist + MTF10; §5.4 Z 20/1.8 |
| `bf9ba32` | Distance-class column on v2 cross-date tables |
| `775e30c` | §4a/c/d WIDEANGLE prose under §5.3 |
| `3381429` | Handover §5.3b (distance-class) marked landed |
| `a06267e` | §4b/§6.5 WIDEANGLE prose; telephoto §5.1 extension proposals |

**Metric changes — what shifted under §5.3:**

- `radial_cutoff`: REF_BAND lowered to (0.01, 0.10), Gaussian
  smoothing σ=2 bins, last-crossing instead of first-crossing.
  Absolute values are ~12 % lower for sharp Z7 measurements and
  *higher* for soft cases previously floored at 0.20.
- `mtf50_known_edge` (new §5.1 algorithm): CV-discovered Hough
  edges + ESF contrast normalisation + Tukey taper + smoothed
  spectrum. Reports MTF50, MTF@Nyquist, MTF10 frequency — three
  complementary numbers per measurement.

**Key conclusions that changed under §5.3** (not just rescaled):

1. Z TC effectiveness over bare-cropping went from +10 % / +15 %
   (1.4× / 2.0×) to +24 % / +65 %. The old metric capped the bare
   400 mm at the 0.20 floor, masking the bare-vs-TC gap.
2. Z 100-400 bare's "all apertures look the same" still holds, but
   the absolute level is 0.14–0.19 cy/mm-subj (not the blanket 0.20
   the floor was reporting).
3. 300 PF bare's "best centre aperture" is f/5.6, not f/8 (within
   noise of each other; the f/8 claim was an FFT-bin artefact).
4. **300 PF + TC-20e III edge/centre on 2026-01-28 reads 1.24** in
   the new metric (was 1.02) — could be 3D-scene focal-plane
   artefact, worth visual inspection before publishing.
5. D7200 long-FL TC chains previously all at 0.20 floor now show
   clear ordering: bare 0.183 > Kenko 1.4× 0.158 > TC-20e III
   0.140.
6. **Z 20/1.8 S top of 20 mm lineup on 2026-02-07** (MTF50_known_edge
   0.476, beats Z 14-24 at 0.427) — restored user's visual finding
   via §5.1 CV-edge picker bypassing the grass-centre confound.
7. **Cross-camera bridge factor: Z7 / D7200 ≈ 1.35×** in
   cy/sensor-px (1.21× in cy/mm-sensor — pitch differs only 11 %,
   so the units barely matter). Three F-mount lenses tested on
   both bodies at the stairs scene.

## 1. What was done this session

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
   NaN rate on real scenes; auto-detect doesn't fire on the scene's
   visible edges (handrails / stair treads / wall horizon).
   Superseded by **`mtf50_known_edge`** (§5.1, LANDED 2026-06) which
   CV-discovers long Hough edges on a sharp reference and measures
   MTF50, MTF@Nyquist, and MTF10 at the known direction. NaN rate
   dropped to 9–19 % on wide-angle datasets. See
   [`MTF50_KNOWN_EDGE_RESULTS.md`](MTF50_KNOWN_EDGE_RESULTS.md).
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

These are the surprising / non-obvious takeaways. **All numbers in
this section refer to the §5.3 metric** (post-2026-06). Sections in
the result docs that still cite pre-§5.3 values are flagged with a
banner; tables in §4 / §6 of WIDEANGLE_RESULTS.md and §6 / §12 / §13
of LONGDIST_TELE_RESULTS.md were refreshed.

1. **TC vs cropping the bare 400 mm frame** (`LONGDIST_TELE_RESULTS.md` §6a):
   bare-cropped + upsampled cannot exceed the bare-lens cutoff (info
   theory). Z TC-1.4× delivers **+24 %** (was +10 %), Z TC-2.0×
   **+65 %** (was +15 %) over the bare-cropped ceiling. The bare
   ceiling itself is 0.17 cy/mm-subj (was 0.20 — that was the
   §5.2 metric floor masking the gap).

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

4. **Z 100-400 family edge/centre ≈ 1.05–1.12** (flat field at all
   FLs, bare or with Z TCs). **300 PF bare at f/5.6 edge/centre =
   0.60** (centre-only lens at its centre-best stop; best-centre
   moved from f/8 → f/5.6 under §5.3). The 300 PF + TC-20e III at
   f/11 edge/centre 1.24 on 2026-01-28 is **anomalous** — likely a
   3D-scene focal-plane artefact, worth visual inspection.

5. **Algorithm comparison** (`WIDEANGLE_RESULTS.md` §3): radial_cutoff
   (§5.3) is still the primary; `mtf50_known_edge` (§5.1) is the new
   slanted-edge variant for wide-angle/stairs scenes. vol/brenner
   same-family.

6. **Wide-angle centre cluster vs edges**: Z 14-24/2.8 S leads centre
   (0.326 cy/sensor-px at 24 mm f/4 under §5.3); Z 24-120/4 S at
   24 mm f/5.6 takes the #2 spot (0.314); Viltrox AF 50/2 Z best
   50 mm (0.312). Pre-§5.3 the centre values clustered at 0.30–0.35
   due to FFT-bin quantization; that compression is **resolved**
   (442 distinct values across 535 measurements on wide2026_01_24).
   Edge values that hit the 0.20 floor pre-§5.3 (F-mount primes
   wide-open) resolve into 0.13–0.21 range, revealing the actual
   ordering. Viltrox 16/1.8 right edge wide-open is at 0.13–0.16
   (about half the left edge sharpness) — stronger
   stop-down-for-corners recommendation under §5.3.

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

### 5.3b Distance-class labelling on cross-date tables — LANDED 2026-06

(Original §5.3 in this list before the metric-fix §5.3 was added —
kept the original numbering for continuity.)

Addressed via the v2 cross-date overlap and per_date tables (which
now carry a `dist class` column per Reikan two-tier rule: 20× FL
minimum for FL ≥ 300 mm, 50× FL otherwise; 100× FL = infinity-class).
No actual cross-day PNG existed — `combined_field_curves.png` is
single-day 2026-01-28 data so it doesn't need the label. See
`poc_longdist_cross_date_v2_2026_01_out/overlap.md` for the labelled
table.

### 5.4 2026-02-07/wide scene-content confound — RESOLVED 2026-06 by §5.1

Followed path (a) — re-ran the dataset through the §5.1 CV-edge
MTF50 (`mtf50_known_edge`). The CV picker lands on stair-side
diagonals + paver boundaries spread across the frame (x_frac
0.29–0.93) rather than the grass-dominated centre. New ranking
under `mtf50_known_edge` median across edges:

  - **Z 20/1.8 S @ f/5.6: 0.476** (top)
  - Z 14-24/2.8 S @ 20 mm f/8: 0.427
  - AF Nikkor 20/2.8 @ f/8: 0.407
  - Viltrox AF 20/2.8 Z Air @ f/11: 0.379

User's visual finding restored. See
[`MTF50_KNOWN_EDGE_RESULTS.md`](MTF50_KNOWN_EDGE_RESULTS.md) §
"2026-06 — Z 20/1.8 ordering on wide2026_02_07 restored" and
[`WIDEANGLE_RESULTS.md`](WIDEANGLE_RESULTS.md) §4.6a (updated with
the new ranking).

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

### 5.6 Open follow-ups (post-2026-06)

The §5.1–§5.5 list landed in 2026-06. New items the next session
could pick up, in rough priority order:

#### 5.6a Extend `mtf50_known_edge` to telephoto datasets

The §5.1 algorithm currently requires ≥ 400-px Hough segments,
which is plentiful on the wide-angle stairs scene but sparse on
telephoto / 3D-shrubbery. Four concrete paths (full discussion in
[`MTF50_KNOWN_EDGE_RESULTS.md`](MTF50_KNOWN_EDGE_RESULTS.md)
"Extending to telephoto" section):

- **(A) Relaxed-length retry**: drop `HOUGH_MIN_LINE_PX` from 400
  to ~150 and re-run on telephoto datasets. Highest-confidence
  candidates: **2025-07-09 sign-post** (galvanised pole has real
  step edges) and **2026-01-28 / 30 hedge** (sky/hedge horizon +
  distant rooflines). Lowest effort first cut.
- **(B) Sky/hedge boundary segmentation**: brightness-threshold the
  sky region, take the bottom row of sky per column, smooth, then
  MTF perpendicular to local tangent. Most general but biggest
  engineering lift.
- **(C) Hand-pick edge coordinates per dataset**: open one sharp
  F8 reference, note (x, y, angle, length) for 2–6 edges, dump as
  JSON into the per-(lens, FL) `edges.json`. Zero algorithm risk;
  ~5 min manual labour per scene.
- **(D) Stay with `radial_cutoff` for true shrubbery** —
  2026-02-07/telephoto and similar edgeless scenes don't need a
  slanted-edge metric.

Recommendation: start with (A) on 2025-07-09 sign-post. The user
noted that some earlier 2025 and 2026-01/02 telephoto shots may
have usable edges; the late-2026 shots are pure shrubbery.

#### 5.6b 300 PF + TC-20e III edge/centre anomaly on 2026-01-28

§6c of `LONGDIST_TELE_RESULTS.md` shows the TC-20e III combo with
edge/centre **1.24** at f/11 (was 1.02 pre-§5.3). The §5.3 metric
shows edges peaking *above* centre — possibly a 3D-scene focal-plane
artefact (centre and edge branches at different depths) or a
centre-tile-placement issue. **Visual inspection** of the
2026-01-28 frames at this combo's 5 field positions would confirm
whether this is real off-axis-better-than-centre behaviour or an
analysis artefact. Output: brief note added to §6c.

#### 5.6c Spot-refresh remaining pre-§5.3 prose

Most of the per-lens prose in `LONGDIST_TELE_RESULTS.md` §7 and the
`WIDEANGLE_RESULTS.md` §4 / §6 tables were refreshed in 2026-06. A
few small narrative paragraphs further down the docs may still cite
pre-§5.3 numbers — banners at the top of each doc note this.
Rankings hold; only absolute magnitudes shift. Low-priority polish.

#### 5.6d Telephoto datasets in `mtf50_known_edge_out/`

The §5.1 algorithm has only been run on the five wide-angle / mid
datasets so far. If (A)/(C) above proves workable on a tele dataset,
add the relevant `tele*` keys to the DATASETS dict in
`poc_known_edge_mtf50.py` and run.

(Partly exercised: the 2026-06-28 TC-1.4× revalidation ran
`mtf50_known_edge` on `tele2026_06_28` — a brick climbing-wall scene —
with `--min-line-px 150–200`, path (A). It found plenty of edges; see
`docs/CAPTURE_2026-06-28_tc14_revalidation.md`.)

#### 5.6e Slanted-edge MTF over-read — improved metric LANDED 2026-06-29

**Status: best available metric landed; over-read reduced, not fully
eliminated.** `measure_edge_metrics` in `poc_known_edge_mtf50.py` now
windows the LSF with a **Hann centred on its centroid** and renormalises
by the DC bin (`LSF_PROFILE = dict(window="centroid_hann")`) — the
standard ISO-12233 LSF treatment.

*What the over-read actually was* (investigated 2026-06-29, more nuanced
than the 2026-06-28 single-cause guess). Three contributions, in
descending size:

1. **Max-over-frames picking (dominant).** The scary numbers (MTF@Nyq up
   to ~2.4, MTF50 well over the ceiling) came from taking best-focus =
   *max* of the metric over ~30–60 frames per edge — that selects the
   single spurious spike frame. It is a *harness* choice, not the LSF
   metric, and no LSF tweak fixes it. Use a per-edge **median across
   in-focus frames** and the tail is sane.
2. **Asymmetric-LSF handling (the part the fix addresses).** The old
   end-of-ROI taper left the longer / noisier LSF tail intact, mildly
   inflating the FFT high-frequency magnitude. centroid-Hann windowing
   fixes this — but on real edges the per-edge effect is *modest*
   (ΔMTF50 ≈ −0.007 at f/16; see paired result below). Its bigger payoff
   is **edge yield** (3× more edges measured).
3. **Demosaic aliasing residual (unfixable in the LSF stage).** On the
   no-OLPF Z7, AHD demosaic folds above-Nyquist content back in-band, so
   sharp diffraction-limited edges still read ~5–12 % over the f/16
   ceiling even after the fix. The diffraction-ceiling clamp + median
   rule remain necessary.

(The macro scribe-LINE over-read is a *different* code path: there the
asymmetry is between the two *walls* of a dark trough, mitigated by
`lsf_mtf50(combine="min")`. That two-wall trick does not transfer to
single step edges. The 2b-padedge wafer worktree is unrelated, abandoned
scribe-line work.)

*POC* — `scripts/poc_lsf_overread_fix.py` (run on nufan), two yardsticks:

1. **Synthetic** — ESF built from a known PSF (symmetric Gaussian range,
   asymmetric half-Gaussian, diffraction Airy), off-centred + noisy,
   with the *analytic* MTF as ground truth. All variants are unbiased
   (~3 %) on clean edges; under a non-flat background (the over-read
   driver) centroid-windowed variants stay accurate (~7 %) while the
   baseline degrades to ~11 %.
2. **Real RAW** — 2026-06-28 brick wall, bare + TC-1.4× at f/8/11/16,
   **in-focus AF frames, per-edge median across frames** (the original
   "best-focus = max over frames" pick was itself inflating every
   variant — the old max~2.4 MTF@Nyq was largely a max-pick artefact,
   not the metric). Compared against the diffraction ceiling
   (`tile-sharpness/optics.py`).

*Result (centroid_hann vs the old end-taper).* Read these honestly —
the win is real but is **mostly edge yield + a modest per-edge
reduction, not a full over-read elimination**:

- **Edge yield ~triples.** The centred window tolerates lower-contrast /
  off-centre edges, so NaN rate plunges (e.g. f/11 bare 248 → 763
  usable; ~500 edges measured that the old metric rejected). This is the
  biggest practical win — per-edge / decentering maps and sparse-edge
  telephoto become viable.
- **MTF@Nyq tail drops:** f/11 bare p95 0.75 → 0.53, Nyq>1 → 0 %.
- **Per-edge over-read reduction is modest.** Paired *same-edge*
  comparison (`poc_lsf_overread_paired.py`): at f/16 over-ceiling
  70 % → 59 %, median ΔMTF50 −0.007; at f/11 bare 20 % → 17 %, ΔMTF50 ≈ 0.
  The larger aggregate-median drop (f/16 0.225 → 0.194) is **partly a
  population effect** — the extra soft edges hann measures pull the
  aggregate down — not a pure per-edge improvement.
- **The scary numbers were a max-pick artefact, not the metric.** The
  previously-reported max MTF@Nyq ~2.4 came from picking best-focus =
  *max over ~30–60 frames* per edge; that selects the one spurious spike
  frame and is unchanged by any LSF tweak. With a per-edge median across
  in-focus frames the tail is sane (p95 ≤ ~0.5).
- **Residual over-read remains** on sharp, diffraction-limited edges
  (f/16 sharp common edges still ~59 % over the ceiling). centroid
  windowing can't remove it; the likely cause is demosaic aliasing on
  the no-OLPF Z7 near Nyquist (a slanted-edge fundamental), plus the
  metric's own ~3 % bias seen on clean synthetic edges. So the
  diffraction-ceiling clamp + "median, never max" rule still apply.
- centroid_hann beat fixed-width Tukey windows (clip the lobe when
  narrow → over-read), `mirror` (no gain on single edges), and a
  derivative/sinc correction (negligible) — and is the simplest.

*Validation artefacts:* `scripts/poc_lsf_overread_fix_out/summary.md`
(full variant table). The refactor that made one LSF→MTF code path
(`_build_esf` + `_esf_to_metrics(**LSF_PROFILE)`) was checked
byte-equivalent to the pre-fix code on the `endtaper` default.

*Remaining caveat — the "median, never max" rule still stands.* The fix
removes the **systematic** median over-read (f/16 median now sits on the
ceiling) and triples edge yield, but individual *(edge, frame)* readings
can still spike — `poc_longdist_tc14_raw.py`, which picks best-focus =
**max over frames** per edge, still shows max MTF@Nyq ~2.3 (a max-pick +
defocus artefact, not the metric; its median stays ≤ 1.0 and the
TC-1.4× retention PASS is unchanged). So aggregate across in-focus
frames per edge with a **median** — then per-edge / decentering maps are
physical. Do not trust a single-frame single-edge reading at f/11+.
A worthwhile follow-up is to switch `poc_longdist_tc14_raw.py` (and
similar) from max-over-frames to a robust focus pick (median, or pick
the frame by a focus measure then read its metric).

**Downstream re-run still owed (new top follow-up — see §5.6f):** the
cached `poc_known_edge_mtf50_out/` results and the §4.6 / §5.4 numbers
in the result docs were computed under the old `endtaper` metric.
Rankings are expected to hold (centroid_hann is monotonic with sharpness
and preserved orderings on the brick data), but absolute MTF50 values
shift down ~5–12 % and the 0.49-Nyquist saturation eases.

#### 5.6f Re-run wide/mid `mtf50_known_edge` datasets under the over-read fix

The five wide/mid datasets in `poc_known_edge_mtf50_out/` predate the
§5.6e fix. Re-run `poc_known_edge_mtf50.py dataset <key>` for each and
refresh the cited numbers in `MTF50_KNOWN_EDGE_RESULTS.md` §Results,
§2026-06 Z 20/1.8, and `WIDEANGLE_RESULTS.md` §4.6a. Confirm the Z 20/1.8
> Z 14-24 ordering on wide2026_02_07 survives (it should). Run on nufan.

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
- **Metric-change result docs** (all 2026-06):
  - `MTF50_KNOWN_EDGE_RESULTS.md` — §5.1 CV-edge MTF50 + MTF@Nyquist
    + MTF10 algorithm and results; includes "Extending to telephoto"
    proposals (§5.6a target).
  - `RADIAL_CUTOFF_SUBBIN_RESULTS.md` — §5.2 sub-bin interpolation.
  - `RADIAL_CUTOFF_REFBAND_RESULTS.md` — §5.3 ref-band + smoothing.
  - `CROSS_CAMERA_BRIDGE_RESULTS.md` — §5.5 D7200 ↔ Z7 bridge factor.
- **Scripts** in `../scripts/`:
  - `poc_longdist_algorithms.py` — algorithm comparison, all 4 algos.
    Exports `find_cutoff_from_spec()` shared by the cross-date scripts.
  - `poc_known_edge_mtf50.py` — §5.1 CV-edge MTF algorithm
    (discover + dataset + debug-all-segments modes).
  - `poc_known_edge_mtf50_compare.py` — §5.1 vs auto-detect summary.
  - `poc_longdist_cross_date_2026_01.py` — v1 cross-date (lowest-ISO);
    superseded by v2.
  - `poc_longdist_cross_date_v2_2026_01.py` — v2 cross-date with
    distance-class column.
  - `poc_longdist_{100_400,300pf}_field_2026_01_28.py` — single-day field sweeps.
  - `poc_longdist_cross_family_edges_2026_01_28.py` — cross-family edge comparison.
  - `audit_nef_distance.py` — EXIF distance audit.
  - `extract_2025_07_05_jpegs.py` — NEF→JPEG via darktable.
- **Output dirs** (CSVs, MDs, PNGs):
  - `poc_longdist_algorithms_out/{wide,tele,mid}<dataset_key>/` — all
    refreshed under §5.3 in 2026-06.
  - `poc_known_edge_mtf50_out/<dataset>/` — §5.1 per-(lens, FL)
    overlay + edges.json + per_measurement.csv (3 metric columns).
  - `poc_longdist_cross_date_2026_01_out/`,
    `poc_longdist_cross_date_v2_2026_01_out/` — refreshed §5.3 +
    distance-class column on the v2 MD tables.
  - `poc_longdist_{100_400,300pf}_field_2026_01_28_out/` — refreshed §5.3.
  - `poc_longdist_cross_family_edges_2026_01_28_out/` — refreshed §5.3.
  - `audit_nef_distance_out/`.

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
