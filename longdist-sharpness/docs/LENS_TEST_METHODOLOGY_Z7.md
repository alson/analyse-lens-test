# Lens-test methodology — Z7 era (scene design + metric pitfalls)

Reusable, hard-won methodology for long-distance lens / teleconverter
sharpness tests on the **Nikon Z7**, distilled from the 2026-06-28 Z TC-1.4×
revalidation. Worked example with the actual numbers:
[`CAPTURE_2026-06-28_tc14_revalidation.md`](CAPTURE_2026-06-28_tc14_revalidation.md).
Read this before planning the next test.

---

## Part A — Scene & capture design (what changed for the Z7)

### A1. The sloped-scene trick is retired — use a flat frontal target
The old D7200 protocol picked *sloped* subjects (vegetation on a slope,
stairs) so that, given the DSLR's open-loop phase-detect AF (separate module,
per-lens AFMA), the true focal plane landed *somewhere* in frame and the
"pick the sharpest patch" analysis sidestepped focus error. The **Z7 is
closed-loop** (on-sensor PDAF; Pinpoint AF is contrast-detect *at the imaging
plane*), so that defect class is gone. The slope was never free — it
converted a focus problem into a depth-variance problem (off-centre patches
sit at a different distance, confounding edge-vs-centre sharpness with
defocus). **Use a flat, frontal, perpendicular target** (a wall) so the field
is measurable — essential for reading **decentering / tilt**, the #1 defect
of a replacement TC.

### A2. Replace passive focus-insurance with focus-shift shooting
Best implementation of the focus bracket = the Z7 **focus-shift shooting**
feature: focus just in front of the subject, smallest step (1), electronic
shutter, manual fixed exposure (AE-L), several stacks per cell. It guarantees
crossing true peak (unlike AF re-trigger, which only samples AF
repeatability) and the stack doubles as a per-region through-focus
tilt/decentering diagnostic. **Separate the two shot types in analysis**
(EXIF `SilentPhotography`: On = focus-shift frame, Off = Pinpoint-AF
replicate).

### A3. AF shots can be shake-softened; stacks usually win
The Pinpoint-AF replicates often use the **mechanical shutter + remote** and
are few (≈3); in wind they read *softer* than the electronic-shutter
focus-shift stacks (best-of-many). So "AF = most accurate centre" does **not**
always hold — prefer the focus-shift stack for the centre too (at step 1 the
focus-quantisation worry is moot).

### A4. Frame a wall *patch* that fills the sensor — don't tilt up, don't crop
At 560–800 mm / ~45 m the FOV is tiny (~1.5–3 m of wall), so a level camera at
~1.8 m lands the whole frame on façade with no ground. Don't tilt up
(keystone) and don't crop the bottom (that discards the lower corners =
half the decentering field). Align with the EVF **virtual horizon** (roll +
pitch) and the building's own H/V lines (yaw); you need *identical* alignment
across configs (free from an unmoved tripod), not perfect perpendicularity.

### A5. Distance: sufficient, not maximum
Aim for the *flat part* of the MTF-vs-distance curve, not the farthest point.
≥ ~50× FL is plenty (≈ 40 m at 800 mm); beyond that, extra distance only adds
**atmosphere** (shimmer/haze → frame-to-frame variance). Use the brick-count
rangefinder if the focus scale is uninformative (Z 100-400 jumps 15 m → ∞):
at 400 mm each brick (210 mm Waalformaat + 10 mm joint) ≈ 2.45 m of distance.

### A6. Aperture: shoot wide-open, then step down — and the **widest is the
most informative** for measurement
The widest aperture is furthest from both edge-saturation and the documented
f/11–f/16 MTF50 over-read (Part B). For TC comparisons, compare at the widest
**common** aperture (bare f/5.6, TC-1.4× f/8 → use **f/8**; TC-2.0× wide-open
is f/11, so it can't join an f/8 comparison — that's physics, not a gap).

