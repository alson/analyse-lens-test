"""Empirical bellows-factor calibration via diffraction-tail alignment.

For each (lens, magnification, focal length) config in the existing
2026-01-29 and 2026-02-18 datasets, computes a per-F-dir sharpness
metric (peak JPEG file size across the ``cropped/center/`` shots)
and fits the small-aperture (diffraction-dominated) tail of the
resulting sharpness-vs-reported-aperture curve.

Then, for each extension-tube config, finds the horizontal shift
(in EV) that best aligns its curve to its bare-lens reference, and
compares that empirical shift against the formula-predicted shift.

This is the calibration step before any rename of 2026-02-18 F-dirs:
if predicted and empirical agree to within ~0.2 EV across configs,
the formula is trustworthy and can drive the rename. If not, the
empirical shifts are the ground truth.

Reference choices (in order of preference per config):
  1. Same base lens, same focal length, "1_1-resized" magnification
     (so the post-processing upscale factor matches).
  2. Same base lens at native MFD (e.g. bare 24-120 at 1_2.47).

Absolute anchor (optional separate check): the 55mm AIS at 1:1 in
2026-01-29 — its F-dir names are bellows-corrected by manual entry,
so they're already effective f-numbers (ground truth).

Usage::

    uv run python scripts/bellows_calibration.py \\
        --root ~/shared/files/pics/digikam/test-raw-data \\
        --dates 2026-02-18 \\
        --out out_bellows/calibration.csv
"""
from __future__ import annotations

import argparse
import csv
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Lens metadata. Focal lengths in mm. "F_inf" is the at-infinity widest
# f-number. "internal_focus_macro" lenses report bellows-corrected aperture
# from their own close focus; for those the per-tube bellows formula is
# `1 + L_tube / F_eff_close` where F_eff_close = F_inf / (f_reported_at_1to1 /
# F_inf). For non-IF-macros, the bare-at-MFD reported aperture is assumed
# effective (per the user's premise for IF non-macros like the 24-120) and
# the per-tube bellows uses `1 + L_tube / F_inf`.
# ---------------------------------------------------------------------------
LENS_DB = {
    # Z lenses (CPU; FX coverage)
    "NIKKOR Z 24-120mm f_4 S": {
        "F_inf": 4.0,
        "focal_modes": [24, 35, 50, 70, 85, 105, 120],
        "internal_focus_macro": False,
        # 24-120 reports f/4 across native focus range (per user note).
    },
    "NIKKOR Z MC 105mm f_2.8 S": {
        "F_inf": 2.8,
        "focal_modes": [105],
        "internal_focus_macro": True,
        "f_at_1to1": 4.5,  # camera reports this at 1:1
    },
    "NIKKOR Z MC 105mm f_2.8 VR S": {
        "F_inf": 2.8,
        "focal_modes": [105],
        "internal_focus_macro": True,
        "f_at_1to1": 4.5,
    },
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S": {
        "F_inf": 5.6,  # tele end where extension is typically used
        "focal_modes": [100, 200, 300, 400],
        "internal_focus_macro": False,
    },
    # F-mount manual-aperture (ground-truth: F-dir is effective)
    "Nikon Micro-Nikkor 55mm f_2.8 AIS": {
        "F_inf": 2.8,
        "focal_modes": [55],
        "internal_focus_macro": False,
        "manual_aperture_effective": True,  # F-dir is already effective f
    },
    "Nikon Micro-Nikkor Auto 55mm f_3.5": {
        "F_inf": 3.5,
        "focal_modes": [55],
        "internal_focus_macro": False,
        "manual_aperture_effective": True,
    },
}


# Tube length lookup (mm). Slug-tail substring → length.
TUBE_LENGTHS_MM = {
    "+ 10mm extension": 10,
    "+ 16mm extension": 16,
    "+ 26mm extension": 26,
    "+ 35mm extension": 35,
    "+ 45mm extension": 45,
    "+ 61mm extension": 61,
}


# ---------------------------------------------------------------------------
# Path parsing
# ---------------------------------------------------------------------------

