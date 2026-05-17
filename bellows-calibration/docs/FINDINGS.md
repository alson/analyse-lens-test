# Bellows-factor findings (2026-05-17 validation)

## TL;DR

The camera-reported f-number on Z-mount lenses
**does not include** the bellows contribution from external
extension tubes. Cross-config comparisons of the existing
2026-01-29, 2026-02-18, and 2026-05-13 lens-test trees by reported
aperture mix different effective f-numbers. The 24-120 + 61mm
extension at 400mm with the 100-400 reaches effective f/12 when
indicated as f/5.6 — significant for diffraction-aware analysis.

## Per-lens behaviour

### Z 24-120 f/4 S (IF non-macro)

* **Bare lens, native MFD, infinity-vs-MFD**: mean ΔEV across 7
  focal lengths in the 1/4000 s cloud series = **+0.02 EV** (within
  scene noise). The lens fully compensates its own MFD bellows
  across the entire 24-120 mm zoom range. **Reported f-number =
  effective f-number for bare lens at any native focus distance.**
* **With extension tube on**: empirical bellows grows monotonically
  with `L_tube/F` but slightly exceeds the simple `1 + L_tube/F`
  thin-lens prediction at high `L/F`. At 120 mm the formula
  understates by 0.05-0.42 EV (small tubes to 61 mm stack); at 70
  and 50 mm the formula *over*states by 0.10-0.50 EV.

  This is the opposite-direction discrepancy at different focal
  lengths and likely reflects the lens's design: it has near-zero
  hidden bellows at bare MFD, but its internal compensation
  doesn't extend to the tube + close-focus regime in a uniform
  way across the zoom range. **Use the empirical multipliers, not
  the formula, for the rename.**

### Z MC 105 f/2.8 S / VR S (IF macro)

* The lens reports a bellows-corrected aperture at MFD (f/2.8 →
  f/4.5 at 1:1). Bare-MFD reported f/4.5 is already the effective
  f-number at native 1:1 — no further hidden bellows at the bare
  configuration.
* With extension tube on top, the empirical bellows is
  monotonically larger than `1 + L_tube/F_inf=105` predicts, by
  +0.05 EV at small tubes growing to +0.35 EV at the 61 mm stack.
* This means the lens's own internal compensation handles its
  native MFD bellows but doesn't extend to additional external
  extension. Past native 1:1 the tube's contribution behaves
  closer to thin-lens than fully-compensated.
* All seven stack combinations (10, 16, 26, 35, 45, 51, 61 mm)
  were tested. One combination (+35 mm) was replicated
  immediately for a tightness check (same setting, Y differs by
  −0.01 EV).

### Z 100-400 f/4.5-5.6 VR S (IF non-macro)

* **Bare 400 mm @ MFD vs @ infinity**: ΔEV = **+0.13 EV**. The lens
  hides most but not all of its MFD bellows — at the native
  hard-stop close-focus position there's a ~1/8 stop residual that
  isn't reflected in the reported f/5.6.
* **With extension tube**: the lens essentially behaves
  **thin-lens-equivalent**. The tube's full geometric bellows is
  visible, with no further internal compensation:
  - +35 mm @ 400 mm: ΔEV vs bare-INF = +0.83 (formula predicts
    +0.24, lens compensates 0 EV of tube bellows on top)
  - +61 mm @ 400 mm: ΔEV vs bare-INF = +1.34 (formula predicts
    +0.41 — the empirical is closer to thin-lens m_total = 0.53,
    ΔEV = 1.22 EV)
* The 200 mm setup shows the same pattern at lower magnitude.

### Viltrox AF 85 f/2 Z (non-IF non-macro)

* Bare-MFD vs bare-INF: ΔEV = **+0.20 EV** (some hidden bellows
  at MFD).
* With tube: empirical bellows substantially exceeds `1 + L/F`
  prediction at all tube lengths (off by 0.24-0.66 EV at +26/+35
  /+45/+61 stacks). The Viltrox seems to allow focus past native
  MFD when a tube is attached, gaining additional m beyond the
  thin-lens prediction.
* All four tube settings (26, 35, 45, 61 mm) tested — confirmed
  by user.

## Summary of empirical effective-f-numbers

See `data/per_config.csv` for the complete table including
effective-f at each reported aperture (F2.0, F2.8, F4, F4.5,
F5.6, F8, F11, F16) for each (lens, focal, tube) combination.

Quick reference for the most-affected configs at widest aperture:

| Lens | focal | tube | reported widest | empirical effective |
|---|---:|---:|---:|---:|
| Z 24-120 | 120 | 61 | f/4 | **f/7.0** |
| Z MC 105 | 105 | 61 | f/4.5 | **f/8.7** |
| Z 100-400 | 400 | 35 | f/5.6 | **f/8.4** |
| Z 100-400 | 400 | 61 | f/5.6 | **f/11.9** |
| Viltrox 85 | 85 | 61 | f/2 | **f/6.8** |

For comparison, at reported F11 (a common test aperture):

