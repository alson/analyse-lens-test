# Cross-Lens Sharpness Metrics — Alternatives to JPEG File Size

> This document covers the **macro / silicon-wafer** test rig (StackShot
> rail, periodic bond-pad target, fixed planar subject). For the
> **long-distance natural-target** rig (sloped stair scene at 14-50mm,
> distant hedge at 300mm) see [`SHARPNESS_METRICS_LONGDIST.md`](SHARPNESS_METRICS_LONGDIST.md).

The current pipeline (`select-crops.sh`, `make-9-crops.sh`) uses JPEG file
size as a sharpness proxy via `ls -S | head -n1`. This works *within* a
replicate set because the framing is fixed and entropy-coded JPEG length
scales with the amount of detail captured. It does **not** generalise
across lenses, because:

- Different lenses / focal lengths frame different parts of the wafer.
- JPEG length is driven by the entropy of the scene content, not by lens
  resolution alone — a coarser piece of wafer with high local contrast
  can produce a larger file than a finer piece resolved with the same
  acuity.

Below are alternatives that handle the "different framing on the same
wafer" case, roughly ordered by robustness for this particular dataset.

The wafer crops contain two features that make scene-invariant sharpness
measurement unusually tractable here:

- Long, straight die-boundary edges (slanted-edge MTF input).
- Regular periodic arrays of bond pads / bumps (built-in sinusoidal MTF
  target).

---

## 1. Slanted-edge MTF (ISO 12233) via MTF Mapper *(failed on this rig — see "Empirical results" below)*

The gold standard *in principle*, and the most scene-invariant option.
MTF Mapper auto-detects straight edges in arbitrary photos and
reports per-edge MTF50 in cycles/pixel; the die boundaries visible in
many crops are ideal targets. Cross-lens comparison reduces to
"compare MTF50".

> **Empirical caveat (POC 2026-05-15):** on this rig's wafer crops,
> MTF Mapper's default component-finding step fails ("No black
> objects found") because the wafer is not a chart with isolated
> dark targets. The ``--single-roi`` workaround returns one MTF50
> per tile but it correlates poorly with visual sharpness (1/5 on
> manual review) and has the worst noise of any tested method
> across same-model lens copies (CV = 0.54). See "Empirical
> results" near the bottom of this document.
>
> **2026-05-16 update:** the slanted-edge approach was revived in a
> different form (FFT the dark-trough cross-section directly as an
> LSF, skip mtfmapper). Combined with a 2D-FFT on the wafer's
> fine-maze grid for the high-frequency band, this replaces the
> POC's eight-method comparison. See "2026-05-16 update —
> methodology supersedes the POC" at the bottom of this document.

- Binary already built locally: `MTF mapper/workspace/mtfmapper/bin/mtf_mapper`.
- AUR alternative: `mtfmapper-git`.
- Caveats:
  - Needs an edge slanted ~5-10°; perfectly axis-aligned edges fail
    the oversampling step.
  - JPEG-compressed input under-reports the absolute MTF tail.
    Rankings between lenses remain consistent if JPEG settings match.
  - For absolute MTF50 numbers (e.g. comparable to a published lens
    chart), feed RAW-extracted TIFFs instead.

## 2. Radial power-spectrum cutoff with a parametric fit

Compute the 2D FFT of each crop, radially average to obtain P(f), then
fit a model that separates scene statistics from the lens response:

    P(f) = A · f^(-α) · |MTF(f)|² + N₀

where `α` is the natural-image spectral slope (scene-dependent) and
`MTF(f)` is a 1- or 2-parameter shape (Gaussian, or
`sinc(f·b)·exp(-(f·c)²)` for diffraction + defocus). Extract the MTF
cutoff frequency or MTF50 from the fitted curve.

This explicitly *separates* the scene's 1/f spectrum from the lens
response — the central problem with cross-framing comparison. Strictly
better than naive "high-band energy" because it doesn't conflate scene
complexity with sharpness.

Tooling: NumPy + SciPy (`scipy.optimize.curve_fit`) is sufficient. No
extra system packages.

## 3. Harmonic analysis of the bump grid *(exploits the specific target)*

The wafer's regular array of bond pads is, in effect, a built-in
sinusoidal MTF target.

