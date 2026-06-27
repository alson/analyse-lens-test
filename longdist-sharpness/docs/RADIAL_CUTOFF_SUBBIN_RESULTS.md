# `radial_cutoff` sub-bin interpolation — §5.2

Follow-up to the FFT-bin-quantisation issue noted as §5.2 in
[`LONGDIST_HANDOVER.md`](LONGDIST_HANDOVER.md): many lenses' centre
measurements were compressed onto the same `1/n`-cy/px-spaced grid
value (0.30–0.35 cluster on wide-angle), making it impossible to
discriminate, e.g., Z 14-24 vs Z 20/1.8 at the centre at the same
aperture even when they differ optically.

## Fix

Linearly interpolate between the bracketing FFT bins at the
`CUTOFF_THRESHOLD = 0.05` crossing rather than returning the
discrete bin frequency.

```python
v_prev = norm[i - 1]   # last bin still above threshold
v_curr = norm[i]       # first bin below threshold
if v_prev > CUTOFF_THRESHOLD and v_prev != v_curr:
    frac = (v_prev - CUTOFF_THRESHOLD) / (v_prev - v_curr)
    return freq[i - 1] + frac * (freq[i] - freq[i - 1])
return freq[i]
```

Implemented in `poc_longdist_algorithms.py::alg_radial_cutoff`. No
new tunables. Linear (not log-linear) — consistent with the existing
`mtf50_slanted_edge` interpolation in the same file, and within ~25 %
of a log-linear estimate over the small range that brackets the
threshold.

## Effect (wide2026_01_24, Z7 wide-angle)

| Metric | Before | After |
|---|---|---|
| Distinct `top` values across 535 measurements | 38 | 382 |
| Distinct `top` values at centre (`position_frac=0.50`) | 36 | 92 |
| Std of centre `top` across (lens, FL, aperture) | 0.04097 | 0.04063 |
| Spearman correlation old vs new | — | 0.99867 |

Interpretation:

- **10× more distinct values** (38 → 382). Bin quantisation was
  binning 14 measurements per quantum on average; sub-bin scatters
  them onto a continuous scale.
- **Ranking essentially identical** (Spearman 0.9987). The fix is
  pure resolution, not a re-interpretation of the metric — anyone's
  prior rank-based conclusions still hold.
- **Centre cluster spread is preserved**: total std stays at 0.041.
  We didn't widen the range, we just got finer steps within it.

## Per-dataset rollout

| Dataset | n_meas | Distinct before | Distinct after | Centre distinct before | Centre distinct after | Spearman |
|---|---|---|---|---|---|---|
| wide2026_01_24 (Z7) | 535  | 38 | 382 | 36 | 92 | 0.999 |
| wide2026_01_26 (Z7) | 555  | 35 | 35  | 8  | 8  | 1.000 |
| wide2026_02_07 (Z7) | 260  | 33 | 169 | 21 | 34 | 1.000 |
| wide2025_09_10 (D7200) | 1185 | 21 | 21  | 4  | 4  | 1.000 |
| mid2025_09_11 (D7200)  | 1240 | 27 | 392 | 14 | 51 | 0.983 |

Three datasets see the expected 5–15× distinct-value increase; two
do not. Section below.

## Why two datasets show no improvement

`wide2025_09_10` (D7200 wide-angle, cloudy day) and `wide2026_01_26`
(Z7 wide-angle, mostly soft-corner glass at the centre) both have a
**radial-spectrum cutoff that falls inside the ref band**
(`REF_BAND = (0.01, 0.20)` cy/sensor-pixel).

Concretely, for a Z 14-24 at 24mm F8 centre tile on 2026-01-26:

```
bin 49 (freq 0.1914):  norm=0.0754
bin 50 (freq 0.1953):  norm=0.0496   ← actual threshold crossing here
bin 51 (freq 0.1992):  norm=0.0358   ← last ref-band bin, already below 0.05
bin 52 (freq 0.2031):  norm=0.0256   ← first post-ref bin → "cutoff" reported
```

The cutoff *actually* happens at ~0.193 cy/px (inside the ref band)
but the algorithm reports `freq[52] = 0.2031` because the search
starts past the ref band. Sub-bin interpolation between bin 51 and
bin 52 doesn't help — both are already below the threshold.

For `wide2025_09_10` D7200 the situation is more dramatic:
**231 of 237 centre measurements landed on exactly 0.2031** — the
metric is at its floor for nearly the entire dataset.

This is a **ref-band issue, not an interpolation issue**. The §5.2
fix is mechanically correct; some datasets just live outside the
range where it can matter.

### §5.3 follow-up: lower the ref band

The remedy is to lower `REF_BAND[1]` from 0.20 to ~0.10 cy/sensor-px
(or use a fixed DC-anchored normalisation). That keeps the cutoff
search past the ref-band for softer datasets. Would change the SCALE
of the metric — affecting downstream comparison tables — so it's
deliberately out of scope here.

## Caveat for `mtf50_known_edge` (§5.1 sibling)

`mtf50_known_edge` already does sub-bin linear interpolation at the
MTF=0.5 crossing. Its saturation at ~0.49 cy/px is a Nyquist physical
limit, not a bin-quantisation artefact — that's a separate metric
problem (would need a different threshold like MTF@Nyquist or
area-under-MTF to discriminate sharp edges further).
