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

## Empirical results — POC 2026-05-15

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
