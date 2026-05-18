"""Validate v1/v2 rail-step calibration against archived 2026-05 newer-rig data.

Uses the post-rename archive at
``~/shared/files/pics/digikam/test-raw-data/2026-05-{13,14,15}/<lens>/<F_dir>/``
which is on NFS and accessible from nufan too. Each ``<lens>`` dir is
self-contained with ``metadata.json`` (carrying ``magnification`` and
``sample_plan.rail_step_mm`` for ground truth) and ``shots.csv``
(per-shot ``rail_position_mm``). Aperture sub-dirs are post-rename
(rounded effective), and the corresponding exact effective f comes from
``effective_apertures.csv`` at the date root.

For each (lens_config, F_dir) sweep:
  * Build a ``Sweep`` of ``Shot``s from the ``step_*.jpg`` files.
  * Monkey-patch ``phase1.resolve`` to inject M from metadata.json.
  * Run phase1; capture per_shot_per_tile + peaks_v2 rows.
  * Compute ground-truth per-shot rail step from shots.csv replicas.
  * Look up exact effective_f from effective_apertures.csv.
  * Run v1 calibration; compare derived vs actual; write comparison.csv.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

import tile_sharpness.phase1 as phase1_mod
from tile_sharpness.m_lookup import MagLookup, MLookup
from tile_sharpness.rail_calibration import (
    EffectiveApertureLookup, calibrate_sweep, parse_aperture,
)
from tile_sharpness.sweeps import Shot, Sweep

ARCHIVE_ROOTS = [
    Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13"),
    Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-14"),
    Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-15"),
]
EFF_AP_CSVS = [r / "effective_apertures.csv" for r in ARCHIVE_ROOTS]
OUT_DIR = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness/out_newer_validation_2026_05")

STEP_FILENAME_RE = re.compile(r"^step_(\d+)\.jpg$", re.IGNORECASE)


def discover_archived_sweeps() -> list[tuple[Sweep, float]]:
    """Walk the archive; yield ``(Sweep, M)`` per (lens_config, F_dir) found."""
    out: list[tuple[Sweep, float]] = []
    for root in ARCHIVE_ROOTS:
        if not root.is_dir():
            continue
        for lens_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            metadata_path = lens_dir / "metadata.json"
            if not metadata_path.exists():
                continue
            try:
                meta = json.loads(metadata_path.read_text())
            except Exception:
                continue
            cfg = meta.get("lens_config", {})
            M = float(cfg.get("magnification") or float("nan"))
            slug = cfg.get("slug") or lens_dir.name
            shots_csv = lens_dir / "shots.csv"
            if not shots_csv.exists():
                continue
            shots_df = pd.read_csv(shots_csv)
            for f_dir in sorted(p for p in lens_dir.iterdir() if p.is_dir()):
                if not f_dir.name.lower().startswith("f_"):
                    continue
                # Collect images, ordered by step number.
                entries: list[tuple[int, Path]] = []
                for jpg in f_dir.glob("step_*.jpg"):
                    m = STEP_FILENAME_RE.match(jpg.name)
                    if m:
                        entries.append((int(m.group(1)), jpg))
                if len(entries) < 3:
                    continue
                entries.sort()
                # Match shots.csv rows to filenames to get rail_position_mm.
                fname_to_rail: dict[str, float | None] = {}
                f_dir_rel = f_dir.name + "/"  # filename in shots.csv has "f_X/step_NNNN.jpg" form
                for _, row in shots_df.iterrows():
                    if str(row.get("phase")) != "sweep":
                        continue
                    fname = str(row.get("filename") or "")
                    if not fname.startswith(f_dir_rel):
                        continue
                    try:
                        rm = float(row.get("rail_position_mm"))
                    except (TypeError, ValueError):
                        rm = None
                    fname_to_rail[fname.split("/", 1)[1]] = rm
                shots: list[Shot] = []
                for k, (_, p) in enumerate(entries):
                    rm = fname_to_rail.get(p.name)
                    shots.append(Shot(path=p, rail_step=k, rail_position_mm=rm))
                if not shots:
                    continue
                label = f"{root.name}__{slug}__{f_dir.name}"
                sweep = Sweep(
                    label=label, family="archive-2026-05",
                    lens=slug, aperture=f_dir.name, shots=shots,
                )
                out.append((sweep, M))
    return out


def ground_truth_per_shot_step(shots_csv: Path, lens: str, f_dir: str) -> float | None:
    """Per-shot-idx rail step (mm) for one (lens, F_dir), folding in replicas."""
    df = pd.read_csv(shots_csv)
    sweep = df[(df["phase"] == "sweep") & (df["lens_config_slug"] == lens)].copy()
    sweep = sweep[sweep["filename"].astype(str).str.startswith(f_dir + "/")]
    if sweep.empty:
        return None
    rmm = sweep.sort_values("rail_step")["rail_position_mm"].astype(float).values
    if len(rmm) < 2:
        return None
    n_unique = len(set(rmm.tolist()))
    if n_unique < 2:
        return None
    per_pos = abs(rmm.max() - rmm.min()) / (n_unique - 1)
    return per_pos / (len(sweep) / n_unique)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    ea_lookup = EffectiveApertureLookup.from_csvs([p for p in EFF_AP_CSVS if p.exists()])
    print(f"effective_apertures: {len(ea_lookup.table)} (slug, F_dir) entries from "
          f"{sum(1 for p in EFF_AP_CSVS if p.exists())} CSV(s)")

    sweeps_with_m = discover_archived_sweeps()
    print(f"Discovered {len(sweeps_with_m)} archived sweeps")
    if not sweeps_with_m:
        return

    # M lookup table keyed by sweep.label
    label_to_m = {sw.label: m for sw, m in sweeps_with_m}

    original_resolve = phase1_mod.resolve

    def patched_resolve(sweep, mlookup):
        m = label_to_m.get(sweep.label)
        if m is not None and m == m and m > 0:
            return MagLookup(measured=m, source="metadata_json", confidence="planned")
        return original_resolve(sweep, mlookup)

    phase1_mod.resolve = patched_resolve

    all_rows, peaks_rows = [], []
    mlookup = MLookup()
    for i, (sweep, M) in enumerate(sweeps_with_m, 1):
        if not (M == M and M > 0):
            print(f"[{i}/{len(sweeps_with_m)}] SKIP (M missing): {sweep.label}")
            continue
        print(f"[{i}/{len(sweeps_with_m)}] {sweep.label}  ({len(sweep.shots)} shots, M={M:.3f})", flush=True)
        rows, peaks = phase1_mod.analyse_sweep_phase1(sweep, mlookup, workers=16)
        print(f"  → {len(rows)} rows, {len(peaks)} peaks", flush=True)
        all_rows.extend(rows)
        peaks_rows.extend(peaks)

    pd.DataFrame(all_rows).to_csv(OUT_DIR / "per_shot_per_tile.csv", index=False)
    pd.DataFrame(peaks_rows).to_csv(OUT_DIR / "peaks_v2.csv", index=False)
    print(f"\nWrote {OUT_DIR / 'per_shot_per_tile.csv'}")

    # Comparison.
    df = pd.read_csv(OUT_DIR / "per_shot_per_tile.csv")
    comparison_rows = []
    for sweep, M in sweeps_with_m:
        sweep_id = f"{sweep.family}/{sweep.label}"
        grp = df[df["sweep"] == sweep_id]
        if grp.empty:
            continue
        # Ground truth from the shots.csv for this lens_config
        shots_csv = sweep.shots[0].path.parent.parent / "shots.csv"
        actual = ground_truth_per_shot_step(shots_csv, sweep.lens, sweep.aperture)
        eff_f = ea_lookup.get(sweep.lens, sweep.aperture)
        res = calibrate_sweep(grp, effective_aperture=eff_f)
        slug_f = parse_aperture(sweep_id)
        comparison_rows.append({
            "lens": sweep.lens,
            "F_dir": sweep.aperture,
            "M": M,
            "slug_f": slug_f,
            "csv_effective_f": eff_f,
            "f_used": res.aperture_f,
            "actual_rail_step_mm": actual,
            "derived_rail_step_mm": res.rail_step_mm,
            "ratio": (res.rail_step_mm / actual) if actual else None,
            "n_estimates": res.n_estimates,
            "rel_uncertainty": res.rel_uncertainty,
            "verdict": res.verdict,
            "note": res.note,
        })

    cdf = pd.DataFrame(comparison_rows)
    cdf.to_csv(OUT_DIR / "comparison.csv", index=False)
    print()
    print("=== Comparison ===")
    print(cdf.to_string(index=False))


if __name__ == "__main__":
    main()
