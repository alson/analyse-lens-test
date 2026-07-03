# Capture log — 2026-06-28 — Z TC-1.4× replacement revalidation

Field session capturing data to validate a **replacement Z TC-1.4×** (the
original was dropped/lost) on the Z 100-400, compared within-session against
the **bare lens** and the **Z TC-2.0×**. The 300 PF is no longer owned and
is not part of this test. Primary comparison is *within this session* (bare
lens = unchanged-hardware anchor); cross-date comparison to the old/lost
copy is secondary. See the revalidation plan and Z7-era scene-design notes.

## ✅ Verdict (consolidated 2026-06-29)

**Replacement Z TC-1.4× is a good, well-centred copy — validated.** Matched-
aperture f/11 retention vs bare = **0.88** (≈ the lost copy's ~0.80,
`LONGDIST_TELE_RESULTS.md` §6b); field symmetric (L/R 0.99, T/B 0.98 → no
decentering/tilt). That answers the revalidation question.

**Three distinct questions — keep them separate:**
1. *Good copy?* — **yes** (matched-f/11 retention 0.88).
2. *TC-2.0× beats cropping the bare 400?* — **yes, robustly**: MTF50 FOM
   **+20 %** (lucky-imaging) to **+46 %** (median-of-AF); clears its 0.500
   break-even on every analysis.
3. *TC-1.4× beats cropping?* — **≈ break-even, best estimate marginally
   negative (~−5 %); sign not firmly established.** The right *estimator* is
   the least-gust / lucky-imaging one (sharpest sample = least-gusted =
   true-optics frame), which gives 0.233/0.342 = 0.68 → −5 %. The **+38 %
   median-of-AF is an over-estimate artefact**, not a co-equal number: bare's 3
   AF frames were more gust-hit (−42 % vs its calm-moment peak) than tc14's
   (−26 %), inflating the ratio. **But the effective calm+in-focus sample is
   thin** — of the ~63-frame pools the focus sweep leaves only **~10–16 sharp
   frames** (the rest defocused, correctly rejected), so lucky-imaging may not
   have reached each config's true calm peak; the residual uncertainty is
   two-sided (whichever config missed a lull is underestimated). So: not a
   symmetric "−5 % to +38 %" wash (the +38 % is an artefact, not truth's upper
   bound) — it's centred near break-even, best estimate slightly favouring
   cropping. To pin the sign, shoot a **locked-focus gust-burst** (A8) or a
   calm-day reshoot.

**The flat bare profile was a gust+defocus artefact, not optics.** On
median-of-AF / JPEG, bare MTF50 was flat ~0.20 (no f/8 peak). Per-edge
lucky-imaging over the full stacks (independent gradient proxy) recovered a
**real bare f/8 peak of 0.342** — so the bare lens is genuinely sharp at f/8,
which is why cropping it nearly matches the 1.4×. The ISO-100-vs-500 shake test
was **inconclusive** (variable wind confounds it — a gust hit the tc20 cells),
but lucky imaging settles it: wind was the limiter, not atmosphere (clear and
sunny) or distance.

**Trust hierarchy.** Matched-aperture **f/11** (equal, well-sampled pools) is
the safe cross-config comparison; **f/16 is untrustworthy** (lucky imaging
pushes it over the diffraction-ceiling gate; tc14 f/16 had only 3 frames so the
f/16 ordering violation is a sampling artefact). The TC-vs-cropping FOM is
**re-basing-sensitive** — the marginal TC-1.4× call is exactly what a
**calm-day reshoot** (faster shutter / float ISO / bursts) would settle.

**Distance.** ~45 m is **not a compromise** — it's the minimum for the 800 mm
(TC-2.0×) to sit in the stabilised/infinity MTF regime (56× FL, past the ~50×
FL / 40 m floor); closer would test a close-focus MTF instead.

