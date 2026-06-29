# POC: multi-frequency-spectrum cross-config sharpness ranking (comb + chain)

**Status:** completed exploratory POC, committed as a record (2026-06-29). No
production module was modified by this POC; production helpers are imported read-only.
Compute ran on nufan (16 cores) over the shared NFS path. Spanning subset = 16 configs
(`poc_comb_chain_subset.csv`), M ≈ 0.86 → 2.09, chosen for cross-M frequency overlap.

## Executive summary (bottom line)

A single **cross-magnification absolute** sharpness ranking is **not viable** on this
wafer's existing data. Every avenue converged: fixed-subject-frequency contrast is
M-confounded (corr(M,C)=+0.33/+0.78); fixed-sensor-frequency *relocates* the confound
(corr ~0 only at a degenerate knife-edge); the harmonic-shape intrinsic-correction
de-confounds numerically but the assumed square-wave/sinc(nD) model is wrong for these
textured/specular cells (pad-tooth vs maze-tooth MTF disagree ~5× at the same f_px);
the dark/light-pad cancellation hypothesis is refuted (cells are one population). For
the methods tested, use within-M rankings + the diffraction ceiling + tolerance-ratios
instead.

**Caveat on the verdict — one credible rescue path is UNTESTED.** The harmonic-shape
intrinsic-correction *did* de-confound M (corr→~0); it was rejected only because the
assumed square-wave/sinc(nD) `T_n` produced invalid MTF (>1) and a 5× pad-vs-maze
cross-structure disagreement. But that disagreement is most likely an artifact of
applying ONE wrong (odd-only square-wave) `T_n` model to TWO genuinely different
signals: pads and maze have different harmonic content, and the maze in particular
skips/merges cycles → real EVEN-harmonic (N=2) content the odd-only model omits. So the
5× is plausibly "wrong shared `T_n`," not "method dead." The untested fix: measure each
structure's `T_n` EMPIRICALLY (in a regime where MTF≈1 — e.g. low-order harmonics at
high M — or by self-calibration across M), ideally on the saturation channel (specular-
suppressed). If that makes the cross-structure MTF agree while preserving the
de-confounding, the cross-M chain may be viable after all. NOT yet attempted.

**Salvaged / banked:** (a) **A5** — the M-aware maze/band fix — was a real production
bug (static band locks onto the maze at M≳1.5); promoted to production in commit
`29a3a80`. (b) **Saturation / R−B** decode is a real, M-independent SNR win for these
pad features (2–3× structural contrast vs luma, suppresses achromatic speculars).

## Scripts index (each result references its script)

| script | stage / result |
|---|---|
| `poc_comb_chain_lib.py` | core: M-aware bands (A5), comb prediction, chain (B1) helpers, `LPMM_PER_CYPX` |
| `poc_comb_chain_a5_validate.py` | A5 validation (maze-vs-pad discovery at high M) |
| `poc_comb_chain_a1_driver.py` + `poc_comb_chain_run_a1.sh` | A1 sharded comb extraction → `out/a1_all.csv` |
| `poc_comb_chain_b1_analyse.py` | B1 transitive chain + gate metrics (fixed-subject-freq) |
| `poc_comb_chain_contrast_inspect.py` | luma contrast/bimodality diagnostic |
| `poc_comb_chain_contrast_color.py` | per-channel warm-axis contrast diagnostic (saturation/R−B win) |
| `poc_comb_chain_t1_fpx.py` | Task 1: fixed-sensor-frequency de-confounding test |
| `poc_comb_chain_t1_hmtf.py` | Task 1: harmonic-MTF intrinsic-correction + cross-structure check |
| `poc_comb_chain_t1_psd.py` | Task 1: radial-PSD cross-check |
| `poc_comb_chain_t2_padpop.py` | Task 2: pad-population bimodality |

**Reproduce:** run on nufan via the per-host venv (`~/.cache/uv-venvs/tile-sharpness/bin/python`,
`PYTHONPATH=…/tile-sharpness/src`). The heavy/regenerable artifacts under `out/`
(`a1_all.csv`, shards, the multi-MB `*__roi.png` crops, `view_*`, `*cellmode_map.png`)
are gitignored — regenerate with the scripts above; the small result CSVs + histogram
PNGs are committed alongside this report.

**See also:** production A5 fix `29a3a80`; `SHARPNESS_METRICS.md` and
`REPORT_taskAD_2026-06-28.md` (the periodic-FFT + diffraction-ceiling methodology this
extends); the diffraction-ceiling over-read context that motivated periodic-FFT.

---

## Stage A5 — M-aware bands (VALIDATED)

The production `discover_fundamental` uses a static band `(0.06, 0.30)` cy/px with a
static maze exclude `(0.31, 0.36)`. At M=1 the maze sits at 0.335 cy/px (just outside
the band). But the maze frequency scales as `4.35/(13·M)`, so at **M≈2 the maze slides
to ~0.16 cy/px — squarely INSIDE the old discovery band** — and the old code locks onto
it, mistaking the universal 13 µm maze for the pad fundamental.

