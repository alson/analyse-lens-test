"""Command-line interface.

Two subcommands::

    tile-sharpness list-sweeps [--family newer|older]
    tile-sharpness analyse <sweep-query> [<sweep-query>...] [options]

``<sweep-query>`` matches either an exact sweep id, a full label, or a
unique substring of a label.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .analyse import agreement_dataframe, analyse_sweep, peaks_dataframe
from .characterise import characterise_peaks_v2
from .compare import run_compare
from .cross_lens_export import export_cross_lens_crops, export_peaks_v2_crops
from .crop import DEFAULT_CACHE_ROOT
from .disagreement import export_disagreement
from .m_lookup import load_manifests
from .methods import METHODS, mtf_mapper_available
from .phase1 import analyse_sweep_phase1
from .plots import plot_agreement_summary, plot_sweep
from .sweeps import discover_all, discover_newer, discover_older, find_sweep


def _cmd_list(args: argparse.Namespace) -> int:
    if args.family == "newer":
        sweeps = discover_newer()
    elif args.family == "older":
        sweeps = discover_older()
    else:
        sweeps = discover_all()
    for s in sweeps:
        print(f"{s.id}\t{len(s.shots)} shots\t{s.lens}\t{s.aperture}")
    return 0


def _cmd_analyse(args: argparse.Namespace) -> int:
    if not mtf_mapper_available():
        active_default = ("filesize", "radial_fft", "edge_decay")
        print(
            "[warn] mtf_mapper not reachable over SSH on the remote host; "
            "method 'mtfmapper' will be skipped.",
            file=sys.stderr,
        )
    else:
        active_default = tuple(METHODS.keys())

    methods = tuple(args.methods.split(",")) if args.methods else active_default
    for m in methods:
        if m not in METHODS:
            print(f"unknown method {m!r}; choices: {list(METHODS)}", file=sys.stderr)
            return 2

    all_sweeps = discover_all()
    selected = []
    for q in args.sweep:
        try:
            selected.append(find_sweep(q, all_sweeps))
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    mlookup = load_manifests(list(args.manifest))
    if args.manifest:
        print(f"[setup] loaded {len(mlookup)} manifest rows from {len(args.manifest)} CSV(s)",
              flush=True)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    plots_dir = out / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    results = []
    all_phase1_rows: list[dict] = []
    all_peaks_v2_rows: list[dict] = []

    for sweep in selected:
        print(f"[analyse] {sweep.id}  ({len(sweep.shots)} shots)", flush=True)
        if not args.no_legacy:
            res = analyse_sweep(
                sweep,
                tile_size=args.tile,
                methods=methods,
                cache_root=args.cache_root,
                workers=args.workers,
            )
            results.append(res)
            plot_sweep(res, plots_dir / f"{_safe(sweep.label)}.png")
            n_picked = export_disagreement(res, out, top_k=args.top_disagreement)
            print(
                f"  legacy: on_target={sum(1 for lbl in res.labels.values() if lbl.on_target)}/"
                f"{len(res.tiles)}  disagreement_tiles_exported={len(n_picked)}",
                flush=True,
            )

        # Phase 1 + Phase 2 (LSF + maze-FFT + peaks_v2)
        phase1_rows, peaks_v2_rows = analyse_sweep_phase1(
            sweep, mlookup, cache_root=args.cache_root, workers=args.workers,
        )
        if not phase1_rows:
            print(f"  phase1: skipped (no measured M for sweep)", flush=True)
        else:
            all_phase1_rows.extend(phase1_rows)
            all_peaks_v2_rows.extend(peaks_v2_rows)
            m_val = phase1_rows[0]["m"]
            m_src = phase1_rows[0]["m_source"]
            n_tiles = len({(r["tile_ix"], r["tile_iy"]) for r in phase1_rows})
            print(
                f"  phase1: M={m_val:.3f} ({m_src})  tiles={n_tiles}  "
                f"rows={len(phase1_rows)}", flush=True,
            )

    if not args.no_legacy:
        peaks_df = peaks_dataframe(results)
        peaks_df.to_csv(out / "peaks.csv", index=False)
        agreement_df = agreement_dataframe(results)
        agreement_df.to_csv(out / "agreement.csv", index=False)
        plot_agreement_summary(agreement_df, plots_dir / "agreement_summary.png")
        print(
            f"[done] peaks.csv ({len(peaks_df)} rows), agreement.csv ({len(agreement_df)} rows)",
            flush=True,
        )

    if all_phase1_rows:
        pd.DataFrame(all_phase1_rows).to_csv(out / "per_shot_per_tile.csv", index=False)
        pd.DataFrame(all_peaks_v2_rows).to_csv(out / "peaks_v2.csv", index=False)
        print(
            f"[done] per_shot_per_tile.csv ({len(all_phase1_rows)} rows), "
            f"peaks_v2.csv ({len(all_peaks_v2_rows)} rows)",
            flush=True,
        )
    return 0


def _safe(name: str) -> str:
    return name.replace("/", "_")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tile-sharpness", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-sweeps", help="list discovered sweeps")
    p_list.add_argument("--family", choices=("newer", "older"))
    p_list.set_defaults(func=_cmd_list)

    p_run = sub.add_parser("analyse", help="run tile-sharpness analysis on selected sweeps")
    p_run.add_argument("sweep", nargs="+", help="sweep id or substring of label")
    p_run.add_argument("--tile", type=int, default=1024, help="tile size in pixels (multiple of 16)")
    p_run.add_argument(
        "--methods",
        type=str,
        default=None,
        help="comma-separated subset of methods (default: all available)",
    )
    p_run.add_argument(
        "--out", type=Path, default=Path("out"), help="output directory"
    )
    p_run.add_argument(
        "--cache-root",
        type=Path,
        default=DEFAULT_CACHE_ROOT,
        help=f"tile cache root (default: {DEFAULT_CACHE_ROOT})",
    )
    p_run.add_argument(
        "--workers", type=int, default=4, help="thread workers per scorer step"
    )
    p_run.add_argument(
        "--top-disagreement",
        type=int,
        default=8,
        help="top-K tile positions to export disagreement crops for",
    )
    p_run.add_argument(
        "--manifest",
        action="append",
        type=Path,
        default=[],
        help=(
            "wafer-manifest CSV (from archive-2026-05/measure_wafer_squares); "
            "repeatable. Provides measured magnification (M) per (slug, mag_label) "
            "for the M-driven LSF + maze-FFT pipeline. Falls back to path-parsed "
            "claimed_mag when no manifest covers a sweep."
        ),
    )
    p_run.add_argument(
        "--no-legacy",
        action="store_true",
        help=(
            "skip the legacy 8-method peaks.csv/agreement.csv pass; "
            "only run the LSF + maze-FFT pipeline. Useful for fast iteration "
            "on the new methodology."
        ),
    )
    p_run.set_defaults(func=_cmd_analyse)

    p_cmp = sub.add_parser(
        "compare",
        help="cross-lens + symmetric-corner aggregation over an existing peaks.csv",
    )
    p_cmp.add_argument("peaks_csv", type=Path)
    p_cmp.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default: parent of peaks_csv)",
    )
    p_cmp.set_defaults(func=_cmd_compare)

    p_xcrop = sub.add_parser(
        "cross-lens-crops",
        help="export side-by-side peak tiles per (method × lens) for selected tile positions",
    )
    p_xcrop.add_argument("peaks_csv", type=Path)
    p_xcrop.add_argument("--out", type=Path, required=True)
    p_xcrop.add_argument(
        "--tile",
        action="append",
        type=str,
        help="tile position as 'ix,iy' (repeatable, default: 0,0)",
    )
    p_xcrop.set_defaults(func=_cmd_cross_lens_crops)

    p_v2crop = sub.add_parser(
        "peaks-v2-crops",
        help=(
            "export one crop per (lens, tile) at the v2 primary-metric "
            "argmax shot (maze-FFT amp or scribe-LSF amp). Replaces the "
            "filesize-picked legacy crops from `cross-lens-crops`."
        ),
    )
    p_v2crop.add_argument("peaks_v2_csv", type=Path)
    p_v2crop.add_argument("--out", type=Path, required=True)
    p_v2crop.add_argument(
        "--tile",
        action="append",
        type=str,
        help="tile position as 'ix,iy' (repeatable, default: 0,0)",
    )
    p_v2crop.set_defaults(func=_cmd_peaks_v2_crops)

    p_char = sub.add_parser(
        "characterise",
        help="per-slug lens characteristics rollup from a peaks_v2.csv",
    )
    p_char.add_argument("peaks_v2_csv", type=Path)
    p_char.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output CSV (default: lens_characteristics.csv alongside peaks_v2.csv)",
    )
    p_char.set_defaults(func=_cmd_characterise)
    return parser


def _cmd_characterise(args: argparse.Namespace) -> int:
    out = args.out if args.out is not None else args.peaks_v2_csv.parent / "lens_characteristics.csv"
    n = characterise_peaks_v2(args.peaks_v2_csv, out)
    print(f"[done] {out} ({n} sweep rows)", flush=True)
    return 0


def _cmd_cross_lens_crops(args: argparse.Namespace) -> int:
    if args.tile:
        positions = [tuple(int(v) for v in t.split(",")) for t in args.tile]
    else:
        positions = [(0, 0)]
    export_cross_lens_crops(args.peaks_csv, args.out, positions)
    print(f"[done] cross-lens crops -> {args.out}", flush=True)
    return 0


def _cmd_peaks_v2_crops(args: argparse.Namespace) -> int:
    if args.tile:
        positions = [tuple(int(v) for v in t.split(",")) for t in args.tile]
    else:
        positions = [(0, 0)]
    export_peaks_v2_crops(args.peaks_v2_csv, args.out, positions)
    print(f"[done] peaks_v2 crops -> {args.out}", flush=True)
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    out = args.out if args.out is not None else args.peaks_csv.parent
    run_compare(args.peaks_csv, out)
    print(
        f"[done] cross_lens_per_tile.csv, cross_lens_centre.csv, "
        f"cross_lens_centre_agreement.csv, symmetric_corner.csv "
        f"-> {out}",
        flush=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
