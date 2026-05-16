"""Phase 1 + Phase 2 of the LSF + maze-FFT sharpness pipeline.

Per ``IMPLEMENTATION_PLAN.md`` and ``SHARPNESS_METRICS.md`` "2026-05-16
update", Phase 1 emits per-shot-per-tile raw sharpness records keyed on
``(sweep, tile_ix, tile_iy, shot_idx)``, and Phase 2 aggregates each
``(sweep, tile)`` group to a single ``peaks_v2`` row using a metric-
selection rule: maze-FFT argmax when ``maze_resolves``, scribe-LSF
argmax otherwise (or a filesize fallback for off-target tiles).

Pipeline is M-driven: ROI sizes scale with measured magnification per
the accuracy-over-granularity policy (see ``MEMORY.md``). The legacy
1024-px tile cache is reused for the filesize/on-target side columns —
matched to the new ROI grid by ``(ix, iy)`` since both grids share the
same MCU-aligned centre and step.

Subject-space MTF50 is the cross-config metric:

    mtf50_subject_lp_per_mm = mtf50_sensor_cy_per_px × M × 1000 / pixel_pitch_um

On Z7 (pitch 4.35 µm) this is ``mtf50_sensor × M × 229.9``.
"""

from __future__ import annotations

import math
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from lens_test_detect_core import MCU_SIZE

from .crop import DEFAULT_CACHE_ROOT, extract_tiles, image_dimensions
from .geometry import ROITile, Tile, compute_tiles, compute_tiles_for_roi
from .m_lookup import MLookup, resolve
from .methods.lsf import Segment, cross_section, detect_scribe, lsf_mtf50, lsf_peak_amp
from .methods.maze_fft import MAZE_PITCH_UM, SENSOR_PITCH_UM_Z7, maze_amp
from .on_target import label_tiles
from .sweeps import Sweep


# Physical scribe pitch on the wafer in micrometres.
# The wafer's die boundaries are ~5 mm apart; on Z7 at 1:1 that's ~1150 px.
# (Mirrors the heuristic in IMPLEMENTATION_PLAN.md "M comes from
# archive-2026-05/measure_wafer_squares manifest".)
SCRIBE_PITCH_UM = 5000.0

# Physical scribe groove WIDTH on the wafer in micrometres. Back-solved from
# the AIS 287318 + AF 200/4D 1:1 F11 centre tiles where the measured
# trough FWHM was 17-22 sensor pixels — at 4.35 µm pitch that's 74-96 µm
# physical, midpoint ~87 µm. Used to gate out non-scribe features that
# the LSD/Hough detector accepts but whose trough is too narrow to support
# the ESF→LSF method (a few-px-wide dark feature has overlapping
# left/right edges, so the differentiation can't isolate the optical PSF).
SCRIBE_WIDTH_UM = 87.0

# Reject LSF readings whose measured trough FWHM is below this fraction of
# the expected scribe FWHM at the sweep's magnification. 0.5 catches the
# AF 200/4D (+1, 0) non-scribe outlier (FWHM=8 at M=1.0, expected 20 →
# 8/20 = 0.4 < 0.5) while leaving real low-M scribes intact (M=0.385 →
# expected FWHM ~7.7, threshold ~3.85, so a real FWHM ≥ 4 is accepted).
TROUGH_FWHM_REJECTION_FRACTION = 0.5

# Cross-config conversion: cycles/pixel on sensor → line-pairs/mm on subject.
# On Z7 (4.35 µm pitch) one cycle/px equals 1000/4.35 = 229.9 lp/mm on sensor,
# divided back by M to subject space.
Z7_SUBJECT_FACTOR = 1000.0 / SENSOR_PITCH_UM_Z7


def _trough_fwhm_samples(profile: np.ndarray) -> int:
    """Count samples below the half-depth of the cross-section profile."""
    half = (profile.min() + profile.max()) / 2
    return int((profile < half).sum())


def _expected_scribe_fwhm_px(M: float) -> float:
    """Predicted scribe FWHM on the sensor at magnification ``M`` (Z7 pitch)."""
    return SCRIBE_WIDTH_UM * M / SENSOR_PITCH_UM_Z7


def _align_up(n: int, step: int = MCU_SIZE) -> int:
    rem = n % step
    return n if rem == 0 else n + (step - rem)