Procedure:
1. Locate the two dominant peaks in the 2D FFT (the grid fundamentals
   in x and y).
2. Measure the amplitudes of the 2nd, 3rd, 4th… harmonics.
3. The decay `A_n / A_1` is a direct sample of the lens MTF at known
   spatial frequencies `n · f_fundamental`.

Literature backs the harmonic method as more accurate at high
frequencies than variance-based methods when noise is correlated
(periodic-bar-phantom comparisons in CT imaging).

Only applies to crops where the grid is visible (centre / pad-array
regions, not die-boundary or bond-wire regions). For those, it is
almost free of scene-content bias because the grid period is known.

## 4. Edge-profile decay rate *(no-reference, content-independent)*

Recent literature on no-reference sharpness assessment converges on
metrics that measure the *normalised* gradient decay along detected
edges, designed to be robust against brightness, contrast, exposure,
and image content. Notable variants:

- Normalised gradient-decay (Akamine et al., 2024 — satellite imagery).
- Marziliano edge-width.
- Local kurtosis of DCT coefficients in 8×8 blocks centred on detected
  edge pixels.

These average over many detected edges, so they don't depend on
finding one good slanted edge — useful for crops with no long straight
die boundary in view.

## 5. Imatest-style acutance / SQF

Integrate MTF (from any of §1-§3) against the human contrast-sensitivity
function to get a single perceived-sharpness number per crop. Useful
when you want a scalar ranking rather than full MTF curves.

---

## Lower-priority options

### 6. Wavelet / DCT band-energy ratio

High-band wavelet energy normalised by low-band wavelet energy. Strictly
better than raw JPEG file size as it removes the dependency on absolute
content density at low frequencies. Still scene-dependent at the margin.

### 7. Variance of Laplacian, Tenengrad, Brenner

Classic autofocus metrics. Strongly content-dependent — useful within a
replicate set, bad for cross-lens comparison. (Effectively equivalent
to the current JPEG-size proxy in failure modes.)

### 8. Blind PSF estimation via cepstrum

Recover the effective PSF from a single image. Fragile and
content-dependent; only useful as a sanity cross-check.

### 9. Deep no-reference IQA (BRISQUE, NIQE, MUSIQ, HyperIQA)

Trained on natural photos. Likely fails to generalise to silicon-wafer
microphotography. Use only as a robustness cross-check, not a primary
metric.

---

## JPEG caveat

All FFT- and MTF-based methods are capped by JPEG's high-frequency
quantisation step. For the same JPEG quality setting:
- *Relative rankings* between lenses are preserved → good for "which
  lens is sharper" decisions.
- *Absolute* MTF50 in cycles/pixel is depressed vs the optical truth →
  bad for comparing against published lens charts.

If absolute numbers are needed, re-extract from NEFs to TIFF and run
the metrics on those.

---

## Lossless JPEG cropping eliminates per-crop generation loss

A second round of pipeline tightening, also done while this dataset was
being processed, switched the crop step itself to a lossless JPEG
transform. The crop dimension changed from 500 px to **512 px** (the
smallest 16-multiple at or above 500), so every crop origin lands on a
clean MCU boundary and `TurboJPEG.crop_multiple` can re-pack the
encoded JPEG blocks into the output files without decoding back to RGB
and re-encoding. Crops now inherit the source JPEG's encoded quality
exactly — zero generation loss in the cropping step.

This kills another large source of noise on top of the resampler swap:

- Previously, every `make-N-crops.sh` invocation decoded the camera
  JPEG and re-encoded each sub-crop at GraphicsMagick's defaults. Two
  generations of JPEG compression on every crop before it ever hit the
  rail-coverage analyser.
- Previously, every resize step (`resize_bulk.py`) re-encoded its full
  resized JPEG *and* then re-encoded each of the 9 sub-crops on top of
  that. Three generations of compression on the resized crops.
- After the switch: one generation on lossless-cropped camera JPEGs;
  two generations on resized crops (resize is intrinsically lossy, but
  the 9-crop split itself is lossless).

Origins are computed via
`lens_test_detect_core.compute_crop_origins` (full-frame) and
`compute_dx_origins` (DX inner region); both snap to 16-multiples via
`align_down`. The live runtime cropper, the batch crop scripts and the
resize-bulk 9-crop split all share that source of truth, so the live
and offline analyses can't drift apart on crop geometry.

