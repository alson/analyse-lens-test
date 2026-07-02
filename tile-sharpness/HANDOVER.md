# Sharpness assessment POC — session handover

State as of 2026-05-18 (extended 2026-06-27, 2026-06-28, 2026-06-30, 2026-07-01, 2026-07-02).

> **2026-07-02 (later) — PRODUCTIONISED the class A+B recovery: 8/9 of the remaining
> failures now registrable (commit `06e8fdf`).** New `relmtf-recover` (two-pass: unchanged
> pass-1 extract → pass-2 recovery from a same-family sharp-aperture prior) +
> `wafer-atlas/scripts/sibling_prior_reg.py`. Class A = force the sibling's tilt+pitch into
> detection (reject sub-die texture); class B = seed from the sibling affine + dark-bar
> MATCHED-FILTER scribe-center localization (blur-tolerant) with an M-aware band (~pitch/8).
> Recovers 8/9 as REAL fits vs ground truth: 24-120 F5.6/F8, Z100400 F5.6, Z105+61ext F4.5
> (class A); AF200+6T+5T F5.3/F5.6 (M=2.085, ~11µm, n_int 5), S150+5T+6T & +6T+5T F5.6
> (~12–14µm, n_int 8–9) (class B). Only **Viltrox85+26ext F2** stays out (genuine: f/2 too
> soft — matched filter locks the right M=0.49 but at 202µm object rmse, well over the 25µm
> ceiling). Family-consistency AUDIT: **0/305 flagged** (no silent texture-mislocks in the
> current registered set). 359 tests. The class-B bug that had blocked it: the seed lacked
> `theta_rad` → `grid_xy` KeyError swallowed → None for every frame (fixed via
> `ensure_theta_rad`; also switched the combiner to min OBJECT-space rmse + rejected n_int<4
> fake fix-A inherits).
> **REMAINING (low value, not done):** `relmtf-recover` emits registrations (meta) only —
> to fold the 8 into the ranking/physical/geometry outputs it needs a per-patch extract
> seeded with the recovered reg, then a re-analyse. All 8 are widest-aperture entries of
> families already ranked at F8–F16, so no config family is missing; deferred as optional.

