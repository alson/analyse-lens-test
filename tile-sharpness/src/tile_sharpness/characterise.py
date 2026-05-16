"""Per-slug lens characteristics from a ``peaks_v2.csv``.

Phase 3 of the LSF + maze-FFT pipeline (``IMPLEMENTATION_PLAN.md``).
Sample up to 9 tile positions per sweep — centre + 4 DX-ring corners +
4 FX-ring corners — and roll up to per-slug rows:

* MTF50 centre vs DX-ring vs FX-ring (subject space, lp/mm).
* Uniformity (corner/centre ratios).
* Decentering — peak-VALUE asymmetry per ring (L−R and T−B). Per the
  IMPLEMENTATION_PLAN: peak-VALUE, not peak-INDEX, because index
  asymmetry is contaminated by subject-tilt + field-curvature.
* Subject-tilt + field-curvature from a plane fit on ``(tile_x_px,
  tile_y_px, argmax_rail_position_mm)`` across the available positions.

Ring selection is **grid-extent-based**, not pixel-target-based: the
FX corners are the extreme grid cells ``(ix_min, iy_min), …,
(ix_max, iy_max)``; the DX corners are one grid step inward along each
diagonal. This generalises naturally to the M-driven shrinking grid
under the accuracy-over-granularity policy — if the grid only has 3
distinct ix values, DX-ring is empty and the row carries an
``n_positions=5`` (or fewer) flag with NaN ring aggregates.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


def _grid_extent(rows: pd.DataFrame) -> tuple[int, int, int, int]:
    """Return ``(ix_min, ix_max, iy_min, iy_max)`` for the sweep's grid."""
    return (
        int(rows["tile_ix"].min()), int(rows["tile_ix"].max()),
        int(rows["tile_iy"].min()), int(rows["tile_iy"].max()),
    )


def _row_at(rows: pd.DataFrame, ix: int, iy: int) -> pd.Series | None:
    m = rows[(rows["tile_ix"] == ix) & (rows["tile_iy"] == iy)]
    return m.iloc[0] if not m.empty else None


def _select_rings(
    rows: pd.DataFrame,
) -> tuple[pd.Series | None, list[pd.Series | None], list[pd.Series | None]]:
    """Return ``(centre, dx_corners[4], fx_corners[4])``.

    DX/FX corners are ordered TL, TR, BL, BR (so paired-corner asymmetries
    can be computed by index). Missing corners are ``None``.
    """
    if rows.empty:
        return None, [None] * 4, [None] * 4

    centre = _row_at(rows, 0, 0)
    ix_min, ix_max, iy_min, iy_max = _grid_extent(rows)

    fx_targets = [
        (ix_min, iy_min), (ix_max, iy_min), (ix_min, iy_max), (ix_max, iy_max),
    ]
    fx_corners = [_row_at(rows, ix, iy) for ix, iy in fx_targets]

    # DX ring is one step inward from each FX corner along the diagonal.
    # Requires grid extent ≥ 2 in both directions; otherwise DX ring is empty.
    if ix_max - ix_min >= 2 and iy_max - iy_min >= 2:
        dx_targets = [
            (ix_min + 1, iy_min + 1), (ix_max - 1, iy_min + 1),
            (ix_min + 1, iy_max - 1), (ix_max - 1, iy_max - 1),
        ]
        dx_corners = [_row_at(rows, ix, iy) for ix, iy in dx_targets]
    else:
        dx_corners = [None] * 4

    return centre, dx_corners, fx_corners


def _peak_asymmetry(left: float | None, right: float | None) -> float | None:
    """Return ``(left − right) / mean`` peak-value asymmetry, or None if either is missing."""
    if left is None or right is None:
        return None
    if not math.isfinite(left) or not math.isfinite(right):
        return None
    m = (left + right) / 2
    if m == 0:
        return None
    return (left - right) / m