*Metric pitfalls + the capture/analysis lessons from this session are written up
in [`LENS_TEST_METHODOLOGY_Z7.md`](LENS_TEST_METHODOLOGY_Z7.md) Parts A/B
(A8 gust/ISO, A9 target, B5 over-read fix, B8 lucky imaging, B9 ceiling gate,
B10 matched-aperture). Detailed median-of-AF + lucky-imaging tables: the
subsections below + `scripts/poc_longdist_tc_family_raw_f11f16_out/summary.md`.*

### Clean f/11 + f/16 matched-aperture run — TC-2.0× resolved (2026-06-29)

> **These are the median-of-AF numbers.** They were later refined by the
> per-edge lucky-imaging pass (which recovered the bare f/8 peak and shifted the
> FOMs — see the consolidated verdict above and
> `scripts/poc_longdist_tc_family_raw_f11f16_out/summary.md`). The +38 %/+46 %
> below are the median-of-AF figures; the lucky-imaging figures are −5 %/+20 %.
> Use this subsection for the matched-aperture *ordering*; use the consolidated
> verdict for the cross-cropping call.

The f/8 RAW POC above couldn't include the **TC-2.0×** (it's wide-open at f/11,
so it can't be shot ≤ f/8). The matched-aperture run
(`scripts/poc_longdist_tc_family_raw_f11f16.py`) measures all three configs at
**f/11 and f/16** on the same linear, demosaic-only RAW + brick-mortar edges,
using the **§5.6e `centroid_hann` LSF fix** (the prior f/11–f/16 over-read was
that analysis bug, now fixed) plus a **diffraction-ceiling validity gate**. It
measures the **in-focus AF frames only** (Silent=Off, ×3/cell), takes the
**per-edge median across AF frames**, then the median across edges — never
max-over-frames (that was the artefact). Parallelised over 27 develop+measure
jobs on 8 cores (~3.7 min).

**Metric choice (important):** on this clean RAW data **MTF50 is the trustworthy
primary channel** — bare MTF50 ≈ 0.20 cy/sensor-px sits far below the 0.49
Nyquist cap (no saturation), and every cell passes the ceiling gate. The
**MTF@Nyquist channel is confounded here** and is *not* used for the verdict: it
yields physically impossible orderings (tc14 > bare) because each (config,
aperture) detects an independent edge population on its own reference and the
noise-sensitive Nyquist tail amplifies that mismatch. (This is the opposite of
the f/8 JPEG case, where in-camera sharpening pushed MTF@Nyq > 1 and MTF50
saturated at the cap — there MTF@Nyq was preferred. On linear RAW with sub-cap
MTF50, MTF50 wins.)

**All 9 cells pass the diffraction-ceiling gate** (median MTF50 below the
aperture ceiling → glass/atmosphere-limited, no over-read). The §5.6e fix held.

Median MTF50 (cy/sensor-px), in-focus AF frames:

| config | f/5.6 | f/8 | f/11 | f/16 | ceiling f/11 / f/16 |
|---|---|---|---|---|---|
| bare 400 mm | 0.252 | 0.199 | 0.209 | 0.196 | 0.290 / 0.200 |
| + TC-1.4× 560 mm | — | 0.162 | 0.173 | 0.196 | 0.290 / 0.200 |
| + TC-2.0× 800 mm | — | — | 0.145 | 0.139 | 0.290 / 0.200 |

**Matched-aperture physical ordering bare ≥ TC-1.4× ≥ TC-2.0× HOLDS** on MTF50
at both f/11 (0.209 ≥ 0.173 ≥ 0.145) and f/16 (0.196 ≥ 0.196 ≥ 0.139) → the data
is **not confounded** on the primary channel.

**Retention (MTF50, vs bare at the same f-stop):**

| TC | f/11 | f/16 |
|---|---|---|
| TC-1.4× / bare | 0.831 | 0.986 |
| TC-2.0× / bare | 0.696 | 0.709 |