> **2026-07-02 — CV exploration for the 9 remaining registration failures: BOTH classes
> solved in prototype (not yet productionised; scratch under `tile-sharpness/out_reg_cv/`,
> gitignored).** Corrects the class-A root cause: it is NOT labelling ambiguity — it is a
> TILT/DETECTION bug. At sharp apertures the tilt/peak detector locks onto sub-die TEXTURE
> (mixing ~20–90 ds-px texture lines into the true ~63 ds-px scribe grid, θ→1–3.9° vs the
> true ~4.5°) → the affine mis-scales/collapses (24-120 F5.6→M=0.19, F8→wrong offset); F16
> escapes only because diffraction blurs the texture away.
> - **Class A fix — tilt+pitch prior (`out_reg_cv/approach4b_tiltseed.py`):** the wafer is
>   fixed on the QR plate so θ is ~constant per session (~0.45° spread); force the sibling
>   sharp-aperture's θ + expected die-pitch into de-rotation/peak-detection to reject sub-die
>   texture, then pick the labelling matching the prior. Recovers 24-120 F5.6 → M=0.410
>   (truth 0.408, rmse 0.78px, 24 int) and F8 → 0.407 (rmse 0.52px). Also helps any sharp
>   low-M lens where texture beats scribes.
> - **Class B fix — sibling-prior seed + matched-filter localization
>   (`approach5b_prior.py`/`approach5_matched.py`):** seed the soft config from the family's
>   sharp-aperture affine (phase-correlation origin shift), then REPLACE the sub-pixel trough
>   refiner with a dark-bar MATCHED FILTER (symmetric blur preserves the scribe centroid → the
>   center is recoverable without a sharp gradient), with an M-AWARE search band (`~pitch/8`;
>   the fixed 100px band gave 0 locks at M≈2 pitch 2561px). Recovers AF200+6T+5T F5.6 →
>   M=2.061 (truth 2.070, rmse 5.47px), S150+5T+6T F5.6, Viltrox85+26ext f2 — all dM≤0.008,
>   obj-rmse ≤25µm. Keep min-rmse vs the trough result so already-good configs (Z100400 F5.6)
>   are unaffected.
> - **Rejected:** standalone 2D-FFT physical-scale (locked a constant ~1.02–1.22 M artifact;
>   and `reg_auto.pitch_implied_scale` already provides a labelling-independent scale, better);
>   landmark-template anchoring (NOT needed — the surviving labelling candidates are
>   same-mod-4-phase, measurement-equivalent, so absolute-phase anchoring wouldn't change M).
> - **Both fixes depend on a same-family sharp aperture that registers** (true for all 9
>   targets). Off-axis PSF asymmetry biases matched-filter centers at field edges but averages
>   out over a global affine (fine for registration, not per-scribe MTF). Recommended
>   integration: class A ≈ half-day (tilt/pitch prior into `reg_auto.detect` via
>   `atlas_periodic_fft.register`); class B ≈ 1 day (sibling-prior fallback registrar when
>   `refine_full_res` < 4 locks). NOT yet implemented — awaiting go-ahead.

> **2026-07-01 (later) — PRODUCTIONISED the 4 POCs + the recovered multi-session
> extension into a single CLI pipeline, and reprocessed all Z7 macro data.** New
> production entry point: `tile-sharpness relmtf-extract` / `relmtf-analyse`
> (driver `scripts/relmtf_run.py`), run over the FROZEN 316-config-node multi-session
> subset `data/cross_m_relative_mtf_subset_multisession.csv` (regenerator
> `scripts/build_relmtf_subset.py`; 151 rail-coverage / 165 manual tier across
> 2025-10-17 / 2026-01-29 / 2026-02-18 / 2026-05-12 / 2026-05-13; Z7 only, D7200
> excluded). Pipeline: `multi_session.discover_config_nodes` → `reg_auto` (guard:
> drop M≤0.20 scale-collapse / M∉[0.20,3.50] / rmse>6px → `dropped_configs*.csv`)
> → P1 (all tiers) + P2 through-focus+coverage tier-gated by `p2_rail_available`
> → step resolution (documented `rail_position_mm` for 2026-05+, DoF-estimated only
> pre-2026-05, never DoF when documented) + effective aperture (`effective_f_exact`
> CSV else directory aperture, never analytical) → physical mm (POC 3) → field
> geometry (POC 4, tilt-removed). **Headline ranking = rail-coverage-tier-only**;
> manual tier secondary; **M>1.10 flagged `step_low_confidence` + excluded from
> headline** (DoF M-form calibrated only over M≤1); `<3` ok patches → dropped.
> Overlap reconciliation: POC 1 `coverage_flag` supersedes the recovered
> `focus_peak_at_edge`/`coverage_ok` (dropped); the recovered `p2_rail_available`
> tier gate + multi-session/supersession logic were grafted into `multi_session.py`
> + `cross_m_relative_mtf.py`. The parked `scripts/_recovered_extension_2026-06-30/`
> was DELETED once integrated (provenance in git commit 4085c9c). The four
> `scripts/poc_*.py` remain as the original single-cohort (2026-01-29) validations
> behind their `_REPORT.md`s; `relmtf-*` is the production path. See README
> "Cross-M relative-MTF pipeline (production, multi-session)".
>
> **Re-run outcome (all Z7 macro, `out_relmtf_multisession/`, gitignored/regenerable):**
> 16 shards thread-pinned on nufan, clean (no errors). **282/316 configs registered;
> 34 dropped by `reg_guard`** (concentrated in the high-M extension/diopter families —
> 2026-02-18 −15, 2026-05-13 −19 — where `reg_auto` collapses, a known limit). ~10.6k
> through-focus fits, ~29k field-tagged patches. **Headline rail-coverage-tier ranking =
> 63 configs (M 0.38–1.08; M>1.10 correctly excluded → 0 low-conf in headline)**; manual
> tiers = 0 in headline (secondary `--tier all` view). Relative fixed-f_px (0.1 cy/px)
> sharpest = bare Z 100-400 F11/F16, Z 24-120 F16, Viltrox 85+26mm-ext (low-M tops it —
> the estimator deliberately doesn't credit empty magnification); softest = Viltrox
> 85+61mm-ext wide-open. Physical: documented step used for ALL 2026-05 (never-DoF-when-
> known held). Field geometry (65 configs, tilt-removed) — READ WITH `rms_residual_um` as
> the quality gate: clean strong curvature e.g. V55-287318 F8 (−1.27 DoF sag, −1429 µm,
> RMS 51 µm, corners-nearer) and 100-400+C500D F11 (−1.03 DoF, RMS 47 µm); flattest ~S150
> F16 / Viltrox+45mm-ext (≈0.04 DoF). The huge-sag 24-120+ext wide-open configs have RMS
> >300–1000 µm → NOT clean bowls (tilt/noise-dominated); don't trust their sag.

> **2026-07-02 — registration recovery: 282 → 305/316 registered.** The 34 drops were
> investigated + attacked in two waves (commits `0d37e00`, `bdda766`):
> 1. **min-residual-over-frames frame-selection** (`register_config`/`select_registration`):
>    the honest lock is often NOT the sharpest frame (the sharpest exposure bracket
>    registers WORST; the true lock can sit ~rank 16–28 by lapvar). Widened candidates to
>    top-`REG_SELECT_TOPK` (16, later 20) sharpest + spread, keep min-rmse among PLAUSIBLE
>    locks (`_lock_plausible`: reject M<0.30, and given nominal_M a 0.55–1.90×nom band).
>    → 282→300; also caught wrong-locks the old loose M≥0.15 guard admitted.
> 2. **OBJECT-SPACE `reg_guard` ceiling** (replaced flat 6px): gate on `rmse_px·pitch/M ≤
>    25 µm`. Registration accuracy is a physical constant in object space (~9 µm median,
>    p99≈20 µm, **M-INDEPENDENT**: corr(M,rmse_µm)=−0.06 over 300 fits); the per-px rmse
>    rises with M (corr +0.66) ONLY because a pixel subtends pitch/M. Flat 6px was too
>    strict at high M (clipped good 12–18 µm fits) and too lenient at low M. → +5
>    (Z100400 F8 via TOPK, now the #1-ranked config; near-ceiling S105+5T+6T F16 +
>    Z105+61ext F8/F11/F16 via the object ceiling). **Final: 305/316; headline 67 configs.**
> **9 still unregisterable (after superseding the 2 capture-defects) — CORRECTED
> classification (2026-07-02, re-verified by re-running the failed subset with latest code +
> checking the full aperture ladder per family):** the earlier "M≈2 scribe-count limit" was
> WRONG. **7 of the 9 are simply WIDE-OPEN-SOFT** — each is the single WIDEST aperture of its
> family, and the SAME family registers fine stopped down: AF200+6T+5T fails F5.3/F5.6 but
> registers F8/F11/F16; S150+5T+6T & S150+6T+5T fail F5.6, register F8/F11/F16; Z105+61ext
> fails F4.5, registers F5.6/F8/F11/F16; Z100400 fails F5.6 (central lapvar 370 vs 745@F8),
> registers F8/F11/F16; Viltrox85+26ext fails F2, registers stopped down. So **no config
> FAMILY is lost** — only redundant widest-aperture entries; the sub-pixel refiner is starved
> by wide-open LOW CONTRAST, not by M≈2 lacking scribes (the same M≈2 config at F8 has plenty).
> The remaining **2 are genuinely wrong-grid** (bare 24-120 F5.6/F8, 255/293 µm object) — a
> real reg_auto labelling mis-lock (bare 24-120 registers at F4/F11/F16), the only
> tooling-fixable item left. Populated nominal_M recovered NONE of the 9 (confirms these
> aren't plausibility-band-related — and that the nominal_M change is safe).
> The 2 former capture-defect sweeps (24-120+10ext F4.5/F6.3 @260218 — wafer centre never
> focuses; lapvar flat ~6.7 vs ~1700 sharp) are handled by supersession, below.
>
> **2026-07-02 (cleanup, commit pending):** the 2 capture-defect sweeps were ALREADY reshot
> — the 2026-05-13 24-120+10ext@120mm sweep covers the same regime (M≈0.56, registers at
> 1.6px), so the whole 2026-02-18 120mm+10ext family (5 rows, incl. the 2 defects) is now
> SUPERSEDED and dropped from the frozen subset (**316 → 311 rows**; the 50mm+10ext family,
> not reshot, is kept). `nominal_M` is now populated at subset-build time (288/311; the 23
> empties are genuinely `magnification: null` in metadata.json). Shard-pooling hardened to
> skip empty/0-config shard CSVs (`_read_csv_safe`/`_pool_shards`). Registration lessons
> written into README ("Registration notes") + reg_auto.py docstring. NOTE: the committed
> `out_relmtf_multisession/` (305/316) reflects the prior 316-row run; a future re-run
> reconciles to the 311-row subset (headline rail-coverage ranking is unaffected — the 5
> dropped are 2026-02-18 manual-tier, secondary view only). 331 tests pass.

> **2026-07-01 — follow-up #7 delivered as four chained POCs: focus-coverage
> flagging → DoF step-size → physical-mm FWHM → field geometry.** All verified;
> per-POC reports in `scripts/poc_*_REPORT.md`. Bare `pytest` is now green (277) via
> `testpaths=["tests"]` in pyproject.toml (was a collection clash with the parked
> `scripts/_recovered_extension_2026-06-30/` test + `.venv` globbing).
>
> 1. **POC 1 — focus-coverage flagging** (`cross_m_relative_mtf.py`): the P2
>    through-focus estimator now emits per-patch `mu` (best-focus centre, frames),
>    `peak_pos_frac`, `edge_dist_frames`, and `coverage_flag` ∈
>    {ok, truncated_low, truncated_high, fwhm_truncated} (priority: edge-of-stack
>    first, then HWHM-clipped). `through_focus_scores` excludes non-`ok` patches.
>    2026-01-29 cohort: 677 ok / 45 fwhm_truncated / 2 truncated_low / 0
>    truncated_high; corners NOT disproportionately truncated (corner 8.6 % vs
>    centre 7.1 %).
> 2. **POC 2 — DoF-based rail step-size** (`optics.object_dof_predictor` +
>    `scripts/poc_dof_step_size.py`): estimates mm/frame from a depth-of-focus model
>    × measured through-focus FWHM, validated on the 2026-05 documented
>    `rail_position_mm`. Best predictor **`N_working·(1+M)/M²`, R²=0.871, k=0.04255**;
>    LOO accuracy median 1.05 (IQR [0.91, 1.30]); **beats the scribe-blur calibrator**
>    (scribe under-reads, ratio ~0.67). ⚠ **M-form is weakly identified** — only 3
>    distinct M values (0.385/0.752/1.0, each a lens group, all ≤1.0); the aperture
>    (N_working) dependence is solid but the M-exponent rests on 3 clusters, so
>    absolute mm at M>1 is EXTRAPOLATION (tilt/curvature scale linearly with the
>    unknown M-exponent → ~2× uncertainty at 2:1).
> 3. **POC 3 — physical-mm FWHM** (`focus_physical.py` +
>    `scripts/poc_refine_fwhm.py`): emits per-patch `mu_mm`, `fwhm_mm`, per-sweep
>    `step_mm`+`step_source` (documented where available, DoF-estimated otherwise),
>    coverage-carried + DoF-prior imputation for truncated patches. Non-circular
>    validation vs documented step: mu_mm/fwhm_mm estimated-vs-documented median
>    ~1.05 (just inherits POC 2's step error). `mu` fit stderr ~0.045 frames.
> 4. **POC 4 — field geometry** (`field_geometry_focus.py` +
>    `scripts/poc_field_geometry.py`): plane-fit of `mu_mm` over (x,y) → tilt +
>    field-curvature (radial residual) + decentering, run ALL vs coverage-CLEAN.
>    **The 2026-01-29 top-vs-bottom "decentering" is an UNDER-COVERAGE ARTIFACT** —
>    AF 200 IF-ED 1:1 all-patches sag 8508 µm / T-B +1.99 mm → clean sag 108 µm (78×
>    collapse) / T-B −1.14 mm (sign flip) from 3 truncated patches. Robust residual
>    is L-R/general plane tilt; only Sigma 150 & MC 105 (zero truncated patches) show
>    genuine T-B. Tilt magnitudes agree with `characterise.py` to ~0.5°. (This
>    supersedes the "re-examine the apparent T–B decentering" caveat in the
>    2026-06-30 follow-up #7 below — resolved: artifact.)
>
> **Effective-aperture correctness (load-bearing; bit POC 2 first).** For ANY working
> f-number (DoF, diffraction, defocus, step-size), the aperture is ALREADY effective
> (bellows-corrected) — never re-apply `N·(1+M/p)`. Resolution priority: (1)
> `effective_f_exact` from the in-tree `effective_apertures.csv`
> (`test-raw-data/2026-{01-29,02-18,05-13}/`, load via
> `rail_calibration.EffectiveApertureLookup.from_csvs`; photometric = `sqrt`(brightness
> ratio), so independent of DoF → no circularity); else (2) the **directory-name
> aperture used directly** (it is already effective — AF/IF macros report effective
> EXIF; manual extension-only lenses like the 55mm have f_eff from the published
> manual/analytical extension baked into the folder name; verify via widest-native-folder
> ≈ spec-max·(1+M)); (3) never the analytical formula (needs unpublished focal-at-MFD +
> pupil mag) — drop the config instead. See `../bellows-calibration/` and the
> project `CLAUDE.md` "Effective aperture" note.
>
> **Status of the parked `scripts/_recovered_extension_2026-06-30/`:** its coverage
> helpers are superseded by POC 1, BUT its multi-session/20-aperture extension
> (`--subset`, `@YYMMDD` sid tags + supersession dedup, tier-aware P2 degradation)
> and the 316-config multisession subset CSV are NOT integrated — still the input for
> follow-up #5 (extend the estimator beyond 2026-01-29). Keep until that reprocess lands.

> **2026-06-30 — cross-M relative-MTF estimator (new) + follow-ups.** A long POC arc
> (full record: `scripts/poc_comb_chain_REPORT.md`) established that an ABSOLUTE /
> subject-resolution cross-magnification ranking is dead on this wafer (genuine target
> instability, proven), BUT a RELATIVE, fixed-sensor-frequency glass-MTF ranking IS
> achievable and is corroborated by four independent estimators — now PRODUCTION at
> `src/tile_sharpness/cross_m_relative_mtf.py` (+ CLI `scripts/cross_m_relative_mtf_run.py`,
> commits `5d6810e`/`d5e6a58`). Also fixed a real `discover_fundamental` 2-D-lattice
> mislocking bug (`25d9d43`). FOLLOW-UPS (see REPORT "Future plans"): (5) extend the
> relative estimator beyond the 2026-01-29 cohort to the other Z7 wafer sessions
> (2026-02-xx, 2026-05-12/13, 2025-10-17) — IN PROGRESS. ACQUISITION TIERS (git-confirmed:
> planner/rail-coverage arrived 2026-05-05): rail-coverage tier 2026-05+ (constant
> registered step, full focus coverage → P2 valid) vs MANUAL tier ≤2026-02 incl.
> 2026-01-29 (manual start/stop + fixed step COUNT → non-constant unregistered step,
> possible incomplete focus-peak coverage → P2 degraded; 2026-05 reshot some under-covered
> 2026-01/02 configs, so prefer the 2026-05 versions). (6) **D7200 wafer cross-camera —
> the wafer was shot on the D7200 on 2025-08-06 and 2025-08-19 (DX, 3.91µm, OLPF); bringing
> it in needs sensor-pitch reparameterization + atlas registration + a cross-camera bridge
> — DEFERRED, left for later.** (7) **Field curvature from the stack + focus-coverage
> flagging** — the location-aware estimator already takes per-die best focus, so emit the
> P2 Gaussian peak-CENTRE per patch (not just FWHM), map over (x,y) → tilt + curvature
> surface; and flag patches whose best-focus is truncated at a stack edge (helpers in the
> parked extension; plus the rail-coverage subproject's existing filesize-based truncation
> flags in `rail-coverage/output/scan-cache.json` + `reshoot.html`). NB this means the
> subset's apparent T–B "decentering" is likely an under-coverage artifact, not real
> decentering — re-examine before trusting it.

> **2026-06-28 — accessory-config M validation + atlas-anchored ranking (the two
> top 2026-06-27 follow-ups). Full write-up: `REPORT_taskAD_2026-06-28.md`.**
>
> 1. **The "reg_auto mislabels cols/rows → scales M 8-29%" hypothesis is REFUTED.**
>    Enumerating every phase-consistent label moves M by ≤1.9%
>    (`wafer-atlas/scripts/probe_label_ambiguity.py`); atlas-M is independently
>    validated — reproduces KNOWN nominal M to ~1.6% across M=0.385→2.0 incl. the
>    100-400 zoom (`probe_anchor_validation.py`). So the atlas-vs-nominal gaps are
>    **nominal-label errors**, and atlas-M is the trustworthy M. The real reg_auto
>    failure mode is **scale collapse** (M≈0 at a *too-low* 0.4px residual, few
>    intersections) — guard with an absolute M bound + residual ceiling, not
>    residual alone. Memory `reg_auto_label_scale_uncertainty` corrected.
> 2. **Label errors are concentrated in the 100-400 + close-up-diopter family**:
>    MCON-35 +29% (ratio inversion — `1_1.16` should be ≈`1.16_1`), Canon 500D −16%,
>    6T −10%, 5T −8%. All other 47 of 51 configs match nominal within ±7%
>    (median ~1%). Corrected-M manifest: `wafer-atlas/scripts/atlas_m_manifest.csv`
>    (m_lookup `vision_measured_mag` schema, untrustworthy regs omitted → nominal).
> 3. **Ranking uses the atlas-anchored 5-position method, NOT blind characterise**
>    (which is ~6 min/sweep and collapses to centre-only at M≈1.1). New driver
>    `scripts/atlas_rank_accessory.py` → `out_accessory_atlas/ranking_resolution.csv`
>    (51 configs × F8/F11, centre+4-corner subject lp/mm + diffraction headroom).
>    **MCON-35 (28.9) > 6T (23.8) at centre confirmed** (matches 2026-06-27 exactly).
>    Trust only `glass-ltd` rows; sharp macro+diopter centres and ~all of F11
>    OVER-READ the ceiling (LSF artifact at high N_eff) — F11 buys no real resolution
>    over F8 at these magnifications (diffraction/empty-mag regime).
> 4. **Compute note:** the registration/measurement is CPU-bound and per-combo
>    sequential — shard it across workers and run on **nufan** (16-core 5800X, vs a
>    mobile i5); `scripts/atlas_rank_accessory.py` honours `SHARD="i/N"` writing
>    per-shard CSVs to merge. ~6× faster than single-threaded on bumblebee.
> 5. **2026-06-28b — both follow-ups executed (REPORT_taskAD §E):**
>    - **LSF over-read: documented cause DISPROVEN.** Not noise-floor / peak-vs-DC
>      normalisation (DC-norm+window moved it the wrong way, reverted; ESF is clean
>      monotonic). Real cause = **L/R trough-wall asymmetry** (one wall ≈ceiling,
>      the other ~1.6× over; mean over-reads). Shipped `lsf_mtf50(combine="min")`
>      (opt-in; default `mean` unchanged, 117 tests pass) — cuts over-reads F11
>      40→28/44, F8 11→8/38, but NOT both-walls-over-read configs. Full fix needs
>      symmetric sub-pixel ESF extraction. **2026-06-29 update:** the
>      symmetric-window idea (Hann centred on the LSF centroid + DC renorm) was
>      built and validated on the *long-distance single-edge* estimator (a
>      different code path — see `longdist-sharpness` §5.6e). It is the candidate
>      port for this two-wall scribe case (window each wall independently) but is
>      NOT yet ported; `combine="min"` still ships here.
>    - **Bare macros measured** (`enumerate_bare_configs.py` + same driver, min) →
>      `out_accessory_atlas/unified_ranking.csv` (bare+accessory, one axis). F8
>      trustworthy: modern bare macros (Sigma 150 41.6, Sigma 105 40.2, 105VR 39.5,
>      AF60 38.1, AF200 35.8) > vintage 55mm primes (21–32) > 100-400+diopter (17–28).
>    - **Still open:** residual both-walls over-read; the high-M Sigma stacked +
>      2:1 AF200 configs (registration fails/collapses).

> **2026-06-27 — cross-config resolution ranking: diffraction ceiling +
> the MTF50 over-read finding.** Goal: rank lens/accessory configs by
> subject-space resolution at centre/corner (e.g. best route to 2:1; is an
> extension/TC/diopter worth it; keep-or-cut). Existing-data only (no new
> acquisition). Key outcomes:
>
> 1. **The centre/corner ranking framework already exists** —
>    `characterise.py` (Phase 3) emits subject-space MTF50 at centre / DX-ring /
>    FX-ring + uniformity + decentering + field-curvature; `compare.py` does
>    cross-lens ranking + corner asymmetry. The **bare lenses are characterised**
>    (`out*/lens_characteristics*.csv`); the **accessory/2:1 configs
>    (extension/TC/diopter, 2026-05-xx + 100-400 combos) are NOT yet** — they need
>    an `analyse --no-legacy` → `characterise` run on existing JPGs.
> 2. **Diffraction ceiling overlay** — new `optics.py` (effective f-number
>    `N·(1+M/p)`; diffraction-limited subject-space MTF50 ceiling) +
>    `scripts/diffraction_ranking.py`. Separates real resolving power from empty
>    magnification (tubes/TCs push N_eff to f/20+ where the ceiling collapses).
>    Centre/corner glass-limited breakdown: median headroom (measured/ceiling)
>    centre 0.71, DX-corner 0.62, FX-corner 0.56 — **corners are systematically
>    glass-limited** (field-dependent lens/diopter quality), not
>    diffraction-limited. So effective aperture is NOT the only relevant metric;
>    corner resolution discriminates real glass.
> 3. **⚠ MTF50 OVER-READS the diffraction ceiling** — 12/29 configs report a
>    *physically impossible* centre MTF50 above the ceiling (worst stopped down; a
>    55mm reads higher at f/16 than f/8). **It is a MEASUREMENT-METHODOLOGY
>    artifact, NOT a JPEG one** — the RAW-vs-JPEG diagnostic
>    (`scripts/raw_vs_jpg_mtf.py`, atlas-anchored deterministic scribes) shows
>    8-bit JPEG, linearised JPEG, and linear/unsharpened RAW (dcraw) ALL over-read
>    at f/11-f/16; RAW is not lower. Cause: the slanted-edge LSF (derivative of the
>    ESF) inflates on low-contrast / diffraction-blurred edges (noise floor in the
>    differentiated LSF holds |FFT| up past the true 0.5 crossing), compounded by
>    `_mtf50_from_lsf` normalising to the spectral PEAK (DC dropped) and large
>    scribe-to-scribe variance (±~5 lp/mm). **So the absolute lp/mm ranking is not
>    physically calibrated; trust measured MTF50 only where it sits comfortably
>    below the ceiling (glass-limited — corners, wider apertures).** For
>    diffraction-limited configs use the physics ceiling (depends only on M +
>    effective aperture, both reliable; M from the atlas registration scale).
> 4. **Atlas-anchored corner measurement** (`scripts/atlas_corner_mtf.py`, uses
>    wafer-atlas `reg_auto`) closes the coverage gap the blind per-tile detector
>    leaves at high M: on 100-400 + MCON-35/6T/5T @ F8 the blind pipeline gave 6T
>    only 1 tile (centre); the atlas covers all 5 field positions for all three at
>    1.6-1.9px registration. **Result: MCON-35 > 6T** (centre 28.9 vs 23.8 lp/mm
>    ~21%, corner-mean 19.4 vs 17.9) — confirms the user's recollection; centre is
>    the clean signal. MCON-35 ≫ 5T at corners (blind pipeline, 23-29 vs 17).
>    **Caveats:** per-corner scribe noise ±~5 lp/mm (corner gap within noise); 5T
>    looks best, contradicting the blind pipeline (don't trust); **reg_auto
>    label/scale uncertainty** — atlas-M disagreed with nominal labels by 8-29%
>    even at clean ~1.6px residual (a wrong col/row LABELLING scales M while still
>    fitting), so absolute lp/mm carries scale uncertainty on accessory configs.
>
> **Follow-ups (existing data; no new acquisition):**
> - **Highest leverage: M/label validation** for `reg_auto` on accessory configs
>   (cross-check atlas-M vs nominal; detect/fix mislabelling) — underpins every
>   absolute cross-config number.
> - **Scribe averaging** (several scribes per field position) to beat the ±5 lp/mm
>   corner noise; and an **LSF over-read fix** (normalise to DC not peak; denoise/
>   window the differentiated LSF) to make absolute MTF50 ≤ ceiling.
> - **Run `characterise` on the accessory/2:1 configs** to bring them into the
>   ranking (extension ladder, Sigma±TC, lens+Kenko, crop-vs-native).
> - New files: `src/tile_sharpness/optics.py` (+`tests/test_optics.py`),
>   `scripts/diffraction_ranking.py`, `scripts/raw_vs_jpg_mtf.py`,
>   `scripts/atlas_corner_mtf.py`. Runs use `direnv exec . uv run …` on nufan
>   (per-host venv via `.envrc`); dcraw is on nufan for RAW decode.

> **2026-05-18 (atlas track) — wafer-atlas subproject + atlas-anchored
> 4D-bar slanted-edge demo.** New subproject at
> `../wafer-atlas/`. Read its README + HANDOVER first for the full
> picture. Highlights:
>
> 1. **Atlas built** from f/8 + 35mm extension overview photo:
>    16 super-cell die types catalogued with bond_pads / slanted_edge /
>    experimental features. User-painted feature regions parsed into
>    `wafer-atlas/atlas.json`.
> 2. **Anchor-based per-sweep registration** working (RMSE 2-8 px on
>    4 test sweeps spanning M=0.385 to M=2.0). Per-sweep affine fit
>    from 3 user-supplied scribe-intersection anchors. ~30 sec
>    GIMP work per sweep.
> 3. **Atlas-anchored 4D-bar slanted-edge MTF50** (`task15`): finds
>    focus argmax within **±1 shot of LSF reference** on Task 2
>    (M=0.385) and Task 4 (M=2.0). Two anomalies (sweep 2 gap of
>    −13, sweep 4 monotonic decrease) under investigation. This is
>    a viable atlas-targeted alternative to scribe-LSF at low M
>    where scribes are under-sampled.
> 4. **Autonomous registration** (work-in-progress): morphological
>    long-line detection ported from
>    `archive-2026-05/measure_wafer_squares` recovers scale + rotation
>    + super-cell pattern but has up-to-3-way absolute-label ambiguity
>    for partial-wafer sweeps. Resolution path: whole-vs-jagged-die
>    counting per super-cell type (see wafer-atlas/HANDOVER §2).

> **2026-05-18 (late) — verdict relabel, peaks-v2 crops, task 7 result.**
>
> 1. **Verdict labels renamed** to spread-only descriptors:
>    `tight / moderate / wide / unusable / insufficient / failed`
>    (was `publishable / comparison_ok / sanity_only / ...`). The old
>    names implied accuracy claims the algorithm doesn't actually
>    deliver — the validation showed "publishable" verdicts
>    systematically under-estimate while "sanity_only" over-estimates.
>    Labels now describe per-estimate cluster **spread**, not
>    accuracy. Back-compat aliases for the numeric thresholds retained
>    (`PUBLISHABLE_REL_UNCERTAINTY` etc.).
>
> 2. **Task 7 subject-tilt sanity check ran.** Older-rig (2026-01-29
>    9-group cohort) with v2 pooled rail-step lookup applied:
>    median |tilt_x|=0.45°, median |tilt_y|=0.12°, max 1.67°.
>    **NOT the 3-6° this plan predicted**. The 3-6° figure came from
>    visual "scribes look tilted ~+4.5° in captured frames" — that's
>    *in-plane* scribe rotation (rig rotation), not the *out-of-plane*
>    subject-plane tilt that `subject_tilt_*_deg` measures. Different
>    angles entirely; the prediction was based on a category error.
>    Older-rig data is in fact close to coplanar (<1°) — the rig was
>    well-aligned.
>
> 3. **peaks-v2 crops export added.** New CLI `peaks-v2-crops` +
>    `export_peaks_v2_crops()` emits one crop per (lens, tile) at
>    the v2 primary-metric argmax shot (maze-FFT amp where M≥0.7,
>    scribe-LSF amp otherwise). Replaces the filesize-picked
>    `cross_lens_crops/` legacy that HANDOVER previously flagged as
>    unsafe. Family-aware discovery skips slow newer-rig walks when
>    only older-rig sweeps are present.
>
> 4. **out_55mm crops regenerated** at
>    `out_55mm/cross_lens_crops_v2/` from maze-FFT argmax. AIS 287318
>    vs 537016 maze peaks now within 3 % — confirming the previous
>    "287318 decentered" claim was a filesize mis-pick artifact.
>
> 5. **EffectiveApertureLookup now bridges both rig label
>    conventions.** Newer-rig sweep IDs use the raw lens name with
>    spaces; older-rig slugifies spaces to underscores. The lookup
>    stores both forms as keys so calibration overrides apply
>    uniformly. Verified end-to-end on older-rig 100-400 @ 1:2.60 F11:
>    CSV applies the 1.0474 bellows multiplier (slug 11 → effective
>    11.52); rail-step shifts +4.7 % accordingly.

> **2026-05-18 (early) — newer-rig validation + diopter analytical fallback.**
>
> 1. **Validation against 2026-05 newer-rig data done.** 120 archived
>    sweeps from `~/shared/files/pics/digikam/test-raw-data/2026-05-{13,14,15}/`,
>    scored on nufan (16 cores) in ~4 h. Outputs at
>    `out_newer_validation_2026_05/`.
>
> 2. **Honest accuracy picture**: median ratio (derived / actual) = 1.30,
>    IQR 0.85-1.83 across 70 valid sweeps. **Verdict labels reflect
>    per-estimate spread, not bias direction** — see "tight/moderate/
>    wide" relabel above. The per-spread bias asymmetry is the same
>    finding that drove the relabel.
>
> 3. **CSV-effective-aperture mechanism works.** Extension-tube chains
>    in `effective_apertures.csv` converge to median 0.92 vs 1.63 for
>    slug-only.
>
> 4. **Analytical diopter-N fallback added.**
>    `analytical_diopter_effective_f` in `rail_calibration.py` —
>    thin-lens model for close-up filters (Canon 500D, Nikon 5T/6T
>    etc.). Cuts diopter-chain median ratio from 1.38 → 1.19. Wired
>    into `rail_step_lookup_v1`/`_v2` via `resolve_effective_aperture`
>    (priority: CSV → analytical-diopter → slug).
>
> 5. **Follow-up: empirical diopter calibration shoots.**
>    `bellows-calibration/data/per_shot.csv` only covers bare-lens +
>    tube chains. A cloud/ceiling session with each diopter attached
>    would let `build_calibration.py` produce empirical multipliers
>    for those configs and close the residual ~20% diopter bias.
>
> 6. **Bugs fixed during validation:**
>    * `parse_aperture` didn't handle post-rename underscore-decimal
>      `f_5_6` format. Now handles all three formats.
>    * `phase1._decode_gray` crashed on MPO-format JPEGs (Nikon
>      multi-shot). Added eager `import PIL.MpoImagePlugin`.
>
> 7. **Operational note**: shared `.venv/` on NFS doesn't work across
>    hosts with different OS distros. Per-host venvs via direnv +
>    `.envrc` containing
>    `export UV_PROJECT_ENVIRONMENT="$HOME/.cache/uv-venvs/$(basename "$PWD")"`.

> **2026-05-17 update — validation runs + rail-step calibration + M-driven window fix.**
>
> 1. **Tasks 2/4/5 + maze-pitch validation ran.** Task 5 (AF 200/4D
>    + 5T + 6T @ 2:1 F11) centre MTF50 = 24.76 lp/mm vs predicted
>    23 ✓. Task 2 (100-400 @ 0.385× F11) = 10.4 vs predicted 33 —
>    low-M LSF algorithmic limit (narrow trough, too few ESF samples
>    per edge); deferred. Task 4 (Sigma + TC-2001 @ 2:1 F11): was
>    NaN → fixed today by `_half_window_px_for(M)`. Centre subject
>    MTF50 now reads 86.4 lp/mm (sensor 0.188 cy/px); sits ~2× above
>    the ~41 plan target, same direction as task 3's 1.3× over-read,
>    likely an ESF→LSF-at-high-M bias and tracked as a follow-up.
>    Task 2 unchanged after the fix (low-M path takes the 24-px
>    floor) — confirms no regression.
>
> 2. **`MAZE_PITCH_UM=13.0` is cohort-stable** across AIS (M=1.0),
>    Sigma+TC2001 (M=2.0), AF200+5T+6T (M=2.06). Best-fit pitch
>    spread ±3.5 % within FFT bin width. Safe to publish absolute
>    lp/mm with the existing constant.
>
> 3. **Rail-step-mm calibration landed** (`src/tile_sharpness/
>    rail_calibration.py`). Task 7 (subject-tilt sanity check) is
>    now unblocked. Through-focus scribe-blur back-derivation with
>    v1 (per-sweep) + v2 (multi-aperture pooling). See
>    IMPLEMENTATION_PLAN.md "Rail-step-mm calibration" for the
>    physics + use-case-named verdict labels.
>
> 4. **Pre-existing characterise.py bugs found + fixed** during the
>    rail-step wire-in:
>    * `subject_tilt_*_deg` was reporting `arctan(slope)` without
>      pixel→object-space scaling — values were 200× too small.
>      New `_slope_to_tilt_deg` applies M-scaling.
>    * `field_curvature_um_rms` was storing mm in a µm-labelled
>      column. Now multiplied by 1000.
>    * Centre-only grids silently returned the centre row 4× as FX
>      corners, making `uniformity_fx` report 1.0 instead of NaN.
>
> 5. **`parse_aperture` regex bug**: was unanchored, matching the
>    first `_F<digit>_` substring in slugs. Lens names with F-specs
>    (`Sigma_..._F2.8_EX_DG_OS_HSM`) hijacked the result. Fixed by
>    anchoring to the last `__`-separated segment, handling both
>    older-rig (`F8`) and newer-rig (`f_8`) formats. **Old Sigma
>    v2 results are wrong** — Sigma 150 was reading 6.61 µm before
>    fix vs 18.99 µm after (consistent with the rest of the cohort).
>
> Test count: 98 passing.

> **2026-05-16 follow-up — read this before any prior conclusions.**
> A second empirical pass surfaced two findings that supersede parts of
> the POC report below:
>
> 1. **`filesize` argmax fails at sharp configs.** On AIS 55mm at 1:1
>    F8, only 26 % / 46 % of tiles agree between filesize and maze-FFT
>    argmax. Filesize systematically picks 6-10 shots too late. At the
>    centre tile of AIS 287318 it under-reported the lens's true sharpness
>    by 2.13× through pure focus mis-pick. The POC's "filesize 5/5
>    within-sweep" validation was on a *soft* config (24-120 + Raynox
>    M-250) where the bell curve has a sharp peak; on sharp configs it
>    saturates and flattens.
> 2. **The AIS-copy "decentering" was a measurement artifact.** Once
>    each tile is judged at its own FFT-amp peak (not filesize's pick),
>    AIS 287318 and AIS 537016 are within 1 % at every tile and both
>    centred on the sensor. The previously reported 5.8× centre-tile
>    gap and the "287318 top edge 6.3× stronger than its own centre"
>    were both filesize mis-picking on 287318.
>
> **New methodology** (full details in
> `SHARPNESS_METRICS.md` "2026-05-16 update — methodology supersedes
> the POC"): per-tile scribe-LSF MTF50 + maze 2D-FFT amplitude. Both
> sized by measured magnification. Cross-config metric is subject-space
> MTF50. The eight POC methods remain available as cross-validation
> columns but no longer drive primary analysis. Resampled cohorts are
> for human visual comparison only — measurement runs on native frames.
>
> **Status of the `out_55mm/cross_lens_crops/` JPEGs**: these are
> filesize-picked and are not safe for any further numerical analysis.
> Visual review is fine (filesize picks *some* sharp shot, just not
> always the sharpest). Regenerate them via maze-FFT argmax before
> publishing any AIS cross-copy comparisons.
>
> Artefacts from the 2026-05-16 analysis: `/tmp/ais55_decentering_*.png`
> (per-copy maze-FFT amplitude heatmaps); `/tmp/ais_fft_analysis_run2.log`
> (definitive run log); scripts at `/tmp/ais_fft_analysis*.py`. Visual
> validation crops at `/tmp/ais287318_centre_*.png` (also on `nufan:/tmp/`).
>
> **Implementation plan**: see `IMPLEMENTATION_PLAN.md` in this directory
> for the three-phase pipeline (per-shot per-tile CSV → corrected
> peaks_v2.csv → per-slug lens_characteristics.csv) that picks up from
> the 2026-05-16 findings.
>
> **Implementation status (initial commit `9097def`, 2026-05-16):**
> sequencing steps 1-6 of the IMPLEMENTATION_PLAN have landed. New
> modules: `src/tile_sharpness/m_lookup.py` (manifest lookup),
> `methods/lsf.py` (OpenCV LSD scribe detect + cross-section + FFT;
> Hough fallback added in `7cfd5dd`; ESF→LSF math in `17a8d6a`),
> `methods/maze_fft.py` (M-aware annulus sum, matches the prototype to
> 0.4 % on a real AIS centre tile), `phase1.py` (per_shot_per_tile.csv
> + peaks_v2.csv; trough-FWHM filter in `3d3c31c`),
> `characterise.py` (lens_characteristics.csv). CLI gains
> `--manifest <path>` (repeatable), `--no-legacy`, and a
> `characterise` subcommand. 72 tests pass.
>
> Validation status (refreshed 2026-05-17):
>   * **Task 1** ✓ — out_55mm AIS centre maze-FFT amp ratio = 1.0412 (≤ 1.05).
>   * **Task 2** ✓ ran, FAIL — 100-400 @ 0.385× F11 centre = 10.4 vs
>     expected 33. Low-M LSF under-read (algorithmic limit). Unchanged
>     post-windowing-fix (low-M floor preserves the pre-fix readout).
>   * **Task 3** ✓ — AF 200/4D 1:1 F11 centre subject MTF50 = 42.7 lp/mm
>     (target ~33; within physical limits, f/11 diffraction ≈ 67 lp/mm).
>     Uniformity_dx = 0.92, uniformity_fx = 1.02 (matches "high uniformity
>     (sharp macro)" prediction).
>   * **Task 4** ✓ unblocked 2026-05-17 by M-driven `half_window_px`.
>     Sigma + TC-2001 @ 2:1 F11 centre subject MTF50 = 86.4 lp/mm
>     (sensor 0.188 cy/px); ~2× over-read vs ~41 target tracked
>     as follow-up.
>   * **Task 5** ✓ — AF 200/4D + 5T + 6T @ 2:1 F11 centre = 24.76 lp/mm
>     (target ~23). Degenerate-grid path (centre-only) works correctly.
>   * **Task 6** — partial. Post-windowing-fix ordering by centre
>     subject MTF50: task 4 (86.4) > task 3 (42.7) > task 5 (24.76) >
>     task 2 (10.4). Top matches plan (Sigma+TC the sharpest);
>     bottom still constrained by task 2's low-M under-read.
>   * **Task 7** ✓ unblocked — rail-step calibration in
>     `rail_calibration.py` provides per-sweep / per-group rail step
>     for older datasets without recorded `rail_position_mm`.
>   * **Maze-pitch validation** ✓ — `MAZE_PITCH_UM=13.0` stable across
>     three cohorts (±3.5 % spread).
>
> Steps 7-8 of the IMPLEMENTATION_PLAN (HTML report wiring + full
> cohort re-runs) deferred.
>
> **M-aware non-scribe rejection (`trough_fwhm_px` filter).** LSD/Hough
> accepts long dark lines regardless of width; some non-scribe features
> (bond-pad shadows, single dark texture lines) slip through with
> 5-12 px troughs even when real scribes at that M would be 20+ px
> wide. `phase1._score_shot` now records the measured trough FWHM and
> NaN-out the LSF columns when it's below half the predicted scribe
> FWHM at the sweep's M (`SCRIBE_WIDTH_UM × M / sensor_pitch`).
> AF 200/4D task 3 effect: `(+1, 0)` 81 lp/mm outlier (FWHM=12.5,
> predicted 20) → NaN; uniformity_dx 1.41 → 0.92, fx 1.65 → 1.02 —
> corners now correctly read as slightly softer than centre.
>
> **MTF50 method fixed: ESF→LSF differentiation, per-edge averaging.**
> The previous "FFT the whole trough as LSF" reading was
> scribe-width-limited (~11 lp/mm subject across every config tested),
> because wafer scribes are 20-px-wide dark bands, not impulses.
> Replaced with classic slanted-edge mechanics: split the trough at
> its deepest point, treat each side as an ESF, differentiate to an
> LSF, FFT each independently, average MTF50. AF 200/4D 1:1 F11
> centre: 11.1 → 42.7 lp/mm; AIS 287318 centre: 11.9 → 45.1 lp/mm.
> Validation task 1 unchanged (centre maze-FFT amp ratio 1.0412).
>
> **Hough fallback raised scribe-detection rate on the AIS sweeps from
> 43 % → 90 % per-tile.** When LSD's longest dark
> segment falls below the length threshold, `detect_scribe()` now runs
> `skimage.transform.probabilistic_hough_line` on Canny edges, groups
> lines by angle, clusters by perpendicular offset, and spans the
> dominant cluster's endpoints to recover a single long composite line.
> Compute cost: one Hough call (~3 s on a 3456 px ROI) at most once per
> (sweep, tile) — Phase 1 caches scribe detection at the filesize-argmax
> shot, so this is sweep-level overhead, not per-shot. Composite spans
> average 3240 px vs LSD's 690 px — a 4.7× longer cross-section anchor,
> giving more samples for the LSF profile.

## TL;DR

A POC has compared 8 sharpness metrics against the wafer dataset on
four cohorts. The slanted-edge "gold standard" recommendation from
`SHARPNESS_METRICS.md §1` did not survive — `mtfmapper` is unusable
on this rig. `filesize` is more robust than the doc previously
credited it with; `wavelet_ratio` and `dct_kurtosis` (added during
the POC) are the best new cross-frame supplements. Doc updates are
in place. **The one pending human action is an eyeball review of the
cross-lens disagreement crops from the three new cohorts** — see "What's
pending" below.

## Key documents (read in this order)

1. **`analyse-lens-test/SHARPNESS_METRICS.md`** — start at the
   **"Empirical results — POC 2026-05-15"** section near the bottom.
   That's the canonical write-up: cohort summaries, the
   "Recommended setup for cross-lens / cross-frame work" matrix, and
   per-method conclusions. The §1 caveat at the top of the file
   points back to that section.
2. **`analyse-lens-test/tile-sharpness/README.md`** — eight-method
   registry with orientations, per-method caveats, the SSH-to-nufan
   setup for `mtfmapper`, the `compare` / `cross-lens-crops`
   subcommand reference, and a recommended-combinations table.
3. **`analyse-lens-test/CLAUDE.md`** — project conventions index
   (git author email, uv/pytest tooling, analysis style, rig
   semantics, dataset layout, subproject pointers).
4. **`analyse-lens-test/ANALYSIS_NOTES.md`** §2 — bell-curve
   detection thresholds plus the rig-semantics paragraph (off-target
   crops are geometric; reshoot direction is not actionable).
5. **`run-lens-test/DESIGN_NOTES.md`** §6.31 — aperture convention,
   manual-aperture mode mechanics, and the brute-force
   `target_for_next_aperture` solver rationale.

## What's pending

### 1. Manual eyeball review of cross-lens disagreement crops *(partly superseded — see 2026-05-16 update at top)*

**Status as of 2026-05-16**: the disagreement-crops review is *less*
load-bearing now that the path forward is scribe-LSF + maze-FFT subject-
space MTF50 (which makes its own predictions independent of filesize /
wavelet / mtfmapper). The eyeball priorities that remain useful:

* The Sigma 150 + TC-2001 vs AF 200/4D + 5T + 6T comparison at 2:1
  (validated: TC chain looks ~1.8× sharper, matching the metric).
* The 100-400 2:1-resized vs native (to *see* Lanczos halo on
  resampled data — validates "don't measure on resampled").
* Scribes-as-lines confirmation at 400 % zoom on a single die-boundary
  in a 1:1 macro frame.

The original POC-era tasks below are kept for completeness but
deprioritised; only revisit if you specifically want to decide
whether to retain ``radial_fft`` / ``mtfmapper`` as cohort columns.

The three cross-cohort runs produced side-by-side per-method peak
tiles. The numbers say wavelet_ratio and filesize agree closely with
each other and with the consensus on cohorts with wide quality
spreads; they disagree on narrow ones. Whether the methods' picks
*look* sharper to a human is the open question. Three directories,
listed in priority order:

- **`analyse-lens-test/tile-sharpness/out_bare1to1/cross_lens_crops/tile_+0_+0/`** (31 JPEGs, 4 lenses × 8 methods)
  - Concrete pairs to compare:
    - `filesize__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED__shot_029.jpg` (filesize's #1) vs `wavelet_ratio__NIKKOR_Z_MC_105mm_f_2.8_VR_S__shot_040.jpg` (wavelet's #1) — same scene at 1:1, three methods disagree about which lens is sharpest at the centre.
    - `mtfmapper__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM__shot_035.jpg` (mtfmapper's #1) — does Sigma 150 actually deserve mtfmapper's nod?
- **`analyse-lens-test/tile-sharpness/out_resized1to1/cross_lens_crops/tile_+0_+0/`** (49 JPEGs, 6 lens configs)
  - Compare `wavelet_ratio__NIKKOR_Z_MC_105mm_f_2.8_VR_S_+_5T__*.jpg` (consensus best) against `wavelet_ratio__NIKKOR_Z_24-120mm_f_4_S_+_Raynox_M-150__*.jpg` (consensus worst). Visual gap should be obvious — that's the sanity check.
  - Compare `radial_fft__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED_+_5T__*.jpg` (rank 1 by radial_fft) against `filesize__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED_+_5T__*.jpg` (rank 4 by filesize) — same lens, 3-rank disagreement. Who's right?
- **`analyse-lens-test/tile-sharpness/out_55mm/cross_lens_crops/tile_+0_+0/`** (40 JPEGs, 5 sweeps × 8 methods)
  - The two AIS copies (s/n 287318 vs 537016) should look near-identical at `filesize__*.jpg` — if they don't, one is decentered.
  - The three Auto copies (209088 vs 258263 vs 262711) — `258263` ranks consistently better by mean-rank-across-tiles; does its centre tile actually look sharper or is it framed differently?
  - **Filesize artefact worth seeing**: at the centre tile, filesize picks Auto 209088 first (peak 318k bytes), but across all 35 tiles the AIS copies win. That's filesize being content-fooled at one position. Open `filesize__Nikon_Micro-Nikkor_Auto_55mm_f_3.5_209088__shot_030.jpg` and compare to either AIS centre crop.

Each tile dir also has a `README.txt` listing every method's pick
with peak metric value and shot index.

Also worth looking at the off-axis dirs in each cohort if the centre
read is ambiguous: `tile_+3_+0`, `tile_-3_+0`, `tile_+0_+2`,
`tile_+0_-2`.

### 2. Decide whether to drop methods from the registry

- **`mtfmapper`** scored 1/5 on the earlier within-sweep eyeball
  review (the Raynox M-250 sweep, results in `SHARPNESS_METRICS.md`
  empirical section). On the resized cohort it can't discriminate
  at all (all six lenses rank ~3.3). Its CV across same-model copies
  is 0.54, 3-25× the next-worst method.
  - **Open question**: would it perform better on a sweep that has
    clear isolated slanted-edge targets (a real chart card, or
    higher-magnification crops where individual bond pads are
    isolated dark blobs)? The default component-finder needs that
    input shape; `--single-roi` is a fallback. Try once on a chart
    card before deciding to drop the method entirely.
- **`edge_decay`** peak quantises to integer pixels and produces
  ties; useful only for *argmax* (which rail step within a sweep).
  Recommended action: keep it but exclude its `peak_value` from
  cross-tile / cross-lens ranking; let the cross_lens routines
  filter to argmax-only for this method.
- **`radial_fft`** argmax is unreliable (picks heavily-defocused
  end-of-sweep shots due to near-Nyquist noise). Its peak ranking
  is fine. Recommended action: same as `edge_decay` — keep `peak`,
  drop `argmax` from cross-method consumers.

### 3. Integration into rail-coverage?

The empirical section's "Recommended setup" matrix is the candidate
for codifying. The simplest move would be to add
`wavelet_ratio` as a second column alongside the existing
file-size proxy in `analyse-lens-test/rail-coverage/`, and flag
scenarios where filesize and wavelet_ratio rank a lens / scenario
more than ~2 ranks apart. The eyeball review (TODO 1) gates this —
don't integrate until visual confirmation lands.

### 4. Cross-M comparison guardrails (Nyquist-fraction column)

Even after the low-M LSF fix lands, lp/mm-subject readings at low M
are bounded by **sensor-Nyquist**, not by lens quality. On Z7 the
sensor Nyquist in subject space is `0.5 cy/px × 1000 / 4.35 × M =
115 × M lp/mm`. So at M=0.4 the ceiling is **46 lp/mm subject** no
matter how good the lens — a config reading near that cap is
sensor-bounded (pixel-limited regime), not optics-bounded, and
"lens A is sharper than lens B" comparisons between two
near-Nyquist configs are degenerate.

Action: add `nyquist_fraction = mtf50_sensor_cy_per_px / 0.5` as a
column in `peaks_v2.csv` and `lens_characteristics.csv`. Then a
config reading `0.4×: 25 lp/mm (54 % of Nyquist)` is clearly
optics-limited and ready to compare against a `1.0×: 35 lp/mm
(30 % of Nyquist)`; a `0.4×: 44 lp/mm (96 %)` flags
"sensor-bounded — comparison degenerate at this end".

Cross-M range the rule of thumb covers:
- **M=0.4 to M=1.0**: clean comparison in lp/mm-subject as long as
  both sides stay under ~80 % of Nyquist. The Nyquist-fraction
  column makes the regime visible.
- **M=0.1 to M=2.0**: the original plan's `A_n/A_1` harmonic-ratio
  MTF readout (from the maze 2D-FFT at high M and from a pad-grid
  2D-FFT at low M — see TODO 5 below) is what would close this
  span. Not yet implemented.

### 5. Low-M LSF under-read — POC track (Fix #2)

Task 2 (100-400 at 0.385× F11) reads 10.4 lp/mm subject vs plan
target ~33 — algorithmic limit: the scribe is 7.7 px FWHM at M=0.385
and the ESF→LSF split puts ~4 samples per edge. Two parallel POCs
launched 2026-05-17, both uncommitted under
`tile-sharpness/scripts/poc_*.py`:

- **A — slanted-edge sub-pixel binning of grid pixels.** Classic
  ISO 12233: bin grid pixels by sub-pixel perpendicular distance
  to the detected scribe; super-resolved ESF; real bandwidth gain.
  Direct fix for the LSF tail; preserves the cross-M lp/mm-subject
  axis at low M.
- **B — pad-grid 2D-FFT at an intermediate wafer pitch.** Mirrors
  the maze-FFT method one scale up (pad pitch ~100-200 µm,
  resolves at M ≥ 0.3 on Z7). Same harmonic-amplitude approach the
  maze method uses; extends the "primary high-resolution
  discriminator" framing down into the low-M regime.

**Concerns about B to verify in the POC writeup**:
1. Not every wafer tile contains pads — pad coverage is region-
   dependent (test-pattern blocks vs in-die structures). Need to
   characterise coverage on the actual Z7 frames before relying
   on this as a primary metric.
2. Bond pads are *metalised* — specular highlights at certain
   light angles. Lighting variation across the test rig (and
   across the wafer's micro-tilt) could change pad amplitude
   independently of lens sharpness. The agent should sanity-check
   pad-FFT amplitude stability across nominally-identical shots
   if possible.

If A works it's the simpler land. B is the bigger architectural
move — it would also feed the eventual `A_n/A_1` MTF readout that
extends the cross-M comparison up to M=2.0.

**2026-05-18 update — atlas approach lands a third option, C:**

POCs A and B both ran but each had limitations:
- A (subpixel binning, `scripts/poc_subpixel_binning.py`): lifts
  Task 2 from 10.4 → 20.5 lp/mm subject (~2× gain) but still below
  the ~33 target. LSD/Hough endpoint bias produces L/R-asymmetric
  ESFs; Task 3 over-reads 1.5× (65.8 vs cached 42.7 lp/mm).
- B (pad-grid FFT, `scripts/poc_pad_grid_fft.py`): pitch discovery
  via 2D FFT finds 18.4 µm pad fundamental. Argmax slipped by 18
  shots from LSF reference but the LSF argmax shot is within 0.5-
  3.3 % of pad-FFT max — viable as a peak-value cross-lens signal
  at low M, not a drop-in argmax picker.
- C (atlas-anchored 4D-bar slanted-edge, `wafer-atlas/scripts/
  task15_*.py`): runs the existing `methods/lsf.cross_section +
  lsf_mtf50` on the wafer's 4D vertical bar via atlas-anchored
  position. **Argmax shot 136 vs LSF reference shot 137 on Task 2
  (gap −1)**, same on Task 4 (gap −1). MTF50 magnitude is lower
  (14.75 vs A's 20.5 lp/mm) because the 4D bar's intrinsic optical
  geometry is what's measured, but per-shot focus discrimination
  is excellent. Production-track candidate.

### 6. Retry scribe-line / scale detection with corrected super-cell grid

Earlier attempts at fitting a uniform die grid for scribe / scale
detection (in `archive-2026-05/measure_wafer_squares` or precursors)
were rejected because they didn't work well. The wafer-atlas work on
2026-05-18 found out **why**: the wafer's die grid is a 4×4 super-cell
with one wide column type (~542 px) and one tall row type (~546 px) on
the f/8 overview photo, while the other types are ~452 px. A uniform-
pitch fit will be off by up to ~20 % on any individual die boundary,
so the residuals would have looked like a failed fit.

**Action when revisiting:** use the super-cell parameters from
`wafer-atlas/scripts/grid_supercell.py` — per-(col mod 4) widths and
per-(row mod 4) heights — and refit with that model. Also: any
"distance across N dies" magnification measurement must span an
integer number of super-cells (N = 4, 8, 12…) OR record exactly which
(col mod 4) positions are included.

### 7. mtf_mapper available only on nufan

The local Arch host had its `mtf_mapper` binary deleted during a
failed rebuild attempt earlier in this session, and `cmake` isn't
installed locally so a rebuild is blocked. The rebuilt binary now
lives on nufan (Ubuntu 25.10, OpenCV 4.10) at the in-tree workspace
path — same shared-mount path as before, so callers don't change.
The `score_mtfmapper` scorer in `methods.py` routes via SSH with a
`ControlMaster` to keep one connection warm. To get `mtf_mapper`
working locally again, install `cmake` and rebuild the same way (see
`tile-sharpness/README.md` "SSH setup" for the apt package list and
build steps).

## Repository state

`analyse-lens-test/` repo, recent commits (tile-sharpness only):

```
3d3c31c tile-sharpness: M-aware trough-FWHM filter for non-scribe rejection
17a8d6a tile-sharpness: ESF→LSF MTF50 fixes scribe-width-limited reading
7cfd5dd tile-sharpness: Hough fallback for scribe detection (43 % → 90 %)
9097def tile-sharpness: implement LSF + maze-FFT pipeline (Phases 1-3)
8fecab0 docs: 2026-05-16 methodology supersession + LSF/maze-FFT plan
f869d78 sharpness POC empirical findings + project-conventions doc
cdf1c67 tile-sharpness POC + long-distance metrics doc
```

`lens-test-detect-core/` repo: clean, last commit `75cdc54`. (The
local box now has `/home/alson/shared/projects/personal/fotografie/lens-test-detect-core`
on the git `safe.directory` allowlist; you'll need to do the same
on nufan if you haven't already — same command.)

`run-lens-test/` repo: untouched in this session.

## How to resume

The cohort runs are cached. Tile JPEGs live at
`~/shared/projects/personal/fotografie/.tile-sharpness-cache/` on the
shared mount, so nufan sees the same cache. A re-run of any of the
three cohorts is near-instant for the cropping and ~20-30 min for
mtfmapper-via-SSH plus the four other scoring methods.

```sh
cd analyse-lens-test/tile-sharpness

# List candidate sweeps:
uv run tile-sharpness list-sweeps

# Re-run a cohort (uses cached tiles, re-scores):
uv run tile-sharpness analyse <substring-of-label> ... --out out_<name>/

# Cross-cohort aggregation + crop export:
uv run tile-sharpness compare out_<name>/peaks.csv
uv run tile-sharpness cross-lens-crops out_<name>/peaks.csv \
    --out out_<name>/cross_lens_crops \
    --tile 0,0 --tile -3,0 --tile 3,0 --tile 0,-2 --tile 0,2

# All three driven from one place:
./scripts/finalize_cohorts.sh                          # compare + crops
uv run python scripts/cross_cohort_summary.py          # mean-rank tables + CV
```

The 2026-05-16 LSF + maze-FFT pipeline runs via the same `analyse`
subcommand, with two new flags + a follow-up subcommand:

```sh
# Run Phase 1 + Phase 2 only (per_shot_per_tile.csv + peaks_v2.csv).
# --manifest is repeatable; --no-legacy skips the 8-method pass.
uv run tile-sharpness analyse <sweep> [<sweep>...] \
    --out out_<name>/ \
    --manifest /path/to/wafer-manifest-2026-01-29.csv \
    --no-legacy

# Phase 3 rollup: per-slug centre/DX/FX MTF50 + uniformity +
# peak-value decentering + plane-fit tilt + curvature.
uv run tile-sharpness characterise out_<name>/peaks_v2.csv
# → writes out_<name>/lens_characteristics.csv
```

The new pipeline needs `archive-2026-05/measure_wafer_squares` output
to resolve M per sweep (drives ROI sizing + subject-MTF50 conversion);
falls back to path-parsed `claimed_mag` per sweep if no manifest row
matches, with `m_source = "path_parsed"` flagged in the CSV.

The three cohorts that produced the current findings:

```sh
# Bare native macros at 1:1, F8 (4 lenses, same scene)
uv run tile-sharpness analyse \
    "2026-01-29__NIKKOR_Z_MC_105mm_f_2.8_VR_S__1_1__F8" \
    "2026-01-29__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED__1_1__F8" \
    "2026-01-29__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM__1_1__F8" \
    "2026-01-29__Sigma_Macro_105mm_F2.8_EX_DG_OS_HSM__1_1__F8" \
    --out out_bare1to1 --workers 8

# Resized 1:1 cross-config (6 mixed configs)
uv run tile-sharpness analyse \
    "2026-01-29__NIKKOR_Z_MC_105mm_f_2.8_VR_S_+_5T__1_1-resized__F8" \
    "2026-01-29__Nikon_AF_Micro-Nikkor_200mm_f_4D_IF-ED_+_5T__1_1-resized__F8" \
    "2026-01-29__Sigma_APO_Macro_150mm_F2.8_EX_DG_OS_HSM_+_5T__1_1-resized__F8" \
    "2026-01-29__Nikon_AF_Zoom-Micro_Nikkor_70-180mm_f_4.5-5.6D_ED_+_5T__1_1-resized__F8" \
    "2026-01-29__NIKKOR_Z_100-400mm_f_4.5-5.6_VR_S_+_Nikon_5T__1_1-resized__F8" \
    "2026-02-18__NIKKOR_Z_24-120mm_f_4_S_+_Raynox_M-150__1_1-resized__120.0_mm__F8" \
    --out out_resized1to1 --workers 8

# Multi-copy 55mm primes (2× AIS + 3× Auto)
uv run tile-sharpness analyse \
    "2026-01-29__Nikon_Micro-Nikkor_55mm_f_2.8_AIS_287318__1_1__F8" \
    "2026-01-29__Nikon_Micro-Nikkor_55mm_f_2.8_AIS_537016__1_1__F8" \
    "2026-01-29__Nikon_Micro-Nikkor_Auto_55mm_f_3.5_209088__1_1__F8" \
    "2026-01-29__Nikon_Micro-Nikkor_Auto_55mm_f_3.5_258263__1_1__F8" \
    "2026-01-29__Nikon_Micro-Nikkor_Auto_55mm_f_3.5_262711__1_1__F8" \
    --out out_55mm --workers 8
```

All three are committed under `out_*` glob in `.gitignore` so the
generated trees stay out of git. The peaks.csv / agreement.csv /
disagreement directory layout is documented in
`tile-sharpness/README.md`.

## What changed in this session, in one paragraph

POC validated. Four new methods added to the registry
(`laplacian_var`, `tenengrad`, `dct_kurtosis`, `wavelet_ratio`).
Sweep discovery extended to handle bare-prime 3-level layouts and
`*-resized` cohort directories. `compare` and `cross-lens-crops`
CLI subcommands added for cross-sweep aggregation. `mtf_mapper`
moved from local to nufan over SSH (ControlMaster-multiplexed); tile
cache moved from `~/.cache` to the shared mount so nufan reads
tiles by path. Docs updated to reflect empirical findings; memory
files reduced to pointers since the canonical content now lives in
the shared docs. Three cross-lens cohorts run (bare 1:1, resized
1:1, multi-copy 55mm) but the manual eyeball verification step has
not been done yet.
