"""Archive completed 2026-05 lens-test shoots to NFS test-raw-data.

Step 0 of the archive pipeline. Reads :mod:`archive_2026_05.manifest`
(the encoded audit decisions from
``analyse-lens-test/merge-audit-2026-05.md``) and routes each
``(session_id, lens-config-slug)`` pair to a destination — flat
lens-config dirs under both date roots, matching the shape of the
existing ``test-raw-data/2026-01-29/<slug>/...`` archive:

* ``merge_source`` and ``superseded`` → ``<nfs>/2026-05-12/<slug>
  (<session_id>)/`` — flat lens-config dirs, raw archive. The
  ``(session_id)`` suffix disambiguates same-slug entries.
* ``canonical`` and ``labeled_duplicate`` → ``<nfs>/2026-05-13/
  <slug>/`` — flat lens-config dirs. Step 4 (``sort_to_lens_tree.py``)
  later adds ``<mag>/<focal>/<F>/`` subdirs inside each.
* Each merged dir's output slug → ``<nfs>/2026-05-13/<output_slug>/``
  with every relative symlink rewritten to point at the
  corresponding 2026-05-12 destination. The merge's ``shots.csv``
  travels with it.

Provenance (which source session each config came from) lives in
each dir's ``metadata.json`` rather than in the path.

The script is idempotent — destinations that already exist are
skipped rather than overwritten. Use ``--dry-run`` to see what
would happen without copying.

Runs on bumblebee (where the source lives). Subsequent pipeline
steps (``measure_wafer_squares.py``, ``rename_for_digikam.py``,
``sort_to_lens_tree.py``) are intended to run on nufan over SSH.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from archive_2026_05.manifest import (
    ENTRIES,
    MERGED_DIRS,
    SKIP_SESSIONS,
    Entry,
    calibration_methodology,
    entries_by_role,
)


# ---- Pure helpers ---------------------------------------------------------


def archive_12_dir_name(slug: str, session_id: str) -> str:
    """Directory name under 2026-05-12 for a (slug, session) pair.

    The ``(session_id)`` suffix disambiguates same-slug entries — the
    four ⛔ MC 105 + 61mm dev-era shoots all share the same slug, and
    `2026-05-15_093455` provides both a 35mm-merge-source and a 61mm
    canonical entry. The suffix collapses to a unique path either way.
    """
    return f"{slug} ({session_id})"


def slice_shots_csv(source_csv: Path, slug: str, dest_csv: Path) -> int:
    """Write rows from ``source_csv`` whose ``lens_config_slug``
    column equals ``slug``, prepended with the header row. Returns
    the number of data rows written.

    Reads byte-for-byte and splits on commas — fast and matches
    the runner's writer (which doesn't quote fields).
    """
    with source_csv.open(encoding="utf-8") as src:
        header = src.readline()
        cols = [c.strip() for c in header.rstrip("\n").split(",")]
        try:
            slug_idx = cols.index("lens_config_slug")
        except ValueError as exc:
            raise RuntimeError(
                f"{source_csv}: 'lens_config_slug' column not in header {cols}"
            ) from exc
        rows = 0
        with dest_csv.open("w", encoding="utf-8") as dst:
            dst.write(header)
            for line in src:
                fields = line.split(",")
                if len(fields) > slug_idx and fields[slug_idx].strip() == slug:
                    dst.write(line)
                    rows += 1
    return rows


def build_metadata(source_session: Path, entry: Entry) -> dict:
    """Construct the per-config ``metadata.json`` content from the
    parent session's ``session.json`` and the manifest entry.

    Falls back gracefully when ``session.json`` is missing or its
    ``lens_configs`` array is empty (some early/aborted sessions
    never populated those fields).
    """
    session_json = source_session / "session.json"
    if session_json.exists():
        session = json.loads(session_json.read_text(encoding="utf-8"))
    else:
        session = {}
    matching = next(
        (lc for lc in session.get("lens_configs", []) if lc.get("slug") == entry.slug),
        None,
    )
    if matching is None:
        # Synthetic lens-config record so downstream consumers always
        # see a uniform shape; magnification verified in step 1.
        matching = {
            "slug": entry.slug,
            "magnification": None,
            "widest_aperture": None,
            "sample_plan": None,
        }
    matching = dict(matching)
    matching.setdefault("magnification_verified_via_wafer_squares", None)
    started_at = session.get("started_at", "")
    return {
        "session_id": entry.session_id,
        "started_at": started_at,
        "ended_at": session.get("ended_at"),
        "calibration_methodology": calibration_methodology(started_at),
        "role": entry.role,
        "reason": entry.reason or None,
        "lens_config": matching,
    }


def parse_merged_symlink_target(target: str) -> tuple[str, str, list[str]] | None:
    """Parse a relative symlink target written by ``merge_sessions.py``
    of the form ``../../<n>../<session_id>/<src_slug>/<rest>``.

    Returns ``(session_id, src_slug, [rest...])`` or ``None`` if the
    path doesn't look like a merged-session symlink. ``session_id``
    is matched by the ``YYYY-MM-DD_HHMMSS`` shape (17 chars with
    dashes at 4/7 and underscore at 10).
    """
    parts = target.split("/")
    for i, part in enumerate(parts):
        if (
            len(part) == 17
            and part[4] == "-"
            and part[7] == "-"
            and part[10] == "_"
            and part[:4].isdigit()
        ):
            if i + 2 < len(parts):
                return part, parts[i + 1], parts[i + 2 :]
    return None


# ---- Filesystem operations ------------------------------------------------


@dataclass
class CopyStats:
    skipped_existing: int = 0
    copied: int = 0
    missing_source: int = 0


def copy_lens_config_payload(
    src_dir: Path, dst_dir: Path, *, dry_run: bool
) -> None:
    """Mirror ``src_dir``'s aperture subdirs (``f_<n>/``) into
    ``dst_dir``, preserving any internal symlinks. Skips files at the
    parent session level (``shots.csv`` / ``session.json``) — the
    caller writes the sliced versions separately.
    """
    if dry_run:
        print(f"      [dry] copy aperture subdirs from {src_dir}")
        return
    for child in src_dir.iterdir():
        if child.is_dir():
            target = dst_dir / child.name
            if target.exists():
                continue
            shutil.copytree(child, target, symlinks=True)


def archive_entry(
    entry: Entry, *, source_root: Path, nfs_root: Path, dry_run: bool,
    stats: CopyStats,
) -> None:
    src = source_root / entry.session_id / entry.slug
    if not src.exists():
        print(f"  WARN: source missing → {src}")
        stats.missing_source += 1
        return

    if entry.role in ("merge_source", "superseded"):
        dst_root = nfs_root / "2026-05-12" / archive_12_dir_name(entry.slug, entry.session_id)
        date_label = "2026-05-12"
    elif entry.role in ("canonical", "labeled_duplicate"):
        # Flat slug-level: matches the existing test-raw-data/2026-01-29
        # convention. Step 4 will add <mag>/<focal>/<F>/ subdirs.
        dst_root = nfs_root / "2026-05-13" / entry.slug
        date_label = "2026-05-13"
    else:
        raise ValueError(f"unknown role: {entry.role}")

    if dst_root.exists() and any(dst_root.iterdir()) and not dry_run:
        print(f"  [skip-existing] {date_label}/.../{dst_root.name}")
        stats.skipped_existing += 1
        return

    print(f"  [{date_label}] {entry.session_id}/{entry.slug}  (role={entry.role})")
    if not dry_run:
        dst_root.mkdir(parents=True, exist_ok=True)
    copy_lens_config_payload(src, dst_root, dry_run=dry_run)

    src_csv = source_root / entry.session_id / "shots.csv"
    if src_csv.exists():
        if dry_run:
            print(f"      [dry] slice shots.csv for slug={entry.slug!r}")
        else:
            rows = slice_shots_csv(src_csv, entry.slug, dst_root / "shots.csv")
            print(f"      shots.csv: {rows} rows")

    metadata = build_metadata(source_root / entry.session_id, entry)
    if dry_run:
        print(f"      [dry] write metadata.json (role={entry.role}, methodology={metadata['calibration_methodology']})")
    else:
        (dst_root / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    stats.copied += 1


def build_05_12_lookup(nfs_root: Path) -> dict[tuple[str, str], Path]:
    """Build the ``(session_id, src_slug) → 2026-05-12 dir`` map used
    to rewrite merged-dir symlink targets.
    """
    lookup: dict[tuple[str, str], Path] = {}
    for entry in ENTRIES:
        if entry.role in ("merge_source", "superseded"):
            dst = nfs_root / "2026-05-12" / archive_12_dir_name(entry.slug, entry.session_id)
            lookup[(entry.session_id, entry.slug)] = dst
    return lookup


def _read_merge_session_json(merged_src: Path) -> dict:
    js = merged_src / "session.json"
    if not js.exists():
        raise RuntimeError(f"merged dir missing session.json: {merged_src}")
    return json.loads(js.read_text(encoding="utf-8"))


def _earliest_source_started_at(merge_meta: dict, source_root: Path) -> str:
    """Return the earliest ``started_at`` across the merge's source
    sessions, used for D4 cascade-methodology classification. Falls
    back to ``merge_created_at`` if no source session.json is readable.
    """
    earliest = ""
    for src in merge_meta.get("source_sessions", []):
        sid = src.get("session_id")
        if not sid:
            continue
        sjs = source_root / sid / "session.json"
        if not sjs.exists():
            continue
        try:
            started = json.loads(sjs.read_text(encoding="utf-8")).get("started_at", "")
        except (json.JSONDecodeError, OSError):
            continue
        if started and (not earliest or started < earliest):
            earliest = started
    return earliest or merge_meta.get("merge_created_at", "")


def build_merge_metadata(merged_src: Path, output_slug: str, source_root: Path) -> dict:
    """metadata.json for an archived merged config. Mirrors the
    structure used for regular sessions plus a ``merge_info`` block
    that captures provenance the merge tool already wrote.
    """
    merge_meta = _read_merge_session_json(merged_src)
    started_at = _earliest_source_started_at(merge_meta, source_root)
    return {
        "session_id": merged_src.name,
        "started_at": started_at,
        "ended_at": None,
        "calibration_methodology": calibration_methodology(started_at),
        "role": "merged",
        "reason": None,
        "lens_config": {
            "slug": output_slug,
            "magnification": None,
            "widest_aperture": None,
            "sample_plan": None,
            "magnification_verified_via_wafer_squares": None,
        },
        "merge_info": {
            "output_slug": merge_meta.get("output_slug", output_slug),
            "overlap_strategy": merge_meta.get("overlap_strategy"),
            "merge_created_at": merge_meta.get("merge_created_at"),
            "source_sessions": merge_meta.get("source_sessions", []),
            "row_counts": merge_meta.get("row_counts", {}),
        },
    }


def archive_merged_dir(
    merged_id: str, *, source_root: Path, nfs_root: Path,
    lookup: dict[tuple[str, str], Path], dry_run: bool, stats: CopyStats,
) -> None:
    merged_src = source_root / merged_id
    if not merged_src.exists():
        print(f"  WARN: merged source missing → {merged_src}")
        stats.missing_source += 1
        return

    merge_meta = _read_merge_session_json(merged_src)
    output_slug = merge_meta.get("output_slug") or (merge_meta.get("lens_configs") or [None])[0]
    if not output_slug:
        raise RuntimeError(f"can't determine output_slug for {merged_id}")

    output_subdir = merged_src / output_slug
    if not output_subdir.exists():
        raise RuntimeError(
            f"merged dir {merged_id} has no <output_slug> subdir at {output_subdir}"
        )

    dst_root = nfs_root / "2026-05-13" / output_slug
    print(f"  [2026-05-13] {output_slug}  (role=merged, merge_id={merged_id})")
    if dst_root.exists() and any(dst_root.iterdir()) and not dry_run:
        print(f"      [skip-existing] {dst_root}")
        rewrite_merged_symlinks(dst_root, lookup)
        stats.skipped_existing += 1
        return

    if dry_run:
        print(f"      [dry] cp -a {output_subdir} → {dst_root} (symlinks preserved)")
        print(f"      [dry] copy {merged_src}/shots.csv → {dst_root}/shots.csv")
        print(f"      [dry] write metadata.json with merge_info block")
        print(f"      [dry] rewrite each relative symlink target to 2026-05-12/...")
        return

    shutil.copytree(output_subdir, dst_root, symlinks=True)
    shots_src = merged_src / "shots.csv"
    if shots_src.exists():
        shutil.copy2(shots_src, dst_root / "shots.csv")
    metadata = build_merge_metadata(merged_src, output_slug, source_root)
    (dst_root / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    rewrite_merged_symlinks(dst_root, lookup)
    stats.copied += 1


def rewrite_merged_symlinks(
    merged_dst: Path, lookup: dict[tuple[str, str], Path],
) -> None:
    """Walk ``merged_dst``; for each symlink that points into a
    sibling session dir, rewrite its target to the corresponding
    ``2026-05-12/<slug> (<sid>)/...`` path on NFS.
    """
    rewrote = 0
    untouched = 0
    no_lookup = 0
    for path in merged_dst.rglob("*"):
        if not path.is_symlink():
            continue
        old_target = os.readlink(path)
        parsed = parse_merged_symlink_target(old_target)
        if parsed is None:
            untouched += 1
            continue
        src_sid, src_slug, rest = parsed
        key = (src_sid, src_slug)
        if key not in lookup:
            print(f"      WARN: no 2026-05-12 entry for {key}: {path}")
            no_lookup += 1
            continue
        new_abs = lookup[key].joinpath(*rest)
        new_rel = os.path.relpath(new_abs, path.parent)
        path.unlink()
        path.symlink_to(new_rel)
        rewrote += 1
    print(f"      symlinks rewritten: {rewrote}  untouched: {untouched}  no-lookup: {no_lookup}")


def find_broken_symlinks(root: Path) -> list[Path]:
    """Return symlinks under ``root`` whose targets don't resolve."""
    broken: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink() and not path.exists():
            broken.append(path)
    return broken


