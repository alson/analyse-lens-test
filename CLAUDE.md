# Project conventions — fotografie

Cross-cutting notes that aren't naturally scoped to a single subproject's
own README / DESIGN_NOTES. Subproject-specific facts live in their own
docs and are linked from here.

## Compute hosts

- **Run CPU-bound jobs on ``nufan`` (16 cores), not the local box.** Repos
  live on an NFS share mounted at the same path on both hosts, so edit
  locally and run remotely with no syncing. Non-interactive ssh needs a
  login shell + manual direnv (``ssh nufan 'bash -lc "cd … && direnv exec
  . uv run …"'``); per-host venvs via ``.envrc``. Full details — share
  layout, what's *not* on the share, gotchas — in ``COMPUTE.md``.

## Git

- **Commit author email**: ``git@alm.nufan.net`` for every commit in
  this tree. Both this machine and ``nufan`` already have this set as
  the global default (``~/.gitconfig`` here, ``~/.config/git/config``
  on nufan) and no env vars override it, so plain ``git commit`` is
  fine — no per-command ``-c user.email=…`` needed. Only override if
  you see a different identity in ``git log`` (e.g., if a work-machine
  config sync changes the global default in the future).

## Python tooling

- **Dependency / venv management is uv.** Every Python subproject is a
  uv package — ``uv init`` to scaffold, ``uv add`` for deps,
  ``uv sync`` to install, ``uv run`` to invoke. No pip+venv, no poetry,
  no conda.
- **External libs are welcome for analysis tooling.** NumPy, SciPy,
  scikit-image, matplotlib, Seaborn, pandas, pywavelets etc. are fine
  to add via ``pyproject.toml``. Generated HTML reports may reference
  external CSS/JS; ship those assets in a folder alongside the HTML.
  Don't preemptively constrain to stdlib.
- **Pytest + unittest.mock**, no other mocking libs. Structure code so
  the core logic is pure functions / small classes that don't touch
  the filesystem, time, or subprocesses directly — push I/O to thin
  edge modules and mock those at the seams. ``pytest`` as a dev dep
  (``uv add --dev pytest``); ``tests/`` co-located at package root;
  each module gets a corresponding ``test_<module>.py``.

## Analysis / reporting style

- **Lead with caveats and assumptions, not the verdict.** State analysis
  conclusions — especially negative/closure ones ("not viable", "this is
  closed") — as *"negative under [conditions tested]; not yet tested:
  [assumptions / coverage gaps]"*, never as "final" with the caveats
  buried. The assumptions are the headline. Rationale + the four-round
  cross-M-sharpness case study (where "final" was wrong four times, each
  for a different buried assumption) in ``LEADING_WITH_CAVEATS.md``.

- **Aggregate across the sweep before surfacing output.** For any
  N-methods-by-M-inputs analysis, compute the cross-input aggregate
  (peak, argmax, median…) per method first, then compare on the
  aggregates and surface a small *curated* artefact for human
  inspection (e.g. side-by-side crops at the top-K disagreement tile
  positions). Default output size should be ``O(methods ×
  interesting-positions)``, not ``O(methods × inputs × tiles)``.
  Validated in the ``tile-sharpness/`` POC — see that subproject's
  README for the concrete shape this takes.

- **Cross-config sharpness is subject-space MTF50, not resampled
  pixels.** For "which lens / accessory gives more useful resolution"
  comparisons across configurations with different magnifications,
  compute ``MTF50_subject_lp_per_mm = MTF50_sensor_cy_per_px × M ×
  229.9`` (Z7 pitch factor). Resampled cohorts (``1_1-resized``,
  ``2_1-resized``) are for *visual* human comparison only —
  Lanczos overshoot contaminates them by ~20 % at large scale-up
  factors, biasing any metric computed on them. Operate on native
  frames for measurement.

- **Sharpness pipeline depends on measured magnification.** The
  per-config M from ``archive-2026-05/measure_wafer_squares`` is
  now a load-bearing input to sharpness analysis (drives per-metric
  ROI sizing + subject-space conversion). Step 2 of the archive
  pipeline is no longer just folder-labelling; sharpness can't run
  without it.

- **Aperture folder names are EFFECTIVE (bellows-corrected) — never
  re-apply the bellows factor.** For any working-f computation (DoF,
  diffraction, defocus, step-size), resolve N_working by priority:
  (1) ``effective_f_exact`` from the in-tree ``effective_apertures.csv``
  (roots ``test-raw-data/2026-{01-29,02-18,05-13}/``; load via
  ``rail_calibration.EffectiveApertureLookup.from_csvs``) — it's
  *photometric* (``sqrt`` of the brightness ratio), so it's independent
  of DoF and safe as a DoF-model input; (2) else the directory-name
  aperture **used directly** (it is already effective — AF/IF macros
  report effective aperture in EXIF; manual extension-only lenses like
  the 55mm carry published/analytical f_eff baked into the folder name;
  sanity-check widest-native-folder ≈ spec-max·(1+M)); (3) never the
  analytical ``N·(1+M/p)`` formula (needs the unpublished focal length
  at MFD + pupil magnification, unreliable for IF lenses) — drop the
  config instead. Details in ``bellows-calibration/`` (README + FINDINGS)
  and ``tile-sharpness/HANDOVER.md`` (2026-07-01).

- **Filesize is a degenerate fallback only, not a primary sharpness
  proxy.** ``filesize`` argmax saturates at sharp configs (visually
  confirmed: at AIS 55mm 1:1 F8 it under-reports the centre-tile
  sharpness by 2× through pure focus mis-pick). Scribe-LSF works
  universally and doesn't saturate; maze-FFT is even more sensitive
  where M ≥ ~0.7×. Filesize is kept only for off-target tiles where
  neither scribe nor maze have anything to measure — and those tiles
  shouldn't drive argmax decisions anyway. See ``SHARPNESS_METRICS.md``
  "2026-05-16 update" for the full picture.

## Lens-test rig semantics

These apply to ``run-lens-test/``, ``rail-coverage/``,
``tile-sharpness/``, and the wafer dataset under
``~/shared/files/pics/digikam/test-raw-data/`` and
``~/macro-lens-test-output/``.

- **Off-target crops are geometric, not faults to fix.** When the
  silicon wafer target doesn't fully cover the sensor frame at a given
  lens config (typically lower magnifications or wider focal
  lengths), some of the 9/17 crop windows fall outside the wafer and
  capture only out-of-focus background. This is *inherent* to the
  lens config — the user can't fix it by reshooting. Off-target crops
  should be **excluded** from sharpness-peak analysis (their flat
  file-size profile has no real peak), but should **not** appear on a
  reshoot list.
- **Reshoot direction is not actionable.** The user cannot reproduce
  the exact subject-distance range of a previous run. Reshoot
  recommendations should say "this scenario needs to be re-shot" and
  nothing more — don't report which way the rail needs to extend
  (start-side vs. end-side) or "shots short" estimates. Just list
  scenarios + a representative chart so the user can visually confirm.

## Subproject pointers

- ``run-lens-test/`` — capture pipeline (Z7 tethered + StackShot + SB-5000).
  - ``macro_lens_test_plan.md`` — overall design, including §14 manual-aperture mode.
  - ``DESIGN_NOTES.md`` — decisions log, including §6.31 manual-aperture rationale and the brute-force ``target_for_next_aperture`` solver (resolved 2026-05-12 cascade f/8 over-shoot bug).
  - ``INTEGRATION_TESTING.md`` — end-to-end rig checks.
- ``lens-test-detect-core/`` — shared NumPy primitives for bell-curve
  / off-target / partial-frame detection used by both the live runner
  and offline analysis tools.
- ``analyse-lens-test/`` — offline tooling.
  - ``SHARPNESS_METRICS.md`` — sharpness-proxy options. **Read the
    "Empirical results — POC 2026-05-15" section near the bottom
    before believing the §1 "gold standard" claim** — empirical
    findings overturned it for the wafer dataset.
  - ``rail-coverage/`` — focus-coverage analyser over a pre-cropped JPEG tree.
  - ``resize-bulk/`` — lossless TurboJPEG crop tooling; resampler comparison docs.
  - ``tile-sharpness/`` — POC validating 8 sharpness metrics on a
    tile grid; documents cross-lens / cross-config behaviour. As of
    2026-05-17 also hosts the LSF + maze-FFT pipeline (``phase1.py``,
    ``characterise.py``) and the through-focus rail-step-mm
    calibration (``rail_calibration.py``, v1 per-sweep + v2
    multi-aperture pooling) used to unlock subject-tilt + field-
    curvature in real units for older datasets. **Macro-rig / wafer
    work only.**
  - ``longdist-sharpness/`` — long-distance natural-target lens-test
    analysis (telephoto / wide-angle / standard primes at infinity-
    class distances). Z7 and D7200 datasets 2025-07 through 2026-02.
    Distinct from ``tile-sharpness/`` which is for the macro-rig
    wafer setup. Start with ``longdist-sharpness/docs/LONGDIST_HANDOVER.md``.

## Aperture convention (data joins)

The ``aperture`` column in ``shots.csv`` and folder name under
``<lens_dir>/F<aperture>/`` is **lens-internal effective**:
``f_ring × (1 + m_indicated)`` rounded to 1/3 stop, matching the EXIF
behaviour for CPU macro lenses. *External-tube* bellows contribution
is **never** in the label — that's analysis-time, derivable from
``magnification_indicated``, ``f_ring``, and ``magnification``
(= m_total), all of which are recorded in per-lens-config metadata.

Old data is inconsistent and needs a downstream re-bump when joining:

- **2026-01 / 2026-02 CPU lens data** uses lens-internal effective
  (EXIF) — fine, no adjustment.
- **2026-01 / 2026-02 MF lens data** was script-bumped to *total*
  effective (folder ``F11`` on PK-13 at 1:1 = ring f/5.6 × 2, not
  lens-internal). Joining with 2026-05+ data requires a one-time
  re-bump on the old MF data, applied uniformly.

Bellows formula (verified against the Nikon Micro-Nikkor 55mm f/2.8
AIS instruction-manual exposure-factor table at R=0.5):
``f_eff = f_ring × (1 + R)`` where R is the reproduction ratio.
Assumes pupil magnification ≈ 1, which holds for the lenses tested;
residual deviations at smaller apertures or asymmetric designs are
why the manual-aperture flash-power cascade uses a tight tolerance
(``MANUAL_FLASH_TOLERANCE_EV = 0.2``) and a brute-force (power, ISO)
search rather than a closed-form solver.

Full mechanics: ``run-lens-test/macro_lens_test_plan.md §14`` and
``run-lens-test/DESIGN_NOTES.md §6.31``.

## Datasets

- ``~/macro-lens-test-output/<session>/`` — newer rig output (FINE
  JPEG quality). ``shots.csv`` per session with explicit
  ``rail_step``, ``rail_position_mm``, ``aperture``, ``phase``.
- ``~/shared/files/pics/digikam/test-raw-data/{2026-01-29, 2026-02-18}/`` —
  older manual sweeps. NEFs at the date-root level; JPEGs (slightly
  lower quality than current FINE) organised under
  ``<lens-config>/<mag>/[<focal>/]<aperture>/seq|lens|mag|focal|aperture|datetime.jpg``.
  Bare-prime lenses use the 3-level layout (no focal subdir); zooms
  use the 4-level layout. ``-resized`` magnification subdirs (e.g.
  ``1_1-resized``) contain copies upsampled to a common framing for
  cross-config comparison.

Absolute metric values are **not comparable across the two dataset
families** (different JPEG quality settings); per-sweep peak / argmax
comparisons and within-cohort cross-lens rankings remain valid.
