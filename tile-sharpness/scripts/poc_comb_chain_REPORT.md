# POC: multi-frequency-spectrum cross-config sharpness ranking (comb + chain)

**Status:** completed exploratory POC, committed as a record (2026-06-29). No
production module was modified by this POC; production helpers are imported read-only.
Compute ran on nufan (16 cores) over the shared NFS path. Spanning subset = 16 configs
(`poc_comb_chain_subset.csv`), M ≈ 0.86 → 2.09, chosen for cross-M frequency overlap.

## Executive summary (bottom line)

**Outcome (caveats-first — see `../../LEADING_WITH_CAVEATS.md`): two distinct cross-M
questions, two answers.**
- **ABSOLUTE / subject-resolution cross-M** ("which config resolves more detail per mm
  on the wafer"), via the periodic-comb / harmonic-content route, is **DEAD — proven, not
  inferred.** The wafer's periodic targets have genuinely unstable harmonic content
  (Stage Preproc: linear, MTF-preserving pre-processing cannot move the collapse
  residual/floor off ~1.5 — it's the target, not the measurement). Only a purpose-shot
  clean grating/edge chart (new acquisition) would change this.
- **RELATIVE cross-M glass-MTF ranking** ("which lens has higher MTF at a given pixel
  scale") **IS achievable and CORROBORATED** (Stages AltEst / AltEst-2). The
  same-physical-patch **PSD-ratio at a fixed SENSOR frequency**, plus **pad-edge
  averaged-ESF** and **same-patch relative deconvolution** — three estimators on different
  physical principles (with a de-confounded through-focus fourth agreeing) — mutually
  converge on a 38-config ranking that reproduces §L end-to-end. **CAVEATS:** relative not
  absolute; fixed-sensor-frequency not subject-resolution; trustworthy only
  f_px ≈ 0.08–0.15; M≈2 configs reached via a (robust) transitive bridge.

**Use which, for what:** "resolves more SUBJECT detail" → within-M + diffraction ceiling
+ tolerance-ratios (§L). "Which glass is sharper at a pixel scale, across M" → the AltEst
consensus estimator (being productionised).

**The avenues tested (1–5 each reopened by a distinct buried assumption then closed; the
breakthrough is 6–7 — see the case study in `../../LEADING_WITH_CAVEATS.md`):**
1. Fixed-subject-frequency contrast → M-confounded (corr +0.33/+0.78).
2. Fixed-sensor-frequency (comb) → *relocates* the confound (corr ~0 only at a degenerate
   knife-edge that collapses to same-M).
3. Empirical per-structure `T_n` (Stage T_n) → fixed symptoms (maze even-harmonic content
   CONFIRMED, T2/T1=0.31) but no consistent `{T_n}`+MTF collapse (residual 0.79 vs 0.38).
4. Whole-target survey (Stage Targets, all 53 atlas targets) → instability is
   target-general, not pad-pattern-specific; the maze alone doesn't self-collapse (0.84).
5. Feature-locking audit (Stage Relock) → a real mislocking bug found (band floor +
   wrong-axis "auto"), inflating prior residuals (re-anchored 0.79→0.64), but correct
   anchoring did **not** revive cross-M (ratio ~1.46).
6. **Non-comb estimators (Stage AltEst) → BREAKTHROUGH:** the **same-patch PSD-ratio @
   fixed sensor freq** passes all four gates (incl. repeatability the comb failed);
   same-patch direct-detail / blind-PSF / SE-edge variants fail, each provably.
7. **Hardened + corroborated (Stage AltEst-2):** 38 configs → one robust connected graph;
   three independent-principle estimators agree (+ through-focus de-confounded & agreeing);
   consensus reproduces §L. → `out/altest2/p_consensus_ranking.csv`.

**Salvaged / banked (committed):** (a) **A5** M-aware maze/band fix (`29a3a80`).
(b) **Fundamental-detection fix** — added per-axis `discover_fundamental_2d` + opt-in
`PER_AXIS=1`, byte-identical default, §L verdict unchanged, 184 tests (`25d9d43`).
(c) **Saturation / R−B** decode — M-independent SNR win for pad features (2–3× vs luma,
suppresses achromatic speculars). (d) **The AltEst consensus relative cross-M estimator**
— the headline deliverable, being promoted from POC to production.

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
| `poc_comb_chain_tn_{extract,analyse}.py` + `tn_run.sh` | Stage T_n: empirical per-structure `T_n` + self-cal collapse |
| `poc_comb_chain_targets_phase{1,2}.py` | Stage Targets: 53-target 2D-FFT survey + per-target collapse |
| `poc_comb_chain_relock_{a_audit,diag,b_extract,b_analyse}.py` + `relock_b_run.sh` | Stage Relock: feature-locking audit + re-anchored collapse |
| `poc_comb_chain_preproc_{extract,analyse}.py` + `preproc_run.sh` | Stage Preproc: linear pre-processing cause-isolation ablation |
| `poc_altest_{lib,fov,patch_driver,patch_analyse,psf_focus,psf_focus_analyse,edge,edge_analyse,consolidate,smoke}.py` + `poc_altest_run.sh` | Stage AltEst: 5 non-comb estimators + gates |
| `poc_altest2_*.py` + `poc_altest2_subset.csv` | Stage AltEst-2: hardened same-patch ranking, refined through-focus, new variants, cross-agreement |

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

---

## Stage T_n — empirical per-structure harmonic content (PLANNED 2026-06-29)

**Why.** The Task-1 verdict ("fixed-sensor-frequency relocates the M-confound; chain not
viable") rested partly on the harmonic-MTF cross-structure check failing (pad vs maze
intrinsic-corrected MTF disagree ~5× at the same f_px). But two facts reopen it:
1. The intrinsic-correction **already de-confounds M** — `corr(M, MTF)` collapsed from
   +0.33/+0.78 (raw) to −0.27 / −0.17 / +0.03. The axis was never the blocker; the
   harmonic-content model is.
2. The 5× disagreement is most likely an **artifact of the assumed `T_n`**: we applied
   ONE odd-only square-wave model (`T_n=|sinc(nD)|`, even harmonics ≡ 0) to TWO different
   signals. Pads and maze have different real spectra, and the **maze skips/merges cycles
   → genuine EVEN (N=2) harmonic content** the model forces to zero. So neither structure
   is correctly de-weighted, and the residual MTFs can't be expected to match.

If a *correct* `T_n` makes the MTF physical (≤1) AND the cross-structure MTF agree while
preserving the de-confounding, the cross-M chain may be viable after all.

**Approach (run on the saturation channel — specular-suppressed, so `T_n` has the best
chance of being stable):**
1. **Direct empirical `T_n`, where MTF≈1.** At high M the low-order harmonics sit at low
   cy/px where the system MTF≈1, so measured amplitude ≈ `T_n` directly. Clean for pads
   (fundamental ~0.039 cy/px at M=2); only low orders for the maze (fundamental already
   ~0.167 cy/px, into the rolloff).
2. **Self-calibration across M (primary, more robust).** The same structure at several M
   places its teeth at different cy/px. Require all `A_n / T_n` to collapse onto a single
   MTF(f_px) curve, and jointly solve for `{T_n}` and the curve. A consistent solution
   simultaneously (a) measures `T_n` empirically and (b) proves the structure's content is
   stable. If NO `{T_n}` makes them collapse, the content is specular-unstable and the
   approach is genuinely dead — a definitive answer either way.

**Validation (the gates):**
- Re-run the **cross-structure agreement** check with empirical per-structure `T_n` — does
  the ~5× pad-vs-maze disagreement shrink toward ~1×?
- Re-confirm the **M de-confounding** holds (corr stays ~0) and the **MTF values become
  physical** (≤1, monotone non-increasing).
- Re-run the **fixed-f_px ranking** sanity (bare 105≈150; 105 more TC-tolerant than 150;
  macros > primes > diopters; no empty-magnification float).

**Gating risk:** works only if each structure's `T_n` is *stable* (fixed-but-non-square)
across the configs/field/focus compared; if the texture/speculars make it vary, it won't
transfer. The self-calibration collapse test is the direct check. Driver:
`poc_comb_chain_tn_*.py` (to be added).

---

## Stage T_n — RESULTS (2026-06-29)

**Headline: empirical/self-calibrated `T_n` fixes the SYMPTOMS the prior POC flagged
(invalid >1 MTF gone; median pad-vs-maze disagreement 5.15× → 0.93×) and CONFIRMS the
even-harmonic hypothesis (maze `T2/T1 = 0.31`, square-wave predicts 0) — but it does NOT
rescue the cross-M chain. The decisive self-calibration collapse test FAILS: no
consistent `{T_n}` + single MTF(f_px) curve exists. The cross-M sharpness chain is
DEFINITIVELY DEAD on this target.**

New UNTRACKED scripts/data (no production or committed-lib module modified — production
helpers + the committed `poc_comb_chain_lib`/`atlas_periodic_fft` imported read-only;
the maze-harmonic read was copied locally into the extractor, not patched into the lib):
`poc_comb_chain_tn_extract.py` (saturation-channel comb-amplitude extractor: A1 plumbing,
decode HSV-S per region instead of luma, ALSO reads maze harmonics 2f–4f), 
`poc_comb_chain_tn_run.sh` (sharded N=8 nufan runner), `poc_comb_chain_tn_analyse.py`
(structure-typed self-calibration + gates). Heavy regenerable artifacts (`tn_all.csv`,
`tn_shard_*`, logs) added to `.gitignore`; small results live under
`poc_comb_chain_out/tn/` (`tn_empirical.csv`, `tn_mtf_samples.csv`).

**Data.** Re-extracted on the SATURATION channel (specular-suppressed; diag-2 winner),
all 16 configs, M 0.90–2.09, **4766 comb rows** (4251 SNR≥3/ceiling-valid). Teeth grouped
by STRUCTURE TYPE = (cls, pad-pitch cluster) + maze, so different gratings are never
pooled. The a1 fundamental histogram has three pad pitch clusters (~11, ~16, ~35 lp/mm
subject) × {magenta, cyan}, plus the maze. The two data-rich types are `magenta.P11`
(1963 teeth, all 16 configs) and `magenta.P16` (1463, all 16); cyan and the ~35 lp/mm
clusters are thin.

### The decisive stability test — DOES A CONSISTENT {T_n}+MTF COLLAPSE EXIST? **NO.**

Self-calibration solves `log A_n(M) = log MTF(f_px) + log T_n` per structure type
(isotonic-decreasing MTF in f_px × per-order `T_n`, gauge `T_1=1`), pooling all
configs/regions. The **collapse residual** is the load-bearing number; the meaningful
baseline is the *per-order-only* null (remove a per-order mean, ignore the MTF rolloff
entirely): if the MTF curve is real, the collapse residual must fall well below it.

| structure type | n teeth | configs | collapse resid | per-order-only null | square-wave-`T_n` resid |
|---|---|---|---|---|---|
| **magenta.P11** (primary) | 1963 | 16 | **0.790** | 0.866 | 2.722 |
| magenta.P16 | 1463 | 16 | 0.831 | 0.885 | 2.989 |
| maze | 608 | 16 | 0.842 | 1.000 | 1.158 |
| cyan.P11 | 113 | 10 | 0.728 | 0.830 | 2.826 |
| cyan.P16 | 90 | 12 | 0.986 | 1.048 | 3.216 |

Residuals are in **log-contrast units** (0.79 ≈ a factor-2.2 typical miss). The empirical
`T_n` **massively beats the prior square-wave assumption** (0.79 vs 2.72 for the primary
structure — the square-wave model is simply wrong, as suspected). **But it barely beats
ignoring the MTF rolloff at all** (0.79 vs the 0.87 per-order null — a ~9% improvement).
The teeth do **not** collapse onto a single MTF(f_px) curve.

Restricting to the cleanest case — primary `magenta.P11`, **low orders only** (where the
saturation signal is strongest and not noise/alias-dominated) — does not help:

| magenta.P11 | collapse resid | per-order null |
|---|---|---|
| orders ≤3 | 0.686 | 0.719 |
| orders ≤4 | 0.689 | 0.721 |
| orders ≤7 | 0.790 | 0.866 |

Even here the MTF rolloff explains **~5%** of the scatter (0.686 vs 0.719). For
calibration, the **within-single-config** collapse residual (same M, only region-replicate
+ measurement scatter) is **0.382** — so the cross-M residual (0.69) is ~1.8× the
single-config noise floor. The configs do **not** share a common MTF curve beyond what one
config's own region-to-region scatter already imposes. **No `{T_n}` makes the points
collapse → the harmonic content is texture/measurement-unstable across configs → the
approach is genuinely dead (definitive negative).**

### Empirical `T_n` vs the square-wave assumption (and the maze N=2 prediction)

| structure | `T_1` | `T_2` | `T_3` | `T_4` | `T_5` | comment |
|---|---|---|---|---|---|---|
| **magenta.P11** | 1.00 | 0.23 | 0.18 | 0.15 | 0.17 | physically sensible: monotone-ish decay, **strong even (N=2) content** |
| magenta.P16 | 1.00 | 0.95 | 1.25 | 2.97 | 5.02 | **rises with order → unphysical** (high orders noise/alias-dominated) |
| maze | 1.00 | **0.31** | — | — | — | **even N=2 content CONFIRMED** (square-wave predicts 0) |
| square wave (D=0.5) | 1.00 | 0.00 | 0.33 | 0.00 | 0.20 | odd-only — the prior, wrong assumption |

Two clear conclusions:
1. **The maze really does carry even (N=2) harmonic content** — `T2/T1 = 0.31`, exactly
   the report's prediction that the maze "skips/merges cycles." The odd-only square-wave
   model that forced `T_2 ≡ 0` was wrong, which is *why* the prior pad-vs-maze MTF
   disagreed ~5× (it mis-weighted the maze). This part of the hypothesis is **vindicated.**
2. **`T_n` is only stable where signal is strong.** The primary `magenta.P11` low orders
   give a believable falling spectrum; but `magenta.P16`/cyan `T_n` *rise* with order
   (`T7` up to 24×) — a tell-tale that at high order the solver is absorbing
   noise/alias/specular-residual energy into `T_n` because there is no real MTF collapse to
   constrain it. Saturation suppressed the speculars (the channel choice was right and the
   contrasts are physical) but did **not** make the content stable enough to self-calibrate.

### Validation gates (re-run with empirical `T_n`)

| gate | prior (square-wave) | empirical `T_n` (saturation) | verdict |
|---|---|---|---|
| **Physicality** (MTF ≤ 1) | invalid: shapes like `[1, 26.5, …]` | **0.0% of 4245 samples > 1.0**; median 0.029, p95 0.22 | **PASS** |
| **Cross-structure** pad/maze MTF @ shared f_px | **5.15× median** | **0.93× median, 0.85× geomean** | median PASSES… |
| …but its spread | log-spread 0.46 | **log-spread 0.97** (≈ factor-2.6 typical miss) | …**individual pairs scatter worse** |
| **M de-confounding** corr(M, MTF) | +0.33/+0.78 raw → −0.27/−0.17/+0.03 | **−0.17 / −0.48 / −0.45** @ f_px 0.10/0.15/0.20 | over-corrects to negative, not clean 0 |
| **Ranking sanity** | empty-mag float | **still floats** (see below) | **FAIL** |

**Physicality is the real win** of empirical `T_n` + DC-normalisation: dividing by the
*measured* `T_n` and `|F(0)|` keeps every MTF sample ≤ 1, eliminating the impossible >1
shapes that sank the prior variant. The median cross-structure agreement collapsing from
5.15× to ~0.93× confirms the 5× was indeed "wrong shared `T_n`," not a real physical gap —
**but the per-pair log-spread is 0.97**, i.e. a *typical* pad-vs-maze pair still disagrees
by ~2.6×. The median agrees because the errors are now centred, not because they are
small. That scatter is the same non-collapse seen in the residuals.

**Ranking still fails** (the empty-magnification fallacy persists):

| f_px | top-3 | empty-mag +TC floats above bare donor? | bare105/bare150 (want ~1) |
|---|---|---|---|
| 0.10 | bare Sig150, bare Sig105, bare AF200 | marginal (only ZMC105+5T+6T > bare ZMC105) | 0.67 |
| 0.15 | bare Sig150, bare AF200, bare ZMC105 | **YES** — Sig105+TC-2001 & +TC-1401 > bare Sig105 | 0.28 |
| 0.20 | bare Sig150, bare AF200, bare ZMC105 | **YES, badly** — 4 +TC configs > bare Sig105 | 0.08 |

At f_px≈0.10 the bare lenses do lead (good) — but, as in Task 1, that is the knife-edge
window where everyone is on the pad fundamental (same-subject-feature comparison in
disguise). Above f_px≈0.15 the empty-magnification +TC configs float above their bare
donors again, and bare 105 reads 3–12× *below* bare 150 (should be ≈1×). The structure-
corrected MTF still does not produce a physically sane cross-M ranking. The negative
M-correlation is over-correction (the high-M teeth now read systematically *low* after
dividing by a `T_n` fit that the high-M data itself dominated), not a clean de-confounding.

### Verdict & recommendation

**Definitively dead — and now we know precisely why.** The prior POC's caveat ("one
credible rescue path untested: measure `T_n` empirically") has been tested and closed:

- The empirical/self-calibration `T_n` **does** repair the two artifacts that the prior
  square-wave model produced — MTF values are now physical (≤1) and the median pad-vs-maze
  disagreement falls from 5.15× to ~1×. The even-harmonic (maze N=2 = 0.31) hypothesis is
  confirmed. So the prior 5× was indeed a wrong-model artifact, exactly as suspected.
- **But the decisive collapse does not exist.** No `{T_n}` + single MTF(f_px) curve makes
  the teeth collapse (cross-M residual 0.69–0.79 vs a 0.72–0.87 per-order null vs a 0.38
  within-config floor). The harmonic content is not stable enough across configs to define
  the shared MTF the cross-M chain needs — the per-pair cross-structure spread (0.97) and
  the rising-`T_n` instability on the secondary structures are the same failure seen three
  ways. Saturation removed the speculars but the residual texture/measurement variation
  still defeats self-calibration.

This makes the report's **standing conclusion final, not merely "untested": there is no
M-invariant cross-M sharpness axis recoverable from this wafer target.** Do **NOT**
productionise the comb-chain or any absolute cross-M MTF built on it. The salvageable
results are unchanged: **A5** (M-aware maze/band, already promoted) and the **saturation/
R−B decode** SNR win (re-confirmed here — it makes the corrected MTF physical and is the
right channel for these pad features). Use within-M periodic ranking + the diffraction
ceiling + tolerance-ratios for cross-config comparison, as already recommended.

---

## Stage Targets — survey of ALL candidate periodic targets (2026-06-30)

**Why.** Every prior cross-M conclusion rested on ONE dominant magenta pad pattern
(`magenta.P11`) + the maze, whose harmonic content proved texture/specular-UNSTABLE
across configs (Stage T_n self-cal collapse residual 0.79 vs a 0.38 within-config floor).
That instability might have been PAD-SPECIFIC. This stage surveyed EVERY structured
region the atlas knows about — all magenta bond-pad patterns (all pad sizes/pitches),
the cyan `use_for_fft` experimental grids, the cyan slanted-edge bar, and the maze — to
ask whether ANY of them is clean + cross-M-stable + multi-harmonic enough to reopen
cross-M ranking.

**Headline: NO target reopens cross-M.** All candidates share the same instability. The
single cleanest, most multi-harmonic region on the entire wafer self-collapses to 0.62
(within-config floor 0.19 → cross-M scatter ≈ 3.4× the same-M noise) and the maze does
not self-collapse on its own either (0.84 vs 0.49 floor, ratio 1.7). There is no
clean + stable + multi-harmonic target; the standing "cross-M not viable" verdict holds
across the whole target catalogue, not just `magenta.P11`.

New UNTRACKED scripts/artifacts (no production / committed-lib module modified —
`atlas_periodic_fft`, `poc_comb_chain_lib`, `poc_comb_chain_tn_analyse` imported
read-only): `poc_comb_chain_targets_phase1.py` (2D-FFT cleanliness survey on one clean
low-M shot), `poc_comb_chain_targets_phase2.py` (per-target cross-M self-cal collapse,
reusing the Stage T_n machinery). Small result CSVs committed under
`poc_comb_chain_out/targets/` (`phase1_survey.csv`, `phase2_collapse.csv`,
`phase1_run.log`); the heavy 2D-FFT magnitude PNG dump
(`poc_comb_chain_out/targets/fft2d/`, ~7 MB) is gitignored (regenerate from phase1).

### Phase 1 — 2D-FFT cleanliness survey (low M)

Bare Sigma 105 @ 1:1 F8, best focus, M=1.054, registered RMSE 3.6 px. Enumerated **53
in-FOV regions** (49 magenta bond-pad arrays, 2 cyan experimental, 2 cyan slanted-edge).
For each region the best-focus ROI was de-rotated to the wafer u/v axes, decoded on the
SATURATION channel (specular-suppressed) + luma, and a full 2D FFT was run; each axis was
characterised for its fundamental + harmonic comb (peak SNR per harmonic, #harmonics with
SNR≥3). `phase1_survey.csv` (213 region-axis-channel rows) + 17 2D-FFT PNGs.

**Decisive structural finding: the measurable fundamental is the SUB-element pitch
(~11–17 lp/mm subject, 0.045–0.069 cy/px), NOT the atlas SUPER-pitch.** Across magenta
regions whose atlas `pad_pitch_px` spans 17–173 px (i.e. genuinely different pad
sizes/pitches), the discovered fundamental clusters tightly at ~11–17 lp/mm regardless —
the FFT locks onto the fine sub-element periodicity, which is the *same* feature class
the prior `magenta.P11`/`.P16` buckets already tested. So "the magenta class has multiple
pad patterns" is true at the super-pitch but collapses to ~one measurable comb at the
sub-element scale. The "different pad sizes" do **not** give a genuinely different MTF
target.

Cleanest multi-harmonic regions (saturation, ranked by #clean harmonics then fundamental
SNR):

| rank | region | cls | atlas pitch u/v (px) | axis | f0 (cy/px) | f0 subj (lp/mm) | fund SNR | #clean harm |
|---|---|---|---|---|---|---|---|---|
| 1 | 9D/(1,3)#2 | magenta | 45.6/51.2 | u | 0.0485 | 11.8 | 28.7 | **6** |
| 2 | 5D/(1,3)#2 | magenta | 45.6/51.2 | u | 0.0485 | 11.8 | 22.2 | **6** |
| 3 | 6C/(2,2)#1 | magenta | 80.4/11.6 | u | 0.0487 | 11.8 | 13.7 | 5 |
| 4 | 5E/(1,0)#0 | magenta | 173/44.7 | v | 0.0683 | 16.5 | 10.7 | 5 |
| … | (24 magenta regions reach a ≥2-harmonic comb) | | | | | | | |
| — | 4D/(0,3)#0 | cyan_se | (bar) | v | 0.1209 | **29.3** | 27.7 | 2 |
| — | 8C/(0,2)#0 | cyan | 58.9/136 | v | 0.0504 | 12.2 | 6.8 | 2 |
| — | 6C/(2,2)#0 | cyan | 22.6/89 | u | 0.0661 | 16.0 | 3.4 | 2 |

Notes: the cyan `use_for_fft` grids are **scarce in-FOV at M≈1** (only 2 of the 4 cyan
die types landed inside the frame) and **weak** (2 clean harmonics, fundamental SNR 3–7)
— no better than magenta. The cyan **slanted-edge bar** (4D) is the only target with a
genuinely *higher* fundamental (29 lp/mm along v) but it carries only 2 clean harmonics
(it is a single edge pair, not a deep comb) and is 1-D (the user's "horizontal-line
block" / vertical-direction use). The maze is 1-pitch (see Q1).

### Phase 2 — cross-M self-calibration stability (the real test)

Reused the Stage T_n self-calibration (isotonic MTF(f_px) × per-order `T_n`, saturation
channel, all 16 configs, M 0.90–2.09) per target type. The load-bearing number is the
**collapse residual** (log-contrast units) vs the **per-order-only null** (no MTF
rolloff) and the **within-single-config floor** (same M → region-replicate + measurement
scatter only; the cross-M residual cannot beat this, and *approaching* it = stable).

| target | n teeth | configs | orders | collapse resid | per-order null | within-config floor | verdict |
|---|---|---|---|---|---|---|---|
| `magenta.P11` (primary) | 1963 | 16 | 1–7 | 0.790 | 0.866 | 0.392 | UNSTABLE |
| `magenta.P16` | 1463 | 16 | 1–7 | 0.831 | 0.885 | 0.498 | UNSTABLE |
| `cyan.P11` | 113 | 10 | 1–7 | 0.728 | 0.830 | (thin) | UNSTABLE |
| `cyan.P16` | 90 | 12 | 1–7 | 0.986 | 1.048 | 0.217 | UNSTABLE |
| `cyan.P35` | 8 | 2 | 1–3 | 0.360 | 0.409 | 0.267 | UNSTABLE (too thin) |
| **maze (single-pitch)** | 592 | 16 | 1 | **0.842** | — | **0.490** | UNSTABLE (ratio 1.72) |
| cleanest die (1,3)#2 | 153 | 12 | — | **0.624** | 0.975 | (0.19 die-level) | UNSTABLE (ratio ≈3.4) |

low-order-only (orders ≤3): `magenta.P11` 0.686 (floor 0.386), `magenta.P16` 0.637
(floor 0.337) — still ~1.8× the floor, no collapse.

The three user questions, answered explicitly:

1. **Does the maze self-collapse on its own over its resolved range (M≳0.7)?** **NO.**
   The maze is single-pitch (one M-invariant subject frequency), so its fundamentals at
   different M sample ONE MTF(f_px) curve directly — the purest possible cross-M test,
   with NO `T_n` freedom. Its fundamentals span f_px 0.16 (M≈2) → 0.37 (M≈0.9), 592 teeth
   over all 16 configs. Fitting a single isotonic MTF(f_px) leaves a **collapse residual
   0.842 against a within-config floor of 0.490 (ratio 1.72)** — i.e. cross-config scatter
   is ~1.7× the same-M region-to-region noise. The maze does **not** lie on one curve; it
   is **not** the stable single-pitch anchor hypothesised. (Even-harmonic content is real
   but only resolvable at high M — 16 order-2 teeth total — so it adds nothing usable.)
   Even restricting to M≥1.0 the residual is 0.797. The maze's own same-M scatter is also
   large (floor 0.49, vs 0.39 for `magenta.P11`) because it is read across many field
   zones with field-dependent sharpness.

2. **Do any cyan regions give clean, stable combs?** **NO.** Cyan is both **thin** (≤12
   configs, 5–10 teeth/config vs 88–141 for magenta — too few to even define a per-config
   floor, hence the degenerate 0.000/0.217 floors) and **no cleaner**: `cyan.P11` collapse
   0.728, `cyan.P16` 0.986 — same order as magenta, both UNSTABLE. The cyan slanted-edge
   bar (29 lp/mm) is a clean 2-harmonic 1-D target but cannot self-calibrate a comb (only
   2 orders) and is sparse. No cyan target reopens cross-M.

3. **Do other magenta pad patterns (different pad sizes) behave better than P11?** **NO.**
   `magenta.P16` is *worse* (0.831 vs 0.790; floor 0.498 vs 0.392). At the sub-element
   scale that the FFT actually measures, all magenta "pad sizes" reduce to the same
   ~12–16 lp/mm comb (Phase 1), so they are not really different targets. To be maximally
   fair we also self-collapsed the SINGLE cleanest Phase-1 region class on its own — die
   type (1,3), comp #2 (atlas pitch 45.6/51.2, the 6-harmonic winner): collapse **0.624**
   against a within-config floor of **0.19** (ratio ≈3.4). The cleanest, most
   multi-harmonic target on the whole wafer is among the *least* cross-M-stable relative
   to its own noise floor.

### Verdict

**No target reopens cross-M absolute ranking.** Every candidate — the maze on its own,
all cyan grids, every magenta pad pattern, and the single cleanest multi-harmonic region
— shares the same pad-style instability: its harmonic content does not collapse onto a
shared MTF(f_px) curve across configs (collapse residuals 0.62–0.99, all well above their
0.19–0.50 within-config floors). The residuals do beat the per-order null (the MTF
rolloff is real and monotone), but they get nowhere near the noise floor a single curve
would require. The instability is therefore **not pad-pattern-specific** — it is a
property of these textured/specular metal targets imaged through a focus stack with
field-dependent sharpness, which saturation suppresses (the channel choice remains right)
but does not remove.

The maze is the cleanest *physical* idea (single pitch, M-invariant, no `T_n` ambiguity,
spans f_px 0.16–0.37) but it still fails to self-collapse (1.7× its floor), so it cannot
anchor a cross-M range either — not even a narrow one. The cyan slanted-edge bar is the
only higher-frequency clean target but is a single 2-harmonic edge, unusable as a comb.

This **confirms and generalises** the Stage T_n conclusion: there is no M-invariant
cross-M sharpness axis recoverable from ANY structured target on this wafer with this
contrast/MTF estimator — the limitation is the targets + estimator, not the choice of the
one pad pattern. Standing recommendation unchanged: within-M periodic ranking + the
diffraction ceiling + tolerance-ratios; the salvaged A5 + saturation/R−B decode remain
the only bankable results. **Do NOT commit** (exploratory POC, per the plan).

### New untracked files

- `poc_comb_chain_targets_phase1.py` — 2D-FFT cleanliness survey (one low-M shot).
- `poc_comb_chain_targets_phase2.py` — per-target cross-M self-cal collapse.
- `poc_comb_chain_out/targets/phase1_survey.csv` — 53-region ranked inventory (213 rows).
- `poc_comb_chain_out/targets/phase2_collapse.csv` — per-target collapse residuals.
- `poc_comb_chain_out/targets/phase1_run.log` — Phase-1 run log + ranked summary.
- `poc_comb_chain_out/targets/fft2d/*.png` — 17 2D-FFT magnitude images (GITIGNORED, ~7 MB).

---

## Stage Relock — feature-locking audit (2026-06-30)

**Why.** Every prior cross-M conclusion was read off a comb anchored by
`discover_pad_fundamental` (`poc_comb_chain_lib`), which discovers the pad fundamental by
collapsing the ROI to a **1-D profile** and searching a band whose floor is the static
**0.06 cy/px** (period ~17 px) — lowered to ~0.045 cy/px only once a hard-coded
`pad_f1_subj_lpmm=18.0` would clip. But the atlas declares pad-grid super-pitches of
**11.6–192.5 px → f_px ≈ 0.0052–0.086 cy/px**, mostly AT or BELOW that floor. The suspicion:
the genuine pad-array fundamental is excluded by design, the detector locks a finer
feature instead, and the resulting "comb" is not a true harmonic series — which would make
the cross-M instability a feature-locking artifact, not a property of the target.

**Headline: the suspicion is CONFIRMED — the detector is mis-anchored (band floor + a
1-D-collapse axis-selection bug). Re-anchoring on the true per-axis grid DID lower the
absolute collapse residuals (e.g. 0.790 → 0.643 for the dominant grid; low-order 0.686 →
0.34). BUT it did NOT revive cross-M ranking: the residual/floor RATIO only improved from
~2.0 to ~1.46 (best), never approaching the ~1.0–1.3 a single shared MTF curve needs; the
maze (single-pitch, no anchoring freedom) is unchanged at 0.845; the empty-magnification
+TC float and the unphysical bare105/bare150 ratios persist; and the two correctly-anchored
axes now disagree with the maze in OPPOSITE directions (pad_v/maze 0.23×, pad_u/maze 2.0×).
The committed "cross-M not viable (final)" conclusion therefore STANDS — but the mislocking
means the prior magnitudes (0.79/0.84) over-stated the residual; the verdict is now
confirmed for the RIGHT reason (true harmonic series still don't collapse), not the
feature-locking artifact.**

New UNTRACKED scripts/artifacts (no production / committed-lib module modified — all of
`atlas_periodic_fft`, `poc_comb_chain_lib`, `poc_comb_chain_tn_analyse` imported read-only):
`poc_comb_chain_relock_a_audit.py` (Phase A audit), `poc_comb_chain_relock_diag.py`
(per-axis spectrum dump), `poc_comb_chain_relock_b_extract.py` +
`poc_comb_chain_relock_b_run.sh` (re-anchored sharded re-extraction),
`poc_comb_chain_relock_b_analyse.py` (re-anchored cross-M collapse + gates). Small result
CSVs committed under `poc_comb_chain_out/relock/`; the bulk comb CSV (`relock_all.csv`),
shards, and the 2D-FFT PNG dump are gitignored (regenerable).

### Phase A — mislocking audit (ground truth vs detector)

Bare Sigma 105 @ 1:1 F8, best focus, M=1.054, registered RMSE 3.6 px. Six magenta regions
spanning the declared-pitch range, **including dies 5C and 5D**, de-rotated to the wafer
u/v axes (θ=4.37°). The TRUE per-axis grid fundamental = the strongest periodic peak of the
axis-collapsed profile searched from a LOW floor (0.004 cy/px, period ~250 px), so the
coarse grid is visible. Detector = `discover_pad_fundamental` on the same ROI; "det-lo" = the
same machinery with the floor dropped to 0.004 (what it WOULD lock if the floor weren't
clipping).

| region | atlas u/v px | true-u px (SNR) | true-v px (SNR) | aniso | det pitch/axis | det-lo pitch/axis | classification |
|---|---|---|---|---|---|---|---|
| 5C/(1,2)#2 | 77.4/62.8 | 21.2 (55) | **30.3 (224)** | yes | 21.2 / **u** | 30.3 / v | locks-true-grid[u] (but on the WEAKER axis) |
| 5D/(1,3)#2 | 45.6/51.2 | 20.6 (54) | **30.1 (177)** | yes | 20.6 / **u** | 30.1 / v | locks-true-grid[u] (weaker axis) |
| 7D/(3,3)#0 | 173.8/66.3 | 34.3 (91) | 29.0 (128) | no | 22.0 / u | 34.3 / u | finer-subfeature (>1.3× v) |
| 9C/(1,2)#1 | 97.1/64.5 | 21.3 (177) | **29.8 (254)** | yes | 21.3 / **u** | 29.8 / v | locks-true-grid[u] (weaker axis) |
| 7E/(3,0)#0 | 40.2/66.0 | 26.3 (52) | 28.7 (117) | no | 21.8 / u | 28.7 / v | off-by 1.2× |
| 8C/(0,2)#1 | 18.5/22.9 | 133.5 (39) | **41.7 (156)** | yes | 16.9 / v | 41.7 / v | finer-subfeature (>2.5× v) |

**Audit totals (sat channel, 6 regions):** anisotropic (u≠v >1.2×) **4/6**; atlas pad
fundamental below the static 0.06 floor **6/6**; **the floor changes the lock in 6/6**
(prod-floor pick ≠ low-floor pick in every region); **the detector misses the strongest
true axis in 5/6** (it locks the weaker u-axis ~21 px while the strongest periodicity is the
v-axis ~30 px, SNR 117–254).

**Failure classification — the comb IS mis-anchored, and the band floor is the cause, with a
second compounding bug:**

1. **Band floor (the suspected cause — CONFIRMED).** All six regions' true grid lines sit
   *below* the static 0.06 floor (and most below the M-aware 0.045 floor at this M). The
   dominant v-axis grid (~30 px, f≈0.033 cy/px) is *excluded by construction*, so on the
   v-axis only finer harmonics survive the band.
2. **1-D-collapse axis selection (a compounding bug the audit surfaced).** Because the v-axis
   fundamental is clipped, the cross-axis "auto" argmax in `discover_fundamental` picks
   whichever axis has its lowest surviving feature *inside* the band — here the weaker u-axis
   ~21 px line — and reports a single axis. So the detector throws away the single strongest,
   highest-SNR, most-consistent feature on the wafer (a ~29–30 px v-grid present on nearly
   every magenta die, SNR up to 254) and combs the wrong axis instead.
3. **Not "an unrelated fine sub-feature."** Nuance vs the original suspicion: for 5C/5D/9C the
   detector's 21 px u-pick IS a real u-axis grid line (1.00× of the true u fundamental) — so
   it is not locking junk, it is locking the *wrong axis* and *missing the dominant grid*. The
   pick also flips with the floor (det vs det-lo differ in 6/6) and therefore with M, which is
   exactly the kind of anchor instability that can manufacture cross-M scatter.

### Phase B — re-anchor on the true per-axis grid and re-test

Re-extracted the comb on all 16 configs (M 0.90–2.09, saturation channel) anchored on each
region's TRUE per-axis low-floor fundamental, predicting n·f0 (n=1..7) and reading
**axis-locked** bounded Michelson contrast at each rung (u and v never cross-talk).
8 796 rows; 6 594 valid (SNR≥3, ceiling-valid); the v-axis now carries MORE teeth (3 235)
than u (2 751) — the dominant grid the production path was discarding. Re-ran the Stage-T_n
self-calibration collapse (isotonic MTF(f_px) × per-order T_n), structure type =
(cls, axis, fundamental-pitch cluster) so u and v are never pooled.

| target (re-anchored) | n teeth | configs | collapse | per-order null | within-config floor | ratio | verdict |
|---|---|---|---|---|---|---|---|
| magenta.v.C8 (dominant ~29 px v-grid) | 2351 | 16 | **0.643** | 0.669 | 0.423 | 1.52 | UNSTABLE |
| magenta.u.C8 (~34 px u-grid) | 1561 | 16 | 0.755 | 0.773 | 0.516 | **1.46** | UNSTABLE |
| magenta.u.C14 (~20 px) | 779 | 16 | 0.682 | 0.767 | 0.356 | 1.92 | UNSTABLE |
| magenta.v.C14 (~17 px) | 427 | 15 | 0.565 | 0.599 | 0.216 | 2.62 | UNSTABLE |
| maze (single-pitch) | 608 | 16 | **0.845** | 1.000 | 0.313 | 2.70 | unchanged vs prior 0.842 |
| magenta v-axis ~30 px (cleanest, pooled) | 1912 | 15 | 0.671 | 0.702 | 0.432 | 1.55 | UNSTABLE |

Low-order-only (orders ≤3) reaches the lowest *absolute* residuals of the whole POC —
**magenta.v.C14 0.344 (floor 0.121), magenta.u.C14 0.361 (floor 0.183)** — but the floors
drop in lock-step, so the ratio stays ~2–2.9.

**Did correct anchoring change the cross-M verdict? NO — it stays dead, now for the right
reason.**

- **Absolute residuals fell** (e.g. dominant grid 0.643 vs prior magenta.P11 0.790; low-order
  0.34 vs prior 0.686). So the prior 0.79/0.84 *over-stated* the miss — part of that residual
  was the mislocking. The harmonics of the true grid are genuinely cleaner.
- **But the residual/floor RATIO did not collapse.** Best ratio 1.46 (magenta.u.C8) vs prior
  best ~2.0 (magenta.P11) / ~3.4 (cleanest die). A modest improvement, but nowhere near the
  ~1.0–1.3 a single shared MTF(f_px) curve requires — because re-anchoring also lowered the
  within-config noise floor (a cleaner anchor → less same-M scatter too).
- **The single-pitch maze is unchanged** (0.845 vs 0.842): it has zero anchoring freedom, so
  re-locking cannot touch it — and it still fails to self-collapse. This alone is decisive:
  the cleanest, most unambiguous cross-M test on the wafer fails regardless of pad anchoring.
- **Ranking gates still fail the same way.** Empty-magnification float persists — at
  f_px=0.15, Sig105+TC-1401 > Sig105, Sig150+TC-1401 > Sig150, ZMC105+5T+6T > ZMC105 (the
  exact fallacy from Stage T_n). bare105/bare150 ratio = 2.54 / 1.19 / 4.17 at f_px
  0.10/0.15/0.20 (want ~1.0). Cross-structure agreement is actually WORSE, not better: the two
  correctly-anchored axes disagree with the maze in OPPOSITE directions (pad_v/maze 0.23×
  median, pad_u/maze 2.01× median, log-spread 0.82/1.45) — definitive evidence that there is
  no single MTF(f_px) the structures share, even with a true harmonic series on each.

### Verdict

**The committed "cross-M not viable (final)" conclusion STANDS, and the audit strengthens its
basis.** The comb was indeed mis-anchored — the band floor (0.06 / M-aware 0.045 cy/px)
excludes the genuine coarse pad grid (atlas pitches 11.6–192.5 px) in 6/6 audited regions,
and a compounding 1-D-collapse axis-selection bug made the detector lock the *weaker* u-axis
and discard the dominant ~30 px v-grid (SNR up to 254) on nearly every magenta die. Fixing
both (per-axis low-floor anchoring + axis-locked harmonic reads) lowered the absolute
collapse residuals — so the prior 0.79/0.84 numbers were inflated by the artifact — but did
**not** make the teeth collapse onto a shared MTF(f_px): best ratio 1.46 (vs the ~1.0–1.3
needed), the single-pitch maze unchanged at 0.845, and the empty-magnification ranking
fallacy + opposite-sign cross-structure disagreement both persist. So the instability is
**not** a feature-locking artifact after all; it is the underlying property of these
textured/specular metal targets (focus-stack + field-dependent sharpness) that saturation
suppresses but does not remove. The verdict is now confirmed *for the right reason*.

The salvageable results are unchanged (**A5**, **saturation/R−B decode**). NOTE for any future
production use of `discover_pad_fundamental`: the audit surfaced a real anchoring weakness
(coarse-grid clipping by the band floor + single-axis "auto" selection on a 2-D lattice) — it
does not affect the cross-M verdict, but it means the discovered "fundamental" is often the
*weaker* axis's clipped sub-grid rather than the dominant grid line. Worth fixing if the
discovery is reused for *within-M* per-axis MTF. **Do NOT commit** (exploratory POC).

### New untracked files

- `poc_comb_chain_relock_a_audit.py` — Phase A mislocking audit (true 2-D grid vs detector).
- `poc_comb_chain_relock_diag.py` — per-axis low-floor spectrum dump (5C/5D/8C).
- `poc_comb_chain_relock_b_extract.py` + `poc_comb_chain_relock_b_run.sh` — re-anchored sharded comb re-extraction.
- `poc_comb_chain_relock_b_analyse.py` — re-anchored cross-M self-cal collapse + ranking/cross-structure gates.
- `poc_comb_chain_out/relock/phaseA_audit.csv` — per-region audit table (committed).
- `poc_comb_chain_out/relock/phaseB_collapse.csv` — per-target re-anchored collapse residuals (committed).
- `poc_comb_chain_out/relock/phaseA_run.log`, `phaseB_run.log` — run logs (removed as transient during commit cleanup).
- `poc_comb_chain_out/relock/relock_all.csv`, `relock_shard_*` — bulk re-extracted comb (GITIGNORED, regenerable).
- `poc_comb_chain_out/relock/fft2d/*.png` — 6 audit 2D-FFT images (GITIGNORED, ~2.4 MB).

---

## Future plans / open avenues (as of 2026-06-30)

State: cross-M absolute ranking is *negative under the conditions tested* (see Executive
summary), not proven impossible. Live and candidate next steps, in priority order:

1. **Linear pre-processing cause-isolation POC [DONE 2026-06-30 — see "Stage Preproc"].**
   Re-ran the Stage-T_n collapse after MTF-preserving (linear) pre-processing only
   (flat-fielding, specular masking/robust FFT, sub-pixel phase-aligned windowing, a
   consistent cross-config focus criterion). **Result: the collapse residual/floor ratio
   held at ~1.5 through every step (no descent toward the floor), so per the decision rule
   the instability is GENUINE TARGET VARIATION, not measurement-induced — cross-M does NOT
   revive.** The clip negative control behaved as flagged (invalid; worsened the gates).
   This closes the cause that Stages T_n/Targets/Relock left inferred-but-unproven.

2. **Within-M per-axis MTF via the new `PER_AXIS=1` path.** The fundamental-detection fix
   (`25d9d43`) exposes correct per-axis (u≠v) fundamentals + a `true_below_floor` flag.
   Regenerate `rank_all.csv` with `PER_AXIS=1` and build per-axis sharpness / uniformity /
   astigmatism on it. NOTE: `characterise.py`'s existing per-axis metrics run off
   LSF/maze-FFT (`peaks_v2.csv`), NOT periodic_fft — so this is a *new* periodic-FFT
   per-axis product, complementary to characterise, not a replacement.

3. **Alternative cross-M estimator** (only if (1) says measurement-induced but the comb
   still won't behave): deconvolution-based MTF, or registering the *same physical patch*
   across M to compare resolved detail directly rather than via a harmonic comb.

4. **Clean grating/edge chart acquisition** — the only guaranteed route to a real cross-M
   absolute axis. A purpose-shot target with stable, known harmonic content sidesteps the
   textured/specular-metal instability entirely. New shoot, not a re-analysis.

For the standing need ("is this TC/extension/diopter worth it; which config is sharpest"),
the validated answer remains: within-M rankings + the diffraction ceiling + tolerance-
ratios (the §L bare-vs-TC method).

---

## Stage Preproc — cause isolation (2026-06-30)

**Headline (caveats-first): the cross-M instability is GENUINE TARGET VARIATION, not a
measurement artifact — now PROVEN, not inferred.** Stacking LINEAR / MTF-preserving
pre-processing (flat-fielding → specular masking/robust FFT → sub-pixel phase-aligned
windowing → a consistent cross-config focus criterion) onto the correctly-anchored
saturation-channel comb moves the Stage-T_n collapse residual essentially **not at all**:
the dominant-grid residual/floor RATIO holds at **~1.5 across every step** (1.52 → 1.53 →
1.51 → 1.50 → 1.47), never descending toward the ~1.0–1.3 a shared MTF(f_px) curve needs.
Absolute residual barely moves (0.643 → 0.636) and the within-config floor moves in
lockstep, so the ratio is flat. Per the decision rule set in advance, this lands on the
**"residual barely moves → genuine target variation → cross-M is dead for these targets"**
branch. The gates never recover (empty-magnification +TC float persists in every arm;
bare105/bare150 stays 3.7–4.2× at f_px=0.20). The standing "cross-M not viable" verdict is
therefore confirmed *for the deepest available reason*: removing the measurement-induced
sources does not rescue it, so the cause is the textured/specular metal target itself
(field-dependent, region-to-region sharpness variation), not registration/phase/focus
jitter or illumination.

This is the experiment Future-plans §1 named. It was run UNTRACKED on nufan over SSH; no
production or committed-lib module was modified (all helpers imported read-only). New
untracked scripts: `poc_comb_chain_preproc_extract.py` (the ablation extractor — mirrors
the Relock per-axis low-floor anchoring on the saturation channel, adds a `PREPROC` ladder
of linear ops + a `FOCUS=fixed` criterion), `poc_comb_chain_preproc_run.sh` (sharded N=8
runner, one arm per pre-processing combination), `poc_comb_chain_preproc_analyse.py` (the
ablation analysis — reuses the Stage-T_n `self_calibrate` + the Relock structure typing).

### Method — only LINEAR / MTF-preserving ops, added cumulatively

Starting point = the **Relock baseline** (saturation channel + correct per-axis low-floor
anchoring on the TRUE coarse grid, so this POC is NOT re-contaminated by the mislocking bug
Relock found). Each step is linear at the comb frequencies (f0..7f0), so it cannot fake a
collapse by destroying the MTF signal:

- **flat-fielding** — divide by a low-pass (Gaussian, σ capped so its cutoff sits *well
  below* the comb fundamental, ~0.0025 cy/px vs f0≈0.033–0.069): removes the slow
  illumination / field-brightness gradient. Linear per-pixel gain.
- **specular masking / robust FFT** — replace achromatic-specular / outlier pixels
  (flagged on luma p99.5 + the channel's own upper tail) with the local low-pass value
  before the transform: excludes outliers rather than thresholding the signal.
- **sub-pixel phase-aligned windowing** — crop each 1-D profile to an INTEGER number of
  periods phase-anchored on the grid before the Hann window, so window scalloping / leakage
  at the fundamental does not vary config-to-config. Pure re-sampling of the same data.
- **fixed cross-config focus** — instead of a per-region best-focus argmax, select frames
  by the PEAK of the GLOBAL (mean-over-regions) through-focus curve — the same relative
  focus position for every config — to remove residual-defocus variability.
- **clip [NEGATIVE CONTROL — INVALID]** — a hard p2/p98 intensity clip + rescale. NONLINEAR;
  included only to show whether destroying modulation falsely "collapses." Flagged invalid.

The load-bearing number is the residual/within-config-FLOOR **ratio**, NOT the bare
residual: a step that lowers residual and floor in lockstep (ratio flat) is not progress.

### Ablation table — dominant grid `magenta.v.C8` (the ~30 px v-grid, 2.3–2.4k teeth, all 16 configs)

| arm (cumulative) | collapse resid | per-order null | within-config floor | **ratio** |
|---|---|---|---|---|
| baseline (sat + per-axis anchor) | 0.643 | 0.670 | 0.423 | **1.52** |
| + flat-fielding | 0.662 | 0.690 | 0.434 | **1.53** |
| + specular masking / robust FFT | 0.631 | 0.662 | 0.417 | **1.51** |
| + phase-aligned windowing | 0.633 | 0.664 | 0.422 | **1.50** |
| + fixed cross-config focus | 0.636 | 0.666 | 0.432 | **1.47** |
| + clip [NEG CTRL — INVALID] | 0.565 | 0.587 | 0.390 | 1.45 |

Low-order-only (orders ≤3) on the same grid tells the identical story: ratio 1.46 → 1.53 →
1.51 → 1.53 → 1.53 (resid 0.573 → 0.604). The other structure types confirm it — across all
arms `magenta.u.C8` holds ratio ~1.44–1.48, `magenta.u.C14` ~1.9–2.1, `magenta.v.C14`
~2.5–2.6, and the single-pitch **maze ratio stays 2.4–2.7** (resid ~0.82–0.84, essentially
unchanged from the Relock 0.845 — as expected, the maze has no anchoring or windowing
freedom and is the purest test). Full per-arm/per-type numbers in
`poc_comb_chain_out/preproc/preproc_ablation.csv`.

**The baseline arm reproduces the Relock Phase-B numbers to the digit** (magenta.v.C8
0.643/floor 0.423/ratio 1.52; magenta.u.C8 0.755/1.46; maze 0.842/0.313/2.69) — confirming
the ablation's starting point is faithful and the deltas below are attributable to the
pre-processing alone.

### Against the decision rule

- **The ratio does not fall toward 1.0–1.3.** It is flat at ~1.5 (dominant grid) through
  the entire linear ladder. The largest move, fixed-focus, nudges it 1.50 → 1.47 — within
  noise, and driven as much by a floor wobble as by the residual.
- **Residual and floor move in lockstep.** Where a step does lower the residual (e.g.
  specmask 0.643 → 0.631), it lowers the within-config floor by a similar fraction
  (0.423 → 0.417), so the ratio is unchanged. This is exactly the "not progress" case the
  rule flagged — report the ratio, not the residual.
- **No single step is the culprit, because there is no culprit.** None of flat-fielding,
  specular masking, phase-aligned windowing, or a consistent focus criterion meaningfully
  closes the cross-M gap. If the instability were measurement-induced, at least one of these
  four well-targeted linear removals should have collapsed it; none does.
- **The maze (zero pre-processing freedom) is unchanged** at ratio ~2.4–2.7 — the cleanest
  single-pitch cross-M test fails identically with or without the pad-oriented steps.

Therefore: **measurement-induced sources are NOT what drives the instability.** It is
genuine target variation, consistent with the Targets/Relock finding that these are
textured/specular metal cells with field-dependent, region-to-region sharpness that
saturation suppresses but does not remove.

### Gate re-check (does cross-M revive?) — NO

Because the residual did not collapse, cross-M does not revive; the gates confirm it. Across
**every** linear arm:

| arm | empty-mag +TC float? | bare105/bare150 @ f_px 0.10/0.15/0.20 (want ~1) |
|---|---|---|
| baseline | YES (1–3 floats) | 2.53 / 1.19 / 4.15 |
| + flat | YES (2–3) | 0.85 / 1.07 / 3.72 |
| + specmask | YES (2–3) | 0.91 / 1.11 / 3.85 |
| + phasewin | YES (1–3) | 0.90 / 1.09 / 3.78 |
| + fixed focus | YES (2–3) | 0.91 / 1.11 / 3.77 |

The empty-magnification fallacy (e.g. Sig105+TC-1401@1.4 > bare Sig105, ZMC105+5T+6T >
bare ZMC105 at f_px≥0.15) persists in all arms; bare105/bare150 stays far from 1.0 at
f_px=0.20 (3.7–4.2×). `corr(M, MTF)` hovers near 0 only because the per-order T_n fit
re-centres it — not a clean de-confounding (same over-correction noted in Stage T_n).

### Negative control — the clip arm "improves" but is INVALID, and even it doesn't collapse

The nonlinear clip lowers the absolute residual most (0.565 on the dominant grid) — the
expected artifact of compressing modulation — but (a) its within-config floor drops too, so
its **ratio (1.45) is no better than the linear arms**, and (b) it actively *worsens* the
gates: 5 empty-mag floats at f_px=0.10 (vs 1–3 for linear arms) and bare105/bare150 = 4.06
at f_px=0.20. So even destroying the MTF signal does not manufacture a cross-M collapse
here, which is itself further evidence the gap is structural target variation, not leakage
or dynamic-range artefacts a clip would mask. **Do not read anything positive into the clip
arm.**

### Verdict & recommendation

**Cross-M absolute ranking is DEAD for these targets — now proven measurement-robust, not
inferred.** Linear, MTF-preserving pre-processing that removes the plausible
measurement-induced sources (illumination gradient, speculars, window-phase scalloping,
inconsistent focus) does not move the collapse ratio off ~1.5; the instability is genuine
region-to-region/field-dependent variation of the textured-metal target. This closes
Future-plans §1: the cause Stages T_n / Targets / Relock left inferred is now isolated to
the **target**, not the **measurement**. The only remaining routes that could change the
verdict are the *other* Future-plans items — a fundamentally different estimator
(deconvolution / same-physical-patch cross-M registration) or, the guaranteed one, a
purpose-shot clean grating/edge chart (new acquisition). Standing recommendation unchanged:
within-M periodic ranking + the diffraction ceiling + tolerance-ratios; the salvaged **A5**
+ **saturation/R−B decode** remain the bankable results. **Do NOT commit** (exploratory POC,
per the plan).

### New untracked files

- `poc_comb_chain_preproc_extract.py` — ablation comb extractor (per-axis low-floor anchor,
  saturation channel, `PREPROC` linear-op ladder + `FOCUS=fixed` criterion).
- `poc_comb_chain_preproc_run.sh` — sharded N=8 nufan runner, one arm per pre-processing combo.
- `poc_comb_chain_preproc_analyse.py` — ablation analysis (Stage-T_n self-cal collapse +
  ratio/floor + gate re-check per arm).
- `poc_comb_chain_out/preproc/preproc_ablation.csv` — per-arm/per-type collapse residuals +
  ratios (committed).
- `poc_comb_chain_out/preproc/{baseline,flat,flat_spec,flat_spec_win,flat_spec_win_foc,clip_NEGCTRL}_all.csv`,
  `*_shard_*.csv`, `*_shard_*.log`, `run.log` — bulk re-extracted combs + logs
  (GITIGNORED, regenerable from the run script; mirrors the Relock/T_n patterns).

---

## Stage AltEst — non-comb cross-M estimators (2026-06-30)

**Why.** The periodic-comb cross-M route is dead because the wafer's periodic targets
have genuinely unstable harmonic content (Stage Preproc proved it is the *target*, not
the *measurement*). This stage tries a WIDE VARIETY of estimators that do NOT depend on
that harmonic content — where the unstable target spectrum **cancels** (compare the SAME
physical patch), is **estimated per-image** (blind PSF), is read from **through-focus
behaviour**, or is **sidestepped** with a true edge. Exploratory, UNTRACKED
(`poc_altest_*`), no production-module edits (all production + committed-lib helpers
imported read-only). Compute ran on nufan (16 cores). All 16 subset configs, M 0.90–2.09.

**Headline (caveats-first):** ONE non-comb estimator yields a **viable cross-M absolute
ranking under stated conditions** — the **same-physical-patch PSD-ratio relative MTF read
at a fixed SENSOR frequency** (Approach 1, sensor-freq mode). It is the first estimator in
this whole arc to pass **all four gates at once**: M de-confounded (corr(M,score)
−0.41/−0.14/−0.02 at f_px 0.10/0.15/0.20, vs +0.4 for every comb variant), **no
empty-magnification float at any sensor frequency**, the §L known orderings reproduced
(bare modern macros lead, 100-400+diopter tail, TC/diopter degrade, no empty-mag credit),
and — the gate the comb-chain definitively *failed* — **repeatable across independent
patch halves (Spearman ρ = 0.96 / 0.99)**. The strict condition (the caveat that must
lead): it works **only when read at a fixed SENSOR (pixel) frequency, not a fixed subject
frequency** — the same estimator read at fixed subject frequency is M-confounded and
floats empty-mag exactly like the comb. Physically: at a fixed sensor cy/px the sensor
MTF is identical for every config (same body), so the same-patch PSD ratio isolates the
**glass MTF** (incl. the bellows-aperture N_eff effect) and correctly refuses to credit
bare magnification. This is a *fixed-sensor-frequency* axis — it ranks "which lens has the
better MTF at this pixel frequency", NOT "which resolves more subject detail" (the latter
legitimately credits M and is what the subject-freq mode / Approach 2 measure).

The other four approaches FAIL, each in a distinct, *proven* way (not inferred):

| # | approach | M-deconfound corr(M,·) | empty-mag float | known orders | repeatable | gates | verdict |
|---|---|---|---|---|---|---|---|
| **1** | **same-patch PSD-ratio relMTF — SENSOR-freq** | **−0.41/−0.14/−0.02** | **NO** | **YES** | **YES (ρ 0.96/0.99)** | **4/4** | **VIABLE (fixed-sensor-freq only)** |
| 1 | same-patch PSD-ratio relMTF — SUBJECT-freq | +0.38…+0.45 | YES (5T+6T) | partial | (n/a) | 1/4 | M-confounded (credits magnification, as expected) |
| 2 | same-patch direct detail (tenengrad/lap/hf/var) | +0.30…+0.43 | tenengrad NO; lap/hf/var YES | partial (diopter tail OK; macros not separated) | (n/a) | 2/4 | system-MTF metric → credits M; non-spectral cross-check of #1 only |
| 3 | blind PSF — Gaussian σ (subject µm) | −0.23 | **YES, badly** (diopters rank *sharpest*) | **NO (inverted)** | poor (IQR≈value) | 1/4 | FAIL — β/σ degeneracy; low-contrast diopter patches fake a small σ |
| 3 | blind PSF — cepstral radius | nan | — | NO (all railed 3 px) | degenerate | 0/4 | FAIL — cepstral peak floors; zero discrimination |
| 4 | through-focus FWHM (frames) | −0.04 | NO | partial (AF200 narrowest; bare macros tie at 8) | coarse (quantised 5/7/8/11/14) | 3/4 (weak) | de-confounded (corr with N_eff = 0.00!) + sane direction but too COARSE to separate the modern macros |
| 5 | SE-edge MTF50 — fixed sensor cy/px | −1.0 (n=4) | (untestable) | UNTESTABLE | (n/a) | 0/4 | FAIL on COVERAGE — 4/16 configs, **no bare modern macro** survives the quality gate |

### Reusable infrastructure built (the substrate the rest reuse)

`poc_altest_lib.py` registers each config once via `atlas_periodic_fft.register`
(`reg_auto`), then resamples the **SAME physical atlas rectangle** onto a **COMMON
subject-space grid** for any config: a fixed atlas die-grid line-pair rectangle `(cl,rl)`
is the same physical wafer region in every config (atlas grid units are M-invariant), so
sampling it at a fixed `samples_per_unit` (700 px/grid-unit) and `cv2.remap`-ing each
config's pixels onto it gives two patches that share the intrinsic target spectrum `S(f)`
exactly. A vectorised `_cum_vec` mirrors `anchor_fit_sweep._cum` (validated to 1e-12) so
the distortion-aware forward model runs over a dense lattice. Channel = **saturation**
(the comb-POC SNR win). Each frame is decoded once for the through-focus lapvar scan; only
the distinct per-patch best-focus frames are colour-decoded (O(frames), scalable).

**A structural finding that shaped the design:** there is **NO single atlas patch in-FOV
for all 16 configs** (`poc_altest_fov.py`: the common rect is empty — the M≈2 configs were
shot on a *different* die region than the bare/low-M ones, cl≈[1.8,5.0] vs ≈[4.1,10.9]).
So a single universal patch is impossible; instead a **fixed GLOBAL atlas lattice** of
0.5-grid-unit cells is laid down (label = atlas cell = same physical patch), each config
contributes its in-FOV cells (83–94 per config, 171 distinct cells total), and the cross-M
comparison rides on the cells each PAIR shares — bridged transitively. This is exactly why
Approach 1 connects all 16 into **one component (4539 pairwise edges, chain residual
0.22–0.49)** where the comb's cross-M link rode on the single maze frequency.

### Approach 1 — same-physical-patch PSD-ratio relative MTF (TOP) [poc_altest_patch_*]

For every atlas cell two configs share, both best-focus saturation patches are resampled
to the common grid; the **amplitude (√PSD) ratio** is the relative MTF (the shared `S(f)`
cancels). Pairwise log-ratios → a weighted-LS transitive chain (gauge = zero mean) → a
global score, read two ways:
- **SUBJECT-freq** (fixed `f_grid`): compares the same physical detail's end-to-end system
  contrast. corr(M,score) +0.38…+0.45 and the +5T+6T / TC-2001@2:1 configs float above
  bare lenses — **the empty-magnification confound, reproduced**. Correct physics (more M
  *does* put a subject feature at an easier sensor frequency) but not a glass-quality axis.
- **SENSOR-freq** (fixed cy/sensor-px; per-config `f_grid = f_px·px_per_unit/SPU`): isolates
  glass MTF (sensor MTF is common). **This is the viable axis.** At **f_px=0.10 (all 16
  configs)** the ranking is:
  `Z105 (0.56) > S150 (0.51) > S105+TC-1401@1:1 (0.39) > S105 (0.36) > AF200 (0.29) >
  S150+TC-1401@1:1 (0.08) > {+5T+6T, +TC mid, diopters} > … > S105+5T+6T (−0.34) >
  MCON-35 (−0.64)`. Bare modern macros take 4 of the top 5; the 100-400+diopter and
  +5T+6T stacks sink to the tail; **no accessory config outranks the best bare lens at any
  sensor frequency**. Gate evidence: M-deconfound ✓ (negative, not the comb's +0.4),
  empty-mag ✓, known orders ✓, repeatability ✓ (split-half Spearman 0.96 @0.10, 0.99
  @0.15). Coverage thins at f_px≥0.20 (the M≈2 + diopter configs drop out → 11-node chain),
  so **f_px≈0.10–0.15 is the trustworthy band**.
  Caveat vs §L: AF200 lands a touch low at f_px=0.10 (#5, but within 0.07 of S105 — a near
  tie, consistent with §L's "AF200≈S105"; it rises to #2 at f_px=0.20), and
  S105+TC-1401@1:1 sits just above bare S105/AF200 at f_px=0.10 (a mild over-credit that
  vanishes higher up). The macro/diopter separation and the no-empty-mag property are
  robust across the band.

### Approach 2 — same-patch direct detail [poc_altest_patch_*]

On the SAME common-grid patch (scene cancels), Tenengrad / Laplacian / variance /
HF-wavelet energy per cell, chained like #1. These are **system-MTF** (glass×sensor)
energy measures, so like the subject-freq #1 they **credit magnification**: corr(M,score)
+0.30…+0.43, and lap/hf/variance float empty-mag (e.g. S105+TC-2001@2:1 #1 on
Laplacian/HF energy). Tenengrad happens not to float the *very* top but still correlates
+0.40 with M and does not separate the bare macros. Useful only as a non-spectral
*confirmation* of #1's same-patch registration (the diopter/100-400 tail is consistent
across all four detail metrics), not as a cross-M axis.

### Approach 3 — blind PSF / spectrum-falloff [poc_altest_psf_focus_*]

Per config per patch: fit `log PSD(f) = c − β·log f − (2π²σ²)f²` (natural f^−β spectrum ×
Gaussian-PSF MTF²) → σ in sensor px → σ_subject µm = σ_px·4.35/M; plus a cepstral
blur-radius cross-check. **Both FAIL.** The Gaussian σ ranks the **100-400+diopter configs
as the SHARPEST** (smallest σ_subj: C500D 0.76 µm, MCON-35 0.89 µm) — physically inverted
(§L's resolution tail) — because their low-contrast, low-texture patches have a *flat*
high-frequency PSD that the fit reads as a tiny σ; the β/σ trade-off is degenerate on these
targets. Empty-mag floats badly (5 accessory configs above the best bare). The cepstral
estimate is **degenerate — every config rails to 3 px** (the cepstral peak floors on the
specular/texture noise), zero discrimination. Per-patch σ IQR ≈ the σ value itself
(not repeatable). The blind-PSF family does not work on these textured metal patches.

### Approach 4 — through-focus response shape [poc_altest_psf_focus_*]

From the FULL focus stack (data the single-frame analyses discarded): per patch, the
lapvar-vs-frame curve's half-max width (FWHM in frames). A sharper optic should have a
tighter peak. **Partially works and is genuinely de-confounded** — corr(M,FWHM) = −0.04
**and corr(FWHM, N_eff) = +0.001** (so the width is NOT merely diffraction DOF/aperture,
the obvious confound), no empty-mag float, and the direction is sane: **AF200 narrowest
(sharpest), the +5T+6T diopter stacks widest (softest)**. BUT the metric is **too coarse**:
FWHM quantises to 5/7/8/11/14 frames and the four bare modern macros (S105, S150, Z105,
plus several +TC) all tie at 8 frames — it cannot resolve the near-ties §L cares about, and
two diopter configs (C500D, S150+TC-2001@1:1) land mid-pack rather than at the tail. A real,
de-confounded signal lives here (rail-step-calibrated, finer focus sampling, or curvature
instead of FWHM could sharpen it) but as implemented it is a coarse tie-breaker, not a
standalone ranking. Passes 3/4 gates weakly (repeatability is the soft one — quantisation).

### Approach 5 — robust edge MTF at fixed sensor frequency [poc_altest_edge_*]

Direction-aware MTF50 (production `slanted_edge.mtf50_step_erf` + `edge_aggregate`
min-direction) on the atlas's **true** cyan slanted-edge die feature (die (0,3) — NOT the
groove scribe, which over-reads via emboss, §E.4). MTF50 is sensor cy/px by construction.
**FAILS on coverage: only 4 of 16 configs yield a valid SE-edge MTF50**, and — decisively —
**none of the bare modern macros (S105/Z105/AF200/S150) do** (the SE bar is in-FOV but the
single-step quality gate rejects them: "bars present but no valid edge MTF"). The 4 that
survive are accessory/diopter configs; they read *below* the diffraction ceiling (0/4 over,
so the true edge behaves, unlike the groove), but with one edge each and no bare-macro
anchor the §L orderings are **untestable**. This confirms the historical caveat: the
designed SE feature is too sparse to be a cross-config metric. (Bond-pad reflectance edges
have broader coverage but rebuild the §L edge study, which already answered the edge
question at fixed *subject* frequency — out of scope here.)

### Verdict & how it sits with the standing conclusion

**A non-comb cross-M absolute ranking IS achievable — narrowly.** The same-physical-patch
PSD-ratio relative MTF, read at a fixed **sensor** frequency in the f_px≈0.10–0.15 band, is
the first estimator in this entire investigation to clear all four gates simultaneously,
including the repeatability gate the comb-chain failed. It works precisely *because* it
sidesteps the unstable harmonic content (the shared target spectrum cancels in the
same-patch ratio) and because reading at a fixed sensor frequency holds the common sensor
MTF constant so the ratio is pure glass MTF — which is exactly why it refuses to credit
empty magnification. This does **not** contradict the comb verdict: the comb compared
*different* physical features at fixed sensor frequency (M-confounded harmonic bookkeeping
that only degenerated to "same fundamental" at f_px≈0.10); Approach 1 compares the *same*
physical patch, so the fixed-sensor-frequency read is a genuine relative-MTF, not an alias.

**Strict caveats (lead with these):** (1) it is a **fixed-sensor-frequency / relative**
ranking — it answers "which lens has the higher MTF at this pixel frequency", which is the
right glass-quality question but is NOT the same as "resolves more subject detail" (that
credits M); (2) trustworthy only in **f_px≈0.10–0.15** (higher f_px loses the M≈2/diopter
configs to coverage); (3) it requires shared in-FOV patches, and the M≈2 configs share only
a thin overlap region — the chain bridges them transitively but their scores rest on fewer
edges; (4) it is **relative** (a chain of pairwise ratios with a zero-mean gauge), not an
absolute MTF tied to the diffraction ceiling — use the §L diffraction-ceiling for absolute
calibration. Under those conditions it reproduces bare-macros-lead / diopter-tail /
no-empty-mag-credit. For the standing need it **complements** (does not replace) the §L
recommendation: within-M periodic ranking + diffraction ceiling + tolerance-ratios remain
the absolute references; Approach 1 (sensor-freq) is now a viable *cross-M relative* check
that the comb could never provide. Approaches 3 and 5 are dead ends on these targets;
Approach 4 is a coarse but real, de-confounded signal worth refining (rail-calibrated
through-focus) if a second cross-M axis is wanted. **Do NOT commit** (exploratory POC,
per the plan).

### New untracked files

- `poc_altest_lib.py` — registration + same-physical-patch common-grid resampler
  (`_cum_vec`, `atlas_rect_to_common_grid`), saturation decode, focus-stack scan,
  radial PSD, detail metrics, ceiling helper.
- `poc_altest_fov.py` — per-config in-FOV atlas-rect probe (found the empty common rect).
- `poc_altest_patch_driver.py` + `poc_altest_patch_analyse.py` — Approach 1 & 2: same-patch
  PSD-ratio relMTF chain (subject + sensor freq) + direct detail, with the four gates +
  split-half repeatability.
- `poc_altest_psf_focus.py` + `poc_altest_psf_focus_analyse.py` — Approach 3 (blind PSF:
  Gaussian-σ + cepstral) & 4 (through-focus FWHM/curvature), with gates.
- `poc_altest_edge.py` + `poc_altest_edge_analyse.py` — Approach 5: SE-die direction-aware
  edge MTF50 at fixed sensor cy/px vs the diffraction ceiling.
- `poc_altest_run.sh` — sharded N-way nufan runner (patch | psffoc | edge).
- `poc_altest_consolidate.py` — the approaches×gates summary table.
- `poc_comb_chain_out/altest/a1_sensor_scores.csv`, `psffoc_summary.csv`, `edge_summary.csv`,
  `altest_gate_summary.csv` — small committed result CSVs.
- `poc_comb_chain_out/altest/{patches/,*_shard_*.csv,*.log,smoke_*.png}` — GITIGNORED:
  the 487 MB resampled-patch `.npy` cache, per-shard bulk CSVs, logs, smoke PNGs
  (regenerable from the drivers; mirrors the existing poc_comb_chain_out patterns).

---

## Stage AltEst-2 — hardening + variants (2026-06-30)

**Why.** Stage AltEst found ONE viable non-comb cross-M estimator (same-physical-patch
PSD-ratio relative MTF at a fixed SENSOR frequency, P1). This stage (a) HARDENS P1 on a
much wider config set and stress-tests its weak points, (b) REFINES the de-confounded
through-focus signal (P2) to break the macro ties, and (c) EXPLORES five new variants
built on the established principles. A reshoot is weeks away and compute is cheap, so
every approach was run to completion on the full data and is reported even when negative.
Exploratory, UNTRACKED (`poc_altest2_*`), no production edits (all helpers — incl. the
committed `poc_altest_lib` and production `tile_sharpness.*` — imported read-only). Compute
on nufan (16 cores). **Widened subset = 38 configs** (`poc_altest2_subset.csv`; up from 16):
adds the vintage 55mm primes (f/2.8 AIS ×2, f/3.5 Auto ×2) + the 60mm AF-D + a bare 70-180
+ extra apertures (F5.6/F11) on the bare modern macros + more mid-M TC/diopter fills.
M now spans **0.75 → 2.09**. All 38 register cleanly (rmse 0.9–5.4 px, 0 drops).

**Headline (caveats-first).** The Stage-AltEst finding is now **CORROBORATED and
strengthened**: a cross-magnification *relative* (fixed-sensor-frequency) glass-MTF ranking
is real on this data, and **three estimators built on DIFFERENT physical principles
converge on it** — same-patch spectral ratio (P1), spatial averaged-edge ESF (P3.1), and
through-focus defocus response (P2) — plus a whole-spectrum relative deconvolution (P3.2).
P1 hardened: on the 38-config set it links **all configs into ONE component** (29 679
pairwise edges, up from the 16-config chain), stays **M-de-confounded with no
empty-magnification float** through f_px≈0.15, the M≈2 transitive bridge is **ROBUST**
(worst single-anchor jackknife shift ≤0.07), and it is **repeatable** (split-half Spearman
0.98–1.00). The same strict caveats stand and must lead: it is a **fixed-sensor-frequency /
relative** ranking ("which lens has the higher MTF at this pixel frequency"), **NOT** a
subject-resolution ranking (that legitimately credits M — and the subject-freq control
re-introduces the confound, corr +0.17, exactly as before); it is trustworthy only in
**f_px≈0.08–0.15** (above that the M≈2/diopter configs drop out and corr flips positive);
it is relative (zero-mean gauge), not tied to the diffraction ceiling — use §L for absolute
calibration. **This does NOT revive the absolute cross-M ranking** (still negative; Stage
Preproc) and does NOT replace §L; it is a corroborated *cross-M relative* cross-check that
the comb could never provide, now backed by independent estimators.

### Approaches × gates (widened set)

| approach | coverage | M-deconfound | empty-mag | known orders | repeatable | gates | verdict |
|---|---|---|---|---|---|---|---|
| **P1 PSD-ratio relMTF, SENSOR f_px=0.10** | **38/38 (1 comp, 29 679 edges)** | **corr(M)=−0.68** | **NO float** | **YES (med rank macro 7 / vintage 11 / diopter 31)** | **YES (ρ 0.99)** | **4/4** | **HARDENED WINNER — bridge robust** |
| P1 SENSOR f_px=0.12 | 38/38 | −0.58 | NO | YES (8/11/30) | YES (0.98) | 4/4 | HARDENED (window centre) |
| P1 SENSOR f_px=0.15 | 35/38 (M≈2 drop) | −0.37 | NO | YES (7.5/13/30) | YES (1.00) | 4/4 | viable; window edge |
| P1 SENSOR f_px≥0.18 | ≤32/38 | flips **+** | float appears | degrades | — | <4/4 | **WINDOW BREAKS** (coverage loss + noise) |
| P1 SUBJECT-freq (control) | 38/38 | +0.17 | YES (diopters) | partial | — | 1/4 | M-confound RETURNS (confirms sensor-freq does the work) |
| **P2 through-focus Gaussian sub-frame FWHM** | 38/38 | **−0.22 (corr N_eff −0.10)** | ~NO (1 borderline) | **YES (8/23/31)** | finer (sub-frame; **ties BROKEN**) | 3.5/4 | **REFINED A4 — agrees P1 (ρ 0.40–0.58)** |
| P2 log-parabola curvature | 38/38 | +0.13…+0.40 | YES | NO | noisy | 1/4 | FAIL — 2nd-deriv noise-dominated |
| **P3.1 pad-edge averaged-ESF MTF @ f_px=0.10** | **38/38 (vs 4/16 for SE-edge!)** | **corr(M)=+0.01** | NO float | **YES (8/26)** | 100k+ edges/config | 4/4 (relative) | **COVERAGE SOLVED; agrees P1 (ρ 0.52–0.79). CAVEAT: absolute MTF over-reads (>1) → relative read only** |
| P3.1 pad-edge ERF sigma | 38/38 | −0.18 | NO | YES (8.5/24) | floors at sharp end | 3/4 | discriminates the soft tail; saturates (0.2 px floor) at the sharp end |
| P3.2 relative deconvolution (whole-spectrum kernel) | 27/38 (high-M thin) | +0.40 | 1 float (S105+5T) | YES direction | resid 0.21 px² | 2.5/4 | **independent (different math); agrees P1 (ρ 0.73–0.85)**; mild M-confound from the whole-spectrum fit |
| P3.3 edge-mask × same-patch ratio | 38/38 | −0.61 | NO float | YES | resid 0.29 | 4/4 | **PASS — "reproducible-distortion" idea works; ≈P1 (ρ 0.96–0.97)** |
| P3.4 matched-filter (synthetic lattice template) | 38/38 | +0.13 | NO float | partial (TC floats mid) | resid 1.60 (noisy) | 2/4 | WEAK — single-freq template partly credits M; noisy |
| P3.5 full-amp ratio (P1 sibling) | 38/38 | −0.62 | NO float | YES | resid 0.26 | 4/4 | ≈P1 (ρ 0.97–0.98); sanity sibling |
| P3.5 gradient-energy ratio | 38/38 | +0.08 | NO float | partial (tail OK, mid scrambled) | resid 0.43 | 2/4 | system-MTF (credits M like Approach 2); cross-check only |

### P1 hardening details

- **Transitive bridge** (the prior weak point — M≈2 rode on thin overlap). The wider set
  pulls the M≈2 configs into a fully connected graph. Jackknife per-anchor (drop one
  sharing config, re-solve, measure the M≈2 score shift): worst single-anchor shift is
  **0.023** (AF200+5T+6T@2:1, 34 anchors), **0.035** (S150+TC-2001@2:1, 36 anchors), **0.074**
  (S105+TC-2001@2:1, only 10 anchors) — all **ROBUST** (≪ the ±0.3 rank gaps). Bootstrap
  (resample patches, 120×) gives per-config score σ of **0.01–0.03** for well-covered
  configs, rising to 0.03–0.07 for the thinly-shared M≈2/+5T+6T stacks (`p1_ranking_fpx*.csv`).
- **f_px window** (`p1_fpx_sweep.csv`): corr(M,score) = −0.76 / −0.68 / −0.58 / −0.37 at
  f_px 0.08 / 0.10 / 0.12 / 0.15, with the chain staying ONE component (38→35 nodes). At
  **f_px≥0.18 it breaks**: nodes drop to 32→30→26, corr flips POSITIVE (+0.23 at 0.18, a
  +TC config floats), residual climbs (0.28→0.37). The break is exactly the M≈2 + diopter
  configs falling out of frequency coverage (their lower px/grid-unit means a fixed sensor
  cy/px maps past their common-grid Nyquist) plus rising HF noise — **trustworthy window =
  f_px 0.08–0.15**, confirmed.
- **Resampling discipline:** every config is independently `cv2.remap`-ed (INTER_CUBIC)
  onto the SAME fixed common grid (700 px/grid-unit); neither config is resampled onto the
  other's pixels, so interpolation cannot bias the same-patch ratio.
- **§L reproduced, more strongly than the 16-config run:** median ranks modern-macro-bare
  7–8 < vintage-55/60 11–13 < diopter/100-400 tail 30–31. Z105 leads, the bare Sigma/Nikon
  macros cluster next, the vintage **55 f/3.5 Auto** primes sink to the tail (the gate the
  16-config set could not test — vintage < modern, confirmed), TC/diopter degrade, +5T+6T
  and MCON-35 are the softest. No accessory outranks the best bare lens.

### P2 refinement (the de-confounded second axis)

The A4 FWHM was de-confounded but quantised (modern macros tied at 8 frames). Fitting a
**Gaussian-of-defocus to the lapvar(z) peak** yields a continuous sub-frame FWHM that
**breaks the ties** (AF200 7.6 / Z105 9.2 / S150 9.3 / S105 11.6 frames) while keeping the
de-confound property (corr(M)=−0.22, **corr(N_eff)=−0.10** — still not just DOF/aperture).
§L order holds (modern 8 < vintage 23 < diopter 31; the vintage f/3.5 primes are dead last).
It **agrees with the hardened P1** at Spearman **+0.40 (f_px=0.10) → +0.58 (f_px=0.15)**, and
holds at low-M (M<1.2: +0.45–0.54) where P1 coverage is densest — corroboration from an
estimator that uses *no spectrum at all*, only the focus-stack defocus response. (The
curvature / band-pass variants FAILED — 2nd-derivative noise; the full-band Gaussian FWHM
is the usable one. One config, S105+5T+6T, has a degenerate fit (FWHM≈200) and is excluded
from the consensus.)

### Variants (P3) — what the principles bought

- **P3.1 pad-edge [most promising, delivered].** Massively-averaged slanted-edge ESF over
  ALL tilted metal→substrate gradient edges in each sensor-space patch (100k+ edge samples
  per config). This **fixes the coverage that killed Approach-5** (38/38 vs 4/16; every bare
  macro now reads). The MTF@fixed-sensor-f and ERF-sigma rankings are **de-confounded
  (corr(M)≈0.0 / −0.18)**, §L-correct, no empty-mag float at f_px=0.10, and **agree with P1
  (ρ 0.52–0.79, rising with f_px)**. Honest caveat: the *absolute* MTF over-reads (>1; MTF50
  quantised to two values) because co-binning many sub-pixel-jittered edges artificially
  sharpens the mean edge — so it is a valid **relative/ranking** read, not an absolute MTF.
- **P3.2 relative deconvolution.** Fit the relative blur kernel between two registered
  same-patch images as a whole-spectrum log-amplitude-vs-f² slope → Δ(σ_a²−σ_b²), chained
  additively. Genuinely **independent of P1's single-frequency read**, and it **agrees with
  P1 (ρ 0.73–0.85)** with a physically sane direction (macros sharpest, vintage-f/3.5 +
  diopter softest). Mild residual M-confound (corr +0.40) because the whole-spectrum fit
  re-imports some subject-frequency dependence, and the high-M configs thin out (27/38) — so
  it is a corroborating cross-check, not a replacement.
- **P3.3 edge-region mask × same-patch ratio.** A lattice-locked reproducible mask (median
  edge-density across the configs sharing a cell) keeps only the pad-boundary zones and
  cancels in the same-patch ratio. **Passes 4/4** and is ≈P1 (ρ 0.96–0.97) — a clean
  demonstration that the user's "distort toward a reproducible spectrum" idea is valid when
  the distortion is identical across both configs of a pair.
- **P3.4 matched-filter / lock-in.** Correlate each patch with a synthetic ideal-lattice
  template at f₀ (correlation preserves blur, per the principle). WEAK: a single-frequency
  template partly credits M (corr +0.13, TC configs float to mid-pack) and is noisy
  (resid 1.60). Not a standalone axis.
- **P3.5 cross-checks.** Full-amp ratio is the unmasked P1 sibling (≈P1, ρ 0.97); the
  gradient-energy ratio is a system-MTF metric that credits M (like Approach 2) — tail
  correct, mid-pack scrambled.

### Cross-agreement matrix (Spearman; `p_crossagreement_matrix.csv`)

The same-patch *spectral* family is internally near-identical (P1@0.10/0.12/0.15 ↔ P3.3
↔ P3.5-fullamp: **0.95–0.99**). The decisive evidence is that the **independent** estimators
agree with P1 and with each other:

|  | P1@.10 | P1@.15 | P2 fwhm | P3.1 edge | P3.1 σ | P3.2 decon | P3.3 mask |
|---|---|---|---|---|---|---|---|
| P1@.10 | 1.00 | 0.95 | 0.40 | 0.52 | 0.71 | 0.73 | 0.97 |
| P1@.15 | 0.95 | 1.00 | 0.54 | 0.79 | 0.83 | 0.85 | 0.97 |
| P2 fwhm | 0.40 | 0.54 | 1.00 | 0.52 | 0.72 | 0.67 | 0.48 |
| P3.1 edge | 0.52 | 0.79 | 0.52 | 1.00 | 0.77 | 0.82 | 0.60 |
| P3.2 decon | 0.73 | 0.85 | 0.67 | 0.82 | 0.75 | 1.00 | 0.79 |

Three different physical principles — spectral ratio (P1), spatial edge (P3.1), defocus
response (P2) — mutually positive, and the whole-spectrum deconvolution (P3.2) ties them
together. **Mutual agreement of independent estimators is the strongest evidence the
cross-M relative signal is real**, not a measurement artifact of any one method.

### Corroborated consensus cross-M relative ranking (`p_consensus_ranking.csv`)

Rank-average over the seven gate-passing estimators (P1@0.10, P1@0.12, P2-FWHM, P3.1-edge,
P3.2-decon, P3.3-mask, P3.5-fullamp). Top and tail (lower = sharper; `rank_std` = spread
across estimators = the honest per-config uncertainty):

```
 1  Z105   (F5.6/F8/F11 take 3 of the top 6)      — the sharpest modern macro
 4  AF200 F11 / 5 S150 F11 / 6 S105 F11           — bare modern macros, stopped down
 7  S150 F8 / 9 S105 F8 / 10 AF200 F8             — bare modern macros at F8
 8  S105+TC-1401 @1:1  (the most TC-tolerant body, as §L found)
12  AF60 F8        — the 60mm AF-D sits with the modern macros
14  V55 f/2.8 AIS  — vintage f/2.8 primes: respectable, mid-pack
...
32  V55 f/3.5 Auto primes        — vintage f/3.5: the bottom of the prime field
35  Z100400+MCON-35 / 36 AF200+5T+6T / 37 S150+5T+6T / 38 AF200+6T  — diopter/extension tail
```

This reproduces the §L verdict end-to-end on a single cross-M axis: **bare modern macros
(Z105 ≈ AF200 ≈ S105 ≈ S150) lead**, the **60mm joins them**, the **vintage 55 f/2.8 are
mid-pack and the 55 f/3.5 are the prime-field tail**, **TC tolerance favours the 105 bodies**,
and **diopter/extension stacks are the softest** — with no empty-magnification credit. Use
this as a cross-M *relative* check; keep §L's within-M periodic-FFT + diffraction ceiling +
tolerance-ratios as the absolute references.

### New untracked files

- `poc_altest2_make_subset.py` → `poc_altest2_subset.csv` (38-config widened set).
- `poc_altest2_smoke.py` — per-config registration / FOV / in-FOV-cell probe.
- `poc_altest2_patch_driver.py` + `poc_altest2_patch_analyse.py` — P1 hardening: widened
  same-patch PSD-ratio chain, f_px sweep, M≈2 jackknife, bootstrap σ, split-half Spearman,
  subject-freq control. Writes `p1_fpx_sweep.csv`, `p1_ranking_fpx{0.1,0.12,0.15}.csv`.
- `poc_altest2_psf_focus.py` + `poc_altest2_psf_focus_analyse.py` — P2 refined through-focus
  (Gaussian sub-frame FWHM, log-parabola curvature, peak/area, fixed-band variants) + the
  P1↔P2 cross-agreement. Writes `p2_psffoc2_summary.csv`.
- `poc_altest2_padedge_driver.py` + `poc_altest2_padedge_analyse.py` — P3.1 massively-
  averaged pad-edge ESF→MTF at fixed sensor f. Writes `p31_padedge_summary.csv`.
- `poc_altest2_decon.py` — P3.2 relative deconvolution. Writes `p32_decon_scores.csv`.
- `poc_altest2_variants.py` — P3.3 edge-mask, P3.4 matched-filter, P3.5 cross-checks.
  Writes `p33_edgemask_scores.csv`, `p34_matchfilter_scores.csv`, `p35_fullamp_scores.csv`,
  `p35_gradenergy_scores.csv`.
- `poc_altest2_consolidate.py` → `p_crossagreement_matrix.csv`, `p_consensus_ranking.csv`.
- `poc_altest2_gate_summary.py` → `altest2_gate_summary.csv` (the table above).
- `poc_altest2_run.sh` — sharded nufan runner (patch | psffoc | decon | edge).
- `poc_comb_chain_out/altest2/{patches/,*_shard_*.csv,*.log}` — GITIGNORED: the 1.2 GB
  resampled-patch `.npy` cache, per-shard bulk CSVs and logs (regenerable from the drivers;
  mirrors the `altest/` patterns). The small `p*_*.csv` result files are committed.

**Do NOT commit** (exploratory POC, per the plan).

---

## M-resolved cross-estimator agreement (2026-06-30)

`poc_altest2_corr_vs_m.py` → `out/altest2/corr_vs_m.png`. Pairwise Spearman of the four
estimators **within M bands**, per-pair coverage (each pair uses the configs it both
covers; higher-score=sharper sign-aligned).

| pair | M<1.0 | M 1.0–1.4 | M≥1.4 |
|---|---|---|---|
| P1 ↔ pad-edge | +0.41 (10) | +0.84 (18) | +0.18 (10) |
| P1 ↔ decon | +0.65 (10) | +0.70 (17) | — (0) |
| P1 ↔ through-focus | +0.68 (10) | +0.10 (18) | +0.61 (10) |
| pad-edge ↔ decon | +0.67 (10) | +0.81 (17) | — (0) |
| pad-edge ↔ through-focus | +0.55 (10) | +0.22 (18) | +0.71 (10) |
| decon ↔ through-focus | +0.83 (10) | +0.39 (17) | — (0) |

**Robust facts:** (1) every pair is **positive in every band** — the consensus never
inverts along M. (2) **Deconvolution has no M≥1.4 coverage** — a low/mid-M corroborator
only; P1/pad-edge/through-focus reach M≈2.1. (3) **Two complementary regimes:** the
*in-focus-image* family (P1, pad-edge, decon) cohere best at **mid-M (1.0–1.4)**, while
**through-focus** agrees at the **M extremes** and is weakest mid-M — it carries the most
independent (defocus-axis) information. (4) At **high M the in-focus estimators diverge**
(P1↔pad-edge 0.84→0.18, where the TC/diopter/stack targets are worst) and **through-focus
becomes the cross-link** (P1↔P2 0.61, pad-edge↔P2 0.71).

**Caveat:** 3 coarse bands; n≈10 (low/high) / ~17 (mid) → Spearman SE ~0.2–0.3, so only
large band-to-band swings are meaningful; configs cluster near M≈1.

**Net:** the four estimators are **complementary, not redundant** — each is strongest in
a different M regime. That's favorable: cross-M corroboration that holds *because* the
methods cover for each other where individually weakest.
