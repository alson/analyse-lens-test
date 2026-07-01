# POC 1 — Focus-coverage awareness

**Date:** 2026-07-01  **Cohort:** 2026-01-29 (10 configs, 1:1, F8)
**Compute:** all heavy work on **nufan** (16-core) over SSH; nothing committed.

## What this adds

The P2 through-focus estimator fits a Gaussian to each patch's Laplacian-variance
vs frame-index curve, giving a sub-frame FWHM **and** a peak centre `mu` (in frames).
`mu` was previously discarded. A focus stack is a sequence of shots at increasing
rail positions; if a patch's best-focus peak sits at/beyond the first or last
captured frame, the FWHM and the "best focus" position are unreliable (the true peak
is outside the captured range). POC-1 surfaces this.

### New per-patch columns (psffoc extract output)

| column | meaning |
|---|---|
| `mu` | fitted Gaussian peak centre, frames |
| `peak_pos_frac` | `mu / (nstack-1)` — 0 = first frame, 1 = last frame |
| `edge_dist_frames` | `min(mu, (nstack-1) - mu)` — frames from `mu` to nearest stack edge |
| `coverage_flag` | `ok` / `truncated_low` / `truncated_high` / `fwhm_truncated` |

### The coverage rule (`coverage_flag(mu, fwhm, nstack, margin=1.0)`)

Valid frame indices span `[0, nstack-1]`; `HWHM = fwhm/2`; `margin = 1` frame floor.
Evaluated in priority order:

1. **`truncated_low`** — `mu <= margin`: peak at/below the first frames → true best
   focus is at/before the start of the captured range.
2. **`truncated_high`** — `mu >= (nstack-1) - margin`: peak at/beyond the last frames.
3. **`fwhm_truncated`** — centre is inside, but `mu ± HWHM` extends outside
   `[0, nstack-1]`: the curve's half-max width is clipped by the stack edge, so the
   measured FWHM is under-estimated.
4. **`ok`** — centre is `> margin` from each edge **and** the full half-max width
   (`mu ± HWHM`) fits inside `[0, nstack-1]`.

**Design intent:** a patch is `ok` only if the peak *plus at least its HWHM* is
inside the stack. The HWHM-inside requirement is the binding constraint — it is what
makes a fit's FWHM trustworthy (if the half-max points fall off the captured range,
the Gaussian width was measured on a clipped curve). Centre-edge truncation takes
priority over HWHM clipping (a centre at frame 0 reads `truncated_low`, not
`fwhm_truncated`). Non-finite `mu` or `nstack < 2` → `ok` (treated as unknown;
callers additionally require a finite `fwhm` before trusting the patch).

### Propagation into scoring (backward compatible)

`gaussian_defocus_fwhm` is **unchanged** (still returns `(sigma_z, fwhm, mu)`; only
its `mu` is now consumed, not discarded). `through_focus_scores(tf,
require_coverage_ok=True)` now **excludes patches whose `coverage_flag != "ok"`**
from the per-config median FWHM when the column is present (falls back to all valid
FWHMs if a config has no `ok` patch, so configs are not silently dropped). A
DataFrame lacking the column behaves exactly as before. A new
`through_focus_coverage_summary(tf)` emits the per-config truncated fraction.

## What was run on nufan

```
ssh nufan 'bash -lc "cd .../tile-sharpness && direnv exec . uv run pytest tests/ -q"'
# (direnv exec . because .envrc sets a per-host UV_PROJECT_ENVIRONMENT)

# re-extract the 2026-01-29 loctest cohort with the new columns, 5 shards in parallel:
for i in 0 1 2 3 4; do
  direnv exec . env PYTHONPATH=src uv run python scripts/cross_m_relative_mtf_run.py \
    extract --shard $i/5 \
    --subset scripts/cross_m_relative_mtf_subset_loctest.csv \
    --out cross_m_relative_mtf_poc_focus_out &
done; wait

# coverage analysis (per-config / per-zone / top-vs-bottom):
direnv exec . env PYTHONPATH=src uv run python scripts/poc_focus_coverage_analyse.py \
  cross_m_relative_mtf_poc_focus_out
```

The re-extract reproduced the cached `cross_m_relative_mtf_loctest_out` psffoc row
counts exactly (170/176/177/116/… → 724 finite fits over 728 patches) with the four
new columns populated. Field zones come from the existing fieldtag pipeline
(`field_height` → `field_zone` centre `[0,0.33)` / mid `[0.33,0.66)` / corner
`[0.66,∞)`); top/bottom split at the frame mid-line (`py < 5504/2`).

## Results — per-config coverage (2026-01-29)