`poc_comb_chain_lib.py` adds:
- `maze_band_cy_per_px(M)` — the M-tracking maze frequency + a ±10%-of-freq exclusion band.
- `resolvable_band_cy_per_px(M)` — an M-aware floor/ceiling (the pad fundamental's
  pixel frequency moves with M, so a fixed 0.06 floor is M-naive).
- `discover_pad_fundamental(roi, M)` — discovery inside the M-aware band, excluding the
  M-aware maze band.

**Validation** (`poc_comb_chain_a5_validate.py`, Sigma 105/150 + TC-2001 @ 2:1):

| config | M | OLD picks maze (~77 lp/mm) | NEW finds pad fundamental | maze labelled |
|---|---|---|---|---|
| Sigma 150 + TC-2001 2:1 | 2.035 | **11 / 11 regions** | 11 / 11 (~16–36 lp/mm) | separately, from M physics |
| Sigma 105 + TC-2001 2:1 | 2.087 | **8 / 8 regions** | 8 / 8 (~14–36 lp/mm) | separately, from M physics |

Confirmed: the old code returns a ~76 lp/mm "fundamental" that is actually the maze;
A5 correctly separates the pad comb from the maze. Pad fundamentals cluster at two pad
pitches (~16 lp/mm and ~35 lp/mm) — different bond-pad arrays. One region over-read at
85 lp/mm (a harmonic alias) which the A1 SNR/ceiling gate is responsible for dropping.

---

## Stage A1 — atlas-predicted harmonic comb

`poc_comb_chain_a1_driver.py` (sharded, `poc_comb_chain_run_a1.sh`, N=8 on nufan).
Reuses `atlas_periodic_fft`'s registration + ROI enumeration + one-decode-per-frame
top-k-focus plumbing; for each region it discovers the pad fundamental (A5), predicts
the comb {f1..7f1} in subject space + the maze (M physics), and reads bounded Michelson
contrast (`periodic_fft.periodic_contrast`, ceiling-gated) at each rung.

**Coverage: all 16 configs measured, 0 dropped, 3994 long-table rows** (3342 pad +
652 maze). M range 0.90–2.09. Registration RMSE 1.6–5.4 px. Output:
`poc_comb_chain_out/a1_all.csv`.

Sample of the spectrum (bare Sigma 105 @ M≈1.05, median Michelson C per shared node):

| feature | ~subj lp/mm | n regions | median C | max C |
|---|---|---|---|---|
| pad f1 | 12 | 7 | 0.047 | 0.096 |
| pad | 32 | 27 | 0.027 | 0.052 |
| pad | 48 | 23 | 0.022 | 0.048 |
| pad | 68 | 24 | 0.044 | 0.101 |
| maze | 77 | 50 | 0.045 | 0.101 |

Note the *absolute contrasts are tiny* (1–10%): the wafer pad arrays are low-modulation
metal-on-metal, so the cross-config signal-to-noise at M≈1 is poor — a key fragility.

Two configs registered with M far from their nominal label (Canon 500D 1.07→0.90;
MCON-35 0.86→1.12) — the known reg_auto label/scale uncertainty on accessory configs.
Per the corrected memory note (atlas-M validated ±1.6%), atlas-M was trusted.

## Stage B1 — transitive least-squares chain

`poc_comb_chain_b1_analyse.py` + `build_chain` in the lib. Nodes = configs; for every
(feature, subject-frequency-bucket) shared by ≥2 configs (within 4 lp/mm, both SNR≥3,
ceiling-valid, ≥3 region replicates), add `s_i − s_j = log(C_i/C_j)` averaged over
shared frequencies, weighted by min-SNR. Solved by weighted least-squares, gauge =
zero-mean per component. Per-(config,node) contrast aggregated over region replicates
by **median** (robust; recommended) or **max** (dodges pad specular dropouts) — both run.

### Gate metrics

| gate | result |
|---|---|
| **1. Connectivity** | **PASS** — 1 connected component, 16/16 configs, 27–31 shared nodes, 120 edges, 0 isolates. |
| **2. Consistency** | **PASS** — residual RMS 0.06 (max-agg) / 0.09 (median); sign-inconsistent triangles 6.8% (max) / 14.6% (median) of 560. |
| **3. Cross-M transitivity** | **FAIL (substantive)** — with the maze rung removed, **no pad-only indirect cross-M link** survives among the large-ΔM pairs. All cross-M connectivity rides on the single M-invariant maze frequency (76.9 lp/mm), not on a *comb* of shared pad rungs. The core claim ("a shared rung at 54 lp/mm links M=1 and M=2") does not materialise: the pad harmonics at M=1 land near Nyquist where contrast is ~noise, so they do not form trustworthy shared nodes with the high-M configs. |
| **4. Sanity vs known** | **FAIL** — bare Sigma 105 ≠ bare 150 under both aggregations (should be ~equal); and under median aggregation **+TC-1401@1.4 and +TC-2001@2:1 rank #1–#2, above every bare lens** — the empty-magnification fallacy. |