def _roi_sizes(M: float) -> tuple[int, int]:
    """Return ``(lsf_roi_px, maze_roi_px)`` for this magnification."""
    die_period_px = SCRIBE_PITCH_UM * M / SENSOR_PITCH_UM_Z7
    lsf_roi_px = _align_up(max(int(3 * die_period_px), 1024))
    maze_period_px = MAZE_PITCH_UM * M / SENSOR_PITCH_UM_Z7
    maze_roi_px = _align_up(max(int(64 * maze_period_px), 256))
    return lsf_roi_px, maze_roi_px


def _decode_gray(path: Path) -> np.ndarray:
    """Decode a JPEG to a 2-D float32 grayscale array."""
    with Image.open(path) as im:
        return np.asarray(im.convert("L"), dtype=np.float32)


def _crop_box(arr: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """Slice ``arr[y0:y1, x0:x1]`` from a box ``(x0, y0, x1, y1)``.

    Returns a numpy view (no copy). Clips silently if the box extends
    past the array; callers should size ROIs to fit.
    """
    x0, y0, x1, y1 = box
    h, w = arr.shape
    return arr[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]


def _legacy_filesize_and_labels(
    sweep: Sweep, cache_root: Path,
) -> tuple[dict[tuple[int, int], list[int]], dict[tuple[int, int], bool]]:
    """Compute filesize per shot and on-target label per legacy 1024 tile.

    Returns two ``(ix, iy)``-keyed dicts:
      * ``filesize_seq``: list of filesize bytes per shot for each legacy tile.
      * ``on_target``: bool per legacy tile.
    """
    w, h = image_dimensions(sweep.shots[0].path)
    tiles = compute_tiles(w, h, 1024)
    per_shot_tile_paths: list[dict[Tile, Path]] = []
    for shot in sweep.shots:
        tp_list = extract_tiles(shot.path, tiles, cache_root=cache_root)
        per_shot_tile_paths.append({tp.tile: tp.path for tp in tp_list})
    sizes_by_tile: dict[Tile, list[int]] = {
        t: [shot[t].stat().st_size for shot in per_shot_tile_paths] for t in tiles
    }
    labels = label_tiles(sizes_by_tile, per_shot_tile_paths)
    fs_by_ixiy = {(t.ix, t.iy): sizes for t, sizes in sizes_by_tile.items()}
    ot_by_ixiy = {(t.ix, t.iy): lbl.on_target for t, lbl in labels.items()}
    return fs_by_ixiy, ot_by_ixiy


def _detect_scribes(
    sweep: Sweep,
    roi_tiles: list[ROITile],
    fs_by_ixiy: dict[tuple[int, int], list[int]],
) -> dict[tuple[int, int], Segment | None]:
    """Run scribe detection once per (sweep, tile) at the filesize-argmax shot."""
    scribes: dict[tuple[int, int], Segment | None] = {}
    # Group ROI tiles by their filesize-argmax shot index so we decode
    # each source JPEG at most once across the scribe-detect pass.
    by_shot: dict[int, list[ROITile]] = defaultdict(list)
    for roi in roi_tiles:
        sizes = fs_by_ixiy.get((roi.ix, roi.iy))
        if sizes is None:
            scribes[(roi.ix, roi.iy)] = None
            continue
        argmax_k = int(np.argmax(sizes))
        by_shot[argmax_k].append(roi)
    for k, rois in by_shot.items():
        full = _decode_gray(sweep.shots[k].path)
        for roi in rois:
            lsf_roi = _crop_box(full, roi.lsf_box())
            scribes[(roi.ix, roi.iy)] = detect_scribe(lsf_roi)
    return scribes


def _score_shot(
    shot_path_str: str,
    shot_idx: int,
    rail_mm: float | None,
    roi_tuples: list[tuple],
    scribes_data: dict[tuple[int, int], tuple | None],
    M: float,
    sweep_id: str,
    m_source: str,
    fs_by_ixiy: dict[tuple[int, int], list[int]],
    ot_by_ixiy: dict[tuple[int, int], bool],
) -> list[dict[str, Any]]:
    """Process one source JPEG: decode once, score every ROI tile.

    ROI tiles and Segments are passed as plain tuples for pickle.
    """
    full = _decode_gray(Path(shot_path_str))
    rows: list[dict[str, Any]] = []
    for roi_t in roi_tuples:
        ix, iy, cx, cy, lsf_roi_px, maze_roi_px = roi_t
        half_lsf = lsf_roi_px // 2
        half_maze = maze_roi_px // 2
        lsf_roi = _crop_box(full, (cx - half_lsf, cy - half_lsf, cx + half_lsf, cy + half_lsf))
        maze_roi = _crop_box(full, (cx - half_maze, cy - half_maze, cx + half_maze, cy + half_maze))

        seg_t = scribes_data.get((ix, iy))
        trough_fwhm: int | None = None
        if seg_t is not None:
            seg = Segment(x0=seg_t[0], y0=seg_t[1], x1=seg_t[2], y1=seg_t[3])
            profile = cross_section(lsf_roi, seg)
            trough_fwhm = _trough_fwhm_samples(profile)
            lsf_amp = lsf_peak_amp(profile)
            lsf_mtf = lsf_mtf50(profile)
            scribe_detected = True
            # M-aware trough-width gate: reject readings whose trough is
            # too narrow to be a real wafer scribe at this M. The
            # LSD/Hough detector accepts long dark features regardless
            # of width; this filter drops sub-scribe-width features
            # (bond-pad shadows, single dark texture lines) before they
            # contaminate the per-tile MTF50 with anomalously-high values.
            expected_fwhm = _expected_scribe_fwhm_px(M)
            if trough_fwhm < TROUGH_FWHM_REJECTION_FRACTION * expected_fwhm:
                lsf_amp = float("nan")
                lsf_mtf = None
        else:
            lsf_amp = float("nan")
            lsf_mtf = None
            scribe_detected = False

        maze_amp_val = maze_amp(maze_roi, M)
        maze_resolves = maze_amp_val is not None and M >= 0.7

        fs_seq = fs_by_ixiy.get((ix, iy))
        fs_bytes = fs_seq[shot_idx] if fs_seq is not None and shot_idx < len(fs_seq) else None
        on_target = ot_by_ixiy.get((ix, iy))

        rows.append({
            "sweep": sweep_id,
            "tile_ix": ix,
            "tile_iy": iy,
            "shot_idx": shot_idx,
            "rail_position_mm": rail_mm,
            "tile_x_px": cx,
            "tile_y_px": cy,
            "lsf_roi_px": lsf_roi_px,
            "maze_roi_px": maze_roi_px,
            "filesize_bytes": fs_bytes,
            "on_target": on_target,
            "m": M,
            "m_source": m_source,
            "scribe_detected": scribe_detected,
            "trough_fwhm_px": trough_fwhm,
            "lsf_peak_amp": lsf_amp,
            "lsf_mtf50_cy_per_px": lsf_mtf,
            "maze_resolves": maze_resolves,
            "maze_fft_amp": maze_amp_val,
        })
    return rows


def analyse_sweep_phase1(
    sweep: Sweep,
    mlookup: MLookup,
    *,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    workers: int = 4,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run Phase 1 + Phase 2 on one sweep.

    Returns ``(per_shot_per_tile_rows, peaks_v2_rows)``. If M can't be
    resolved (e.g. newer-rig label without a mag_label), returns
    ``([], [])`` — caller logs and skips.
    """
    m_info = resolve(sweep, mlookup)
    M = m_info.measured
    if not math.isfinite(M) or M <= 0:
        return [], []

    lsf_roi_px, maze_roi_px = _roi_sizes(M)
    w, h = image_dimensions(sweep.shots[0].path)
    roi_tiles = compute_tiles_for_roi(w, h, lsf_roi_px, maze_roi_px)
    if not roi_tiles:
        return [], []

    fs_by_ixiy, ot_by_ixiy = _legacy_filesize_and_labels(sweep, cache_root)
    scribes = _detect_scribes(sweep, roi_tiles, fs_by_ixiy)

    # Repackage data for pickle into the worker pool.
    roi_tuples = [
        (r.ix, r.iy, r.cx, r.cy, r.lsf_roi_px, r.maze_roi_px) for r in roi_tiles
    ]
    scribes_data: dict[tuple[int, int], tuple | None] = {
        k: (s.x0, s.y0, s.x1, s.y1) if s is not None else None
        for k, s in scribes.items()
    }

    all_rows: list[dict[str, Any]] = []
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    _score_shot,
                    str(shot.path),
                    k,
                    shot.rail_position_mm,
                    roi_tuples,
                    scribes_data,
                    M,
                    sweep.id,
                    m_info.source,
                    fs_by_ixiy,
                    ot_by_ixiy,
                )
                for k, shot in enumerate(sweep.shots)
            ]
            for fut in futures:
                all_rows.extend(fut.result())
    else:
        for k, shot in enumerate(sweep.shots):
            all_rows.extend(_score_shot(
                str(shot.path), k, shot.rail_position_mm, roi_tuples,
                scribes_data, M, sweep.id, m_info.source,
                fs_by_ixiy, ot_by_ixiy,
            ))

    peaks_v2 = _rollup_peaks_v2(all_rows, sweep, M)
    return all_rows, peaks_v2


def _rollup_peaks_v2(
    per_shot_rows: list[dict[str, Any]], sweep: Sweep, M: float,
) -> list[dict[str, Any]]:
    """Phase 2: select primary metric per (sweep, tile) and emit one peak row.

    Selection rule (per IMPLEMENTATION_PLAN.md):
      * off-target → filesize_fallback (or skip if no filesize either)
      * else if any shot's maze_resolves → primary = maze_fft argmax
      * else → primary = lsf_peak_amp argmax
    Subject-space MTF50 is computed from the LSF MTF50 at the argmax shot
    whenever an LSF reading is available (regardless of which method
    picked argmax — keeps the cross-config metric uniform).
    """
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in per_shot_rows:
        grouped[(r["tile_ix"], r["tile_iy"])].append(r)

    out: list[dict[str, Any]] = []
    for (ix, iy), rows in grouped.items():
        rows.sort(key=lambda r: r["shot_idx"])

        on_target = rows[0]["on_target"] if rows else None
        any_maze_resolves = any(r["maze_resolves"] for r in rows)
        primary: str
        argmax_idx: int
        peak_value: float

        if on_target is False:
            # filesize fallback (off-target tiles shouldn't drive
            # argmax decisions, but emit for completeness).
            fs_vals = [r["filesize_bytes"] for r in rows if r["filesize_bytes"] is not None]
            if not fs_vals:
                continue
            primary = "filesize_fallback"
            argmax_idx = int(np.argmax([r["filesize_bytes"] or 0 for r in rows]))
            peak_value = float(rows[argmax_idx]["filesize_bytes"])
        elif any_maze_resolves:
            primary = "maze_fft"
            argmax_idx = int(np.argmax([
                (r["maze_fft_amp"] if r["maze_fft_amp"] is not None else -np.inf)
                for r in rows
            ]))
            peak_value = float(rows[argmax_idx]["maze_fft_amp"])
        else:
            primary = "lsf"
            argmax_idx = int(np.argmax([
                (r["lsf_peak_amp"] if not math.isnan(r["lsf_peak_amp"]) else -np.inf)
                for r in rows
            ]))
            peak_value = float(rows[argmax_idx]["lsf_peak_amp"])

        argmax_row = rows[argmax_idx]
        mtf50_sensor = argmax_row["lsf_mtf50_cy_per_px"]
        mtf50_subject = (
            mtf50_sensor * M * Z7_SUBJECT_FACTOR if mtf50_sensor is not None else None
        )
        out.append({
            "sweep": sweep.id,
            "tile_ix": ix,
            "tile_iy": iy,
            "primary_metric_used": primary,
            "argmax_shot_idx": argmax_row["shot_idx"],
            "peak_value": peak_value,
            "mtf50_sensor_cy_per_px": mtf50_sensor,
            "mtf50_subject_lp_per_mm": mtf50_subject,
            "rail_position_mm_at_argmax": argmax_row["rail_position_mm"],
            "m": M,
            "m_source": argmax_row["m_source"],
            "tile_x_px": argmax_row["tile_x_px"],
            "tile_y_px": argmax_row["tile_y_px"],
            "lsf_roi_px": argmax_row["lsf_roi_px"],
            "maze_roi_px": argmax_row["maze_roi_px"],
        })
    return out
