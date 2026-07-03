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

from .methods.maze_fft import SENSOR_PITCH_UM_Z7

# Cross-M guardrail. ``nyquist_fraction = mtf50_sensor_cy_per_px / 0.5`` is the
# fraction of sensor Nyquist a reading sits at (sensor-space → M-independent). A
# subject-space lp/mm comparison between two configs is degenerate — pixel-limited
# rather than optics-limited — once either sits near Nyquist: at that cap the
# reading reflects the sensor, not the lens, no matter how good the glass. Configs
# below the threshold are cleanly optics-limited and safe to compare in lp/mm.
NYQUIST_FRACTION_DEGENERATE = 0.80


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

    # FX corners need both axes to have distinct extreme cells; otherwise
    # all four fx_targets collapse onto a single row (the centre) and
    # uniformity_fx silently reports 1.0 instead of NaN.
    if ix_max > ix_min and iy_max > iy_min:
        fx_targets = [
            (ix_min, iy_min), (ix_max, iy_min), (ix_min, iy_max), (ix_max, iy_max),
        ]
        fx_corners = [_row_at(rows, ix, iy) for ix, iy in fx_targets]
    else:
        fx_corners = [None] * 4

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


def _slope_to_tilt_deg(
    slope_mm_per_sensor_px: float, m: float,
    sensor_pitch_um: float = SENSOR_PITCH_UM_Z7,
) -> float:
    """Convert plane-fit slope (rail mm per sensor px) to subject-plane tilt in degrees.

    The plane fit has ``z`` in rail mm and ``x`` in sensor pixels. One sensor
    pixel corresponds to ``pitch_um / 1000 / M`` mm in object space, so the
    dimensionless object-space slope is ``slope × M × 1000 / pitch_um``;
    arctan of that is the angle between the subject plane and the sensor plane.
    """
    if not math.isfinite(slope_mm_per_sensor_px) or not math.isfinite(m) or m <= 0:
        return float("nan")
    object_slope = slope_mm_per_sensor_px * m * 1000.0 / sensor_pitch_um
    return float(np.arctan(object_slope) * 180 / np.pi)


def _rail_mm_z_for_row(
    row: pd.Series, rail_step_mm: float | None,
) -> tuple[float, str]:
    """Return ``(z_value, source)`` for one plane-fit point.

    Source is ``"recorded"`` when ``rail_position_mm_at_argmax`` is a real
    number, ``"calibrated"`` when synthesized from ``rail_step_mm × shot_idx``,
    and ``"shot_index"`` for the unit-less fallback.
    """
    rail_mm = row.get("rail_position_mm_at_argmax")
    has_recorded = (
        rail_mm is not None
        and isinstance(rail_mm, (int, float))
        and not (isinstance(rail_mm, float) and math.isnan(rail_mm))
    )
    if has_recorded:
        return float(rail_mm), "recorded"
    if rail_step_mm is not None and math.isfinite(rail_step_mm):
        return float(row["argmax_shot_idx"]) * float(rail_step_mm), "calibrated"
    return float(row["argmax_shot_idx"]), "shot_index"


