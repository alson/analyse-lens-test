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
The widest aperture is furthest from edge-saturation and diffraction. The
f/11–f/16 over-read that used to make "shoot wide" mandatory is now **fixed
(B5)**, so f/11–f/16 are usable when **ceiling-gated (B9)** — which lets the
**TC-2.0× join at its f/11 wide-open** via matched-aperture, ceiling-gated
retention (B10) rather than being excluded. Caveat: stopping down forces a
slower shutter, so on a windy day keep it gust-frozen by floating ISO (A8).

### A7. Put the high-contrast *and* fine detail at the CENTRE
A TC frame is a centred crop of the bare frame — **the centre is the same
physical spot** in all configs (modulo tripod slip), so centre is the natural
like-for-like region. But the comparison only works if that shared centre
**has measurable detail**. On 2026-06-28 the wall's centre was plain brick;
the chalk/placard edges sat off-centre, so bare had *zero* central edges and
the cross-config comparison broke. **Next time: place a low-contrast,
fine-detail target dead-centre.** (Brick mortar is fine detail and everywhere,
incl. centre — see B2 for why it still didn't save MTF50.)

### A8. Freeze gust first, float ISO to afford it, burst for lucky imaging
Tripod + VR-off in wind → **wind-induced rig vibration** is the dominant blur
on a gusty day. It flattened the bare MTF-vs-aperture curve on 2026-06-28 — a
gust+defocus artefact lucky imaging later undid, recovering a real f/8 peak
(B8). Blur is angular → scales with effective FL. **Shutter floor 1/f_eff;
target 2–4× faster** (≈1/800 @ 400 mm, 1/1600 @ 800 mm); faster while a gust is
blowing. The original stopped-down TC cells ran 1/100–1/250 — 3–8× too slow.
**Float ISO** (Auto-ISO + min-shutter) to hold that shutter, cap ~ISO
3200–6400; ISO does **not** bias the contrast-normalised MTF (B2), so you need
NOT repeat the full aperture series at every ISO — the only failure mode is
high-ISO **×** low-contrast (the 2026-01-28 ISO-8000 twilight collapse). And
shoot a **locked-focus rapid burst at best focus** (find focus via the sweep or
AF, then lock and burst): with non-constant wind a calm instant gets captured
and the analysis lucky-images it (B8). A **focus-shift stack is inefficient for
this** — it spends most frames on defocus, leaving only ~10–15 in-focus frames
to sample wind; a locked-focus burst gives dozens, which is what actually pins a
marginal cross-config call (e.g. TC-1.4× vs cropping).

### A9. Target: high-contrast, fine, flat, large — and single-depth
Brick mortar is too low-contrast, and **3D scenes mis-rank** (the 2026-01
foliage "edge>centre" was a depth / pick-sharpest-tile artefact — different
field positions land on different depths). Want a **single-depth flat** surface
with **high-contrast fine detail**, large enough to fill the frame: at 45 m an
FX 400 mm frame is ~4 m wide (800 mm ~2 m), so the target must be **≥ ~2–4 m**.
Found-urban options: a **glazed facade's window-mullion grid** (high-contrast
slanted edges, flat, large — best found target), **perforated/expanded-metal
cladding or mesh** (fine periodic detail), **large printed signage/hoardings**.
Most repeatable: a **printed vinyl banner** (~1.5–2 m, slanted-edge /
checkerboard / Siemens-star), mounted flat — controlled contrast + slant, and
reshootable on a calm day.

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

### B5. The f/11–f/16 over-read — FIXED 2026-06-29 (was an analysis bug, not physics)
`measure_edge_metrics` used to over-read MTF50 (above the diffraction ceiling)
at f/11–f/16 and throw MTF@Nyq outliers > 1.0 **even on linear RAW** — an
asymmetric LSF inflating the FFT tail. **Fixed (§5.6e): a Hann window centred
on the LSF centroid + DC renormalisation** (`LSF_PROFILE = centroid_hann`; see
[`LONGDIST_HANDOVER.md`](LONGDIST_HANDOVER.md) §5.6e + root
`SHARPNESS_METRICS.md`). f/11–f/16 are now measurable — the TC-2.0× joins at
its f/11 wide-open. Two rules still apply: **report the median across edges**
(per-frame outliers persist), and **gate on the diffraction ceiling (B9)** —
the over-read bites *near-ceiling* (sharp) edges, so a soft wide-open config at
f/11 is reliable while a sharp stopped-down one can still over-read.

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