(TC-1.4× f/16 ≈ 1.0 is partly diffraction convergence — both configs hit the
f/16 ceiling; the **f/11 figure 0.83 is the more defensible TC-1.4× retention**,
and it lands on the lost copy's ~0.80.)

**FOM over cropping the bare 400 mm frame** (best TC aperture vs bare f/8, the
frame you would crop; FOM = MTF50-retention × f_eff/400 − 1; the *ratio*
cancels common-mode error):

- **TC-1.4× @ f/16:** retention 0.986 (f/11 0.831) → **FOM +38 %** — clears the
  0.714 break-even, beats cropping. Consistent with the f/8 POC (≈0.80, +8 %)
  and the old copy.
- **TC-2.0× @ f/11:** retention **0.731** → **FOM +46 %** — **clears the 0.500
  break-even, beats cropping the bare 400 frame.**

### ✅ TC-2.0× verdict (clean, resolved)

**The Z TC-2.0× clears its 0.500 break-even (retention 0.73 on MTF50, FOM +46 %)
— at f/11 it adds real subject resolution over cropping the bare 400 mm frame.**
Both TC-2.0× cells (f/11, f/16) pass the diffraction-ceiling gate (no over-read),
and the physical ordering bare ≥ TC-1.4× ≥ TC-2.0× holds at both apertures, so
the reading is trustworthy. This **supersedes the earlier "tc20 can't join at
f/8" caveat** — it joins cleanly at f/11.

Versus the **2026-01 foliage** (TC-2.0× ≈ 0 % FOM): that was *scene-floor-
limited* — the whole Z 100-400 family pinned at 0.20–0.25 cy/px on shrubbery, so
the TC couldn't separate from the bare lens. The 2026-06-28 brick wall still has
its own ceiling (bare MTF50 only ≈ 0.20, gust/atmosphere-limited at 45 m, no
textbook f/8 peak — the sweep is flat across f/5.6–f/16), but here the TCs
**separate cleanly from bare on MTF50**, so this is a genuine positive TC-2.0×
result rather than a floor-pinned null.

## Equipment

| Item | Detail |
|---|---|
| Body | Nikon Z7 (45.7 MP, 8256×5504, 4.35 µm pitch) |
| Lens | Z 100-400/4.5-5.6 VR S, set to the **400 mm** long-end stop for all configs |
| TCs | Z TC-1.4× (new replacement copy); Z TC-2.0× |
| VR | **Off** |
| Lens foot | **Kirk** replacement foot (Arca), clamped to the ballhead |
| Head | Arca-Swiss Monoball **Z1+** ballhead |
| Leveling | Markins **TH-230** tripod hub (leveling base) |
| Tripod | Gitzo **GT3542L** (operator's heaviest) |

Three configs, all at the lens's 400 mm setting:

| Config | Effective FL | Wide-open aperture |
|---|---|---|
| Bare | 400 mm | f/5.6 |
| + Z TC-1.4× | 560 mm | f/8 |
| + Z TC-2.0× | 800 mm | f/11 |

## Subject & conditions

- **Subject:** flat brick wall, framed to fill the sensor corner-to-corner;
  camera level (no up-tilt), squared to the wall via the building's H/V
  lines + virtual horizon.
- **Distance:** **~45 m** (±1–2 m), derived from a brick face measuring
  **426 × 106 px** at 400 mm (210 mm Waalformaat, no head joint → m =
  426·4.348 µm / 210 mm = 0.00882 → d ≈ f/m ≈ 45 m). Past the 40 m floor;
  puts 800 mm at ~56× FL (stable-MTF regime). Can refine from EXIF
  (quantized) once imported.
- **Tripod height:** ~1.8 m (level 400 mm frame spans ~0.3–3.3 m up the
  wall, clear of the ground).
- **Location:** Zoetermeer (specific wall not recorded).
- **Date/time:** 2026-06-28, roughly **12:00–13:30** (from frame
  timestamps — verify in EXIF once imported).
- **Weather:** sunny, ~24–26 °C; sun near-overhead (near solstice) → even
  grazing light on the vertical wall. **Wind gusty and varied** — quantified
  after the fact: **sustained ~14–15 km/h but gusts 35–37 km/h WSW** at
  12:00–13:00 (Open-Meteo ERA5 archive reanalysis), a **~2.4× gust-to-mean
  ratio** that independently confirms the gust-limited result. The 3× AF
  replicates + 3× focus-shift stacks per cell gave chances to catch lulls
  (but see methodology A8/B8 — the focus sweep leaves only ~10–16 in-focus
  frames to sample wind; locked-focus bursts are better).
  - **Forecast vs actual (planning caveat):** the pre-shoot forecast
    (`wttr.in/Zoetermeer`, fetched 2026-06-27) called noon **wind 14, gusts
    18 km/h** — sustained was spot-on but it **under-called gusts ~2×**. For
    tripod tele work the **gust** figure dominates (not sustained) and is the
    least-reliable forecast field → grab a genuine lull / shoot bursts rather
    than trust a benign forecast. (Grid reanalysis smooths terrain; local
    building channelling at the wall could make real gusts higher still.)

## Capture matrix

- **ISO:** 100 and 500 (fixed per series).
- **Mode:** Aperture priority (shutter floats; ISO fixed).
- **White balance:** Sunny (fixed) for all shots.
- **Files:** NEF + JPEG **Fine★** (Nikon's optimal-quality JPEG, better
  than plain Fine).
- **Apertures:** whole stops from wide-open through **f/16**:

| Config | Aperture series (whole stops) |
|---|---|
| Bare 400 mm | f/5.6, f/8, f/11, f/16 |
| + TC-1.4× 560 mm | f/8, f/11, f/16 |
| + TC-2.0× 800 mm | f/11, f/16 |

## Per-cell protocol

For each (config/FL, aperture, ISO) cell, two phases:

**Phase 1 — AF replicates (×3):**
- 3 frames, **Pinpoint AF** (re-acquired, **centre of frame**), **remote
  shutter release**.

**Phase 2 — focus-shift stacks (×3 series):**
- Pinpoint AF at centre, then **defocus toward the near side** (so the
  sweep starts in front of the wall and runs through peak toward infinity).
- **Focus-shift shooting**, **exposure locked** (AE-L), **electronic
  shutter**, **step size 1** (finest).
- Shot count per stack: **400 mm → 20**, **560 mm → 20**, **800 mm → 40**.
- **3 stacks per cell**, refocusing (Pinpoint + near-defocus) before each.
- Observed: peak sharpness usually fell within the **first ~10 frames** of
  each stack, so the 20/40 counts carry margin.

## Exceptions & caveats

- **560 mm f/16:** Phase 1 was shot normally (3× at ISO 100 **and** 3× at
  ISO 500), but Phase 2 was reduced to a **single focus-shift stack at
  ISO 500** (memory-card space) — i.e. the ISO 100 stacks and the extra
  ISO 500 stacks are absent for this one cell. Rationale: f/16 is
  diffraction-limited so the loss is minor.
- **Cross-series comparability — anchor, don't compare absolutes.** The
  2026-01 series is shrubbery; this is a brick wall — different scene
  content *and* probably different JPEG quality (2026-01 setting not
  recorded; recover from EXIF `Quality` tag or kB/MP, but see below). So do
  NOT compare new-TC-1.4× to old-TC-1.4× in absolute metric values. Instead
  use **bare 100-400 and 100-400 + TC-2.0× as anchors present in BOTH
  series** (both are unchanged hardware — only the 1.4× was replaced). Per
  series, form MTF-retention ratios vs the bare anchor:
  - `retention_2.0 = M(TC-2.0×)/M(bare)` = **validity check** — unchanged
    hardware, so it should match across series (~60 %, §6b) if the
    normalization transfers.
  - `retention_1.4 = M(TC-1.4×)/M(bare)` = **the actual test** — new copy
    is good if this matches the old copy (~80 %, §6b) once retention_2.0
    confirms the regime transfers.
  Since the anchors share each series' scene + JPEG quality + metric-code
  version, all those confounds cancel in the ratios — so the unknown
  2026-01 JPEG quality is largely moot. Caveat: in 2026-01 the Z 100-400
  family floored at 0.20–0.25, so the anchors are barely separated there
  until the planned metric re-run (new ref-band/sub-bin) lifts them off the
  floor. The **within-this-series** bare-vs-TC-1.4×-vs-TC-2.0× comparison
  (all on the wall, well-separated) stays the primary test; cross-series
  retention is the secondary "behaves like the old copy" check.
- **JPEG quality is NOT a cross-series confound — checked.** The actual
  Z 100-400 frames on all three 2026-01 tele dates are **Fine** at very high
  bitrate (2026-01-18 ~42 MB, -28 ~34 MB, -30 [TC-2.0× anchor] ~37 MB ≈
  750–925 kB/MP). This session is **Fine★**. Both are ~2× the ~370 kB/MP
  that 2025-07-05 showed was already sufficient (only the ~113 kB/MP *basic*
  embedded JPEG floored `radial_cutoff`), and the Fine-vs-Fine★ gap at these
  bitrates is well inside the ≤2 % NEF-vs-JPEG margin (`SHARPNESS_METRICS.md`
  #3). ⇒ **No NEF demosaic needed.** The only cross-series difference is the
  scene (shrubbery vs wall), handled by the bare + TC-2.0× anchors.
  (A stray `Normal`/12 MB `_DSC*.JPG` in 2026-01-18/`results_other/` is not
  part of the test series — ignore.)
- **NEFs** are saved this session anyway, as insurance / for any future
  need — but not required for this comparison.
- f/16 across all configs is diffraction-limited; treat it as a corner /
  field-flatness reference rather than a peak-sharpness contender (peak is
  expected around f/11).
- **VR off** + heavy locked tripod is the intended rigid setup; in the
  gusty wind, rely on the best-of-replicates / best-of-stack picker to
  reject gust-blurred frames.

## Data location

`~/shared/files/pics/digikam/test-raw-data/2026-06-28/`
(imported from card by digiKam).

## How this feeds analysis

Pipeline (scripts in place, validated):

1. **Ingest** — rename + sort the flat capture dir into the
   `<lens ISO>/<focal>/<F>/` tree, NEF+JPG moved together, reproducing the
   digiKam Exiv2 token convention:
   ```
   python3 analyse-lens-test/rename_and_sort_lens_test.py \
       --root ~/.../test-raw-data/2026-06-28            # dry-run
   python3 analyse-lens-test/rename_and_sort_lens_test.py --root ... --apply
   ```
2. **Analyse** — dataset key `tele2026_06_28` is registered in
   `poc_longdist_algorithms.py`; the dedicated within-session report is:
   ```
   cd longdist-sharpness && uv run python -u scripts/poc_longdist_tc14_revalidation.py
   ```

Three validation checks (all within-session, robust to the shrubbery↔wall
scene change and metric-version drift):
1. **Adds real detail vs cropping** — FOM = cutoff × f_eff; TC beats the
   bare-400 frame cropped to its framing iff retention > 400/f_eff (0.714
   for 1.4×, 0.500 for 2.0×).
2. **Not decentered** — left/right field symmetry of the new TC-1.4×.
   *(Current script uses the horizontal-midline L/R from the shared
   `field_boxes()`; full 4-corner / through-focus tilt is a field-box grid
   extension — TODO.)*
3. **Sits sensibly vs the TC-2.0×** — retention_2.0 is the cross-series
   *validity* anchor (unchanged hardware → should match old ~0.60);
   retention_1.4 matching old ~0.80 means the new copy ≈ the lost one.

Focus-shift stacks feed the best-of-stack picker directly (top = best-focus
frame per position; median/range are not meaningful for a focus-shift stack
since most frames are deliberately off-focus). AF was acquired at centre
every time, but the sweep covers the whole range, so corners still reach
peak in some frame.

## To verify once data is imported

1. Exact frame **timestamps** (confirm the ~12:00–13:30 window).
2. **Phase-1 exposure consistency** across the 3 A-priority AF replicates
   (operator noticed no drift; confirm from EXIF).
3. Optionally refine the **~45 m distance** from EXIF FocusDistance
   (quantized) or a cleaner multi-brick measurement.