### A7. Put the high-contrast *and* fine detail at the CENTRE
A TC frame is a centred crop of the bare frame — **the centre is the same
physical spot** in all configs (modulo tripod slip), so centre is the natural
like-for-like region. But the comparison only works if that shared centre
**has measurable detail**. On 2026-06-28 the wall's centre was plain brick;
the chalk/placard edges sat off-centre, so bare had *zero* central edges and
the cross-config comparison broke. **Next time: place a low-contrast,
fine-detail target dead-centre.** (Brick mortar is fine detail and everywhere,
incl. centre — see B2 for why it still didn't save MTF50.)

---

## Part B — Analysis: metric pitfalls (the metric mattered more than the data)

On 2026-06-28 three metrics in turn gave the *physically impossible*
tc14 < tc20 (a 1.4× cannot retain less than a 2.0×). Each was an artifact:

### B1. `radial_cutoff` saturates for a sharp lens
It floored at ~0.20–0.25 cy/sensor-px for the Z 100-400 family in 2026-01 and
again on the 2026-06-28 wall — the lens out-resolves the metric's
discriminating band. Workhorse for *soft* / textured scenes; unreliable for
sharp glass. (The §5.2/§5.3 sub-bin + ref-band rewrites help but don't cure
it here.)

### B2. MTF50 saturation = **lens sharpness, not contrast**
MTF50 is the frequency where the *contrast-normalised* MTF crosses 0.5, so
contrast cancels — a low-contrast but **crisp** edge (brick mortar) caps at
the 0.49 Nyquist limit exactly like a high-contrast one. Masking bright
features or hunting low-contrast edges does **not** fix saturation; the lens
is simply sharp. (Chalk edges only dropped below Nyquist because chalk is
physically *fuzzy* — which then partly measures chalk-blur, not the lens.)
For a sharp lens, MTF50-from-JPEG is the wrong tool.

### B3. Measure MTF on **linear, demosaic-only RAW** — JPEG is contaminated
In-camera JPEG **sharpening** halos push MTF@Nyquist > 1.0 (and the tone curve
distorts the ESF). Developing the NEFs to linear (rawpy:
`gamma=(1,1), no_auto_bright=True, output_bps=16, use_camera_wb=True,
demosaic=AHD`; no sharpening / no lens corrections; luma = channel mean)
removed the halo (MTF@Nyq back ≤ 1.0) and pulled MTF50 off the Nyquist cap →
the comparison finally became physical (bare ≥ tc14, retention ≈ 0.77). This
is why we shoot RAW + JPEG. Measure in **linear light**.

### B4. Detect edges on a gamma'd image, measure on linear
Canny finds ≈0 edges on linear light. Normalise + apply gamma ≈ 1/2.2 for
*detection*, then run the MTF measurement on the underlying **linear** float.

### B5. The f/11–f/16 over-read is an analysis bug, not physics
`measure_edge_metrics` over-reads MTF50 (above the diffraction ceiling) at
f/11–f/16 and throws MTF@Nyq outliers > 1.0 **even on linear RAW** — a
left/right trough-wall asymmetry in the LSF (see
[`LONGDIST_HANDOVER.md`](LONGDIST_HANDOVER.md) §5.6e and root
`SHARPNESS_METRICS.md`). **Workaround: report the MEDIAN across edges, never
the max.** Until fixed, single-edge readings at f/11+ are unreliable — another
reason to shoot/measure wide (A6).

### B6. `top`/`max` reducer is frame-count biased on focus-shift stacks
Reducing a focus-shift stack by its **max** rewards bigger stacks (60-frame vs
160-frame cells) because max-of-more-frames is mechanically higher. Use a
**fixed top-k mean** (k = 3) so stacks of different sizes compare fairly.

### B7. Cross-series / cross-scene comparison: anchor, don't compare absolutes
Different scene (shrubbery vs wall) and possibly different JPEG quality make
absolute cutoffs incomparable across sessions. Use **bare + TC-2.0× as anchors
present in both series** (unchanged hardware) and compare MTF-retention ratios
vs the bare anchor; the shared scene/quality/metric-version cancels. (JPEG
quality was *checked* not assumed: 2026-01 is FINE-class, ~2× the 370 kB/MP
that 2025-07-05 showed sufficient, so it is not the confound.)

---

## Part C — What "validated" looked like (the worked example)

For the replacement Z TC-1.4× (2026-06-28, see the capture log for full
numbers): **retention ≈ 0.77–0.80 of the bare lens** (MTF50 on linear RAW,
brick mortar edges, f/8), matching the lost copy's ~0.80; **+8 % subject-
resolution FOM** over cropping the bare frame; **symmetric field** (no
decentering). → a good, well-centred copy. The "+X % over cropping" magnitude
needed RAW; the decentering check worked on JPEG.

### Scripts (TC-revalidation track)
| Script | Purpose |
|---|---|
| `../rename_and_sort_lens_test.py` (repo root of analyse-lens-test) | Ingest: rename flat capture → digiKam pipe convention (exiv2 translated values; native Z LensModel carries the TC, adapted F-mount falls back to translated LensIDNumber) and sort into `<lens ISO>/<focal>/<F>/`, NEF+JPG together. Dry-run default; `--apply`. |
| `scripts/poc_longdist_tc14_revalidation.py` | Within-session radial_cutoff: AF-vs-stack split (SilentPhotography), 3×3 grid, retention + L/R/T/B decentering. Top-3 reducer. (Saturated → superseded for retention.) |
| `scripts/poc_longdist_tc14_edge_summary.py` | Edge-MTF50 retention/decentering on the `poc_known_edge_mtf50 dataset tele2026_06_28` output. |
| `scripts/poc_longdist_tc14_triangle.py` | Same-feature retention via the green placard (showed MTF50 saturation + JPEG halos). |
| `scripts/poc_longdist_tc14_f8_masked.py` | f/8, placards masked, brick/chalk edges. |
| `scripts/poc_longdist_tc14_brick.py` | Brick mortar edges (dense, central, low-contrast). |
| `scripts/poc_longdist_tc14_raw.py` | **The clean result**: linear demosaic-only RAW (rawpy) + MTF@Nyq/MTF50 on mortar edges. |