F_DIR_RE = re.compile(r"^F(\d+(?:\.\d+)?)$")
MAG_DIR_RE = re.compile(r"^(\d+)_(\d+(?:\.\d+)?)(-resized)?$")
FOCAL_DIR_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*mm$")


@dataclass(frozen=True)
class FDirRef:
    """One F-dir worth of data."""
    date: str
    slug: str
    mag_str: str   # e.g. "1_1-resized", "1_2.47"
    focal_mm: float | None  # None when no focal subdir (2026-01-29 layout)
    aperture_f: float       # reported f-number
    path: Path
    is_resized: bool


def parse_f_dir(path: Path, root: Path) -> FDirRef | None:
    """Decode an F-dir path into structured metadata.

    Layout assumed:
        <root>/<date>/<slug>/<mag>[/<focal mm>]/F<n>/...

    Returns None for paths that don't fit (e.g. ``F<n>/cropped``,
    or unrelated dirs).
    """
    rel = path.relative_to(root)
    parts = rel.parts
    if len(parts) < 4:
        return None
    f_part = parts[-1]
    m_f = F_DIR_RE.match(f_part)
    if not m_f:
        return None
    aperture = float(m_f.group(1))

    # parts[0] = date, parts[1] = slug
    date = parts[0]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return None
    slug = parts[1]

    # mag dir + optional focal dir
    if len(parts) == 5:
        mag_str = parts[2]
        focal_str = parts[3]
        m_focal = FOCAL_DIR_RE.match(focal_str)
        if not m_focal:
            return None
        focal_mm = float(m_focal.group(1))
    elif len(parts) == 4:
        mag_str = parts[2]
        focal_mm = None
    else:
        return None
    if not MAG_DIR_RE.match(mag_str):
        return None
    is_resized = mag_str.endswith("-resized")

    return FDirRef(date, slug, mag_str, focal_mm, aperture, path, is_resized)


def magnification_from_str(mag_str: str) -> float:
    """1_2.47 → 0.405, 2_1 → 2.0, 1_1-resized → 1.0."""
    s = mag_str.replace("-resized", "")
    m = MAG_DIR_RE.match(s)
    assert m is not None, f"unparseable mag: {mag_str!r}"
    num = float(m.group(1))
    den = float(m.group(2))
    return num / den


_LENS_ALIASES = {
    # Same optical design — early labelling differences.
    "NIKKOR Z MC 105mm f_2.8 S": "NIKKOR Z MC 105mm f_2.8 VR S",
}


def base_lens_from_slug(slug: str) -> tuple[str, int | None]:
    """Strip ``+ Nmm extension`` and return (base_slug, tube_length_mm).

    Returns (slug, None) if no tube suffix is found. Base slug is also
    aliased through ``_LENS_ALIASES`` so different labellings of the
    same lens model match.
    """
    for tail, mm in TUBE_LENGTHS_MM.items():
        if slug.endswith(tail):
            base = slug[: -len(tail)].rstrip()
            return _LENS_ALIASES.get(base, base), mm
    return _LENS_ALIASES.get(slug, slug), None


# ---------------------------------------------------------------------------
# Sharpness aggregation
# ---------------------------------------------------------------------------

def peak_center_filesize(f_dir: Path) -> tuple[int, int] | None:
    """Across all JPGs in ``<f_dir>/cropped/center/``, return
    (max_size_bytes, n_files). The max is the best-focused shot in
    the rail sweep — that's the canonical sharpness peak.

    Returns None if no center crops exist.
    """
    center = f_dir / "cropped" / "center"
    if not center.is_dir():
        return None
    sizes = [p.stat().st_size for p in center.iterdir() if p.suffix.lower() in {".jpg", ".jpeg"}]
    if not sizes:
        return None
    return max(sizes), len(sizes)


def walk_dataset(root: Path, dates: list[str]) -> list[FDirRef]:
    refs = []
    for d in dates:
        date_root = root / d
        if not date_root.is_dir():
            continue
        for path in date_root.rglob("F*"):
            if not path.is_dir():
                continue
            if "cropped" in path.parts:
                continue
            ref = parse_f_dir(path, root)
            if ref is None:
                continue
            refs.append(ref)
    return refs