See `resize-bulk/RESIZED_COMPARISON.md` §0.0 for the file-size
implications.

## Empirical confirmation: resampler choice affects the JPEG-size proxy

While doing the resampled-lens comparisons (see
[`resize-bulk/RESIZED_COMPARISON.md`](resize-bulk/RESIZED_COMPARISON.md))
we accidentally produced a useful side-result on the JPEG-size proxy
itself. The original `resize-from-to.sh` upsampler was Lanczos; we
switched to Catmull-Rom (Catrom) for the second run, holding everything
else constant.

Same combo, same resized target, same aperture:
- 24-120 + Olympus MCON-35, 1_1-resized F8 (Lanczos): **113,917 bytes**
- 24-120 + Olympus MCON-35, 1_1-resized F8 (Catrom): **46,021 bytes**

A 60 % drop in file size from changing only the resample kernel. Almost
all of that delta is Lanczos's Gibbs ringing around edges — high-
frequency halos that have nothing to do with the optical signal but
that JPEG dutifully encodes, inflating file size.

Implications for using JPEG size as a sharpness proxy:

- **It is sensitive to upstream processing in unintuitive ways.** Any
  step in the pipeline that adds or removes high-frequency content
  (sharpening, resize kernel, noise reduction, sensor PDAF stripes,
  fast-readout artefacts) directly perturbs the proxy by amounts that
  can swamp the optical signal you're trying to measure.
- **Catrom is the more honest kernel** for this kind of analysis. It
  has only local overshoot, not the long-range Gibbs ringing of Lanczos.
  The relative rankings between lens combos were preserved across the
  two kernels but the gaps were much wider with Catrom — i.e. the proxy
  is more diagnostic when the noise from synthetic HF content is
  removed.
- The Catrom result also strengthens the case for moving to a real MTF
  metric (§1–§3 above). If a resize-kernel choice can move the proxy by
  60 %, the proxy clearly carries a lot of non-optical signal.

---

## Suggested first experiment

Cheapest validation before committing to a metric:

1. Pick ~10 `pick.jpg` files spanning lenses with strong priors
   (e.g. AF 200 f/4D should beat 24-120 + Raynox at matched mag).
2. Run MTF Mapper on each.
3. Plot MTF50; check the ranking matches visual intuition.

If consistent, codify in `rail-coverage/` as a new column alongside the
file-size proxy. If not, fall back to §2 (radial power-spectrum fit).

---

## Empirical results — POC 2026-05-15 *(partially superseded — see 2026-05-16 update below)*

The recommendations above were tested against four datasets using the
``tile-sharpness/`` POC. **The slanted-edge MTF "gold standard" claim
in §1 did not survive contact with the wafer dataset.** What did work:

### Setup

- One common 1024×1024 tile grid, 35 tiles centred on the optical
  axis, MCU-aligned. Tiles extracted losslessly via
  ``TurboJPEG.crop_multiple``.
- Tile cache on the shared mount; ``mtf_mapper`` runs on nufan over
  SSH (rebuilt against Ubuntu 25.10 OpenCV 4.10, since the local
  Arch host's 4.13 was ABI-incompatible).
- Eight scoring methods on each tile across every shot in a focus
  sweep: ``filesize``, ``mtfmapper`` (``--single-roi``),
  ``radial_fft`` (high/low PSD band ratio — see "Method 2 caveat"
  below), ``edge_decay`` (Marziliano edge width), and four added
  during the POC: ``laplacian_var``, ``tenengrad``, ``dct_kurtosis``
  (Ferzli-Karam variant), ``wavelet_ratio`` (db2 detail/approx ratio,
  §6 above).

### Within-sweep test — does the method pick the sharpest rail step?

Manual review of 5 disagreement tiles from a 24-120 + Raynox M-250 @
F8 sweep (85 shots):

| method | times it picked the visually-sharpest shot |
|---|---|
| ``filesize`` | **5/5** |
| ``edge_decay`` (argmax only) | 4/5 |
| ``mtfmapper`` | 1/5 |
| ``radial_fft`` | 0/5 |

``mtfmapper``'s ``peak_MTF50 = 0.972 cy/px`` on a wafer tile (where
0.5 is the Nyquist limit) is the canonical tell that the
``--single-roi`` fallback has latched onto an aliasing artefact.

