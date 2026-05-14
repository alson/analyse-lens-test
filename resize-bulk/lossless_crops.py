"""Lossless 9- or 17-crop split of every JPEG in a directory.

Replaces the ``gm mogrify -crop`` invocations in
``analyse-lens-test/make-9-crops.sh`` and ``make-17-crops.sh``. Crops
are produced via :func:`turbojpeg.TurboJPEG.crop_multiple`, which
re-packs encoded MCU blocks into the output JPEGs without decoding
back to RGB. The output crops inherit the source file's encoded
quality exactly — no generation loss.

Crop origins and sizes come from
:mod:`lens_test_detect_core.mcu`, which is the single source of truth
shared with the runtime cropper (``run-lens-test/sharpness/cropper.py``)
so the live and offline crops can't drift out of sync.

Usage::

    cd <some-aperture-dir-with-jpgs>
    python -m lossless_crops --mode full      # 9 crops
    python -m lossless_crops --mode 17        # 9 + 8 DX
    python -m lossless_crops --mode dx        # 8 DX only

By default reads JPEGs from ``./*.jpg`` and writes to ``./cropped/``.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lens_test_detect_core import (
    DEFAULT_CROP_SIZE,
    compute_crop_origins,
    compute_dx_origins,
)
from turbojpeg import TurboJPEG


def collect_origins(
    image_w: int,
    image_h: int,
    mode: str,
    crop_size: int,
) -> dict[str, tuple[int, int]]:
    """Return the origin map for the requested mode."""
    if mode == "full":
        return compute_crop_origins(image_w, image_h, crop_size)
    if mode == "dx":
        return compute_dx_origins(image_w, image_h, crop_size)
    if mode == "17":
        out = compute_crop_origins(image_w, image_h, crop_size)
        out.update(compute_dx_origins(image_w, image_h, crop_size))
        return out
    raise ValueError(f"unknown mode: {mode!r}")


def crop_one(
    src: Path,
    out_dir: Path,
    origins: dict[str, tuple[int, int]],
    crop_size: int,
    tj: TurboJPEG,
) -> dict[str, int]:
    """Lossless-crop one source JPEG into ``out_dir/<name>/<src.name>``.

    Returns the file-size map (post-write) for sanity checking.
    """
    raw = src.read_bytes()
    names = list(origins.keys())
    params = [(*origins[n], crop_size, crop_size) for n in names]
    crops = tj.crop_multiple(raw, params)
    sizes: dict[str, int] = {}
    for name, data in zip(names, crops, strict=True):
        target = out_dir / name / src.name
        target.write_bytes(data)
        sizes[name] = len(data)
    return sizes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--mode",
        choices=("full", "dx", "17"),
        default="full",
        help="full=9 corners/edges/centre; dx=8 inner; 17=both (default: full)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("."),
        help="Directory whose ``*.jpg`` files become crop sources (default: cwd)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("cropped"),
        help="Output directory; one subdirectory per crop position is created (default: cropped/)",
    )
    parser.add_argument(
        "--crop-size",
        type=int,
        default=DEFAULT_CROP_SIZE,
        help=f"Crop side length in pixels; must be a multiple of 16 (default: {DEFAULT_CROP_SIZE})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Concurrent crop workers (default: 8)",
    )
    args = parser.parse_args(argv)

    if args.crop_size % 16 != 0:
        print(
            f"--crop-size must be a multiple of 16; got {args.crop_size}",
            file=sys.stderr,
        )
        return 2

    src_files = sorted(p for p in args.source.glob("*.jpg") if p.is_file())
    if not src_files:
        print(f"no *.jpg in {args.source}", file=sys.stderr)
        return 1

    tj = TurboJPEG()
    w, h, _, _ = tj.decode_header(src_files[0].read_bytes())
    origins = collect_origins(w, h, args.mode, args.crop_size)

    for name in origins:
        (args.out / name).mkdir(parents=True, exist_ok=True)

    print(
        f"[plan] mode={args.mode} crop={args.crop_size} "
        f"image={w}x{h} positions={len(origins)} files={len(src_files)}",
        flush=True,
    )

    # One TurboJPEG instance per worker (per-thread lazy init) — the
    # native handle is fine across threads but each one owns its own
    # internal scratch buffers.
    import threading

    _tj_local = threading.local()

    def _worker(src: Path) -> tuple[Path, dict[str, int]]:
        local = getattr(_tj_local, "tj", None)
        if local is None:
            local = TurboJPEG()
            _tj_local.tj = local
        return src, crop_one(src, args.out, origins, args.crop_size, local)

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for src, _sizes in pool.map(_worker, src_files):
            done += 1
            if done == 1 or done == len(src_files) or done % 25 == 0:
                print(f"[{done}/{len(src_files)}] {src.name}", flush=True)

    print(f"[done] {done} files, {len(origins)} crops each", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
