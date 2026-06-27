# `radial_cutoff` ref-band tightening + smoothing — §5.3

Follow-up to §5.2. The sub-bin interpolation in §5.2 didn't help two
of the five wide-angle datasets (D7200 wide2025_09_10 and Z7
wide2026_01_26) because their actual spectrum cutoff falls *inside*
the old `REF_BAND = (0.01, 0.20)`. On those datasets the metric
saturated at 0.2031 cy/px (231 of 237 centre measurements on
wide2025_09_10).

## What changed

`alg_radial_cutoff` in `poc_longdist_algorithms.py` now combines three
modifications. None of them changes the metric's units (still cy per
sensor pixel) but the absolute scale moves and the search window
moves.

1. **Lower `REF_BAND` upper bound**: `(0.01, 0.20) → (0.01, 0.10)`.
   The cutoff search now starts past 0.10 cy/px instead of 0.20.
   That gives soft datasets headroom: their natural cutoffs around
   0.12–0.18 cy/px are now inside the search window rather than
   inside the ref band.
2. **Gaussian smoothing of the normalised spectrum** (σ = 2 bins ≈
   0.008 cy/px). Suppresses bin-to-bin oscillations that otherwise
   let the crossing logic fire on noise dips.
3. **Last-crossing instead of first-crossing**. Finds the highest
   frequency where the smoothed spectrum is still above the
   threshold and linearly interpolates to where it would cross.
   More robust on noisy spectra than picking the first dip.

## Results

| Dataset | Centre distinct (§5.2 → §5.3) | Centre std (§5.2 → §5.3) | Within-dataset Spearman |
|---|---|---|---|
| wide2026_01_24 (Z7)    | 92 → 103 | 0.041 → 0.046 | 0.967 |
| wide2026_01_26 (Z7)    | 8  → 80  | 0.007 → 0.022 | 0.972 |
| wide2026_02_07 (Z7)    | 34 → 41  | 0.041 → 0.051 | 0.977 |
| wide2025_09_10 (D7200) | 4  → 94  | 0.004 → 0.026 | 0.881 |
| mid2025_09_11 (D7200)  | 51 → 149 | 0.010 → 0.025 | 0.875 |

Two things worth highlighting:

- **The previously-stuck datasets are no longer stuck.** wide2025_09_10
  went from 4 distinct centre values across 230 configs (effectively
  one bin) to 94, with 7× the spread. wide2026_01_26 went from 8 to
  80, 3× the spread.
- **Within-dataset Spearman is 0.88–0.98.** For the Z7 datasets
  rankings are essentially identical to the §5.2 version. For the
  D7200 datasets (which had near-degenerate rankings under §5.2) the
  new metric ranks measurements differently — but the §5.2 ranking
  was barely informative, so a less-than-1.0 Spearman against it is
  fine.

## Downstream impact — values are not directly comparable

Absolute `radial_cutoff` numbers in the existing result docs are now
out of date:

- `LONGDIST_TELE_RESULTS.md` — telephoto cy/sensor-px tables.
- `WIDEANGLE_RESULTS.md` — wide-angle cy/sensor-px tables.

Same lenses re-evaluated under the §5.3 metric will read lower
(typical sharp Z7 wide-angle: was ~0.27, now ~0.24). The RANKINGS
within each comparison should be the same except where the old
metric was at floor, in which case the new values reveal previously-
hidden ordering. Re-running the cross-date analyses below would
refresh those tables:

```
direnv exec . uv run python -u scripts/poc_longdist_cross_date_v2_2026_01.py
direnv exec . uv run python -u scripts/poc_longdist_100_400_field_2026_01_28.py
direnv exec . uv run python -u scripts/poc_longdist_300pf_field_2026_01_28.py
direnv exec . uv run python -u scripts/poc_longdist_cross_family_edges_2026_01_28.py
```

(Not done in this commit — kept as a follow-up so the headline
analysis docs can be reviewed and edited deliberately.)

## Worked example — what changed in one centre tile

For the Z 14-24 at 24mm F8 on 2026-01-26 (Z7, slightly soft day):

| Quantity | §5.2 value | §5.3 value |
|---|---|---|
| Reported `radial_cutoff` | 0.2031 (floor) | 0.1300 |
| Ref-band mean (sum) | mean(bins 3–51) | mean(bins 3–25) |
| Where the spectrum actually crosses 0.05 | bin 50 = freq 0.1953 | (now correctly captured by the metric) |

Under §5.2 the algorithm only searched past bin 52 (the first bin
past the old `REF_BAND[1]=0.20`); since the spectrum is already
below threshold there, it returned `freq[52] = 0.2031`. Under §5.3
the search starts past bin 26 (the new `REF_BAND[1]=0.10`), smoothing
removes the mid-range noise dips, and last-crossing finds the highest
above-threshold bin in the smoothed spectrum — giving the correct
0.130 cy/px answer.