### Cross-lens test — same scene, four bare native macros at 1:1, F8

Mean rank per (method × lens) across 35 tile positions (1 = sharpest):

```
                            Z MC 105  AF 200/4D  Sigma 150  Sigma 105
filesize                       2.57      1.34       2.54       3.54
radial_fft                     3.17      1.46       2.63       2.74
mtfmapper                      2.38      2.82       2.26       2.27
laplacian_var                  1.94      2.03       2.46       3.57
tenengrad                      1.60      2.94       2.14       3.31
wavelet_ratio                  1.17      2.94       3.09       2.80
dct_kurtosis                   2.29      2.11       2.23       3.37
edge_decay                     1.34      1.17       1.37       1.40  (saturated ties)
```

Three different lenses appear in first place across methods. Only
consensus: ``Sigma Macro 105mm F2.8 EX DG OS HSM`` is last by every
discriminating method. **No clean winner for cross-lens ranking on
the bare-native-macro case** — quality differences here are smaller
than the methods' framing/content sensitivities.

### Cross-config test — six different lens combos all resized to 1:1, F8

When the lens-quality spread is large, methods *do* converge:

- ``NIKKOR_Z_MC_105mm_f_2.8_VR_S + 5T`` (modern native macro + mild
  diopter) ranks 1.0–2.31 across every method except mtfmapper.
- ``NIKKOR_Z_24-120mm_f_4_S + Raynox_M-150`` (general zoom + strong
  diopter) ranks 5.00–5.89 across every method except mtfmapper.
- Pairwise Spearman ρ on centre-tile ranking: 0.83–0.94 between
  ``filesize``, ``laplacian_var``, ``wavelet_ratio`` and
  ``radial_fft``.
- ``mtfmapper`` is **completely flat** here — all six lenses rank
  3.21–3.34, i.e. mean rank of (n+1)/2 = 3.5. It can't discriminate
  on the resized cohort at all.

### Multi-copy test — 5 copies of two 55mm prime models at 1:1, F8

3× Auto 55mm f/3.5 (s/n 209088, 258263, 262711) and 2× AIS 55mm
f/2.8 (s/n 287318, 537016). Every method except ``mtfmapper`` cleanly
separates AIS (sharper) from Auto (softer). Same model copies should
score similarly; **coefficient of variation across copies**:

```
edge_decay      0.000  (artefact: integer-pixel ties hide variation)
filesize        0.021
dct_kurtosis    0.032
tenengrad       0.106
wavelet_ratio   0.148
laplacian_var   0.151
radial_fft      0.179
mtfmapper       0.536    ← ~25× noisier than filesize/dct_kurtosis
```

### Conclusions

1. **``mtfmapper`` is not viable for this rig.** Three independent
   strikes: failed the manual within-sweep check (1/5), completely
   flat on the resized cross-config cohort, and the worst CV across
   nominally-identical lens copies. Two failure modes:
   - On wafer tiles the default component-finding step can't locate
     chart-style "black objects", and the ``--single-roi`` fallback
     measures whatever gradient happens to dominate, which is often
     an aliasing artefact.
   - Where it does measure, the result is noise-limited.
   Don't write a rail-coverage column for it. If a future dataset
   contains isolated dark targets (a real chart card, individual
   bond pads under high magnification), revisit — the method works,
   just not on this subject.

2. **``filesize`` is more robust than this doc previously credited it
   with.** It picked the visually-sharpest rail step on 5/5 manually
   reviewed tiles, and on cross-config comparisons with a wide
   quality spread it agreed strongly with the more principled
   methods (ρ ≈ 0.94 with ``wavelet_ratio`` and ``laplacian_var``).
   The known failure mode — being content-fooled when framings
   differ subtly — manifested clearly only in narrow comparisons
   (centre-tile of multi-copy 55mm: picked the Auto over the AIS).
   Keep it as a primary proxy in ``rail-coverage/``; don't replace
   it.

3. **``wavelet_ratio`` (§6) is the best cross-frame supplement.** db2
   3-level detail/approximation energy ratio. Tracks the consensus
   ranking on cross-config (ρ ≈ 0.83–0.94 with filesize), gets the
   AIS-vs-Auto distinction right on multi-copy. The LL approximation
   normalisation is exactly the property that compensates for
   different framings.

