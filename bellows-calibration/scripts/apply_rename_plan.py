"""Apply a rename plan CSV to a test-raw-data tree.

For each row in the plan:

1. Rename the F-dir from `<tree>/<original_path>` to `<tree>/<new_path>`.
2. Inside that dir, rewrite any filename containing the F-component
   `|<original_F_dir_name>|` to `|<new_F_dir_name>|`. Applies to .nef,
   .jpg, .xmp and any other extension equally — the rewrite is on the
   F-component in the filename, not on the extension.
3. Append the operation to a manifest CSV for reversibility.

Safety rules — **never delete or overwrite data**:

- All renames go via a temp-suffix sibling first ("pass 1"), then to
  the final destination ("pass 2"). This handles within-slug chains
  like F4 → F5.6 → F7.1 where the intermediate name was also a
  source.
- A plan row is treated as **already done** if its destination dir
  exists and its internal filenames already carry the new F-name.
- File-rename targets are checked for non-existence before each move.
- Multiple plan rows mapping to the same destination is a hard error.
- Default mode is dry-run (`--dry-run`). Pass `--execute` to actually
  perform the moves.

Usage:

    python apply_rename_plan.py \\
        --plan data/rename_plan_2026-02-18.csv \\
        --tree ~/shared/files/pics/digikam/test-raw-data/2026-02-18 \\
        --manifest data/rename_manifest_2026-02-18.csv

    python apply_rename_plan.py [...] --execute
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

TMP_SUFFIX = ".bellows-rename-tmp"
IN_TREE_MANIFEST = ".bellows-rename-applied.csv"


def load_plan(plan_csv: Path) -> list[dict]:
    with plan_csv.open() as fh:
        return list(csv.DictReader(fh))


def planned_file_moves(scan_dir: Path, old_F: str, new_F: str) -> list[tuple[Path, Path]]:
    """For files inside scan_dir whose name contains `|<old_F>|`,
    return (current_path, target_path) pairs."""
    old_pipe = f"|{old_F}|"
    new_pipe = f"|{new_F}|"
    return [
        (f, f.parent / f.name.replace(old_pipe, new_pipe))
        for f in scan_dir.rglob("*")
        if f.is_file() and old_pipe in f.name
    ]


def has_correctly_named_files(d: Path, F_name: str) -> bool:
    """True iff d contains at least one file whose name embeds
    `|<F_name>|`, or contains pipe-format files but none matching
    any F-name (i.e. layout without F in filenames). In the latter
    case (2026-05-13 style), dir presence alone is the evidence."""
    pipe_files = [f for f in d.rglob("*") if f.is_file() and "|F" in f.name]
    if not pipe_files:
        return True
    want_pipe = f"|{F_name}|"
    return any(want_pipe in f.name for f in pipe_files)


def load_in_tree_manifest(tree: Path) -> set[tuple[str, str]]:
    """Read previously-applied (orig_path, new_path) pairs from the
    in-tree manifest. Returns empty set if no manifest yet."""
    p = tree / IN_TREE_MANIFEST
    if not p.exists():
        return set()
    out = set()
    with p.open() as fh:
        for r in csv.DictReader(fh):
            out.add((r["original_path"], r["new_path"]))
    return out


def append_in_tree_manifest(tree: Path, new_records: list[tuple[str, str, str, str]]) -> None:
    """Append (orig_path, new_path, applied_at_iso, bellows_multiplier)
    records to the in-tree manifest. Creates the file if it doesn't
    exist."""
    if not new_records:
        return
    p = tree / IN_TREE_MANIFEST
    write_header = not p.exists()
    with p.open("a", newline="") as fh:
        w = csv.writer(fh)
        if write_header:
            w.writerow(["original_path", "new_path", "applied_at", "bellows_multiplier"])
        w.writerows(new_records)


def classify_row(orig_dir: Path, new_dir: Path, old_F: str, new_F: str,
                 applied: set[tuple[str, str]], op: dict) -> str:
    """Diagnose a single plan row's pre-execution state.

    Rules:
    - In-tree manifest says this row was applied → "already_done".
    - If src exists → "ready" (two-pass handles dest conflicts).
    - If src doesn't exist + dest exists with consistent content → "already_done".
    - If src doesn't exist + dest doesn't exist → "src_missing".
    - If src doesn't exist + dest exists but content mismatches → "dest_unexpected_REFUSED".
    """
    if (op["original_path"], op["new_path"]) in applied:
        return "already_done"
    src_exists = orig_dir.exists()
    dest_exists = new_dir.exists()
    if src_exists:
        return "ready"
    if not dest_exists:
        return "src_missing"
    if has_correctly_named_files(new_dir, new_F):
        return "already_done"
    return "dest_unexpected_REFUSED"


def execute_pass1(orig_dir: Path, new_dir: Path) -> Path:
    """Rename orig_dir to a temp-suffixed sibling of new_dir."""
    tmp_dir = new_dir.parent / (orig_dir.name + TMP_SUFFIX)
    if tmp_dir.exists():
        raise RuntimeError(f"Pass-1 temp dir already exists: {tmp_dir}")
    orig_dir.rename(tmp_dir)
    return tmp_dir


def execute_pass2(tmp_dir: Path, new_dir: Path, old_F: str, new_F: str) -> int:
    """Rename tmp_dir to new_dir, then rewrite F-component in files inside."""
    if new_dir.exists():
        raise RuntimeError(f"Pass-2 dest already exists: {new_dir}")
    moves = planned_file_moves(tmp_dir, old_F, new_F)
    for src, dst in moves:
        if dst.exists():
            raise RuntimeError(f"Refuse to overwrite: {dst}")
    tmp_dir.rename(new_dir)
    for src, dst in moves:
        src_in_new = new_dir / src.relative_to(tmp_dir)
        dst_in_new = new_dir / dst.relative_to(tmp_dir)
        if not src_in_new.exists():
            raise RuntimeError(f"Source vanished mid-rename: {src_in_new}")
        if dst_in_new.exists():
            raise RuntimeError(f"Destination appeared mid-rename: {dst_in_new}")
        src_in_new.rename(dst_in_new)
    return len(moves)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--tree", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--execute", action="store_true",
                   help="Actually perform renames (default is dry-run)")
    args = p.parse_args(argv)

    rows = load_plan(args.plan)
    rows = [r for r in rows if r.get("new_path") and r["new_path"] != r["original_path"]]

    # One operation per original F-dir
    by_orig: dict[str, dict] = {}
    for r in rows:
        by_orig[r["original_path"]] = r

    # Collision check: any new_path used by >1 original
    by_new = defaultdict(list)
    for op in by_orig.values():
        by_new[op["new_path"]].append(op["original_path"])
    collisions = [(new, origs) for new, origs in by_new.items() if len(origs) > 1]
    if collisions:
        print("HARD ERROR: multiple source dirs map to the same destination:")
        for new, origs in collisions:
            print(f"  {new}  <-  {origs}")
        return 1

    dry_run = not args.execute
    print(f"Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print(f"Plan: {args.plan}")
    print(f"Tree: {args.tree}")
    print(f"{len(by_orig)} F-dir operations planned\n")

    # Classify everything FIRST so we know what would happen before any move
    applied = load_in_tree_manifest(args.tree)
    if applied:
        print(f"In-tree manifest has {len(applied)} previously-applied rows.\n")
    plan_state = {}
    for orig_path, op in by_orig.items():
        orig_dir = args.tree / op["original_path"]
        new_dir = args.tree / op["new_path"]
        old_F = orig_dir.name
        new_F = new_dir.name
        plan_state[orig_path] = {
            "op": op,
            "orig_dir": orig_dir, "new_dir": new_dir,
            "old_F": old_F, "new_F": new_F,
            "status": classify_row(orig_dir, new_dir, old_F, new_F, applied, op),
            "n_files_renamed": 0,
        }

    # Summary print of intended actions
    n_ready = sum(1 for s in plan_state.values() if s["status"] == "ready")
    n_done = sum(1 for s in plan_state.values() if s["status"] == "already_done")
    n_missing = sum(1 for s in plan_state.values() if s["status"] == "src_missing")
    n_refused = sum(1 for s in plan_state.values() if s["status"].endswith("REFUSED"))
    print(f"  ready: {n_ready}    already_done: {n_done}    "
          f"src_missing: {n_missing}    refused: {n_refused}\n")

    if n_refused > 0:
        print("HARD ERROR: at least one row has dest existing with wrong content.")
        for orig_path, s in plan_state.items():
            if s["status"].endswith("REFUSED"):
                print(f"  {s['orig_dir']} -> {s['new_dir']}")
        return 3

    # Determine what each row's "n_files_renamed" would be (or actually is)
    for orig_path, s in plan_state.items():
        if s["status"] == "ready":
            file_moves = planned_file_moves(s["orig_dir"], s["old_F"], s["new_F"])
            s["n_files_planned"] = len(file_moves)
        else:
            s["n_files_planned"] = 0

    if dry_run:
        for orig_path in sorted(plan_state):
            s = plan_state[orig_path]
            print(f"  [{s['status']:<24}] {s['old_F']:<8} -> {s['new_F']:<8}  "
                  f"(+{s['n_files_planned']} files inside)  "
                  f"{s['orig_dir'].relative_to(args.tree).parent}")
        write_manifest(args.manifest, plan_state, executed=False)
        print(f"\nManifest: {args.manifest}")
        return 0

    # EXECUTE: pass-1 (move all sources to .tmp), then pass-2 (move to dest + rewrite files)
    pass1_tmp: dict[str, Path] = {}
    for orig_path, s in plan_state.items():
        if s["status"] != "ready":
            continue
        try:
            tmp = execute_pass1(s["orig_dir"], s["new_dir"])
        except RuntimeError as e:
            print(f"ABORT in pass-1 for {s['orig_dir']}: {e}")
            return 2
        pass1_tmp[orig_path] = tmp

    import datetime
    applied_records = []
    for orig_path, s in plan_state.items():
        if s["status"] != "ready":
            continue
        tmp = pass1_tmp[orig_path]
        try:
            n = execute_pass2(tmp, s["new_dir"], s["old_F"], s["new_F"])
        except RuntimeError as e:
            print(f"ABORT in pass-2 for {tmp}: {e}")
            return 2
        s["n_files_renamed"] = n
        s["status"] = "RENAMED"
        applied_records.append((
            s["op"]["original_path"],
            s["op"]["new_path"],
            datetime.datetime.now().isoformat(timespec="seconds"),
            s["op"].get("bellows_multiplier", ""),
        ))
    append_in_tree_manifest(args.tree, applied_records)

    for orig_path in sorted(plan_state):
        s = plan_state[orig_path]
        print(f"  [{s['status']:<24}] {s['old_F']:<8} -> {s['new_F']:<8}  "
              f"(+{s['n_files_renamed']} files inside)  "
              f"{s['orig_dir'].relative_to(args.tree).parent}")
    write_manifest(args.manifest, plan_state, executed=True)
    print(f"\nManifest: {args.manifest}")
    return 0


def write_manifest(path: Path, plan_state: dict, executed: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "lens", "focal_mm", "tube_mm", "original_path", "new_path",
        "bellows_multiplier", "status", "n_files",
        "executed", "note",
    ]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for orig in sorted(plan_state):
            s = plan_state[orig]
            op = s["op"]
            n = s.get("n_files_renamed") or s.get("n_files_planned", 0)
            w.writerow({
                "lens": op.get("lens", ""),
                "focal_mm": op.get("focal_mm", ""),
                "tube_mm": op.get("tube_mm", ""),
                "original_path": op["original_path"],
                "new_path": op["new_path"],
                "bellows_multiplier": op.get("bellows_multiplier", ""),
                "status": s["status"],
                "n_files": n,
                "executed": "yes" if executed else "no",
                "note": op.get("note", ""),
            })


if __name__ == "__main__":
    raise SystemExit(main())
