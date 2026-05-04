from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class CropFrame:
    seq: int
    size: int
    path: Path


@dataclass
class CropSeries:
    name: str
    frames: list[CropFrame]


@dataclass
class Scenario:
    cropped_dir: Path
    crops: list[CropSeries]


def parse_seq(filename: str) -> int | None:
    """Extract the leading capture-sequence integer from a crop filename.

    Files are named e.g. ``03488|Sigma...|F8|alm-20260130-222036-953.jpg``.
    Returns the integer before the first ``|``, or ``None`` if the filename
    doesn't follow that convention.
    """
    head, sep, _ = filename.partition("|")
    if not sep or not head.isdigit():
        return None
    return int(head)


def build_series(
    files: list[tuple[str, int]],
    *,
    min_size: int = 1024,
) -> list[CropFrame]:
    """Build a sorted list of CropFrames from ``(filename, size)`` tuples.

    Pure: no filesystem access. ``min_size`` filters out corrupt / empty
    files (some of the user's data has 11-byte stubs).
    """
    frames: list[CropFrame] = []
    for name, size in files:
        if size < min_size:
            continue
        seq = parse_seq(name)
        if seq is None:
            continue
        frames.append(CropFrame(seq=seq, size=size, path=Path(name)))
    frames.sort(key=lambda f: f.seq)
    return frames


def read_crop_series(crop_dir: Path, *, min_size: int = 1024) -> CropSeries:
    """Read one ``cropped/<crop>/`` directory into a CropSeries."""
    files: list[tuple[str, int]] = []
    for entry in crop_dir.iterdir():
        if entry.name == "pick.jpg" or not entry.is_file():
            continue
        if entry.suffix.lower() not in (".jpg", ".jpeg"):
            continue
        files.append((entry.name, entry.stat().st_size))
    frames = [
        CropFrame(seq=f.seq, size=f.size, path=crop_dir / f.path)
        for f in build_series(files, min_size=min_size)
    ]
    return CropSeries(name=crop_dir.name, frames=frames)


def find_cropped_dirs(root: Path) -> Iterator[Path]:
    """Yield every ``.../cropped`` directory under ``root``.

    Skips already-output directories and hidden dot-dirs.
    """
    for path in root.rglob("cropped"):
        if not path.is_dir():
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        yield path


def read_scenario(cropped_dir: Path, *, min_size: int = 1024) -> Scenario:
    """Build a Scenario from a ``.../cropped`` directory."""
    crops: list[CropSeries] = []
    for child in sorted(cropped_dir.iterdir()):
        if not child.is_dir():
            continue
        crops.append(read_crop_series(child, min_size=min_size))
    return Scenario(cropped_dir=cropped_dir, crops=crops)