4. **``dct_kurtosis``** (Ferzli-Karam DCT-AC variant, §4) is the most
   stable across same-model copies (CV = 0.032, second only to
   ``edge_decay``'s quantisation-trick zero). Useful as a calibration
   stability check; tracks consensus rankings reasonably.

5. **§2 (parametric radial power-spectrum fit) does not converge on
   wafer tiles.** σ saturates at the physical Nyquist bound on
   nearly every in-focus tile, producing identical fitted MTF50s
   across the frame. The fallback I shipped (``radial_fft`` = high
   ``E[0.30, 0.45]`` / low ``E[0.10, 0.20]`` cy/px band ratio) works
   for spatial ranking but its **argmax across a sweep is unreliable**
   because near-Nyquist JPEG quantisation noise inflates the
   numerator on heavily defocused frames. Use it for ranking tiles
   within a known-good shot, not for picking which shot is the
   best-focus.

6. **``edge_decay`` (Marziliano width)** quantises to integer pixels
   and saturates at 4–5 on these crops; useful only for *which rail
   step* (argmax) within a sweep, not for peak-magnitude ranking
   across tiles or lenses.

7. **``laplacian_var`` and ``tenengrad``** are content-dependent
   autofocus classics. On cross-config with a wide quality spread
   they ride the consensus; on narrow comparisons they're as
   framing-dependent as filesize.

### Recommended setup for cross-lens / cross-frame work

| use case | primary | sanity check | notes |
|---|---|---|---|
| within-sweep argmax (which rail step is sharpest) | ``filesize`` | ``edge_decay`` argmax | manual confirms 5/5; both stable |
| cross-lens ranking, similar framing | ``filesize`` | ``wavelet_ratio`` | ρ ≈ 0.94; disagreement → investigate |
| cross-config ranking, different framings | ``wavelet_ratio`` | ``dct_kurtosis`` | both content-normalised; agree on extremes |
| same-model copy consistency | ``dct_kurtosis`` | ``filesize`` | both CV ≤ 0.035 |

Where the primary and the sanity-check disagree by more than ~2 ranks
on a 4–6-lens cohort, that's the signal worth manually inspecting
(``tile-sharpness cross-lens-crops --tile 0,0 …``).

---

## Tool availability

Already present:
- `MTF mapper/workspace/mtfmapper/bin/mtf_mapper` (built from source).

May need installing (Arch):
- `python-scipy`, `python-scikit-image`, `python-opencv` for §2-§4
  (likely already available via uv envs).
- `paru -S mtfmapper-git` if the locally built binary is awkward to
  invoke.

---

## References

- Akamine et al., "A Novel No-Reference Image Quality Metric For
  Assessing Sharpness In Satellite Imagery" (2024) —
  <https://arxiv.org/html/2410.10488>
- Imatest, "Sharpness" — <https://www.imatest.com/imaging/sharpness/>
- Ferzli & Karam, "No-reference sharpness metric based on local edge
  kurtosis" (IEEE) — <https://ieeexplore.ieee.org/document/1038901/>
- Image Engineering, "Image Resolution / ISO 12233" —
  <https://www.image-engineering.de/library/image-quality/factors/1055-resolution>
- "Comparative evaluation of uncertainty in MTF estimation using
  periodic bar patterns: variance vs. harmonic methods" (2025) —
  <https://pubmed.ncbi.nlm.nih.gov/40614766/>
- "An Improved Method for Evaluating Image Sharpness Based on Edge
  Information" — <https://www.mdpi.com/2076-3417/12/13/6712>
- "A Simple Model for Sharpness in Digital Cameras" —
  <https://www.strollswithmydog.com/resolution-model-digital-cameras-iii/>
- Wikipedia, "Optical transfer function" —
  <https://en.wikipedia.org/wiki/Optical_transfer_function>

---

## 2026-05-16 update — methodology supersedes the POC

A follow-up empirical pass (driven by visual disagreement between
``filesize``-picked cross-lens crops on the AIS 55mm cohort) invalidated
two of the POC's conclusions and replaced the recommended-setup table.
The POC section above is retained as a historical record; this section
is the current source-of-truth.

### Filesize argmax fails at sharp configs

The POC's "filesize 5/5 within-sweep" claim was validated on the
24-120 + Raynox M-250 sweep — a *soft-chain* config with a steep
bell curve. At *sharp* configs (1:1+ with quality glass, F8-F11),
JPEG file size saturates against high-detail content and the curve
flattens near the true peak; small focus errors stop moving the
file size.

Verified on AIS 55mm at 1:1 F8 (35 tiles × 2 lens copies × full
sweep): **only 26 % / 46 % of tiles agree within ±1 shot** between
``filesize`` argmax and maze-FFT amplitude argmax across the sweep.
Filesize systematically picks 6-10 shots **too late**. At the centre
tile of one AIS copy, FFT-amp at the filesize-picked shot is
**2.13× lower** than at the FFT-picked shot — i.e. filesize
under-reported that lens's sharpness by 2× through pure focus mis-pick.

**Practical consequence**: any cross-lens comparison done on
filesize-picked peak crops at high-sharpness configs is corrupted
by mis-picking, not by lens differences. The POC's earlier
"AIS 287318 looks 5.8× softer than 537016 at the centre tile"
finding was such an artifact — once each tile is judged at its own
FFT-amp peak, the two copies are within 1 %.

**Visually confirmed 2026-05-16**: side-by-side eyeball at 200-400 %
of the AIS 287318 centre tile at filesize-pick (within-sweep shot 37,
FFT-amp 281) vs FFT-pick (shot 30, FFT-amp 600) shows the FFT-pick
**unambiguously sharper** — the fine maze grid is clearly defined,
while the filesize-pick is visibly smudged. The methodology pivot
is empirically settled, not a marginal call. PNGs preserved at
``/tmp/ais287318_centre_{filesize_pick_shot037,fft_pick_shot030}.png``
on bumblebee + nufan.

### The new methodology

Two complementary metrics, computed per tile from the **native frame**
(not resampled, not a fixed-size centre crop):

1. **Scribe LSF — universal, works at any magnification.** Detect
   the dominant near-full-span scribe (LSD or morphological opening;
   no tilt-correction so the slant is preserved). Take the dark-trough
   cross-section perpendicular to it, FFT directly as a line-spread
   function, read MTF50 off the |FFT| curve. **Skip the
   differentiation step** that classic slanted-edge uses (ESF → LSF) —
   the trough cross-section *is* the LSF, since wafer scribes are
   narrow dark lines, not step edges. Confirmed empirically: scribe
   FWHM is comparable to optical edge rise at this rig's typical
   apertures, so ESF math leaks the opposite side of the scribe into
   the integration window.

2. **Fine-maze 2D-FFT — high-resolution discriminator at M ≥ ~0.7×.**
   The wafer carries a fine maze/grid structure (period ~13 µm
   physical, ~3 px on Z7 at 1:1) that's universal across every die
   *except inside the scribes themselves*. 2D-FFT the tile, sum
   amplitude in the annulus around the maze fundamental (~0.33 cy/px
   at 1:1; scales with M). Higher amplitude = more high-frequency
   content survives the optical chain = sharper. **Two orders of
   magnitude more sensitive** to real lens-quality differences than
   bulk-energy proxies (5.5× cross-copy ratio at the maze fundamental
   vs ~2 % CV in filesize across same-model copies).

   **Self-gating**: the maze period in pixels scales linearly with M.
   Below ~0.7× the period aliases (sub-Nyquist on the sensor) and
   the FFT amplitude is noise. Read MTF at the maze fundamental from
   the scribe LSF; if that MTF is above the noise threshold, the
   maze method is valid for this image. Below the threshold, fall
   back to scribe LSF only.

3. **JPEG vs NEF is not a concern.** Paired analysis on three sharp
   configs measured JPEG-derived edge widths to be within **≤ 2 %**
   of NEF-derived widths (in fact slightly *narrower* — the in-camera
   tone curve compresses midtones rather than blurring). Shoot
   JPEG; the cap on absolute MTF50 is at most a few percent and
   doesn't affect within- or cross-config rankings.

### Subject-space MTF50 is the cross-config metric

> **⚠ 2026-06-27 caveat — subject-space MTF50 OVER-READS at low contrast; it is
> not absolutely calibrated.** A diffraction-ceiling overlay
> (`tile-sharpness/optics.py` + `scripts/diffraction_ranking.py`) found 12/29
> characterised configs report a centre MTF50 *above* the diffraction-limited
> ceiling — physically impossible (a real lens MTF50 ≤ the optical ceiling, since
> the sensor only degrades it; a 55mm even reads higher at f/16 than f/8). The
> RAW-vs-JPEG diagnostic (`scripts/raw_vs_jpg_mtf.py`) shows this is a
> MEASUREMENT artifact, NOT a JPEG one: 8-bit JPEG, linearised JPEG, and
> linear/unsharpened RAW all over-read at f/11-f/16. Cause: the differentiated
> ESF→LSF inflates on low-contrast / diffraction-blurred edges (noise floor holds
> |FFT| up past the true 0.5 crossing), + `_mtf50_from_lsf` normalising to the
> spectral PEAK (DC dropped), + large scribe-to-scribe variance (±~5 lp/mm).
> **Practical rule:** trust subject-space MTF50 for cross-config ranking only
> where it sits comfortably *below* the ceiling (glass-limited — corners, wider
> apertures), where corner differences between same-strength diopters (e.g.
> MCON-35 vs 6T) are real and the metric ranks them correctly. For
> diffraction-limited configs (stopped-down centres) use the physics ceiling
> directly — it depends only on M and effective aperture `N·(1+M)`. Fixing the
> absolute calibration needs an LSF over-read fix (normalise to DC; denoise the
> LSF) + scribe averaging. See `tile-sharpness/HANDOVER.md` (2026-06-27).

    MTF50_subject_lp_per_mm = MTF50_sensor_cy_per_px × M × 1000 / pixel_pitch_µm

On Z7 (pitch 4.35 µm):

    lp/mm_subject = MTF50_sensor_cy_per_px × M × 229.9

This collapses every config onto one axis — bare zoom at 0.385×,
sharp macro at 1:1, TC at 2:1, diopter chain at 2:1, etc. — without
resampling. Empirically validated against visual ranking on a 5-config
preview: ranks bare 100-400 (33 lp/mm) ≈ bare AF 200/4D (33 lp/mm) <
Sigma 150 + TC-2001 (41 lp/mm), with 200/4D + 5T + 6T at 23 lp/mm.
Bare 100-400 at 0.385× was found to be pixel-limited (Nyquist =
44 lp/mm subject), all others optics-limited.

Resampling (``1_1-resized``, ``2_1-resized``) is **not needed for
measurement** and actively contaminates it via Lanczos overshoot
(the 100-400 resized to 2:1 measures 40 lp/mm in resampled pixels
vs 33 lp/mm true — the 20 % gain is fake high-frequency content,
not optical detail; see §0.0 of ``resize-bulk/RESIZED_COMPARISON.md``).
Resized cohorts are kept only for human visual side-by-side review.

### M-driven crop sizing

The measured magnification (from ``measure_wafer_squares``) drives
the analysis ROI size per metric:

| metric | rule (px on sensor) |
|---|---|
| scribe LSF | ``max(3 × die_period_px, 1024)`` |
| maze 2D-FFT (single-tile measurement) | ``max(64 × maze_period_px, 256)`` |
| maze 2D-FFT (decentering-map tile) | ``max(40 × maze_period_px, 128)`` |

So a 1024×1024 tile-sharpness POC tile is **fine for the maze FFT**
at 1:1 (340 cycles per side) but **too small for scribe LSF** at 1:1
(die period ~1100 px, tile contains < 1 die). Per-metric ROIs replace
the one-size-fits-all 1024 tile.

**Dependency reversal**: ``measure_wafer_squares`` (archive-2026-05
step 2) is now a **load-bearing input** to the sharpness pipeline,
not just a folder-labelling step. Without M per config the sharpness
metric can't size its ROIs or convert to subject space.

### Cross-frame report (rail-coverage column set)

Per (lens, mag, focal, aperture) slug — derived from existing
per-position tile measurements at centre + 4 DX-ring corners + 4 FX-ring
corners:

| field | meaning |
|---|---|
| ``mtf50_centre_lpmm`` | subject-space MTF50 from the centre tile |
| ``mtf50_dx_corner_lpmm`` | mean over 4 DX-ring corners |
| ``mtf50_fx_corner_lpmm`` | mean over 4 FX-ring corners |
| ``uniformity_dx`` | ``mtf50_dx / mtf50_centre`` |
| ``uniformity_fx`` | ``mtf50_fx / mtf50_centre`` |
| ``decentering_dx`` | peak-VALUE asymmetry across the 4 DX corners |
| ``decentering_fx`` | peak-VALUE asymmetry across the 4 FX corners |
| ``subject_tilt_deg`` | wafer-plane tilt recovered from per-slug plane fit on ``peak_idx`` across the 9 positions |
| ``field_curvature_mm_rms`` | residual after subtracting the subject-tilt plane, in µm of focus shift |

The decentering pair (DX-ring vs FX-ring) distinguishes element-tilt
(uniform across rings) from element-shift (grows from DX to FX). Use
peak-VALUE, not peak-INDEX — index asymmetry is contaminated by
subject tilt + field curvature.

Subject-tilt is **per-slug**, not session-wide (the rig is moved
between magnifications even within one session — older shoots
have larger and more variable subject tilt than recent ones). The
mag × tilt interaction is `1/M`-scaling: low-mag configs are
where un-corrected subject tilt most strongly contaminates the
field-curvature read.

### Updated recommended setup

| use case | primary | sanity check |
|---|---|---|
| within-sweep argmax, M ≥ 0.7× *and* on-target | maze-FFT amp | scribe-LSF amp at chosen shot |
| within-sweep argmax, M < 0.7× *or* maze aliased | scribe-LSF amp | filesize (only if no scribe present) |
| within-sweep argmax, off-target tile | ``filesize`` (degenerate; off-target tiles shouldn't be argmaxed) | — |
| per-tile cross-lens sharpness, M ≥ 0.7× | maze-FFT amp | scribe-LSF MTF50 |
| per-tile cross-lens sharpness, M < 0.7× | scribe-LSF MTF50 | filesize (peak-shot only) |
| cross-config / cross-magnification ranking | subject-space MTF50 (from scribe LSF) | maze-FFT decentering-map peak |
| decentering / field-uniformity per lens | maze-FFT amp map across the tile grid | DX-ring vs FX-ring peak-value asymmetry |

Key shift from POC: **filesize is not primary anywhere for on-target
tiles.** It saturates at sharp configs (the failure shown above) and
adds no information that maze-FFT or LSF doesn't. It's retained only
as the degenerate fallback for off-target tiles, where neither maze
nor scribe have anything to measure — and those tiles shouldn't drive
argmax decisions anyway. The "filesize as soft-config primary"
framing from the POC was a 2026-05-15 hypothesis the 2026-05-16
maze-FFT evidence supersedes.

The POC's eight scoring methods (``filesize``, ``mtfmapper``,
``radial_fft``, ``edge_decay``, ``laplacian_var``, ``tenengrad``,
``dct_kurtosis``, ``wavelet_ratio``) all remain available as
cohort columns for cross-validation, but no longer drive primary
analysis: ``mtfmapper`` failed (§1 above); ``radial_fft`` and
``edge_decay`` are within-sweep argmax-only; the autofocus classics
and ``wavelet_ratio`` / ``dct_kurtosis`` are content-fooled at narrow
comparisons; none replicate maze-FFT's frequency-direct readout at
a known target frequency.

### Open work

- Implement scribe-LSF MTF50 and maze-FFT amplitude as production
  methods in ``tile-sharpness/methods.py`` (LSF replaces mtfmapper;
  maze-FFT is new). Wire ``measure_wafer_squares`` M into the ROI
  sizing.
- Add the 9-position cross-frame columns (centre + DX-ring +
  FX-ring) to ``rail-coverage/``.
- Re-run the ``out_55mm`` cohort with maze-FFT argmax instead of
  filesize to fix the AIS-copy comparison (already validated as
  identical within 1 %, but the per-tile peak crops in
  ``out_55mm/cross_lens_crops/`` are still filesize-picked and need
  regeneration before being used for any further visual review).
- Re-evaluate other sharp-config cohorts (``out_bare1to1``) where
  filesize mis-picking may have skewed cross-lens conclusions.