def _plane_fit(
    xs: list[float], ys: list[float], zs: list[float],
) -> tuple[float, float, float, float]:
    """Least-squares plane ``z = ax + by + c``; return ``(a, b, c, rms_residual)``."""
    if len(xs) < 3:
        return float("nan"), float("nan"), float("nan"), float("nan")
    A = np.column_stack([xs, ys, np.ones(len(xs))])
    coef, *_ = np.linalg.lstsq(A, zs, rcond=None)
    a, b, c = float(coef[0]), float(coef[1]), float(coef[2])
    residuals = np.asarray(zs) - (A @ coef)
    rms = float(np.sqrt((residuals * residuals).mean()))
    return a, b, c, rms


def _safe_mean(values: list[float | None]) -> float:
    arr = [v for v in values if v is not None and not math.isnan(float(v))]
    return float(np.mean(arr)) if arr else float("nan")


def characterise_sweep(sweep_rows: pd.DataFrame) -> dict:
    """Compute per-slug characteristics from a single sweep's peaks_v2 rows."""
    sweep_rows = sweep_rows.reset_index(drop=True)

    centre_row, dx_rows, fx_rows = _select_rings(sweep_rows)

    sampled: list[pd.Series] = []
    for r in [centre_row, *dx_rows, *fx_rows]:
        if r is not None:
            sampled.append(r)

    if centre_row is None:
        return {"n_positions": 0, "note": "no_tiles"}

    mtf50_centre = float(centre_row.get("mtf50_subject_lp_per_mm") or float("nan"))

    # Distinct rows for plane fit and decentering: dedupe by tile_ix/iy.
    seen_ixiy: set[tuple[int, int]] = set()
    distinct: list[pd.Series] = []
    for r in sampled:
        key = (int(r["tile_ix"]), int(r["tile_iy"]))
        if key in seen_ixiy:
            continue
        seen_ixiy.add(key)
        distinct.append(r)
    n_distinct = len(distinct)

    # Corner-mean MTF50 (subject space) and uniformity
    def _mtf(rows: list[pd.Series | None]) -> list[float]:
        return [
            float(r.get("mtf50_subject_lp_per_mm") or float("nan"))
            for r in rows if r is not None
        ]

    dx_mtfs = _mtf(dx_rows)
    fx_mtfs = _mtf(fx_rows)
    mtf50_dx_corner_mean = _safe_mean(dx_mtfs)
    mtf50_fx_corner_mean = _safe_mean(fx_mtfs)

    uniformity_dx = (
        mtf50_dx_corner_mean / mtf50_centre if math.isfinite(mtf50_dx_corner_mean) and mtf50_centre else float("nan")
    )
    uniformity_fx = (
        mtf50_fx_corner_mean / mtf50_centre if math.isfinite(mtf50_fx_corner_mean) and mtf50_centre else float("nan")
    )

    # Decentering: peak-VALUE asymmetry between paired corners (TL-TR vs BL-BR).
    # Use `peak_value` (the primary metric's amplitude at argmax shot) per the
    # IMPLEMENTATION_PLAN — not `mtf50_*` which has more averaging noise.
    def _peak(r: pd.Series | None) -> float | None:
        if r is None:
            return None
        v = r.get("peak_value")
        return float(v) if v is not None else None

    def _ring_asymmetries(rows: list[pd.Series | None]) -> tuple[float | None, float | None]:
        # rows order: TL TR BL BR
        if len(rows) < 4:
            return None, None
        tl, tr, bl, br = rows
        left = _peak(tl), _peak(bl)
        right = _peak(tr), _peak(br)
        top = _peak(tl), _peak(tr)
        bottom = _peak(bl), _peak(br)
        l_avg = _safe_mean(list(left)) if any(v is not None for v in left) else None
        r_avg = _safe_mean(list(right)) if any(v is not None for v in right) else None
        t_avg = _safe_mean(list(top)) if any(v is not None for v in top) else None
        b_avg = _safe_mean(list(bottom)) if any(v is not None for v in bottom) else None
        lr = _peak_asymmetry(l_avg, r_avg) if (l_avg is not None and r_avg is not None and math.isfinite(l_avg) and math.isfinite(r_avg)) else None
        tb = _peak_asymmetry(t_avg, b_avg) if (t_avg is not None and b_avg is not None and math.isfinite(t_avg) and math.isfinite(b_avg)) else None
        return lr, tb

    dec_dx_lr, dec_dx_tb = _ring_asymmetries(dx_rows)
    dec_fx_lr, dec_fx_tb = _ring_asymmetries(fx_rows)

    # Subject-tilt + field-curvature via plane fit on (x_px, y_px, rail_mm).
    # When rail_position_mm is None across the board (older datasets without
    # shots.csv), fall back to argmax_shot_idx — subject-tilt is unitless
    # but uniformity/decentering still hold.
    xs, ys, zs = [], [], []
    used_rail_mm = False
    for r in distinct:
        rail_mm = r.get("rail_position_mm_at_argmax")
        if rail_mm is not None and isinstance(rail_mm, (int, float)) and not (
            isinstance(rail_mm, float) and math.isnan(rail_mm)
        ):
            xs.append(float(r["tile_x_px"]))
            ys.append(float(r["tile_y_px"]))
            zs.append(float(rail_mm))
            used_rail_mm = True
    if not used_rail_mm:
        for r in distinct:
            xs.append(float(r["tile_x_px"]))
            ys.append(float(r["tile_y_px"]))
            zs.append(float(r["argmax_shot_idx"]))

    a, b, _c, rms = _plane_fit(xs, ys, zs)
    # Slope is mm/px (or shot/px in the fallback). Convert to angle via
    # arctan; for the fallback case we don't multiply by a rail step (we
    # don't know it), so subject_tilt_deg is in shot-index units —
    # comparable across slugs only when fallback is in play for all.
    tilt_x_deg = float(np.arctan(a) * 180 / np.pi) if math.isfinite(a) else float("nan")
    tilt_y_deg = float(np.arctan(b) * 180 / np.pi) if math.isfinite(b) else float("nan")
    curvature_units = rms if used_rail_mm else float("nan")  # mm-RMS only with real rail mm

    note_parts: list[str] = []
    if n_distinct < 9:
        note_parts.append(f"n_positions<9")
    if n_distinct == 1:
        note_parts.append("centre_only")
    if not used_rail_mm:
        note_parts.append("rail_mm_unavailable")
    note = ";".join(note_parts) if note_parts else ""

    return {
        "n_positions": n_distinct,
        "note": note,
        "mtf50_centre_lpmm": mtf50_centre,
        "mtf50_dx_corner_mean_lpmm": mtf50_dx_corner_mean,
        "mtf50_fx_corner_mean_lpmm": mtf50_fx_corner_mean,
        "uniformity_dx": uniformity_dx,
        "uniformity_fx": uniformity_fx,
        "decentering_dx_lr": dec_dx_lr if dec_dx_lr is not None else float("nan"),
        "decentering_dx_tb": dec_dx_tb if dec_dx_tb is not None else float("nan"),
        "decentering_fx_lr": dec_fx_lr if dec_fx_lr is not None else float("nan"),
        "decentering_fx_tb": dec_fx_tb if dec_fx_tb is not None else float("nan"),
        "subject_tilt_x_deg": tilt_x_deg,
        "subject_tilt_y_deg": tilt_y_deg,
        "field_curvature_um_rms": curvature_units,
    }


def characterise_peaks_v2(peaks_v2_csv: Path, out_csv: Path) -> int:
    """Roll up ``peaks_v2.csv`` to one row per sweep; write ``out_csv``."""
    df = pd.read_csv(peaks_v2_csv)
    if df.empty:
        out_csv.write_text("sweep\n")
        return 0
    rows: list[dict] = []
    for sweep_id, grp in df.groupby("sweep"):
        m_val = grp["m"].iloc[0] if "m" in grp.columns else float("nan")
        m_source = grp["m_source"].iloc[0] if "m_source" in grp.columns else ""
        result = characterise_sweep(grp)
        rows.append({
            "sweep": sweep_id,
            "m": m_val,
            "m_source": m_source,
            **result,
        })
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    return len(rows)