| Lens | focal | tube | empirical effective |
|---|---:|---:|---:|
| Z 24-120 | 120 | 61 | **F19.2** |
| Z MC 105 | 105 | 61 | **F21.3** |
| Z 100-400 | 400 | 61 | **F23.4** |
| Viltrox 85 | 85 | 61 | **F37.3** (heavy diffraction on Z7) |

## Validation against existing assumptions

* The earlier-memorised `F_eff = 49 mm` for the Z MC 105 at 1:1
  (from photomacrography.net) **does not match** the empirical
  ΔEV. Using F_eff = 49 mm in `1 + L/F_eff` overpredicts the
  bellows; the simple `1 + L/F_inf = 105 mm` underpredicts by
  ~0.05-0.35 EV. Neither closed-form formula is right; the
  empirical multipliers are the ground truth.
* The earlier-memorised "Z 24-120 has 3% breathing, F_eff ≈ 120
  at MFD" appears consistent with the bare-MFD ΔEV ≈ 0
  measurement. The lens *behaves* with low breathing for
  metering purposes (whether by actual constant F or by aperture-
  diaphragm widening, we can't distinguish from this experiment).
* The fec_bellows_compensation memory's "calibrator lands on
  ~+1 EV for extension tubes" is consistent with our 24-120 +
  35 mm at 120 mm bellows of +0.94 EV (within 0.06 EV).

## Caveats

* Empirical multipliers are calibration coefficients for this
  rig (camera + flash bounce + MFD-style focus). They are not
  pure optical first-principles values.
* Brightness was measured on JPGs (raw NEFs wiped with the card).
  D-Lighting / picture-control effects are baked in but apply
  identically to bare and tube shots within a continuous block,
  so they cancel from the ratio.
* "Effective f-number" here means the relative light-loss
  ratio. For computing diffraction limits this is the correct
  value to use (diffraction depends on the actual transmitted
  cone angle, which the brightness ratio reflects). For other
  contexts (e.g. exposure-bracket arithmetic that's already
  using EXIF f-number) the bellows correction may double-count
  if the camera does its own internal aperture compensation.
  The Z 24-120's near-zero bare bellows suggests internal
  aperture compensation; the 100-400's +0.13 EV suggests
  imperfect compensation; the MC 105's f/4.5-at-1:1 reporting
  is honest reporting of the internal bellows.

## Reference choice: bare-MFD vs bare-INF

For each lens block we have both bare-MFD and bare-INF brightness
measurements. The bellows multiplier in `per_config.csv` is
`sqrt(Y_ref / Y_with_tube)`, where `Y_ref` is:

| Lens / focal | Y_ref | Why |
|---|---|---|
| Z 100-400 @ 400 mm | bare-INF | Empirical bare-MFD-vs-INF = +0.13 EV — real, above noise floor |
| Viltrox 85 @ 85 mm | bare-INF | Empirical bare-MFD-vs-INF = +0.20 EV — real |
| Everything else | bare-MFD | Empirical inf-vs-MFD is within ±0.08 EV scene noise; using bare-INF would inject spurious corrections |

Tagged in `per_config.csv` via the `reference_kind` column. The
two real corrections (100-400 @ 400 mm and Viltrox @ 85 mm) fold
the hidden bare-MFD bellows into the multiplier; for these,
`effective_f = reported_f × multiplier` is the *absolute* effective
f-number (vs. infinity-focus reference).

For the other lens blocks where bare-MFD is the reference, the
multiplier is "tube bellows on top of bare-MFD state" — which is
nearly identical to absolute for IF macros / non-IF lenses where
the camera-reported f-number is already honest at MFD.

## Source data

* `data/per_shot.csv` — every validation JPG's EXIF + linear-
  light center brightness at 5 crop sizes.
* `data/tube_assignments.csv` — manual mapping of group
  → tube length, with the section labels matching the order of
  shoot.
* `data/per_config.csv` — auto-generated bellows multipliers and
  effective-f tables per (lens, focal, tube).
* `data/rename_plan_2026-{01-29,02-18,05-13}.csv` — F-dir rename
  mappings (canonical, generated against the original tree state).
* `data/rename_plan_2026-{02-18,05-13}_v1.csv` — historical first-
  generation plans archived for provenance. Differ from canonical
  only in the 100-400 + ext and Viltrox + ext rows (post-correction).
* `data/delta_plan_2026-05-13.csv` — the (applied → corrected)
  delta rename applied as a follow-up pass. Records how the
  100-400 + ext and Viltrox + ext F-dirs got re-renamed after the
  bare-MFD correction.
* `data/rename_manifest_*.csv` — operation log per F-dir, written
  by `apply_rename_plan.py` at execute time.

## In-tree outputs

Each test-raw-data subtree (2026-01-29, 2026-02-18, 2026-05-13)
gets two artefacts written to its root:

* `.bellows-rename-applied.csv` — idempotency marker; re-running
  the rename script classifies already-applied rows as `already_done`.
* `effective_apertures.csv` — canonical lookup of every F-dir's
  *exact* effective f-number (un-snapped). Downstream code (step
  size, diffraction limits) should consult this rather than
  re-interpret the snapped F-dir name. The F-dir name is just the
  rounded half-stop label.

See `docs/PROCEDURE.md` for the shoot methodology and
`scripts/` for the analysis pipeline.