### The killing confound (diagnosed, not assumed)

Contrast at a **fixed subject frequency is not M-comparable.** The same subject feature
lands at a *different pixel frequency* depending on M:

| config | M | f_px of the 77 lp/mm maze | median C |
|---|---|---|---|
| bare Sigma 105 | 0.99 | 0.337 cy/px (near Nyquist) | 0.011 |
| Sigma 105 +TC-1401 | 1.48 | 0.225 | 0.073 |
| Sigma 105 +TC-2001 @2:1 | 2.09 | 0.160 (easy) | 0.076 |

A higher-M config reads the **same** subject detail at a lower, easier pixel frequency
(higher on the sensor MTF, above the noise floor) and therefore higher contrast — even
though magnification cannot *add* subject resolution. Quantified: corr(M, median raw
contrast) = **+0.33**; ceiling-normalising makes it **worse, +0.70** (high-M features
sit closer to their local ceiling). So neither raw nor ceiling-normalised contrast at a
shared subject frequency isolates glass quality from magnification. The chain faithfully
propagates this M-bias into the scores, floating empty-magnification configs to the top.

### Other failure modes observed

- **Low absolute pad contrast (1–10%)** ⇒ cross-config differences at M≈1 are within
  measurement noise; the bare-105-vs-150 separation is noise, not signal.
- **Aggregation-dependent ranking** — median vs max reshuffle the top half (a robust
  ranking should not), confirming the per-node reads are noise-dominated.
- **Maze read via 1-D collapse** under-reads vs the production 2-D annulus
  (`maze_amp`), so the one rung that *does* link all M is itself the weakest read.

### Gate verdict

**THE CHAIN DOES NOT HOLD.** Connectivity and internal consistency pass, but the two
load-bearing claims fail: cross-M transitivity rests entirely on the single maze
frequency (not a comb), and the ranking is physically wrong (empty-magnification
configs outrank bare lenses) because Michelson contrast at a fixed subject frequency is
confounded by magnification. The coded verdict prints `CHAIN HOLDS: False` for both
aggregations.

## Stage A3 — 2D reciprocal-lattice (NOT RUN)

Per the plan, A3 runs only if the gate passes. **The gate failed, so A3 was not run.**
A3 (richer 2-D lattice sampling) would add more frequency nodes but cannot fix the
root cause — it would feed the *same* M-confounded contrasts into the *same* chain, and
the extra nodes would still be compared at fixed subject frequency across different M.
Improving coverage does not repair a biased estimator.

## Diagnostic follow-up — is the low FFT contrast a duty-cycle artifact, or are the pads genuinely low-contrast?

Challenge: the FFT-fundamental Michelson C (`2|F(f0)|/|F(0)|`) is suppressed by duty
cycle / sparse coverage / 1-D collapse, so the reported 1–10% might understate the true
pad-vs-substrate contrast. `poc_comb_chain_contrast_inspect.py` re-registers two configs,
picks a well-covered magenta pad ROI (same plumbing as A1), and computes three contrasts
on the SAME best-focus de-rotated ROI. Artifacts under
`poc_comb_chain_out/contrast_inspect/`.

| config | M | ROI | (a) percentile C (p95,p5) | (b) Otsu-bimodal C | (c) FFT-fundamental C |
|---|---|---|---|---|---|
| bare Sigma 105 @ 1:1 | 1.05 | 5C/(1,2)#0, 587×1270 | **0.519** | **0.229** | **0.037** |
| Sigma 105 +TC-2001 @ 2:1 | 2.09 | 2D/(2,3)#0, 1556×872 | **0.486** | **0.230** | **0.036** |

**Bimodality verdict: the ROIs are NOT cleanly bimodal — they are unimodal.** The
histograms (`*__hist.png`) show a single broad peak; `valley_depth = 0.00` (low-M) and
`−0.09` (high-M) — there is no valley between two modes, the "dark/bright" split is an
Otsu cut through one continuous distribution. The pad-mean and substrate-mean differ by
only ~50–60 DN out of 255. The upscaled crops (`*__roi.png`) explain why: the pads are
**textured/dimpled metal pads on a substrate of similar mean brightness**, peppered with
sparse specular highlights — not high-contrast dark-square-on-bright-field bond pads.

