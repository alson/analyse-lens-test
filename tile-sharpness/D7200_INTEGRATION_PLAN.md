# D7200 wafer-macro integration into the cross-M relative-MTF pipeline — plan

State: 2026-07-03. Evidence-backed; sample tests run on nufan. POC script:
`tile-sharpness/scripts/poc_d7200_probe.py`; output `out_d7200_probe/probe_report.json`.

## TL;DR (lead with caveats)

- **Cleanly achievable, and de-risked:** an *internal D7200 relative-MTF ranking* using the
  existing pipeline. The two hardest unknowns are resolved empirically — the wafer-atlas
  `reg_auto` **registers D7200 (DX + OLPF) frames** at 4–11 µm object-space RMSE (well under
  the 25 µm guard), and the D7200 `<lens>/<aperture>/` layout is **already a solved shape**
  (the Z7 2025-10-17 manual session uses the identical layout and is integrated).
- **The one genuinely new axis is the camera** (3.91 µm pitch, DX crop, OLPF). It is a
  single scalar (pitch) plus a boolean (OLPF) threaded through ~5 call sites, all of which
  are already parameterized or trivially so.
- **Caveated / not yet proven:** the **Z7 ↔ D7200 cross-camera absolute lp/mm bridge** stays
  hard (different Nyquist, OLPF present-vs-absent, different pitch) — treat cross-camera
  numbers as uncertain, not a deliverable of phase 1. **Lighting drift is real and larger
  than Z7** (measured) and needs per-shot normalization before the through-focus fit.
- **Not yet tested:** sub-1:1 D7200 configs (70-180 etc.) — my 4 samples all landed M≈1.1;
  low-M on D7200 inherits the same scribe-undersampling caveat as low-M Z7.

---

## PHASE 1 + 2 RESULTS (2026-07-03) — implemented & validated

