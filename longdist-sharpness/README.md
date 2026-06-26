# longdist-sharpness

Sharpness analysis of long-distance natural-target lens tests
(telephoto / wide-angle / standard primes shot at infinity-class
distances). Distinct from the [`tile-sharpness/`](../tile-sharpness/)
subproject, which targets the macro-rig silicon-wafer test setup.

Scope: Z7 and D7200 lens-test sessions 2025-07 through 2026-02.
Single-day per-(lens, FL, aperture) sharpness, cross-date robustness,
cross-camera comparisons.

## Quick start

```bash
direnv allow
direnv exec . uv run python scripts/poc_longdist_algorithms.py wide2026_01_24
```

## Layout

- `scripts/` — analysis scripts. Each writes to a sibling `*_out/` dir.
- `docs/` — methodology + results + handover docs:
  - [`SHARPNESS_METRICS_LONGDIST.md`](docs/SHARPNESS_METRICS_LONGDIST.md)
    — protocol design
  - [`LONGDIST_TELE_RESULTS.md`](docs/LONGDIST_TELE_RESULTS.md)
    — Z7 + D7200 telephoto findings
  - [`WIDEANGLE_RESULTS.md`](docs/WIDEANGLE_RESULTS.md)
    — Z7 + D7200 wide-angle / standard findings
  - [`LONGDIST_HANDOVER.md`](docs/LONGDIST_HANDOVER.md)
    — session handover, state of the project, open follow-ups

## Scripts

| Script | Purpose |
|---|---|
| `poc_longdist_algorithms.py` | 4-algorithm comparison (radial_cutoff, mtf50_slanted_edge, vol, brenner) on a per-dataset basis with consensus tile selection. Run as `poc_longdist_algorithms.py <dataset_key>` where dataset keys are listed in the script. |
| `poc_longdist_cross_date_2026_01.py` / `_v2_2026_01.py` | Cross-date analysis for the Z7 2026-01 telephoto sessions. v2 adds sharpest-of-ISO + replicate spread (top/median/min/etc.). |
| `poc_longdist_100_400_field_2026_01_28.py` / `_300pf_field_2026_01_28.py` | Single-day 5-position field-position sweeps for the Z 100-400 and 300 PF families on 2026-01-28. |
| `poc_longdist_100_400_tc_2026_01_28.py` | Original POC: TC vs cropping bare 100-400 frame. |
| `poc_longdist_cross_family_edges_2026_01_28.py` | Cross-family edge / FOM comparison combining 100-400 + Z TCs and 300 PF + F-mount TCs. |
| `poc_longdist_diag.py` / `_diag2.py` | Diagnostic / spectrum-plot helpers used during methodology development. |
| `audit_nef_distance.py` | EXIF FocusDistance audit (NEFs preferred, JPEG fallback). Used for the 2025-07-09 and 2025-09-11 distance-class checks. |
| `extract_2025_07_05_jpegs.py` | Develops 2025-07-05 NEFs to FINE-quality JPEGs via darktable-cli (those NEFs have no co-located JPEGs and the embedded ones are "basic" quality). |
