"""Bulk resize driver — generates *-resized siblings for native lens-test captures.

Walks one or more source roots, finds (combo, focal_length) folders that
hold native-magnification JPEGs, and produces 1_1-resized / 2_1-resized
trees alongside them. Each resized JPEG is followed by a make-9-crops
pass that materialises the centre / edge / corner sub-crops the rail-
coverage analyser consumes.

Resampling choice (matches the rationale in resize-from-to.sh):

    upsample   : Pillow BICUBIC (= Catmull-Rom B=0, C=0.5)
    downsample : Pillow BICUBIC

Catmull-Rom is the most neutral practical interpolator for the file-size-
as-sharpness comparison: sharp without the long-range Gibbs ringing of
Lanczos (which would inflate file sizes with synthetic halos) and not
soft like bilinear (which would deflate them). Pillow does not expose
Mitchell-Netravali natively; BICUBIC is used for downsampling too. For
the small downsample factors actually present in this dataset (0.5-0.9)
the difference is well under the noise floor of the comparison.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# Pillow >= 11 exposes Resampling enum
RESAMPLE_UP = Image.Resampling.BICUBIC
RESAMPLE_DOWN = Image.Resampling.BICUBIC

JPEG_QUALITY = 75  # matches camera embedded-preview quality
CROP_SIZE = 500    # 9-crops sub-crop edge length

CROP_OFFSETS = {
    # (x_anchor, y_anchor) -> "center" | "edge" | "corner"
    "center":       ("c", "c"),
    "left-edge":    ("0", "c"),
    "right-edge":   ("1", "c"),
    "top-edge":     ("c", "0"),
    "bottom-edge":  ("c", "1"),
    "top-left":     ("0", "0"),
    "top-right":    ("1", "0"),
    "bottom-left":  ("0", "1"),
    "bottom-right": ("1", "1"),
}


def _anchor(anchor: str, full: int, crop: int) -> int:
    if anchor == "0":
        return 0
    if anchor == "1":
        return full - crop
    return (full - crop) // 2


def parse_mag_folder(name: str) -> tuple[float, bool]:
    """Parse '1_1.75' / '1_1-resized' → (ratio_value, is_resized).

    Returns (0.0, False) if the folder doesn't look like a magnification.
    """
    base, dash, suffix = name.partition("-")
    if "_" not in base:
        return (0.0, False)
    num, _, denom = base.partition("_")
    try:
        n, d = float(num), float(denom)
    except ValueError:
        return (0.0, False)
    if d == 0:
        return (0.0, False)
    return (n / d, suffix == "resized")


def is_focal(name: str) -> bool:
    return name.replace(".", "", 1).rstrip().endswith("mm") or name.endswith(" mm")


def is_aperture(name: str) -> bool:
    return name.startswith("F") and any(c.isdigit() for c in name)


@dataclass(frozen=True)
class ResizeJob:
    """One resize unit-of-work: every JPEG in src goes to dst, scaled by
    factor (target_mag / source_mag)."""

    combo_dir: Path      # the lens / combo container
    source_mag: str      # e.g. '1_1.75'
    source_value: float  # 1 / 1.75
    target_mag: str      # e.g. '1_1' or '2_1'
    target_value: float  # 1.0 or 2.0
    focal: str | None    # focal_length folder name, or None
    aperture: str        # 'F8', 'F11', etc.
    src_dir: Path        # full path to source aperture folder
    dst_dir: Path        # full path to destination aperture folder
    factor: float        # target_value / source_value

    def is_upsample(self) -> bool:
        return self.factor > 1.0


def discover_native_aperture_dirs(root: Path) -> list[tuple[Path, str, float, str | None, str]]:
    """Return (combo_dir, mag_folder, mag_value, focal_folder_or_none, aperture_folder)
    for every native (non-resized) aperture folder that contains *.jpg.
    """
    out: list[tuple[Path, str, float, str | None, str]] = []
    # Walk a level at a time: combo_dir -> mag_folder -> [focal] -> aperture
    for combo_dir in sorted(root.iterdir()):
        if not combo_dir.is_dir():
            continue
        # combo_dir might itself be a magnification folder (top-level resized
        # trees in 2026-02-18). Walk both shapes.
        for mag_dir in sorted(combo_dir.iterdir()):
            if not mag_dir.is_dir():
                continue
            mag_val, is_resized = parse_mag_folder(mag_dir.name)
            if not mag_val:
                continue
            if is_resized:
                # we never resize a resized tree
                continue
            # Inside mag_dir: either focal folders or aperture folders directly
            for sub in sorted(mag_dir.iterdir()):
                if not sub.is_dir():
                    continue
                if is_aperture(sub.name):
                    if any(sub.glob("*.jpg")):
                        out.append((combo_dir, mag_dir.name, mag_val, None, sub.name))
                elif is_focal(sub.name):
                    for ap in sorted(sub.iterdir()):
                        if not ap.is_dir() or not is_aperture(ap.name):
                            continue
                        if any(ap.glob("*.jpg")):
                            out.append(
                                (combo_dir, mag_dir.name, mag_val, sub.name, ap.name)
                            )
    return out


def plan_jobs(
    natives: list[tuple[Path, str, float, str | None, str]],
    targets: list[tuple[str, float]],
) -> list[ResizeJob]:
    """For each native aperture folder, queue one job per target magnification
    (skipping when source == target)."""

    # Group natives by (combo_dir, focal, aperture). For each group, pick
    # the native magnification that's *closest* to each target — this avoids
    # generating multiple resize variants for one target when a combo has
    # multiple native mags (e.g. 24-120 + 26mm ext at 1:1.20 / 1:1.28 / 1:1.29).
    by_key: dict[tuple[Path, str | None, str], list[tuple[str, float]]] = {}
    for combo_dir, mag_name, mag_val, focal, ap in natives:
        by_key.setdefault((combo_dir, focal, ap), []).append((mag_name, mag_val))

    jobs: list[ResizeJob] = []
    for (combo_dir, focal, ap), mags in by_key.items():
        for tgt_name, tgt_val in targets:
            # Skip when one of the natives matches the target exactly.
            if any(abs(v - tgt_val) < 1e-6 for _, v in mags):
                continue
            # Pick the native mag closest to the target (in log-ratio space).
            best_name, best_val = min(
                mags, key=lambda mv: abs(mv[1] / tgt_val + tgt_val / mv[1] - 2)
            )
            tgt_resized = f"{tgt_name}-resized"
            src_dir = combo_dir / best_name
            dst_dir = combo_dir / tgt_resized
            if focal:
                src_dir = src_dir / focal
                dst_dir = dst_dir / focal
            src_dir = src_dir / ap
            dst_dir = dst_dir / ap
            jobs.append(
                ResizeJob(
                    combo_dir=combo_dir,
                    source_mag=best_name,
                    source_value=best_val,
                    target_mag=tgt_name,
                    target_value=tgt_val,
                    focal=focal,
                    aperture=ap,
                    src_dir=src_dir,
                    dst_dir=dst_dir,
                    factor=tgt_val / best_val,
                )
            )
    return jobs


def resize_one_image(args: tuple[Path, Path, float]) -> tuple[Path, str]:
    """Resize a single JPEG and write 9 sub-crops. Returns (dst, status).

    Same final pixel content as the bash resize-from-to.sh, but fused:
    for upsample (factor > 1) we crop the centre (w/factor × h/factor)
    *first* and then upsample that crop back to (w, h) — equivalent to
    "resize whole image then centre-crop" but 5-10× faster because we
    never materialise the giant intermediate. For downsample we resize
    the whole image (smaller now, cheap) and pad with black to (w, h).
    """
    src, dst, factor = args
    try:
        with Image.open(src) as im:
            im.load()
            exif_bytes = im.info.get("exif")  # preserve EXIF so file sizes are comparable to GM-resized outputs
            w, h = im.size

            if factor > 1.0:
                # Upsample: crop centre at (w/factor, h/factor), resize back to (w, h).
                crop_w = max(1, round(w / factor))
                crop_h = max(1, round(h / factor))
                cx0 = (w - crop_w) // 2
                cy0 = (h - crop_h) // 2
                cropped = im.crop((cx0, cy0, cx0 + crop_w, cy0 + crop_h))
                final = cropped.resize((w, h), resample=RESAMPLE_UP)
            elif factor < 1.0:
                # Downsample: resize whole image, pad with black to (w, h).
                new_w = max(1, round(w * factor))
                new_h = max(1, round(h * factor))
                shrunk = im.resize((new_w, new_h), resample=RESAMPLE_DOWN)
                final = Image.new("RGB", (w, h), (0, 0, 0))
                px = (w - new_w) // 2
                py = (h - new_h) // 2
                final.paste(shrunk, (px, py))
            else:
                # factor == 1: just copy through (with same JPEG round-trip).
                final = im.convert("RGB") if im.mode != "RGB" else im.copy()

            # Crop subdirs are pre-created at job start; no mkdir in the hot path.
            save_kwargs = {"quality": JPEG_QUALITY, "subsampling": 2, "optimize": False}
            if exif_bytes:
                save_kwargs["exif"] = exif_bytes
            final.save(dst, "JPEG", **save_kwargs)

            # 9-crop split into ./cropped/<position>/ (no EXIF on tiny crops)
            crops_root = dst.parent / "cropped"
            for pos, (ax, ay) in CROP_OFFSETS.items():
                cx = _anchor(ax, w, CROP_SIZE)
                cy = _anchor(ay, h, CROP_SIZE)
                tile = final.crop((cx, cy, cx + CROP_SIZE, cy + CROP_SIZE))
                tile.save(crops_root / pos / dst.name, "JPEG", quality=JPEG_QUALITY, subsampling=2)
        return (dst, "ok")
    except Exception as e:  # pragma: no cover - diagnostic path
        return (dst, f"error: {e!r}")


def dst_name(src_name: str) -> str:
    stem = src_name.rsplit(".", 1)[0]
    return f"{stem}|resized.jpg"


def execute_job(job: ResizeJob, force: bool, workers: int) -> dict:
    """Resize every *.jpg in job.src_dir into job.dst_dir, then make 9 crops."""
    job.dst_dir.mkdir(parents=True, exist_ok=True)
    # Pre-create crop subdirs once per job — saves 9 NFS mkdir/stat ops per image.
    crops_root = job.dst_dir / "cropped"
    for pos in CROP_OFFSETS:
        (crops_root / pos).mkdir(parents=True, exist_ok=True)

    src_files = sorted(job.src_dir.glob("*.jpg"))
    src_files = [s for s in src_files if "|resized" not in s.name]
    if not src_files:
        return {"job": job, "status": "no_sources", "n": 0}

    tasks = []
    for src in src_files:
        dst = job.dst_dir / dst_name(src.name)
        if dst.exists() and not force:
            continue
        tasks.append((src, dst, job.factor))

    if not tasks:
        return {"job": job, "status": "up_to_date", "n": 0}

    errors = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for dst, status in pool.map(resize_one_image, tasks, chunksize=1):
            if status != "ok":
                errors.append((dst, status))

    return {
        "job": job,
        "status": "ok" if not errors else "partial",
        "n": len(tasks),
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("roots", nargs="+", type=Path, help="One or more source roots to scan")
    p.add_argument("--targets", default="1_1,2_1",
                   help="Comma-separated target magnifications (default: 1_1,2_1)")
    p.add_argument("--force", action="store_true", help="Re-resize even if outputs exist")
    p.add_argument("--wipe-existing-resized", action="store_true",
                   help="Delete existing *-resized trees in the roots before generating")
    p.add_argument("--workers", type=int, default=8,
                   help="Parallel image workers (default: 8)")
    p.add_argument("--dry-run", action="store_true",
                   help="Plan jobs but don't execute")
    args = p.parse_args(argv)

    targets: list[tuple[str, float]] = []
    for t in args.targets.split(","):
        val, _ = parse_mag_folder(t.strip())
        if not val:
            print(f"Bad target magnification: {t}", file=sys.stderr)
            return 1
        targets.append((t.strip(), val))

    if args.wipe_existing_resized and not args.dry_run:
        for root in args.roots:
            for d in root.rglob("*-resized"):
                if d.is_dir():
                    print(f"[wipe] {d}", flush=True)
                    shutil.rmtree(d)

    all_natives: list[tuple[Path, str, float, str | None, str]] = []
    for root in args.roots:
        natives = discover_native_aperture_dirs(root)
        print(f"[discover] {root}: {len(natives)} native aperture folders", flush=True)
        all_natives.extend(natives)

    jobs = plan_jobs(all_natives, targets)
    print(f"[plan] {len(jobs)} resize jobs", flush=True)

    if args.dry_run:
        for j in jobs:
            print(
                f"  {j.source_mag:14} → {j.target_mag:6} "
                f"(factor {j.factor:.3f}) {j.dst_dir.relative_to(args.roots[0]) if j.dst_dir.is_relative_to(args.roots[0]) else j.dst_dir}"
            )
        return 0

    ok = err = 0
    for i, job in enumerate(jobs, 1):
        print(
            f"[{i}/{len(jobs)}] {job.combo_dir.name} {job.source_mag}→{job.target_mag} "
            f"(factor {job.factor:.3f}) focal={job.focal} ap={job.aperture}",
            flush=True,
        )
        result = execute_job(job, force=args.force, workers=args.workers)
        if result["status"] in ("ok", "up_to_date"):
            ok += 1
        else:
            err += 1
            for d, s in result.get("errors", []):
                print(f"   ERROR {d}: {s}", file=sys.stderr)

    print(f"[done] {ok} ok, {err} errors", flush=True)
    return 0 if err == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
