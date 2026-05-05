from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


# Default capture session is 25 rail positions × 3 replicas = 75 shots.
# Folders with materially more frames are partial reshoots — the user
# was interrupted by battery droop, resumed later, and both runs ended
# up in the same folder. We split such folders on large seq gaps and
# analyse only the longest contiguous chunk.
DEFAULT_TARGET_FRAMES = 75
DEFAULT_GAP_THRESHOLD = 30


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


def split_at_gaps(
    frames: list[CropFrame],
    *,
    gap_threshold: int = DEFAULT_GAP_THRESHOLD,
) -> list[list[CropFrame]]:
    """Split a sorted frame list into contiguous chunks.

    A "chunk" is a run of frames whose ``seq`` numbers don't jump by
    more than ``gap_threshold``. Within a single shooting session
    consecutive frames have ``seq`` differences of 1; partial reshoots
    that resumed later show a much larger gap (often hundreds).
    """
    if not frames:
        return []
    chunks: list[list[CropFrame]] = [[frames[0]]]
    for prev, curr in zip(frames, frames[1:]):
        if curr.seq - prev.seq > gap_threshold:
            chunks.append([curr])
        else:
            chunks[-1].append(curr)
    return chunks


def select_primary_chunk(
    frames: list[CropFrame],
    *,
    target_size: int = DEFAULT_TARGET_FRAMES,
    gap_threshold: int = DEFAULT_GAP_THRESHOLD,
) -> list[CropFrame]:
    """Pick the longest contiguous chunk for analysis.

    When a folder has materially more frames than ``target_size`` it
    typically means the original session was interrupted by battery
    droop and a follow-up session ended up in the same folder. The two
    sessions show up as two contiguous chunks separated by a large
    ``seq`` gap. We prefer the longest chunk; if there are ties, the
    later (higher-``seq``) one wins on the assumption that it is the
    more complete re-run.

    If the input has at most ``target_size`` frames, or if it's a
    single contiguous chunk (no large gaps), the input is returned
    unchanged — the caller still gets the full sweep when it's a
    deliberately-long single session rather than a multi-session
    concatenation.
    """
    if len(frames) <= target_size:
        return frames
    chunks = split_at_gaps(frames, gap_threshold=gap_threshold)
    if len(chunks) <= 1:
        return frames
    longest = max(len(c) for c in chunks)
    candidates = [c for c in chunks if len(c) == longest]
    return candidates[-1]


def read_crop_series(
    crop_dir: Path,
    *,
    min_size: int = 1024,
    target_size: int = DEFAULT_TARGET_FRAMES,
    gap_threshold: int = DEFAULT_GAP_THRESHOLD,
) -> CropSeries:
    """Read one ``cropped/<crop>/`` directory into a CropSeries.

    Folders with multi-session concatenations (>``target_size`` frames
    plus a large gap in ``seq``) are filtered to the longest
    contiguous chunk so the bell-curve detector sees one curve, not
    two stitched together.
    """
    files: list[tuple[str, int]] = []
    for entry in crop_dir.iterdir():
        if entry.name == "pick.jpg" or not entry.is_file():
            continue
        if entry.suffix.lower() not in (".jpg", ".jpeg"):
            continue
        files.append((entry.name, entry.stat().st_size))
    raw_frames = [
        CropFrame(seq=f.seq, size=f.size, path=crop_dir / f.path)
        for f in build_series(files, min_size=min_size)
    ]
    frames = select_primary_chunk(
        raw_frames, target_size=target_size, gap_threshold=gap_threshold
    )
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


def read_scenario(
    cropped_dir: Path,
    *,
    min_size: int = 1024,
    target_size: int = DEFAULT_TARGET_FRAMES,
    gap_threshold: int = DEFAULT_GAP_THRESHOLD,
) -> Scenario:
    """Build a Scenario from a ``.../cropped`` directory."""
    crops: list[CropSeries] = []
    for child in sorted(cropped_dir.iterdir()):
        if not child.is_dir():
            continue
        crops.append(
            read_crop_series(
                child,
                min_size=min_size,
                target_size=target_size,
                gap_threshold=gap_threshold,
            )
        )
    return Scenario(cropped_dir=cropped_dir, crops=crops)