# ---------------------------------------------------------------------------
# Diffraction-tail fit & alignment
# ---------------------------------------------------------------------------

def diffraction_tail_mask(apertures: list[float], threshold: float = 8.0) -> list[bool]:
    """Indicator for the small-aperture tail (>= threshold f-number).
    f/8 is the empirical break-even on Z7: by here diffraction is the
    dominant loss term for most lens-extension setups.
    """
    return [a >= threshold for a in apertures]


def empirical_ev_shift(
    ref_apertures: list[float], ref_sharpness: list[float],
    tgt_apertures: list[float], tgt_sharpness: list[float],
    tail_threshold: float = 8.0,
) -> tuple[float, float, int] | None:
    """For two sharpness curves (sharpness as a fn of reported f-number),
    find the horizontal shift in EV that best aligns the diffraction
    tails. Both curves must overlap in the tail region (after shifting).

    Returns ``(ev_shift, residual_rms_log_sharpness, n_tail_points)`` or
    None if not enough overlap.

    The shift is defined so ``f_eff_target = f_reported_target * 2**(ev_shift/2)``.
    Positive means the target has more bellows than the reference.
    """
    # Operate in log space: log(F) is linear in EV (log2(F)*2 = EV).
    if not ref_sharpness or not tgt_sharpness:
        return None

    # Normalise each curve by its OWN max so absolute scale (e.g. upscale
    # factor differences) cancel out. Use only points where reported f
    # is in the small-aperture regime.
    ref = sorted(zip(ref_apertures, ref_sharpness))
    tgt = sorted(zip(tgt_apertures, tgt_sharpness))
    if not ref or not tgt:
        return None
    ref_max = max(s for _, s in ref)
    tgt_max = max(s for _, s in tgt)
    if ref_max <= 0 or tgt_max <= 0:
        return None
    ref_norm = [(f, s / ref_max) for f, s in ref]
    tgt_norm = [(f, s / tgt_max) for f, s in tgt]

    # Linear interp helper in log2(F) space:
    def interp(curve, x):
        xs = [math.log2(f) for f, _ in curve]
        ys = [s for _, s in curve]
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        for i in range(1, len(xs)):
            if xs[i] >= x:
                t = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
                return ys[i - 1] * (1 - t) + ys[i] * t
        return ys[-1]

    # 1-D grid search over shift in EV; finer around minimum.
    def residual(ev):
        shift_log2 = ev / 2.0  # log2 = EV/2
        tail = [(f, s) for f, s in tgt_norm if f >= tail_threshold]
        if not tail:
            return None, 0
        residuals = []
        for f_tgt, s_tgt in tail:
            f_ref_equiv_log2 = math.log2(f_tgt) + shift_log2
            s_ref = interp(ref_norm, f_ref_equiv_log2)
            # Compare in log-sharpness space; clip to avoid log(0).
            r = math.log(max(s_tgt, 1e-6)) - math.log(max(s_ref, 1e-6))
            residuals.append(r * r)
        return sum(residuals) ** 0.5 / max(1, len(residuals)), len(residuals)

    # Coarse grid then refine.
    best_ev = 0.0
    best_res = float("inf")
    best_n = 0
    for ev in [x * 0.1 for x in range(-30, 31)]:  # -3.0 to +3.0 EV in 0.1 steps
        res, n = residual(ev)
        if res is None:
            continue
        if res < best_res:
            best_res = res
            best_ev = ev
            best_n = n
    # Refine
    for ev_off in [x * 0.01 for x in range(-10, 11)]:
        ev = best_ev + ev_off
        res, n = residual(ev)
        if res is None:
            continue
        if res < best_res:
            best_res = res
            best_ev = ev
            best_n = n
    if best_n == 0:
        return None
    return best_ev, best_res, best_n


# ---------------------------------------------------------------------------
# Formula predictions
# ---------------------------------------------------------------------------

def predict_shift_if_lens(L_tube_mm: float, F_inf_mm: float) -> float:
    """For lens that compensates internally so reported = effective at native
    MFD: tube bellows = (1 + L_tube / F_inf). Returns EV shift."""
    if L_tube_mm <= 0 or F_inf_mm <= 0:
        return 0.0
    return 2.0 * math.log2(1.0 + L_tube_mm / F_inf_mm)