**Reconciling the three numbers.** (a) percentile C ≈ 0.5 is high only because it spans
the 5th–95th percentile of a wide unimodal spread *including specular highlights* — a
dynamic-range measure, not a structural-contrast measure. (b) Otsu C ≈ 0.23 is modest
and, with no histogram valley, splits one mode rather than separating two. (c) FFT-
fundamental C ≈ 0.036 is low for three compounding, real reasons: (i) sparse/low-duty
pad array → small fraction of modulation in the fundamental; (ii) `|F(0)|` dominated by
the large near-uniform substrate area, deflating `2|F(f0)|/|F(0)|`; (iii) the 1-D
collapse averages across imperfectly-aligned rows and misses 2-D texture/harmonic energy.

**Bottom line: the low-contrast finding stands.** Part of the (a)-vs-(c) gap is the
expected duty-cycle/DC/1-D-collapse deflation the challenge describes — but the
structural contrast itself is genuinely modest (Otsu C ≈ 0.23, no valley): these are
low-modulation textured pads, not crisp bimodal pads. The poor cross-config SNR at M≈1
has a real physical cause, not merely a metric artifact. (a),(b),(c) are also nearly
identical across M=1.05 and M=2.09 — consistent with B1's finding that these reads
barely discriminate configs.

## Diagnostic follow-up 2 — is the pad structural contrast hiding in a color channel?

Challenge: the prior contrast was measured on grayscale (`_decode_gray`); structure may
live in a color channel luma discards, and achromatic specular dots would be suppressed
there. **Corrected target model** (the "magenta" class name is only the GIMP *marking*
colour): the structure is **dark specular-metal cells on a light-brown substrate**, so
the discriminating axis is **warm/chroma** — headline channels `R−B` and `saturation`
(HSV S), with plain `R` and `luma` for comparison. (The earlier magenta-opponent
`Mag=(R+B)/2−G` is kept only for the record — deprioritised.)
`poc_comb_chain_contrast_color.py` decodes the SAME best-focus frame in COLOR, crops the
SAME ROI, and recomputes (a)(b)(c) per channel; it also reports a **specular-suppression**
metric `specLift` = (median value at the achromatic luma-p99.5 specular pixels − channel
median) / channel IQR (large + = dots still bright in this channel; ≤0 = dots
suppressed). (`contrast_color_stats.csv`.)

