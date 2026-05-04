"""Top-level orchestration: scan → detect → plot → render."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

from rail_coverage.cache import dump_cache, load_cache
from rail_coverage.detect import analyze_scenario
from rail_coverage.labels import slugify
from rail_coverage.plots import make_chart_png, write_chart
from rail_coverage.render import build_scenario_row, render_report, render_reshoot
from rail_coverage.scan import find_cropped_dirs, read_scenario


def run(
    sources: Path | list[Path],
    out: Path,
    *,
    verbose: bool = True,
    cache: Path | None = None,
    rescan: bool = False,
) -> int:
    """Walk every ``source``, analyze every scenario, and write the report.

    Accepts either a single ``Path`` or a list of paths so that multiple
    date trees can be folded into one report. Returns the number of
    scenarios processed.

    When ``cache`` is given:

    - If the file exists and ``rescan`` is False, scenarios are loaded
      from it and the filesystem walk is skipped.
    - Otherwise the filesystem is walked and the result is written to
      the cache for the next run.
    """
    if isinstance(sources, Path):
        sources = [sources]
    out.mkdir(parents=True, exist_ok=True)
    charts_dir = out / "assets" / "charts"
    _copy_static_assets(out)

    items: list[tuple[Path, "Scenario"]] = []  # noqa: F821 — runtime import only
    if cache is not None and cache.is_file() and not rescan:
        if verbose:
            print(f"loading scan from cache: {cache}", file=sys.stderr)
        cached = load_cache(cache)
        items = cached.items
    else:
        t0 = time.monotonic()
        discovered: list[tuple[Path, Path]] = []
        for source in sources:
            for cropped in sorted(find_cropped_dirs(source)):
                discovered.append((source, cropped))
        for i, (source, cropped) in enumerate(discovered, start=1):
            if verbose:
                print(f"[scan {i}/{len(discovered)}] {cropped}", file=sys.stderr)
            scenario = read_scenario(cropped)
            items.append((source, scenario))
        if verbose:
            print(
                f"scan done in {time.monotonic() - t0:.1f}s "
                f"({len(items)} scenarios)",
                file=sys.stderr,
            )
        if cache is not None:
            dump_cache(cache, sources, items)
            if verbose:
                print(f"wrote cache: {cache}", file=sys.stderr)

    t0 = time.monotonic()
    rows = []
    for i, (source, scenario) in enumerate(items, start=1):
        if verbose and i % 25 == 0:
            print(f"[render {i}/{len(items)}] {scenario.cropped_dir}", file=sys.stderr)
        analysis = analyze_scenario(scenario)
        rel = (
            scenario.cropped_dir.relative_to(source)
            if _is_relative(scenario.cropped_dir, source)
            else scenario.cropped_dir
        )
        # Prefix the scenario id with the source-root basename so two
        # trees with the same nested layout don't collide on slugs.
        slug = slugify(Path(source.name) / rel)
        for crop_analysis, crop_series in zip(analysis.crops, scenario.crops):
            sizes = [f.size for f in crop_series.frames]
            png = make_chart_png(sizes, peak_idx=crop_analysis.peak_idx)
            write_chart(charts_dir / slug / f"{crop_analysis.name}.png", png)
        rows.append(build_scenario_row(analysis, slug=slug))
    if verbose:
        print(f"render done in {time.monotonic() - t0:.1f}s", file=sys.stderr)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    source_label = ", ".join(str(s) for s in sources)
    (out / "report.html").write_text(
        render_report(rows, source=source_label, generated_at=generated_at)
    )
    (out / "reshoot.html").write_text(
        render_reshoot(rows, generated_at=generated_at)
    )
    return len(rows)


def _is_relative(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _copy_static_assets(out: Path) -> None:
    """Copy ``style.css`` (and any other static files) into ``out/assets/``."""
    assets_pkg = files("rail_coverage") / "assets"
    target_dir = out / "assets"
    target_dir.mkdir(parents=True, exist_ok=True)
    for entry in assets_pkg.iterdir():
        if entry.is_file():
            (target_dir / entry.name).write_bytes(entry.read_bytes())


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyse rail-coverage and crop validity for a tree of lens-test "
            "scenarios. Produces report.html and reshoot.html."
        )
    )
    parser.add_argument(
        "sources",
        type=Path,
        nargs="*",
        default=[Path(".")],
        help="One or more roots to scan; each contributes scenarios to a single combined report",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("output"),
        help="Output directory for report.html, reshoot.html and assets",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress per-scenario progress output"
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=None,
        help=(
            "Path to a JSON file that caches scan results. If the file "
            "exists, loaded instead of re-scanning the filesystem; "
            "otherwise, the scan output is written to it."
        ),
    )
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Force a fresh filesystem scan even if a cache file exists",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    sources = args.sources if args.sources else [Path(".")]
    n = run(
        sources,
        args.out,
        verbose=not args.quiet,
        cache=args.cache,
        rescan=args.rescan,
    )
    print(f"Processed {n} scenarios → {args.out}/report.html, {args.out}/reshoot.html")


if __name__ == "__main__":
    main()