def predict_shift_honest_macro(L_tube_mm: float, F_eff_close_mm: float) -> float:
    """For IF macro that reports honest bellows at close focus: tube adds
    on top of the lens's own close-focus state."""
    if L_tube_mm <= 0 or F_eff_close_mm <= 0:
        return 0.0
    return 2.0 * math.log2(1.0 + L_tube_mm / F_eff_close_mm)


def derive_F_eff_close(F_inf: float, f_at_1to1: float, F_nominal_mm: float) -> float:
    """For IF macro: F_eff_close = F_nominal / (f_at_1to1 / F_inf)."""
    return F_nominal_mm / (f_at_1to1 / F_inf)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

@dataclass
class ConfigCurve:
    date: str
    slug: str
    base_lens: str
    tube_mm: int | None
    mag_str: str
    focal_mm: float | None
    apertures: list[float]
    sharpness: list[float]
    n_shots_per_aperture: list[int]


def aggregate_curves(refs: list[FDirRef]) -> list[ConfigCurve]:
    """Group F-dirs by (date, slug, mag_str, focal_mm) and produce one
    aperture-sharpness curve per group, sorted by aperture."""
    buckets: dict[tuple, list[tuple[float, int, int]]] = defaultdict(list)
    for r in refs:
        result = peak_center_filesize(r.path)
        if result is None:
            continue
        peak, n = result
        buckets[(r.date, r.slug, r.mag_str, r.focal_mm)].append(
            (r.aperture_f, peak, n)
        )

    curves = []
    for (date, slug, mag_str, focal_mm), entries in buckets.items():
        entries.sort()
        apertures = [e[0] for e in entries]
        sharpness = [float(e[1]) for e in entries]
        n_shots = [e[2] for e in entries]
        base_lens, tube_mm = base_lens_from_slug(slug)
        curves.append(ConfigCurve(
            date=date, slug=slug, base_lens=base_lens, tube_mm=tube_mm,
            mag_str=mag_str, focal_mm=focal_mm,
            apertures=apertures, sharpness=sharpness,
            n_shots_per_aperture=n_shots,
        ))
    return curves