def characterise_sweep(
    sweep_rows: pd.DataFrame, *, rail_step_mm: float | None = None,
) -> dict:
    """Compute per-slug characteristics from a single sweep's peaks_v2 rows.

    ``rail_step_mm`` is an optional through-focus rail-step calibration
    (from ``rail_calibration``). When the sweep lacks recorded
    ``rail_position_mm_at_argmax`` (older datasets) but a calibration is
    supplied, the plane-fit ``z`` is synthesized as
    ``rail_step_mm × argmax_shot_idx`` so subject_tilt comes out in
    degrees and field_curvature in µm. Without either, the plane-fit
    fallback uses raw ``argmax_shot_idx`` and the tilt/curvature columns
    carry shot-index units (flagged in ``note``).
    """
    sweep_rows = sweep_rows.reset_index(drop=True)

    centre_row, dx_rows, fx_rows = _select_rings(sweep_rows)

    sampled: list[pd.Series] = []
    for r in [centre_row, *dx_rows, *fx_rows]:
        if r is not None:
            sampled.append(r)

    if centre_row is None:
        return {"n_positions": 0, "note": "no_tiles"}

    mtf50_centre = float(centre_row.get("mtf50_subject_lp_per_mm") or float("nan"))
    # Sensor-Nyquist fraction of the centre reading (cross-M degeneracy guard).
    mtf50_sensor_centre = float(centre_row.get("mtf50_sensor_cy_per_px") or float("nan"))
    nyquist_fraction_centre = (
        mtf50_sensor_centre / 0.5 if math.isfinite(mtf50_sensor_centre) else float("nan")
    )

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

    # Subject-tilt + field-curvature via plane fit on (x_px, y_px, z).
    # z is rail_mm when recorded or synthesizable from rail_step_mm;
    # raw shot_idx (unit-less) otherwise.
    xs, ys, zs = [], [], []
    sources: set[str] = set()
    for r in distinct:
        z, src = _rail_mm_z_for_row(r, rail_step_mm)
        xs.append(float(r["tile_x_px"]))
        ys.append(float(r["tile_y_px"]))
        zs.append(z)
        sources.add(src)

    if sources == {"recorded"}:
        rail_z_source = "recorded"
    elif sources == {"calibrated"}:
        rail_z_source = "calibrated"
    elif sources == {"shot_index"}:
        rail_z_source = "shot_index"
    elif sources <= {"recorded", "calibrated"}:
        # Mixed real-mm sources still produce real-mm units — keep going.
        rail_z_source = "mixed_mm"
    else:
        rail_z_source = "mixed"

    z_is_real_mm = rail_z_source in {"recorded", "calibrated", "mixed_mm"}

    a, b, _c, rms = _plane_fit(xs, ys, zs)

    # Magnification for the pixel→object-space scaling. Defaults to the
    # sweep's m column (which is uniform within a sweep).
    m_value = (
        float(sweep_rows["m"].iloc[0])
        if "m" in sweep_rows.columns and not pd.isna(sweep_rows["m"].iloc[0])
        else float("nan")
    )

    if z_is_real_mm and math.isfinite(m_value) and m_value > 0:
        tilt_x_deg = _slope_to_tilt_deg(a, m_value)
        tilt_y_deg = _slope_to_tilt_deg(b, m_value)
        field_curvature_um_rms = rms * 1000.0  # mm-RMS → µm-RMS
    else:
        # Fallback: dimensionless atan; "degrees" units only nominally.
        tilt_x_deg = float(np.arctan(a) * 180 / np.pi) if math.isfinite(a) else float("nan")
        tilt_y_deg = float(np.arctan(b) * 180 / np.pi) if math.isfinite(b) else float("nan")
        field_curvature_um_rms = float("nan")

    note_parts: list[str] = []
    if n_distinct < 9:
        note_parts.append("n_positions<9")
    if n_distinct == 1:
        note_parts.append("centre_only")
    if rail_z_source == "shot_index":
        note_parts.append("rail_mm_unavailable")
    elif rail_z_source == "calibrated":
        note_parts.append("rail_mm_calibrated")
    elif rail_z_source == "mixed":
        note_parts.append("rail_mm_mixed_sources")
    if math.isfinite(nyquist_fraction_centre) and nyquist_fraction_centre >= NYQUIST_FRACTION_DEGENERATE:
        # Centre reading is near sensor Nyquist: pixel-limited, so its lp/mm is
        # not a clean cross-M comparison point (see NYQUIST_FRACTION_DEGENERATE).
        note_parts.append("sensor_bounded")
    note = ";".join(note_parts) if note_parts else ""

    return {
        "n_positions": n_distinct,
        "note": note,
        "mtf50_centre_lpmm": mtf50_centre,
        "nyquist_fraction_centre": nyquist_fraction_centre,
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
        "field_curvature_um_rms": field_curvature_um_rms,
        "rail_z_source": rail_z_source,
        "rail_step_mm": float(rail_step_mm) if rail_step_mm is not None else float("nan"),
    }


def characterise_peaks_v2(
    peaks_v2_csv: Path,
    out_csv: Path,
    *,
    rail_step_lookup: dict[str, float] | None = None,
) -> int:
    """Roll up ``peaks_v2.csv`` to one row per sweep; write ``out_csv``.

    ``rail_step_lookup`` optionally maps ``sweep_id`` → calibrated
    rail-step-mm (from ``rail_calibration.rail_step_lookup_v1`` or
    ``rail_step_lookup_v2``). Sweeps absent from the lookup fall back to
    the rail-mm-unavailable path.
    """
    df = pd.read_csv(peaks_v2_csv)
    if df.empty:
        out_csv.write_text("sweep\n")
        return 0
    rows: list[dict] = []
    for sweep_id, grp in df.groupby("sweep"):
        m_val = grp["m"].iloc[0] if "m" in grp.columns else float("nan")
        m_source = grp["m_source"].iloc[0] if "m_source" in grp.columns else ""
        rail_step = (
            rail_step_lookup.get(str(sweep_id)) if rail_step_lookup else None
        )
        result = characterise_sweep(grp, rail_step_mm=rail_step)
        rows.append({
            "sweep": sweep_id,
            "m": m_val,
            "m_source": m_source,
            **result,
        })
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    return len(rows)
