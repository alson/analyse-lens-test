"""Pure helpers that turn a ``cropped/`` path into human-readable labels and
sort keys. Kept separate from scan/detect so that tests can exercise the
parsing rules without any filesystem fixtures.

Path convention (set by ``sort-files-by-lens-magnification-focal-length-aperture.sh``):

    .../<lens>/<magnification>/<focal_length>/<aperture>/cropped

Magnifications use ``_`` in place of ``:`` (e.g. ``1_1`` is 1:1, ``1_1.33`` is
1:1.33), with optional ``-resized`` suffix from the resize step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScenarioLabel:
    lens: str
    magnification: str  # original folder name, e.g. "1_1.33"
    focal_length: str
    aperture: str
    magnification_pretty: str  # e.g. "1:1.33"
    magnification_value: float  # numeric, used for sorting (1.33 → 0.752)


_APERTURE_RE = re.compile(r"^[Ff](\d+(?:\.\d+)?)$")


def parse_scenario_label(cropped_dir: Path) -> ScenarioLabel:
    """Walk up four levels from a ``.../cropped`` path and label the parts.

    Raises ``ValueError`` if the path doesn't have enough parents.
    """
    if cropped_dir.name != "cropped":
        raise ValueError(f"expected a 'cropped' directory, got {cropped_dir}")
    parts = cropped_dir.parents
    try:
        aperture = parts[0].name
        focal_length = parts[1].name
        magnification = parts[2].name
        lens = parts[3].name
    except IndexError as exc:
        raise ValueError(
            f"path is not deep enough to extract lens labels: {cropped_dir}"
        ) from exc
    pretty, value = parse_magnification(magnification)
    return ScenarioLabel(
        lens=lens,
        magnification=magnification,
        focal_length=focal_length,
        aperture=aperture,
        magnification_pretty=pretty,
        magnification_value=value,
    )


def parse_magnification(folder: str) -> tuple[str, float]:
    """Convert ``"1_1"`` → ``("1:1", 1.0)``, ``"1_1.33"`` → ``("1:1.33", 0.7518...)``.

    A trailing ``-resized`` (or any ``-<suffix>``) is preserved verbatim in
    the pretty form. Unparseable values fall back to the raw string with a
    sentinel value of 0.0 (sorts at the bottom).
    """
    base, _, suffix = folder.partition("-")
    if "_" not in base:
        return (folder, 0.0)
    num, _, denom = base.partition("_")
    try:
        n = float(num)
        d = float(denom)
        if d == 0:
            return (folder, 0.0)
    except ValueError:
        return (folder, 0.0)
    pretty = f"{num}:{denom}" + (f" ({suffix})" if suffix else "")
    return (pretty, n / d)


def aperture_sort_key(aperture: str) -> float:
    """Numeric sort key for aperture strings like ``"F2.8"``.

    Falls back to a large value so unrecognised strings sort last.
    """
    m = _APERTURE_RE.match(aperture)
    if m:
        return float(m.group(1))
    return float("inf")


def slugify(path: Path) -> str:
    """Filesystem-safe id for a scenario, used as a directory name in
    ``output/assets/charts/<id>/``.
    """
    s = str(path)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")