def find_reference(curves: list[ConfigCurve], target: ConfigCurve) -> ConfigCurve | None:
    """Find the best bare-lens reference for a tube-config target.

    Priority:
      1. Same base lens, same focal_mm, same mag_str (so upscale factor
         matches), zero tube.
      2. Same base lens, same focal_mm, native MFD bare (any mag_str
         without -resized), zero tube.
    """
    if target.tube_mm is None:
        return None  # target IS a reference
    candidates_a = [
        c for c in curves
        if c.tube_mm is None
        and c.base_lens == target.base_lens
        and c.focal_mm == target.focal_mm
        and c.mag_str == target.mag_str
    ]
    if candidates_a:
        return candidates_a[0]
    candidates_b = [
        c for c in curves
        if c.tube_mm is None
        and c.base_lens == target.base_lens
        and c.focal_mm == target.focal_mm
        and not c.mag_str.endswith("-resized")
    ]
    if candidates_b:
        return candidates_b[0]
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path,
                   default=Path.home() / "shared/files/pics/digikam/test-raw-data",
                   help="NFS root containing date-stamped trees.")
    p.add_argument("--dates", nargs="+",
                   default=["2026-01-29", "2026-02-18"],
                   help="Date dirs under --root to walk.")
    p.add_argument("--out", type=Path,
                   default=Path("out_bellows/calibration.csv"),
                   help="Output CSV path.")
    p.add_argument("--tail-threshold", type=float, default=8.0,
                   help="Smallest reported f-number to include in tail fit.")
    args = p.parse_args(argv)

    print(f"Walking {args.root} for dates {args.dates}…")
    refs = walk_dataset(args.root, args.dates)
    print(f"  {len(refs)} F-dirs found")

    print("Aggregating per-F-dir sharpness (peak center-crop file size)…")
    curves = aggregate_curves(refs)
    print(f"  {len(curves)} (date, slug, mag, focal) groups")

    # Build output rows. Bare-lens configs are emitted too so the
    # reference curves are visible alongside the tube configs.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n_calibrated = 0
    rows = []
    for target in sorted(curves, key=lambda c: (c.base_lens, c.focal_mm or 0, c.tube_mm or 0, c.mag_str)):
        if target.tube_mm is None:
            rows.append(_row(target, None, None, None, None, "bare-reference"))
            continue
        ref = find_reference(curves, target)
        if ref is None:
            rows.append(_row(target, None, None, None, None, "no-bare-reference"))
            continue
        result = empirical_ev_shift(
            ref.apertures, ref.sharpness,
            target.apertures, target.sharpness,
            tail_threshold=args.tail_threshold,
        )
        if result is None:
            rows.append(_row(target, ref, None, None, None, "no-tail-overlap"))
            continue
        ev_emp, residual, n_tail = result
        # Formula prediction(s). Use IF-lens formula if marked IF macro;
        # otherwise use the "lens-compensates-fully" formula.
        lens_meta = LENS_DB.get(target.base_lens, {})
        F_inf = lens_meta.get("F_inf")
        if lens_meta.get("internal_focus_macro") and "f_at_1to1" in lens_meta:
            F_eff_close = derive_F_eff_close(
                F_inf, lens_meta["f_at_1to1"], target.focal_mm or 105
            )
            ev_pred_honest = predict_shift_honest_macro(target.tube_mm, F_eff_close)
        else:
            ev_pred_honest = None
        if F_inf is not None and target.focal_mm:
            ev_pred_if = predict_shift_if_lens(target.tube_mm, target.focal_mm)
        else:
            ev_pred_if = None
        rows.append(_row(
            target, ref,
            ev_emp=ev_emp,
            ev_pred_if=ev_pred_if,
            ev_pred_honest=ev_pred_honest,
            note=f"residual={residual:.3f} n_tail={n_tail}",
        ))
        n_calibrated += 1

    # Write CSV
    with args.out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "date", "slug", "base_lens", "tube_mm",
            "mag_str", "magnification", "focal_mm",
            "n_apertures", "apertures", "peak_sharpness",
            "ref_date", "ref_slug", "ref_mag",
            "ev_shift_empirical",
            "ev_shift_pred_if_compensating",  # (1 + L/F_inf) prediction
            "ev_shift_pred_honest_macro",     # (1 + L/F_eff_close) prediction
            "note",
        ])
        for r in rows:
            w.writerow(r)

    print(f"\nWrote {len(rows)} rows ({n_calibrated} calibrated) to {args.out}")
    _print_summary(rows)
    return 0


def _row(target, ref, ev_emp, ev_pred_if, ev_pred_honest, note):
    return [
        target.date, target.slug, target.base_lens,
        target.tube_mm if target.tube_mm is not None else "",
        target.mag_str, f"{magnification_from_str(target.mag_str):.3f}",
        target.focal_mm if target.focal_mm is not None else "",
        len(target.apertures),
        ";".join(f"{a:g}" for a in target.apertures),
        ";".join(f"{s:.0f}" for s in target.sharpness),
        ref.date if ref else "", ref.slug if ref else "", ref.mag_str if ref else "",
        f"{ev_emp:.3f}" if ev_emp is not None else "",
        f"{ev_pred_if:.3f}" if ev_pred_if is not None else "",
        f"{ev_pred_honest:.3f}" if ev_pred_honest is not None else "",
        note,
    ]


def _print_summary(rows):
    print()
    print("=" * 100)
    print(f"{'lens / tube / mag / focal':<70} {'empirical':>10} {'pred_IF':>9} {'pred_macro':>11}")
    print("=" * 100)
    for r in rows:
        if not r[13]:  # no empirical
            continue
        label = f"{r[2]} +{r[3]}mm  m={r[5]} @{r[6]}mm" if r[3] != "" else r[2]
        emp = r[13]
        pred_if = r[14] or "—"
        pred_macro = r[15] or "—"
        print(f"{label:<70} {emp:>10} {pred_if:>9} {pred_macro:>11}")


if __name__ == "__main__":
    raise SystemExit(main())