**Low-M (bare Sigma 105 @ 1:1, ROI 5C/(1,2)#0):**

| channel | (a) pct C | (b) Otsu C | (c) FFT C | valley | bimodal? | specLift |
|---|---|---|---|---|---|---|
| R | 0.461 | 0.245 | 0.032 | −0.23 | no | +3.67 |
| G | 0.535 | 0.238 | 0.039 | 0.00 | no | +4.90 |
| B | 0.639 | 0.347 | 0.048 | 0.00 | no | +3.98 |
| luma (baseline) | 0.519 | 0.231 | 0.037 | 0.00 | no | +4.80 |
| **R−B** (warm) | 0.509 | 0.305 | **0.101** | 0.33 | **yes** | **−0.77** |
| **sat** (HSV S) | **0.862** | **0.531** | 0.070 | **0.41** | **yes** | **−1.03** |
| Mag=(R+B)/2−G | 0.278 | 0.140 | nan | 0.28 | "yes" | +0.30 |

**High-M (Sigma 105 +TC-2001 @ 2:1, ROI 2D/(2,3)#0):**

| channel | (a) pct C | (b) Otsu C | (c) FFT C | valley | bimodal? | specLift |
|---|---|---|---|---|---|---|
| R | 0.449 | 0.241 | 0.036 | −0.11 | no | +2.61 |
| G | 0.522 | 0.240 | 0.041 | −0.10 | no | +3.62 |
| B | 0.547 | 0.272 | 0.036 | 0.00 | no | +4.25 |
| luma | 0.485 | 0.230 | 0.036 | −0.10 | no | +3.51 |
| **R−B** (warm) | 0.426 | 0.264 | **0.092** | **0.54** | **yes** | **−0.78** |
| **sat** (HSV S) | **0.788** | **0.466** | 0.086 | 0.11 | no* | **−1.29** |
| Mag | 0.220 | 0.109 | nan | 0.08 | no | 0.00 |

**Verdict: YES — extracting a warm/chroma channel materially raises the pad STRUCTURAL
contrast, makes the histogram bimodal, AND suppresses the specular dots. The corrected
warm-axis hypothesis is confirmed; the magenta-opponent is refuted.**

- **Best channel is `sat` (saturation); `R−B` is the best FFT/bimodality channel.**
  Saturation beats luma on Otsu C by **+130%** at low-M (0.531 vs 0.231) and **+103%** at
  high-M (0.466 vs 0.230), and on FFT C by +89%/+139% (0.070/0.086 vs 0.037/0.036). `R−B`
  more than **doubles–triples** the FFT C (0.101/0.092 vs 0.037/0.036) and is the most
  robustly **bimodal** channel (valley 0.33 low-M, 0.54 high-M). This is a real
  structural gain, not the marginal lift B gave — it is a different, cleaner signal.
- **The histograms become genuinely bimodal** (substrate mode vs metal mode separate):
  `R−B` flags bimodal at both M; `sat` is strongly bimodal at low-M (valley 0.41) and
  near-threshold at high-M (valley 0.11, just under the 0.15 flag — call it ~bimodal).
  Luma and all single primaries (R,G,B) stay unimodal (valley ≤0.00). *This overturns the
  follow-up-1 "unimodal / genuinely low-contrast" conclusion on the warm axis* — the pads
  are NOT low-contrast against the substrate; luma was hiding the chromatic separation.
- **Specular dots are suppressed — confirmed quantitatively and visually.** In luma the
  achromatic dots sit ~4.8 IQRs above median (specLift +4.80/+3.51); in `R−B` and `sat`
  they drop to **−0.8 to −1.3** (i.e. *below* the substrate median — neutral specks are
  desaturated). The own-channel bright tail (`spec_p999`) collapses from ~4.8 IQR (luma)
  to ~1.0–1.6 IQR (R−B/sat). Visually (`view_*chan_best_sat__roi.png` vs
  `*chan_luma__roi.png`): luma is peppered with white dots over a low-contrast grid; in
  saturation the dots vanish and the pad grid pops as dark cells on a bright saturated
  substrate.
- **Plain R does NOT beat luma** (Otsu 0.245/0.241 vs 0.231/0.230) and does not suppress
  speculars (specLift +3.67/+2.61) — the warm separation needs the *difference/ratio*
  (R−B) or the *saturation*, not the R primary alone. **Mag is the worst** channel
  (Otsu 0.14/0.11, FFT undefined) — the pads are not magenta-dominant, confirming the
  correction.
- **Chroma subsampling is not the limiter** (confirming the challenge): the pad
  fundamental is low-frequency (0.034–0.093 cy/px) and the winners (R−B, sat) survive
  4:2:0 with the highest FFT C of any channel — low-freq chroma is preserved.
- **RAW would likely *strengthen*, not change, this conclusion.** JPEG chroma is
  subsampled and slightly denoised; a RAW demosaic would give cleaner per-pixel chroma,
  so R−B/sat separation can only improve. The qualitative result (warm axis is bimodal &
  specular-free) already holds on JPEG.

**Net effect on the main verdict:** this is the most actionable diagnostic finding.
Reading these magenta-pad arrays on **saturation or R−B instead of luma** roughly
**doubles** the pad structural contrast, makes the histogram bimodal, and removes the
specular-highlight contamination that was inflating the percentile/dynamic-range
measure. It does **not** rescue the cross-M comb-chain (the M-confound is an axis
problem, orthogonal to channel choice — both M's improved by similar large factors), but
it is a clear, M-independent SNR win worth promoting if A5/periodic-FFT is productionised:
**decode the warm/saturation channel for these pad features, not luma.**

## A5 is the salvageable result

A5 (the M-aware maze/band utilities) is correct and independently useful: it fixes a
real, demonstrated bug in `atlas_periodic_fft.discover_fundamental` — at M≳1.5 the
static (0.06,0.30) band locks onto the maze and reports a bogus ~77 lp/mm "pad
fundamental" (11/11 and 8/8 regions on the two TC-2001 @2:1 configs). The M-aware band
+ M-aware maze exclusion is a drop-in correction worth promoting to production
*independently of the chain*.

## Recommendation

- **Do NOT promote the comb-chain (A1+B1) to production.** The cross-M comparison at
  fixed subject frequency is fundamentally M-confounded; it ranks empty magnification as
  resolving power. The transitive idea is sound *only within a single M* (where pixel
  frequency is shared), which collapses it back to the existing same-M periodic ranking.
- **Do consider promoting A5** (the M-aware band + maze labelling) into
  `periodic_fft.discover_fundamental` / `atlas_periodic_fft` — it fixes a confirmed
  high-M bug with no downside.
- If a cross-M sharpness chain is still wanted, the comparison variable must be
  M-invariant: either compare **self-normalised harmonic-MTF *shape*** within each
  config (`harmonic_mtf` already gives MTF(nf)/MTF(f) with the target content divided
  out — a true M-free ratio) and chain the *shapes*, or compare at a fixed **sensor**
  (pixel) frequency rather than a fixed subject frequency. That is a different POC.

---

# Follow-up POC (2026-06-29) — fixed-sensor-frequency test + pad-population diagnostic

New UNTRACKED scripts (no production module modified; production helpers imported
read-only): `poc_comb_chain_t1_fpx.py` (pure-CSV re-analysis of `a1_all.csv`),
`poc_comb_chain_t1_hmtf.py` (decode-based intrinsic-corrected harmonic_mtf, nufan),
`poc_comb_chain_t1_psd.py` (decode-based radial PSD cross-check, nufan),
`poc_comb_chain_t2_padpop.py` (pad-population segmentation, nufan).

## Task 1 — fixed-SENSOR-frequency (cy/px) re-analysis: does it de-confound M?

**Headline answer: NO. Fixing the sensor (pixel) frequency does not de-confound
magnification — it only relocates the confound, and the relocation is f_px-dependent.**
The M-confound is not an artifact of *which* frequency axis you pick; it is the wafer
target's harmonic structure interacting with the sensor MTF, and that survives the
change of axis.

### 1. De-confounding test (headline numbers)

Apples-to-apples with the report's baseline (per-config aggregate vs M; the +0.33/+0.70
figures = per-config MEDIAN contrast over all valid SNR≥3/ceiling-valid rungs vs M,
reproduced here as +0.327/+0.778). The fixed-f_px variant interpolates each config's
median-contrast-vs-f_px curve to a common cy/px and correlates that with M:

| comparison axis | corr(M, C_raw) | corr(M, C/ceiling) |
|---|---|---|
| **fixed f_subj (BASELINE)** | **+0.327** | **+0.778** |
| fixed f_px = 0.10 cy/px | **−0.095** | +0.233 |
| fixed f_px = 0.12 | +0.177 | +0.528 |
| fixed f_px = 0.15 | **+0.627** | +0.805 |
| fixed f_px = 0.18 | **+0.778** | +0.864 |
| fixed f_px = 0.20 | +0.547 | +0.822 |

The correlation does **not** fall to ~0 across the board. It is strongly *f_px-dependent*:
near-zero (even slightly negative) only in a narrow window around **f_px ≈ 0.10 cy/px**,
and it *rises back to the baseline level (+0.55…+0.78 raw)* at f_px ≥ 0.15. Ceiling-
normalising makes it worse at every f_px (as it did for f_subj). The geomean of the
interpolated contrast across {0.10, 0.15, 0.20} vs M is +0.55 — no better than baseline.

**Mechanism (diagnosed, not assumed).** At a fixed pixel frequency the *subject* feature
being read still differs by M (subjLpmm = f_px·229.9·M), so different configs populate
the same f_px bucket with **different harmonic orders**: at f_px≈0.20, the M≈1 configs
can only reach that cy/px with weak high-order pad harmonics (3rd/4th — square-wave teeth
fall as 1/n), while the high-M configs reach it with the strong pad *fundamental* or the
maze. Median contrast in that bucket is 0.011 (low-M) vs 0.052 (high-M) — a 5× gap that
is target-harmonic-order bookkeeping, not glass quality. This is the *dual* of the
f_subj confound: f_subj let high-M read a fixed feature at an easier pixel frequency;
f_px forces low-M to climb to weak high harmonics to reach a fixed pixel frequency.
Neither axis is M-free because the wafer's harmonic comb is not M-free.

**Intrinsic-correction attempt (the coordinator's methodology fix).** Each captured
tooth is MTF(n·f0)·T_n where T_n≈|sinc(nD)| is the target's intrinsic harmonic content.
Dividing it out *should* leave a pure MTF sample. Two ways:
- *Analytic* (divide the CSV `contrast` by |sinc(nD)|/|sinc(D)|, sweep duty D): corr(M,C)
  stays **+0.5…+0.86** and is **unstable in D** — no de-confounding.
- *Proper* (`poc_comb_chain_t1_hmtf.py`: decode the saturation profile, run production
  `harmonic_mtf` which estimates D and applies the sinc correction, divide by DC, then
  interpolate the absolute MTF samples to common f_px): corr(M, MTF) drops to **−0.27 /
  −0.17 / +0.03** at f_px 0.10/0.15/0.20. *Numerically this looks de-confounded* — BUT
  the underlying estimator is unusable: the self-normalised MTF *shapes* it produces are
  **physically impossible** (e.g. bare Sig105 `[1.00, 2.86, 0.15,…]`, Sig150+TC-1401
  `[1.00, 26.47,…]`, ZMC105+5T+6T `[…, 1.96,…]` — a real MTF is monotone ≤1), the
  fixed-f_px rankings are dominated by such outliers (Sig150+TC-2001 1_1 floats to
  MTF=0.21 at f_px=0.10), empty-magnification violations persist at every f_px, and the
  **duty-cycle sensitivity sweep completely reshuffles the top-5** (D=0.3/0.4/0.5/0.6
  give different leaders). So the near-zero correlation reflects estimator *scatter*, not
  a clean M-free measurement — exactly the "T_n is uncertain on textured/specular cells"
  caveat the coordinator flagged, confirmed empirically. The square-wave/duty-cycle model
  is simply wrong for these dimpled metal pads.

### 2. Coverage matrix at common sensor frequencies

Coverage is **excellent and is NOT the problem** — refuting the "low-M target-thin"
worry. At f_px = 0.10, 0.15 and 0.20 (±0.02 cy/px), **all 16/16 configs** have a usable
(SNR≥3, ceiling-valid) rung, and **all 10 low-M configs (M<1.15)** are covered at every
target. Per-config the pad comb resolves all 7 predicted harmonics sub-Nyquist at every
M, and the maze adds 8–56 teeth per config. The teeth-span **intersection across all 16
configs is [0.052, 0.338] cy/px** (low-M intersection [0.052, 0.394], high-M
[0.042, 0.338]) — so a common-f_px comparison needs **no extrapolation** anywhere in
0.052–0.338. (Higher-M configs do slide the comb down and gain more sub-Nyquist teeth,
as expected, but low-M is already comb-rich because its 7 harmonics + maze all fit.)

### 3. Fixed-f_px ranking + the empty-magnification test

Ranking configs at a common cy/px (interpolating each config's contrast-vs-f_px):

| f_px | top-3 | empty-mag +TC floats above bare donor? |
|---|---|---|
| **0.10** | bare AF200, bare Sig105, bare Sig150 (all M≈1) | **mostly NO** — only a marginal Sig105+TC-1401@1:1 (0.0308) ≈ bare Sig105 (0.0295) |
| 0.15 | Sig105+TC-2001@2:1, Sig105+TC-1401@1.4, ZMC105+5T+6T | **YES** — TC-2001@2:1 & +5T+6T outrank their bare donors |
| 0.20 | Sig105+TC-1401@1.4, Sig150+TC-1401@1.4, Sig150+TC-2001@2:1 | **YES, badly** — 7 +accessory configs float above their bare donors |

Sanity vs known orderings is **only satisfied at f_px≈0.10**: there bare 105 ≈ bare 150
(0.0295 vs 0.0294 ✓), bare modern macros lead, and the diopter/MCON-35 stacks sink to
the bottom (✓), and — critically — **fixed-f_px at 0.10 STOPS floating empty-mag +TC
configs above bare lenses** (the f_subj failure). At f_px ≥ 0.15 the empty-mag float
returns in force, so the de-confounding only "works" in a knife-edge low-f_px window
that happens to coincide with where every config's pad fundamental lands (subjLpmm≈20–25
there, the actual pad pitch) — i.e. it works only where everyone is reading the *same
fundamental*, which is just same-subject-feature comparison in disguise, not a general
cross-f_px method.

### 4. Radial-PSD cross-check (target-agnostic)

`poc_comb_chain_t1_psd.py` computes a windowed radial PSD on the best-focus saturation
ROI and reads normalised PSD at fixed f_px — target-agnostic, works at low M (caveat:
PSD = MTF²·intrinsic-spectrum). It **agrees with the comb finding**:

| f_px | PSD top-3 | corr(M, PSD) |
|---|---|---|
| **0.10** | bare Sig150, bare Sig105, bare ZMC105 | **−0.40** |
| 0.15 | Sig105+TC-2001@2:1, Sig105+TC-1401@1.4, ZMC105 | +0.55 |
| 0.20 | Sig105+TC-1401@1.4, Sig105+TC-2001@2:1, ZMC105 | +0.53 |

Same pattern, independent metric: at f_px≈0.10 the bare lenses correctly lead and
corr(M,·) is negative; at f_px≥0.15 the empty-mag +TC configs float to the top and
corr(M,·) climbs back to ~+0.5. (`psd_fpx.csv`, `psd_curves_sat.png`.)

### Task 1 recommendation

**Fixed-sensor-frequency is NOT a viable cross-M axis worth productionising.** It does
not de-confound magnification; it relocates the confound and only "works" in a narrow
f_px≈0.10 window that coincides with everyone reading the same pad fundamental — i.e. it
degenerates to a same-subject-feature (≈ same-M) comparison, the very thing the existing
periodic ranking already does. Above f_px≈0.15 it floats empty-magnification +TC configs
above bare lenses just as the f_subj axis did. The proper intrinsic-correction
(`harmonic_mtf`) cannot rescue it because the duty-cycle/square-wave target model breaks
on these textured/specular metal pads (impossible MTF shapes, duty-cycle-sensitive
rankings) — and the cross-structure check below shows the same break directly. The
report's standing conclusion is unchanged and now stronger: there is **no M-invariant
cross-M sharpness axis recoverable from this wafer target with this contrast/MTF
estimator**; cross-M comparison collapses to within-M (same pixel frequency = same
subject feature) comparison.

#### Cross-structure consistency + cross-M overlap (coordinator extensions)

Treating the comb as structure-agnostic (a pad tooth and a maze tooth at the same f_px
both estimate the *same* system MTF) gives two sharp diagnostics:

- **Cross-structure consistency FAILS.** Where a pad tooth and a maze tooth land at the
  same f_px within a config, their intrinsic-corrected MTF estimates should agree.
  Instead the **pad/maze MTF ratio is median 5.15× (geomean 4.74×, log-spread 0.46 ≈ 58%
  typical disagreement)** across all 16 configs — pad reads ~5× higher than maze at the
  same sensor frequency. A valid MTF would give ~1×. This confirms the absolute-MTF
  variant is untrustworthy: either the duty-cycle/square-wave model is wrong (textured
  pads) or the 1-D maze collapse under-reads (the report already noted maze under-reads
  vs the 2-D `maze_amp` annulus) — probably both. **Trust nothing built on the absolute
  intrinsic-corrected MTF.**
- **Cross-M overlap at f_px≈0.20 does NOT line up.** The hope: low-M reads its pad
  fundamental there, mid-M its 3rd, high-M its 5th, and after intrinsic correction they
  coincide. They don't: the intrinsic-corrected pad-MTF proxy at f_px=0.20 is ~0.02–0.05
  for M≈1 but jumps to **0.25–0.31 for M≈1.45–1.48** — a 5–10× discontinuity exactly at
  the M where the harmonic order populating the bucket changes. The pad comb alone cannot
  compare across the full M range at fixed f_px. The **only band with usable cross-M
  coverage is f_px≈0.10**, and only because there everyone is on the fundamental (which,
  as noted, is same-subject-feature comparison, not a genuine cross-f_px chain).

## Task 2 — pad-population diagnostic (metal cells: TWO brightness populations or ONE?)

`poc_comb_chain_t2_padpop.py` segments the metal cells using the SATURATION channel
(diag-2's clean grid), recovers the pad lattice (FFT pitch + phase along u and v), tiles
per-cell regions, and asks whether the **metal cells themselves** split into two
brightness modes (distinct from the expected substrate-vs-metal grid contrast). Per cell
it takes a specular-robust central statistic (MEDIAN and p40) on LUMA and R−B over the
inner 50% of each cell. Artifacts under `poc_comb_chain_out/contrast_inspect/padpop/`
(`padpop_stats.csv`, `*__metal_luma_median_hist.png`, `*__cellmode_map.png`).

| config (region) | M | metal cells | luma-median bimodality | R−B-median bimodality | neighbour alternation | two-pop Michelson (luma) |
|---|---|---|---|---|---|---|
| bare Sigma 105 @1:1 (5C/(1,2)) | 1.05 | 308 | **UNIMODAL** valley −0.86 | unimodal valley −0.71 | 0.04 | 0.135 |
| Sigma 105 +TC-2001 @2:1 (2D/(2,3)) | 2.09 | 303 | weakly **BIMODAL** valley 0.32 | bimodal valley 0.32 | 0.40 | 0.125 |

**Verdict: predominantly ONE population; no clean two-population structure that would
cancel the fundamental.**

- **Primary config (low-M bare Sigma 105 @ 1:1): ONE population.** The per-cell
  luma-median histogram (`low_M_bareSigma105_1to1__metal_luma_median_hist.png`) is a
  single peak at ~115 DN with a thin left tail; `valley_depth = −0.86` (no valley — the
  Otsu cut at 103 clips the tail of one continuous mode). Only 25/308 cells (8%) fall in
  the "dark" Otsu class, and the cell-mode map (`*__cellmode_map.png`) shows those few
  dark cells confined to the right-edge column (partial/edge cells), NOT interspersed
  through the array. Neighbour alternation 0.04 ⇒ no checkerboard, no blocks — there is
  no second population to arrange. **No fundamental cancellation from a dark/light pad
  split.**
- **High-M config is a DIFFERENT wafer region** (2D/(2,3), not the same pads viewed at
  higher M), and there a genuine secondary dark mode appears: the luma-median histogram
  has a clear shoulder at ~90 DN (86/303 cells, valley 0.32). So *some* pad-array regions
  do carry two metal-cell brightness levels. But its spatial arrangement is **MIXED**
  (neighbour alternation 0.40 — neither a clean checkerboard/interleave at 0.55+ that
  would cancel the fundamental, nor clean separate blocks at <0.35). The cell-mode map
  shows the dark cells scattered among bright ones without a consistent pitch-scale
  pattern.
- **Cost is small either way.** Even where a second mode exists, the two-population
  Michelson on luma is only ~0.125–0.135 — comparable to the substrate-vs-metal grid
  contrast and far below the saturation/R−B structural contrast that diag-2 found. The
  R−B channel splits the metal cells ~50/50 with Michelson ~0.40, but that is the
  warm/chroma substrate-vs-metal separation bleeding into the "metal" pool via imperfect
  saturation thresholding, not a within-metal brightness split.

**Bottom line:** the dark/light-pad fundamental-cancellation hypothesis is **not** the
explanation for the low FFT contrast in the primary low-M case — those metal cells are
one brightness population. A weak, spatially-mixed second mode exists in some other
regions but is small and not arranged to cancel the fundamental. This is consistent with
diag-1's "one broad mode" finding and reinforces that the low pad FFT-fundamental
contrast is a genuine low-modulation/duty-cycle/DC-deflation effect, not a two-population
cancellation artifact.