### B8. Lucky imaging for gust + focus-shift stacks — select per-edge by an INDEPENDENT proxy
Gusty / focus-shift data has most frames blurred (defocused or gust-hit). Don't
**median** the stack (defocus contaminates) and don't **max** the MTF (that
re-introduces the B5/B6 over-read). Instead, **per edge**, rank every frame by
an MTF-independent sharpness proxy (Tenengrad / Brenner / var-of-Laplacian on
the edge ROI) — it rejects defocused AND gust-blurred frames together — take
the **top-k** (k≈3) and read MTF50 on those. Per-edge (not per-frame) selection
handles field curvature (different frames focus at different field positions).
Worked 2026-06-28: recovered a real **bare f/8 peak 0.342** from a gust-
flattened ~0.20 profile; ~50–135 of each stack's frames were correctly rejected
as defocused. Two-pass to save compute: half-size develop to score the proxy,
full-develop only the selected frames.
**Power caveat:** gust-recovery scales with the **in-focus** frame count, not
the total — a focus-shift stack leaves only ~10–16 sharp frames per cell after
the defocused majority is rejected, so a marginal cross-config call can stay
unresolved even with 63-frame pools (the calmest-of-~12 need not be a true
lull). For gust work, capture locked-focus bursts (A8), not just focus sweeps.

### B9. Diffraction-ceiling gate — the over-read is a near-ceiling effect, not an aperture
A reading is trustworthy only if it sits **below** the aperture's diffraction
MTF50 ceiling (`tile-sharpness/optics.py`,
`diffraction_mtf50_sensor_lpmm(N)·pitch`). The B5 over-read bites *sharp, near-
ceiling* edges — so a **soft wide-open TC at f/11 is reliable** (glass-limited,
well below ceiling) while a sharp stopped-down config can over-read. This
replaces the blunt "avoid f/11–f/16" rule with a per-config physical check.
Caveat: lucky imaging (B8) can push f/16 readings *over* the ceiling → those are
the least trustworthy.

### B10. Cross-config retention: sharpest-sample (least-gust), equal well-sampled pools
Under gust scatter the **sharpest sample is the least-gusted ≈ true-optics**
frame (same logic as lucky imaging, B8), so compare each config at its
**calm-moment best** — valid *only* when pools are **equal and well-sampled**
(each burst must have caught a lull). On 2026-06-28 this **corrected** the
TC-1.4×-vs-cropping verdict from a gust-contaminated +38 % to the true **−5 %**:
the +38 % came from the median of 3 AF frames where **bare's reference was
suppressed more** (−42 % vs its calm-moment peak) than tc14 (−26 %), inflating
the ratio; equalising to each config's calm-moment best removed it. This is a
*correction*, not a re-basing artefact. Re-basing bites only with **unequal**
pools — the f/16 ordering violation (tc20 > tc14) is that case (tc14 f/16 had 3
frames, no stack, so its "best" underestimates). So: sharpest-sample on equal
well-sampled pools (matched **f/11** here) = trustworthy; unequal pools (f/16) =
not. Keep the questions separate: *is the copy good* (matched-aperture
retention) ≠ *does the TC beat cropping* (best-vs-best FOM).

---

## Part C — What "validated" looked like (the worked example)

For the replacement Z TC-1.4× (2026-06-28, see the capture log for full
numbers): **a good, well-centred copy** — matched-aperture f/11 retention vs
bare **0.88** (≈ the lost copy's ~0.80), symmetric field (no decentering). That
is the revalidation answer. *Separately*, does the TC beat just cropping the
bare 400? — **TC-2.0× yes** (FOM +20 % lucky-imaging to +46 % median-of-AF,
clears 0.500), **TC-1.4× marginally loses** (≈ −5 %, the least-gust estimate;
the +38 % median-of-AF over-credited it via a gust-suppressed bare reference — B10).
Lucky imaging (B8) recovered a real **bare f/8 peak 0.342** that gust+defocus
had flattened, which is what makes cropping competitive with the 1.4×. Trust
matched-f/11; distrust f/16 (over ceiling, B9). The decentering check worked on
JPEG; the sharpness magnitudes needed linear RAW + the centroid_hann fix.

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
