#!/usr/bin/env python3
"""One-off fixup for mislabelled Sigma 105/150 + TC magnifications in
2026-01-29.

Three whole-folder relabels + one partial-folder split, derived from
agreement between the wafer-square algo (archive_2026_05.measure_wafer_squares)
and per-file Nikon FocusDistance EXIF:

  150 + TC-2001 / 1_1   → 1.5_1   (algo 1.450×, full folder)
  105 + TC-1401 / 1_1   → 1.5_1   (algo 1.456×, full folder)
  105 + TC-1401 / 1.4_1 → 1_1     (algo 1.010×, full folder)
  105 + TC-2001 / 2_1   → 1_1     (232 files at seq 15777..16008,
                                    fd 0.398m matches 1_1 fd)

For whole-folder relabels we move the entire <slug>/<old_mag>/ subtree
to <slug>/<new_mag>/, then rename each JPG (including all cropped/<region>/
files) to substitute the mag substring. NEFs at root are renamed in
place. After moves we drop any stale cropped/<region>/pick.jpg files;
caller re-runs select-crops.sh / equivalent to repopulate them.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")

# --- The four planned actions ---------------------------------------------

WHOLE_FOLDER_RENAMES = [
    # (slug, old_mag, new_mag)
    #
    # NOTE: The original commit of this script also renamed
    #   "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001" / "1_1" -> "1.5_1"
    # based on the wafer-square algo's F11 reading of 1.45×. That was an
    # algorithm artifact (F11 latched onto a sub-feature harmonic at
    # ~1.5× the true die pitch). Lens focus-scale + direct GIMP die-pitch
    # measurement subsequently showed this dir is actually ~1.02× on
    # sensor — i.e. the original "1_1" label was right. That rename was
    # reverted by `revert-sigma-150-tc-2001-1_1-rename-2026-01-29.py`;
    # the entry is removed here so re-running this script doesn't
    # re-apply the over-correction.
    # Sigma 105 + TC-1401 — labels swapped at GT-measurement time vs
    # achieved magnification: the dir labelled "1_1" was actually
    # ~1.49× on sensor (TC-1.4 effective ≈ 1.44, lens ~1.034× = ~1.49×;
    # see ANALYSIS_NOTES §7a.4) and the dir labelled "1.4_1" was at
    # ~1.0×. Swap to match achievement; both ends round to their new
    # label's value (1.49 → 1.4 with the same convention applied to
    # Sigma 150 + TC-1401 / 1.4_1's 1.443×, and 1.01 → 1.0). The
    # swap routes through a tmp intermediate so re-running on fresh
    # data doesn't collide. The original commit of this script went
    # via "1.5_1" as the intermediate (algo's 1-decimal rounding of
    # 1.456 → "1.5_1"); subsequent analysis showed both same-setup
    # dirs (Sigma 150 + TC-1401 / 1.4_1 and Sigma 105 + TC-1401 /
    # 1.4_1) should carry the same 1.4_1 label, and the intermediate
    # was renamed via rename-sigma-105-tc-1401-1.5to1.4-2026-01-29.py.
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401",     "1_1", "_tmp_swap"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401",     "1.4_1", "1_1"),
    ("Sigma Macro 105mm F2.8 EX DG OS HSM + TC-1401",     "_tmp_swap", "1.4_1"),
]

PARTIAL_SPLIT = {
    "slug": "Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001",
    "old_mag": "2_1",
    "new_mag": "1_1",
    "seq_lo": 15777,
    "seq_hi": 16008,
}


# --- Filename helpers ------------------------------------------------------

# NNNNN|<slug>|<mag>|<focal>|F<n>|<orig>.<ext>
_PIPE_RE = re.compile(r"^(\d{5})\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|(.+)$")


def parse_pipe_name(name: str) -> tuple[int, str, str, str, str, str] | None:
    """Return (seq, slug, mag, focal, ap, orig) or None."""
    m = _PIPE_RE.match(name)
    if not m:
        return None
    return (int(m.group(1)), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6))


def swap_mag_in_name(name: str, new_mag: str) -> str:
    parts = name.split("|", 5)
    if len(parts) != 6:
        raise ValueError(f"unexpected name shape: {name!r}")
    parts[2] = new_mag
    return "|".join(parts)


# --- Whole-folder rename ---------------------------------------------------


def plan_whole_folder(
    slug: str, old_mag: str, new_mag: str,
) -> tuple[list[tuple[Path, Path]], list[Path]]:
    """Return (renames, stale_picks).

    Renames is a list of (old_path, new_path) tuples; stale_picks are
    cropped/<region>/pick.jpg paths to delete after the rename.
    """
    renames: list[tuple[Path, Path]] = []
    stale_picks: list[Path] = []

    # Root-level NEFs (no .jpg.xmp for any Sigma+TC).
    for ext in ("nef", "jpg.xmp"):
        for p in ROOT.iterdir():
            if not p.is_file() or not p.name.endswith("." + ext):
                continue
            parsed = parse_pipe_name(p.name)
            if parsed is None:
                continue
            _, p_slug, p_mag, _, _, _ = parsed
            if p_slug == slug and p_mag == old_mag:
                renames.append((p, p.with_name(swap_mag_in_name(p.name, new_mag))))

    # Sorted-tree dir for this slug/mag — move whole dir, then rename JPG basenames.
    old_dir = ROOT / slug / old_mag
    new_dir = ROOT / slug / new_mag
    if not old_dir.is_dir():
        return renames, stale_picks

    # The dir move itself: parent rename. Record as a special op via marker
    # (handled in apply).
    renames.append((old_dir, new_dir))

    # After the dir rename, every JPG inside still has |<old_mag>| in its
    # basename — collect basename renames using the NEW path (post dir-rename).
    for jpg in old_dir.rglob("*.jpg"):
        if jpg.name == "pick.jpg":
            # Stale; will be regenerated.
            stale_picks.append(_translate_path(jpg, old_dir, new_dir))
            continue
        rel = jpg.relative_to(old_dir)
        new_jpg_dir = new_dir / rel.parent
        new_basename = swap_mag_in_name(jpg.name, new_mag)
        renames.append((new_jpg_dir / jpg.name, new_jpg_dir / new_basename))

    return renames, stale_picks


def _translate_path(p: Path, from_dir: Path, to_dir: Path) -> Path:
    """Same path with ``from_dir`` prefix swapped for ``to_dir``."""
    return to_dir / p.relative_to(from_dir)


# --- Partial split ---------------------------------------------------------


def plan_partial_split(
    slug: str, old_mag: str, new_mag: str, seq_lo: int, seq_hi: int,
) -> tuple[list[tuple[Path, Path]], list[Path]]:
    renames: list[tuple[Path, Path]] = []
    affected_pick_dirs: set[Path] = set()

    # Root NEFs.
    for p in ROOT.iterdir():
        if not p.is_file() or not p.name.endswith(".nef"):
            continue
        parsed = parse_pipe_name(p.name)
        if parsed is None:
            continue
        seq, p_slug, p_mag, _, _, _ = parsed
        if p_slug == slug and p_mag == old_mag and seq_lo <= seq <= seq_hi:
            renames.append((p, p.with_name(swap_mag_in_name(p.name, new_mag))))

    # Sorted-tree JPGs (top-level under F<n>/ + cropped/<region>/).
    src_root = ROOT / slug / old_mag
    dst_root = ROOT / slug / new_mag
    if not src_root.is_dir() or not dst_root.is_dir():
        return renames, []

    for jpg in src_root.rglob("*.jpg"):
        if jpg.name == "pick.jpg":
            continue
        parsed = parse_pipe_name(jpg.name)
        if parsed is None:
            continue
        seq, p_slug, p_mag, _, _, _ = parsed
        if p_slug != slug or p_mag != old_mag:
            continue
        if not (seq_lo <= seq <= seq_hi):
            continue
        rel = jpg.relative_to(src_root)
        dst_dir = dst_root / rel.parent
        new_basename = swap_mag_in_name(jpg.name, new_mag)
        renames.append((jpg, dst_dir / new_basename))
        # The cropped/<region>/ moved-from dir loses files; the moved-to dir
        # gains files. Both may have stale pick.jpg.
        affected_pick_dirs.add(jpg.parent)
        affected_pick_dirs.add(dst_dir)

    stale_picks = [d / "pick.jpg" for d in sorted(affected_pick_dirs)
                   if (d / "pick.jpg").exists()]
    return renames, stale_picks


# --- Apply ----------------------------------------------------------------


def apply_renames(ops: list[tuple[Path, Path]]) -> int:
    """Execute renames. For Path destinations whose parent doesn't exist
    yet (cross-mag moves in the partial split), the parent is created.
    """
    n = 0
    for old, new in ops:
        if old == new:
            continue
        if new.exists():
            print(f"  SKIP (dest exists): {new}", file=sys.stderr)
            continue
        if not old.exists():
            print(f"  SKIP (src missing): {old}", file=sys.stderr)
            continue
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)
        n += 1
    return n


def delete_stale_picks(picks: list[Path]) -> int:
    n = 0
    for p in picks:
        if p.exists():
            p.unlink()
            n += 1
    return n


# --- CLI ------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Execute the moves; otherwise dry-run only.")
    args = parser.parse_args()

    print("=" * 60)
    print("Sigma+TC mislabel fixup for", ROOT)
    print("=" * 60)

    all_ops: list[tuple[Path, Path]] = []
    all_picks: list[Path] = []
    per_action_summary: list[tuple[str, int]] = []

    for slug, old_mag, new_mag in WHOLE_FOLDER_RENAMES:
        ops, picks = plan_whole_folder(slug, old_mag, new_mag)
        per_action_summary.append((
            f"{slug} / {old_mag} -> {new_mag}", len(ops),
        ))
        all_ops.extend(ops)
        all_picks.extend(picks)

    ops, picks = plan_partial_split(**PARTIAL_SPLIT)
    per_action_summary.append((
        f"PARTIAL SPLIT  {PARTIAL_SPLIT['slug']} / "
        f"{PARTIAL_SPLIT['old_mag']} -> {PARTIAL_SPLIT['new_mag']}  "
        f"(seq {PARTIAL_SPLIT['seq_lo']}..{PARTIAL_SPLIT['seq_hi']})",
        len(ops),
    ))
    all_ops.extend(ops)
    all_picks.extend(picks)

    print("\nPlanned operations per action:")
    for label, count in per_action_summary:
        print(f"  {count:6d}  {label}")
    print(f"  ------")
    print(f"  {len(all_ops):6d}  total rename/move operations")
    print(f"  {len(all_picks):6d}  stale pick.jpg files to drop")

    # Show a few example renames per action.
    print("\nSample operations (first 3 per action):")
    sampled = 0
    seen_actions: dict[str, int] = defaultdict(int)
    for slug, old_mag, new_mag in WHOLE_FOLDER_RENAMES:
        ops, _ = plan_whole_folder(slug, old_mag, new_mag)
        print(f"\n  [{slug} / {old_mag} -> {new_mag}]")
        for old, new in ops[:3]:
            old_disp = str(old.relative_to(ROOT) if ROOT in old.parents else old.name)
            new_disp = str(new.relative_to(ROOT) if ROOT in new.parents else new.name)
            print(f"    {old_disp}\n      → {new_disp}")
    ops, _ = plan_partial_split(**PARTIAL_SPLIT)
    print(f"\n  [PARTIAL SPLIT]")
    for old, new in ops[:3]:
        old_disp = str(old.relative_to(ROOT) if ROOT in old.parents else old.name)
        new_disp = str(new.relative_to(ROOT) if ROOT in new.parents else new.name)
        print(f"    {old_disp}\n      → {new_disp}")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to execute.")
        return 0

    print("\nApplying renames...")
    n_done = apply_renames(all_ops)
    n_pick = delete_stale_picks(all_picks)
    print(f"Done. {n_done} renames applied, {n_pick} stale pick.jpg removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