# ---- Entry point ----------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="archive_to_nfs",
        description="Archive 2026-05 lens-test shoots to NFS test-raw-data tree.",
        epilog=(
            "Routing comes from analyse-lens-test/merge-audit-2026-05.md "
            "(encoded in archive_2026_05.manifest)."
        ),
    )
    parser.add_argument(
        "--source-root", type=Path,
        default=Path.home() / "macro-lens-test-output",
        help="Where the captured shoots live (default: ~/macro-lens-test-output)",
    )
    parser.add_argument(
        "--nfs-root", type=Path,
        default=Path.home() / "shared/files/pics/digikam/test-raw-data",
        help="NFS root (default: ~/shared/files/pics/digikam/test-raw-data)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print actions without copying or writing.",
    )
    parser.add_argument(
        "--verify-only", action="store_true",
        help="Skip copies; just enumerate planned actions + check for broken symlinks under nfs-root/2026-05-13.",
    )
    args = parser.parse_args(argv)

    if not args.source_root.exists():
        print(f"ERROR: source-root not found: {args.source_root}", file=sys.stderr)
        return 1
    if not args.nfs_root.exists():
        print(f"ERROR: nfs-root not found: {args.nfs_root}", file=sys.stderr)
        return 1

    print(f"Source: {args.source_root}")
    print(f"NFS:    {args.nfs_root}")
    print(f"Mode:   {'DRY-RUN' if args.dry_run else ('VERIFY-ONLY' if args.verify_only else 'COPY')}")
    print()

    stats = CopyStats()

    # 1) 2026-05-12 first (merge sources + superseded) so the lookup
    #    for symlink rewriting is built up as we go.
    print("== 2026-05-12 (merge sources + superseded) ==")
    for entry in ENTRIES:
        if entry.role in ("merge_source", "superseded"):
            if args.verify_only:
                print(f"  [verify] {entry.session_id}/{entry.slug}  (role={entry.role})")
            else:
                archive_entry(
                    entry,
                    source_root=args.source_root,
                    nfs_root=args.nfs_root,
                    dry_run=args.dry_run,
                    stats=stats,
                )

    # 2) 2026-05-13 canonical + labeled-duplicate.
    print()
    print("== 2026-05-13 (canonical + labeled duplicates) ==")
    for entry in ENTRIES:
        if entry.role in ("canonical", "labeled_duplicate"):
            if args.verify_only:
                print(f"  [verify] {entry.session_id}/{entry.slug}  (role={entry.role})")
            else:
                archive_entry(
                    entry,
                    source_root=args.source_root,
                    nfs_root=args.nfs_root,
                    dry_run=args.dry_run,
                    stats=stats,
                )

    # 3) 2026-05-13 merged dirs (after 2026-05-12 so lookups resolve).
    print()
    print("== 2026-05-13 (merged dirs) ==")
    lookup = build_05_12_lookup(args.nfs_root)
    for merged_id in MERGED_DIRS:
        if args.verify_only:
            print(f"  [verify] {merged_id}")
        else:
            archive_merged_dir(
                merged_id,
                source_root=args.source_root,
                nfs_root=args.nfs_root,
                lookup=lookup,
                dry_run=args.dry_run,
                stats=stats,
            )

    print()
    print("== Summary ==")
    print(f"  copied:            {stats.copied}")
    print(f"  skipped-existing:  {stats.skipped_existing}")
    print(f"  missing source:    {stats.missing_source}")
    print(f"  skipped sessions:  {len(SKIP_SESSIONS)} (aborted / empty / test)")

    if not args.dry_run and not args.verify_only:
        print()
        print("== Broken-symlink check (2026-05-13) ==")
        broken = find_broken_symlinks(args.nfs_root / "2026-05-13") if (args.nfs_root / "2026-05-13").exists() else []
        print(f"  broken: {len(broken)}")
        for b in broken[:10]:
            print(f"    {b}  →  {os.readlink(b)}")
        if len(broken) > 10:
            print(f"    ... and {len(broken) - 10} more")
        return 0 if not broken and stats.missing_source == 0 else 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