| config | n | ok | trunc_low | trunc_high | fwhm_trunc | frac_truncated |
|---|---|---|---|---|---|---|
| Z100400+MCON-35 1:1.16 | 69 | 47 | 0 | 0 | 22 | **0.319** |
| V55 f/3.5 209088 | 93 | 74 | 0 | 0 | 19 | **0.204** |
| AF200+5T+6T 2:1 | 16 | 15 | 0 | 0 | 1 | 0.063 |
| AF200+6T 1.7:1 | 28 | 27 | 0 | 0 | 1 | 0.036 |
| AF200 1:1 | 88 | 85 | 2 | 0 | 1 | 0.034 |
| V55 f/2.8 287318 | 85 | 84 | 0 | 0 | 1 | 0.012 |
| S150 / S105 / AF60 / Z105 | 83–92 | all | 0 | 0 | 0 | 0.000 |

All truncation is `fwhm_truncated` (half-max width clipped) plus 2 `truncated_low`;
**no `truncated_high`**. Five of ten configs are perfectly bracketed.

## Per-zone truncation (pooled across configs)

| zone | n | ok | fwhm_trunc | trunc_low | frac_truncated |
|---|---|---|---|---|---|
| centre | 184 | 171 | 11 | 2 | 0.071 |
| mid | 400 | 378 | 22 | 0 | 0.055 |
| corner | 140 | 128 | 12 | 0 | 0.086 |

Corner is only **marginally** higher than centre/mid — corners are **not**
disproportionately truncated cohort-wide.

## Top-vs-bottom (the handover's "decentering" suspicion)

Pooled (all zones): **top 7.9 % truncated vs bottom 5.1 %**. Off-axis only
(mid+corner): **top 8.4 % vs bottom 4.3 %** — a real top-heavy asymmetry, the same
direction as the reported apparent top-vs-bottom "decentering".

But broken out by zone × half, the asymmetry is **localised to the MID zone**, and
**corner is symmetric**:

| zone | bottom frac | top frac |
|---|---|---|
| centre | 0.076 (7/92) | 0.065 (6/92) |
| corner | 0.085 (6/71) | 0.087 (6/69) |
| **mid** | **0.029 (6/207)** | **0.083 (16/193)** |

The entire mid-zone top/bottom gap is driven by **one config,
Z100400+MCON-35**: its mid-top patches are 10/18 truncated vs 1/22 mid-bottom, with
**`peak_pos_frac ≈ 0.85` everywhere** — i.e. that sweep's best focus sits near the
*high* end of the rail for the whole frame, so the half-max of the off-axis-top
patches (whose peak shifts further still) runs off the stack end. V55 f/3.5's
truncation is in the **corners and symmetric top/bottom** (5/9 vs 6/9) — a radial
falloff effect, not a directional one.

## Verdict: is the apparent T-B "decentering" an under-coverage artifact?

**Supported.** The top-heavy truncation asymmetry is (a) confined to configs/zones
where the focus stack failed to bracket the peak — Z100400+MCON-35 has its whole
stack pushed to `peak_pos_frac ≈ 0.85`, so its off-axis-top patches clip the stack
end — and (b) **absent in the corners**, where a genuine decentering would show most
strongly; corners are symmetric top/bottom (8.5 % vs 8.7 %). A real decentered lens
would tilt the *best-focus plane* and produce a top/bottom difference that does
**not** vanish when you exclude truncated patches. Here the asymmetry lives entirely
in the truncated patches and in one under-bracketed accessory config, so excluding
`coverage_flag != ok` removes it. The signal is an **under-coverage (focus-peak
truncation) artifact**, not optical decentering.

Effect on the P2 score of applying the coverage filter (`score_cov - score_raw`,
higher = sharper): negligible for the well-bracketed bare macros (S105/S150/Z105/AF60
= 0.00), but **+5.16 for Z100400+MCON-35 and +3.24 for V55 f/3.5** — exactly the two
under-bracketed configs whose truncated patches had spuriously narrow (clipped) FWHMs
inflating their apparent softness. The filter corrects the configs it should.

## Files

- `src/tile_sharpness/cross_m_relative_mtf.py` — new `coverage_flag`,
  `peak_pos_frac`, `edge_dist_frames`, `through_focus_coverage_summary`;
  `through_focus_scores` now coverage-aware (additive, backward compatible);
  `gaussian_defocus_fwhm` unchanged.
- `scripts/cross_m_relative_mtf_run.py` — psffoc extract emits the four new columns.
- `scripts/poc_focus_coverage_analyse.py` — the analysis driver (new).
- `tests/test_cross_m_relative_mtf.py` — +11 tests for the classifier and scoring.
- Data: `cross_m_relative_mtf_poc_focus_out/` (re-extracted psffoc with new columns)
  plus `poc_focus_coverage_per_config.csv`, `…_per_config_zone.csv`,
  `…_pooled_zone.csv`.