**Phase 1 (camera axis) — DONE, committed** (`b1042af`, `24219c8`, `a611f2b`). New
`cameras.py` (Z7 4.35µm/no-OLPF, D7200 3.91µm/OLPF), `ConfigNode.camera`,
`discover_config_nodes` reads a `camera` column (Z7 back-compat); `build_relmtf_subset.py`
gains the column + two D7200 blocks; per-camera pitch threaded into the `reg_guard`
object-space ceiling (fixes the §2b 11.3% over-strict bug). Z7 subset **byte-unchanged**
(311 rows, only the appended `camera=Z7` column differs); D7200 = **79 rows** appended
(total 390). 370 tests pass. **Deviation from §3C:** `phase1.py`/`rail_calibration.py`/
`periodic_fft.py` pitch were NOT threaded — verified `relmtf_run.py` does not import
`phase1` (that's the old characterise path), and the relative ranking is at a fixed sensor
frequency (f_px), so the extract is pitch-independent except `reg_guard`. Pitch→subject-lp/mm
is analyse-time and only matters for the rail-coverage physical outputs, which D7200 (manual
tier) does not produce — so **Phase 4 per-camera-pitch is moot for D7200's achievable
deliverable**.

**Phase 2 (D7200 extract) — DONE** (`run_relmtf_d7200.sh` → `out_relmtf_d7200`, gitignored).
Extract → recover → analyse `--tier all` over the 79-config D7200-only subset
(`data/cross_m_relative_mtf_subset_d7200.csv`). **All 79 registered, 0 dropped, 0 recover
needed, 0 family-audit flags** — registration is robust across the full DX+OLPF set (the
probe's 4/4 held at 79/79). Produced a 50-config within-D7200 relative ranking; no
physical/field-geometry (correctly skipped at manual tier).

**Within-SESSION ranking is coherent** (2025-08-19, 34 configs): Sigma 150 (F11/F8/F16) top →
70-180 ±5T → 105G VR I/II → … → vintage 55mm f/3.5 Auto copies bottom — matches the known
optical-quality ordering and the Z7 bare-macro result.

**⚠ CROSS-SESSION pooling is CONFOUNDED (key Phase-2 finding).** All five 2025-08-06 configs
rank systematically LOW (S150 F8 = 0.215 @0806 vs 0.694 @0819, same lens/aperture) and carry
~half the usable cells (663–707 vs 1200+). 08-19 is *dimmer* yet ranks *higher*, so it is NOT
a simple brightness→amplitude effect — it's a session-level systematic (coverage/framing, and
the P1 amplitude log-ratio carries a per-config illumination offset that does not fully cancel
across sessions). **So D7200 rankings are trustworthy WITHIN a session but NOT across the two
dates as currently pooled.**

**Phase 3 RE-SCOPED by this evidence:** the confound is session-level, not the within-sweep
luma drift Phase 3 was scoped for, so per-shot luma normalization alone likely won't fix it.
Options: (a) a per-session reference normalization of the amplitude log-ratio chain, (b)
restrict D7200 to within-session rankings only (already valid — the 08-19 set is the useful
one; 08-06 is a small 5-config early session), (c) diagnose the 08-06 coverage deficit (663
cells) first. NOT implemented — needs a design decision + a re-extract to validate. Phase 4
(pitch reporting) remains moot at manual tier. **Deliverable achieved: a validated within-D7200
(within-session) relative-MTF ranking; cross-session + cross-camera(Z7↔D7200) stay caveated.**

## RESOLUTION (2026-07-03 later) — 2025-08-06 excluded; confound resolved by construction

The cross-session confound is resolved by **dropping 2025-08-06 entirely** (`build_relmtf_subset.py`
now loops `("2025-08-19",)` only; subset 375 = 311 Z7 + 64 D7200). Justification (EXIF-verified):
08-06 is **fully redundant** with 08-19 — every 08-06 config is reproduced in 08-19 once matched
by actual EXIF aperture, and the AF200 `F7.1/F10` were the bumped-1/3-stop versions of `F8/F11`
(full 34-frame sweeps) that 08-19 captured correctly (42/47 frames). 08-19 is the richer session
(adds the 55mm primes, 70-180, 105G VR I/II that 08-06 lacks). Re-run → **64/64 register, 0
dropped, 0 recover, 0 audit flags; a clean 34-config within-session ranking** (Sigma 150 →
70-180/105G VR → vintage 55mm Auto). No normalization needed — single session removes the confound.

**Aperture labels (EXIF-verified): all 08-19 folders are effective f, and 08-19 is internally
consistent.** For most lenses the folder matches EXIF FNumber (the lens reports effective at
close focus); for the manual 55mm primes and the Sigma 180 the EXIF reports the marked value and
the folder was set to the effective aperture. Do NOT infer magnification from the marked→effective
ratio — for internal-focus lenses (incl. the Sigma 180) the focal length shortens at close focus,
so N_eff ≠ N·(1+M); M comes from the registration, not the aperture. The pipeline's
folder=effective handling is therefore correct for all remaining (08-19) D7200 data.

---

## FOLLOW-ON RESULTS (2026-07-03/04) — centre/corner, ceiling, cross-camera, M-gate

**A. Atlas centre/corner subject-MTF50 for D7200 (`605a519`).** Camera-parameterised
`scripts/atlas_corner_mtf.py` + `atlas_corner_d7200.py` + `run_atlas_corner_d7200.sh`
(DX 6000×4000, 3.91µm, M from reg_auto, effective-folder aperture) → `out_atlas_corner_d7200/`
(gitignored). The "characterise-style" centre + 4-corner subject-lp/mm + uniformity view, MINUS
field curvature (rail-dependent, N/A on manual tier). All 64 configs measured.

**B. Diffraction+Nyquist ceiling overlay → calibrated (`d9b5124`, `atlas_corner_d7200_ceiling.py`).**
Raw centre-MTF50 is over-read-contaminated (rises F8→F16, physically impossible). After flagging
against the diffraction+Nyquist ceiling (n_eff + M + 3.91µm): of 64 centre reads, **4 impossible
over-reads (all F16), 8 diffraction-limited, 52 glass-limited**. Calibrated centre @ F8-effective
(within-D7200, UPPER BOUNDS): modern macros lead — **Sigma 105 ≈ Tamron 90 ≈ Sigma 150 ≈ 40 lp/mm;
Sigma 150 most trustworthy** (flat vs aperture). Absolute values still upper-bounded by the LSF
over-read (grows stopping down) + OLPF; only the within-D7200 ORDERING is reliable.

**C. Cross-camera Z7↔D7200 bridge — DEFINITIVELY CLOSED (both routes exhausted).**
- Atlas-resampled same-patch PSD ratio (Sigma 150), `97d9b30`: failed 4 structural checks — ratio
  aperture-DEPENDENT, rises with freq, optics+target don't cleanly cancel, and the atlas
  700-samples/unit grid band-limits PSD to **0.27 cy/px ≈ 54% of Nyquist** (a PROJECT-WIDE property
  — any near-Nyquist/cross-camera MTF work hits it) so the OLPF region is out of band.
- Native-res-from-raw (`2e40e95`): can't run — **Z7 shared macros were saved JPG-only (0 NEFs)**;
  needs raws on both bodies (Z7-JPG-vs-D7200-RAW invalid). Method validated on the D7200 side
  (raw green reaches 0.49 cy/px), blocker is purely missing input. Z7 raw archive is sparse
  (NEFs only 2026-01-29 & 2026-02-18, not the shared macros). Unfixable: D7200 sold.
- ⟹ "modern-macro Z7↔D7200 difference is sensor/OLPF-dominated, not lens" is a well-founded optics
  PRIOR that **cannot be empirically confirmed with existing data.**

**D. M>1.10 gate decoupled for the relative ranking (`a6f7cd2`).** New `FP.M_REL_SPREAD_MAX=2.8`:
the relative fixed-f_px ranking admits all M when the cohort's M-spread (max/min) ≤ 2.8×, else
falls back to the M>1.10 cutoff; physical/DoF/geometry stay gated at 1.10. Z7-invariant by
construction (Z7 spread 5.88× → wide branch = prior logic, byte-identical). D7200 spread 1.42× →
all 64 configs admitted (was 34); the bare 1:1 macros are now first-class in the relative headline
(top S150 F11/F8/F16 → Z70180 F16 → Sigma 180; bottom vintage 55mm), `_lowconf.csv` auto-removed
for narrow cohorts. This supersedes the "Phase 4 pitch is moot" framing: no pitch reporting was
needed; the deliverables are the relative headline (D) + the calibrated centre/corner (A/B).

---

## 1. Data inventory

Location: `/home/alson/shared/files/pics/digikam/test-raw-data/{2025-08-06,2025-08-19}/`
(dates confirmed via EXIF; camera confirmed `NIKON D7200`, 6000×4000 = 24 MP DX).

**Layout:** `<lens>/<aperture>/<shots>` — NO magnification directory (one level shallower
than the Z7 newer-rig `<lens>/<mag>/<focal>/<aperture>/`, and IDENTICAL to the Z7 manual
`2025-10-17` session). Shots are pipe-delimited `NNNN|<lens>|<focal> mm|F<ap>|alm-<ts>-<seq>.{jpg,nef}`
plus `.xmp` sidecars; ~33 shots/sweep (range 33–130 files incl. NEF+XMP); `cropped/` and
stray `pick.jpg` present in some aperture dirs (register_config already ignores non-jpg;
POC filters `pick.jpg`).

**Configs present:**
- 2025-08-06 (5 lenses): AF 200 f/4D, Sigma 150, Sigma 180, Sigma 105, Tamron 90. Apertures
  ≈ wide→f/11 (e.g. 200: F5.3/F7.1/F10).
- 2025-08-19 (~16 configs): AF 200, 105G VR, 105G VR II, 70-180, 70-180+5T, 70-180+6T,
  55 AIS ×2 (287318/537016), 55 Auto ×3 (209088/258263/262711), Sigma 150/180/105, Tamron 90.
  Apertures up to F16/F22. A `results-ignored/` dir exists (skip, like `results*`).

**Metadata availability:**
- **No `metadata.json`** for either 2025-08 session (rail-tier only) → `nominal_M` unavailable
  from metadata; **M must come from `reg_auto`** registration scale (validated below).
- **No `effective_apertures.csv`** for 2025-08 (present only for 2026-01-29/02-18/05-13) →
  effective-aperture resolution falls to priority (2): **use the directory aperture folder
  directly** (marked f-number; for IF macros ≈ effective per the project's "aperture folder
  is effective" convention). Never analytical.
- EXIF is rich: `Model=NIKON D7200`, `FNumber`, `FocalLength`, `FocusDistance` (coarse/encoded
  — e.g. 0.50 m; same dead-zone caveat as the Sigma 150), `ISO 100`, `ExposureTime`,
  **`Flash: Off, Did not fire`** → sessions used **continuous light, not the Z7 flash rig**
  (root cause of the larger lighting variation — see §5). No MPO quirk observed (single-frame
  JPEG); the existing MPO eager-import guard is harmless.

**Diff vs `multi_session.discover_config_nodes` / `build_relmtf_subset.py` expectations:** none
structural beyond the camera. `discover_config_nodes` reads the **frozen subset CSV**, not the
tree; tree-walking lives entirely in `build_relmtf_subset.py`, whose `2025-10-17` block
(lines 176–197) already walks the exact `<lens>/<aperture>/` shape with empty/`1_1` mag and
`rail_ok=False` (manual tier). D7200 = two more such blocks + a camera column.

---

## 2. Sample-test RESULTS (nufan, `poc_d7200_probe.py`)

### 2a. Registration — 4/4 PASS (the make-or-break)

| session / sweep | M (atlas) | scale | θ° | rmse_px | n_int | rmse_µm (3.91) | guard≤25µm |
|---|---|---|---|---|---|---|---|
| 08-06 AF200 F7.1 | 1.110 | 1.837 | 3.91 | 1.71 | 10 | **6.04** | ✓ |
| 08-06 Sigma150 F8 | 1.086 | 1.798 | 3.02 | 3.10 | 9 | **11.14** | ✓ |
| 08-19 Sigma150 F8 | 1.089 | 1.802 | 6.59 | 2.53 | 11 | **9.10** | ✓ |
| 08-19 55AIS F8 | 1.106 | 1.830 | 6.67 | 1.18 | 4 | **4.18** | ✓ |

- **DX + OLPF does NOT degrade scribe detection or labelling.** All locked `similarity`
  (correct — macro, no radial term), plausible M, object RMSE 4–11 µm.
- **Cross-date consistency:** Sigma 150 F8 gives M=1.086 (08-06) vs 1.089 (08-19) — 0.3%.
  A wrong registration could not reproduce the same M across two independent sessions.
- **Caveat:** 55 AIS locked on only **4 refine intersections** (borderline; still 4.18 µm).
  Low n_int at high M / small FOV is a known thinness — flag `n_int<5` for review.
- θ spread 3.0–6.7° is wider than the Z7 per-session ~0.45° (different mount/day per session),
  but reg_auto's per-frame tilt search absorbs it — not a problem, just not a fixed-angle prior.

### 2b. reg_guard mis-calibration (confirmed, low-severity)

`relmtf_run.py:159 SENSOR_PITCH_UM = 4.35` is hardcoded Z7 and feeds the object-space guard
`rmse_um = rmse_px * pitch / M`. For D7200 the correct pitch is 3.91 → the guard currently
**over-estimates D7200 object RMSE by 4.35/3.91 = 11.3%** (too strict). None of the 4 samples
flip (all ≤11 µm ≪ 25), but a borderline high-M fit could be wrongly dropped. Fix = per-camera
pitch (§3).

### 2c. Lighting variation — CONFIRMED, larger than Z7

Central-ROI mean luma across each sweep (peak-to-peak in stops; CV):

| sweep | luma mean | pp (stops) | CV |
|---|---|---|---|
| 08-06 AF200 F7.1 | 117.4 | 0.152 | 2.1% |
| 08-06 Sigma150 F8 | 101.1 | 0.229 | 4.2% |
| **08-19 Sigma150 F8** | 92.4 | **0.409** | **5.4%** |
| 08-19 55AIS F8 | 99.7 | 0.225 | 3.7% |
| **Z7 baseline** 2025-10-17 AF200 F8 | 118.9 | 0.170 | 2.3% |

- Within-sweep drift on **2025-08-19 is ~2.4× the Z7 baseline** (0.41 vs 0.17 stops pp).
- **Cross-date DC offset:** the *identical* Sigma 150 F8 config is ~13% dimmer on 08-19 than
  08-06 (mean 92.4 vs 101.1) → the two sessions are not on a common photometric scale.
- **Why it matters:** a monotonic ~0.4-stop ramp across ~33 shots is ~1.3%/shot; over a
  ~10–20-shot FWHM that tilts the through-focus *amplitude* curve ~15–25%, biasing FWHM/peak.
  Focus *position* (argmax) is more robust, but amplitude-based width is not. → normalize (§5).

---

## 3. Required code changes (concrete diffs from production)

All are additive/parameterizing; none change Z7 results (Z7 keeps pitch=4.35, OLPF=False).

**A. Camera as a first-class axis.**
- `build_relmtf_subset.py`: add a `camera` column to `FIELDS`; set `camera="Z7"` on all
  existing `add_rows` calls; add two D7200 blocks (see B) with `camera="D7200"`.
- `multi_session.ConfigNode`: add `camera: str` field; `discover_config_nodes` reads it
  (default `"Z7"` for back-compat with any pre-camera CSV).
- Central camera table (new small module or dict in `multi_session`), e.g.
  `CAMERAS = {"Z7": Camera(pitch_um=4.35, olpf=False, width=8256, height=5504),
  "D7200": Camera(pitch_um=3.91, olpf=True, width=6000, height=4000)}`.

**B. Subset builder — two new manual blocks** (mirror the 2025-10-17 block, lines 176–197):
walk `<lens>/<aperture>/`, focal from filename, `rail_ok=False`, `camera="D7200"`. Skip
`results*` / `results-ignored` / `cropped`. Use **empty `mag_label`** (not a fake `1_1`) so
`nominal_M` stays empty and M comes from registration — the 55/70-180 are not all 1:1, and
`resolve_nominal_M` already leaves rail/empty-mag rows blank. (Note: `sid()` builds
`<lens>_<mag>_<ap>`; with empty mag it yields `S150__F8` — add the session `@YYMMDD` tag,
already done for non-baseline sessions, and optionally collapse the double underscore.)

**C. Thread sensor pitch (and OLPF) through the pipeline** — replace the module-level
`SENSOR_PITCH_UM_Z7` *uses* (not the constant itself) with a per-config pitch:
- `relmtf_run.py:159` `SENSOR_PITCH_UM` → look up `node.camera` pitch in the reg guard
  (`rmse_um = rmse_px * pitch(camera) / M`). **[fixes 2b]**
- `phase1.py`: `Z7_SUBJECT_FACTOR` (l.88), `_scribe_fwhm_px` (l.99), die/maze period (l.125/127)
  — make pitch a parameter (default 4.35) plumbed from the config's camera. These drive ROI
  sizing + subject-space conversion; wrong pitch mis-sizes ROIs by 11%.
- `periodic_fft.py:42` `LPMM_PER_CYPX = 1000/pitch` — parameterize.
- `rail_calibration.py:399/456` trough_fwhm→µm — parameterize (only affects DoF-step calib).
- `characterise.py:128` and `field_geometry_focus.py:121` already take `sensor_pitch_um` as a
  **default param** → just pass the camera pitch at the call site. `NYQUIST_FRACTION`
  guardrail (the Fix #5 column) then auto-corrects: D7200 Nyquist-subject = 1000/(2·3.91)·M =
  127.9·M lp/mm (vs Z7 115·M).
- `maze_fft.maze_amp` / `maze_freq_cy_per_px` already accept `pitch_um` — pass it.

**D. Effective aperture (D7200).** No CSV → priority (2): directory aperture used directly.
`EffectiveApertureLookup` returns nothing for 2025-08 (fine). Add nothing; just ensure the
subset builder writes the folder marked-f as `aperture` (it does). Document that D7200 IF-macro
folder-f ≈ effective; the 55 mm manual + 70-180 are the ones where marked≠effective most, and
they lack a CSV — flag as a known residual bias (same class as the Z7 diopter residual).

**E. Tier.** D7200 = MANUAL tier (`p2_rail_ok=false`): P2 through-focus degraded, DoF-estimated
step, **excluded from the headline rail-coverage ranking** (secondary `--tier all` view only) —
identical treatment to 2025-10-17/2026-01-29/2026-02-18. No new code; just `rail_ok=False`.

**F. OLPF flag.** Carry `camera.olpf` on the node for provenance + reporting; used only to
annotate/caveat outputs (see §4). No metric branch in phase 1.

---

## 4. OLPF handling

An OLPF/AA filter is a fixed low-pass on the sensor MTF (a birefringent 4-spot blur, roughly a
`cos`-like attenuation rising toward Nyquist). Consequences:
- **Absolute MTF50 is systematically depressed** on D7200 vs an equivalent OLPF-less sensor.
- **Within-D7200 relative ranking is essentially unaffected:** OLPF is a common multiplicative
  factor across every D7200 lens at a given *sensor* frequency, so it cancels in a
  fixed-sensor-frequency relative comparison (the relmtf estimator's whole premise). This is the
  regime where D7200 integration is clean.
- **Cross-camera (Z7 vs D7200) does NOT cancel:** Z7 has no OLPF, so the OLPF offset is a
  genuine confound on any absolute Z7↔D7200 lp/mm comparison, *on top of* the different pitch
  and Nyquist. → keep cross-camera absolute comparisons caveated; do not publish them as phase-1
  deliverables. If ever needed, estimate the D7200 OLPF MTF (e.g. slanted-edge on a shared
  sharp config, or the published D7200 AA response) and divide it out — deferred, uncertain.

---

## 5. Lighting-variation mitigation (evidence-based)

Measured drift (§2c) is large enough to bias amplitude-based through-focus width. Options,
cheapest first:
1. **Per-shot exposure normalization before the P2 fit** (recommended): divide each shot's
   metric/ROI by that shot's central-ROI mean luma (or a robust flat-field), removing the slow
   multiplicative drift. Cheap, local to phase 1/P2, and helps the manual tier generally.
2. **Check whether the estimator already normalizes:** `maze_amp` is an amplitude on the
   derivative spectrum — confirm whether it's contrast-normalized (DC/energy) per ROI; if so,
   slow luma drift is partly absorbed and (1) becomes a smaller correction. (Verify before
   building; not confirmed in this pass.)
3. **Argmax/position-only for D7200:** if amplitude normalization proves unreliable, rank by
   focus *position* and FWHM-of-normalized-curve only, and down-weight absolute amplitude.
4. **Cross-date:** never pool raw amplitudes across the two D7200 dates without normalization
   (13% DC offset). Relative-within-sweep + fixed-sensor-frequency ratio already avoids this;
   just don't add a cross-date absolute step.

---

## 6. Cross-camera scope — what's proven vs caveated

- **Proven (this pass):** reg_auto registers D7200 at 4–11 µm; DX+OLPF doesn't break detection;
  layout is a solved shape; manual-tier path exists; lighting drift quantified.
- **Achievable cleanly (phase 1):** internal D7200 relative-MTF ranking (per-camera pitch,
  manual tier, folder-f, lighting-normalized), reported as its own axis with an OLPF caveat.
- **Hard / deferred / uncertain:** absolute Z7↔D7200 cross-camera lp/mm (OLPF + pitch +
  Nyquist all differ). State as "cross-camera absolute comparison NOT validated; within-camera
  only" until a de-confounded bridge is built and checked.
- **Not yet tested (call out, don't assume):** sub-1:1 D7200 configs (70-180 ±5T/6T) —
  low-M scribe undersampling caveat carries over; the 55 mm/70-180 folder-f≠effective residual;
  whether `maze_amp` already contrast-normalizes.

---

## 7. Phased implementation + effort + risks

**Phase 1 — camera axis + D7200 discovery (≈0.5–1 day).**
Add `camera` column + `CAMERAS` table + `ConfigNode.camera`; two D7200 blocks in
`build_relmtf_subset.py`; thread pitch through the 5 call sites (§3C). Regenerate the subset
(now Z7 + D7200), diff to confirm Z7 rows unchanged (same 311) and D7200 rows appended.
Risk: `sid` collisions on empty mag_label — mitigate with the `@YYMMDD` tag.

**Phase 2 — probe→production extract on D7200 (≈0.5 day, nufan).**
Run `relmtf-extract`/`analyse --tier all` over the D7200 nodes into `out_relmtf_d7200/`.
Expect most to register (§2a); log drops with `n_int`/rmse. Confirm manual-tier P2 degradation
and that D7200 is excluded from the headline rail ranking. Risk: low-n_int/high-M or sub-1:1
drops — acceptable, log them (loud, not silent).

**Phase 3 — lighting normalization (≈0.5 day).**
Verify maze_amp normalization; if needed add per-shot luma normalization to the P2 path (opt-in,
manual-tier or camera-gated). Re-run D7200; compare FWHM/peak before/after.

**Phase 4 — reporting + caveats (≈0.5 day).**
Emit D7200 relative ranking as a separate axis; annotate OLPF + manual-tier + lighting-normalized;
write the cross-camera caveat. Optionally a `poc_d7200_*_REPORT.md`.

**Open questions:** (a) does `maze_amp` already contrast-normalize? (b) folder-f vs effective-f
for the 55 mm manual + 70-180 without a CSV — measure or accept the residual? (c) is a coarse
per-lens nominal-M prior (from EXIF FocusDistance + lens) worth adding to tighten the
plausibility band, or is the empty-nominal path sufficient (it worked on all 4 samples)?

**Deliverables of this pass:** `scripts/poc_d7200_probe.py`, `out_d7200_probe/probe_report.json`,
this plan. No tracked production module modified; `out_relmtf_311`/HANDOVERs untouched.
