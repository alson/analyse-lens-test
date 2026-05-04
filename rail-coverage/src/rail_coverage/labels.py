"""Pure helpers that turn a ``cropped/`` path into human-readable labels and
sort keys. Kept separate from scan/detect so that tests can exercise the
parsing rules without any filesystem fixtures.

Path layouts in the wild include:

    .../<lens>/<magnification>/<aperture>/cropped                          # 2026-01-29
    .../<lens>/<magnification>/<focal_length>/<aperture>/cropped           # 2026-02-18 normal
    .../<date>/<magnification-resized>/<focal_length>/<aperture>/cropped   # 2026-02-18 top-level resized
    .../<lens>/.../<f_dirty>/<aperture>/cropped                            # 2026-02-18 F16.0/F16/cropped artefact

The parser classifies each directory between ``cropped`` and the
filesystem root by what it looks like — aperture (``F<num>``), focal
length (contains ``mm``), magnification (``<num>_<num>``, optionally with
``-resized``), date (``YYYY-MM-DD``), or "other / lens" — and assigns the
closest match for each label. The closest aperture parent is used as the
canonical aperture; spurious sibling apertures higher up the tree (the
``F16.0`` artefact above) are ignored.

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
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Focal length must look like a *standalone* dimension — "210.0 mm" — not
# any string that happens to contain "mm" (lens names like
# "Sigma 150mm F2.8" contain "mm" but are not focal-length subdirs).
_FOCAL_RE = re.compile(r"^\d+(?:\.\d+)?\s*mm\.?$", re.IGNORECASE)

# How "lens" should look: any non-classifiable directory above the
# magnification, but stop walking once we hit a date directory or the
# filesystem root — those are session containers, not lenses.


def _is_aperture(name: str) -> bool:
    return bool(_APERTURE_RE.match(name))


def _is_focal(name: str) -> bool:
    return bool(_FOCAL_RE.match(name.strip()))


def _is_date(name: str) -> bool:
    return bool(_DATE_RE.match(name))


def _is_magnification(name: str) -> bool:
    _, value = parse_magnification(name)
    return value > 0


def parse_scenario_label(cropped_dir: Path) -> ScenarioLabel:
    """Walk up from ``.../cropped`` and classify each ancestor directory.

    Each label (aperture, focal length, magnification, lens) is filled by
    the closest matching ancestor. Lens is whatever non-classifiable
    directory sits closest above the magnification (or above the focal
    length if magnification is missing); a date-shaped directory is
    treated as a session container and skipped, leaving ``lens=""``.

    Raises ``ValueError`` if no aperture can be identified or the path is
    too shallow.
    """
    if cropped_dir.name != "cropped":
        raise ValueError(f"expected a 'cropped' directory, got {cropped_dir}")

    # Ancestors closest-to-furthest, names only
    ancestors = [p.name for p in cropped_dir.parents]
    if not ancestors:
        raise ValueError(f"path has no parent: {cropped_dir}")

    aperture = ""
    aperture_idx = -1
    for i, name in enumerate(ancestors):
        if _is_aperture(name):
            aperture = name
            aperture_idx = i
            break
    if not aperture:
        raise ValueError(
            f"no aperture-shaped directory found above {cropped_dir}"
        )

    # Magnification: closest match strictly above the aperture
    magnification = ""
    magnification_idx = -1
    for i in range(aperture_idx + 1, len(ancestors)):
        if _is_magnification(ancestors[i]):
            magnification = ancestors[i]
            magnification_idx = i
            break

    # Focal length: closest match strictly above the aperture, but not
    # above the magnification (the focal-length dir always sits between
    # aperture and magnification when present).
    focal_length = ""
    upper_focal_bound = (
        magnification_idx if magnification_idx >= 0 else len(ancestors)
    )
    for i in range(aperture_idx + 1, upper_focal_bound):
        if _is_focal(ancestors[i]):
            focal_length = ancestors[i]
            break

    # Lens: closest non-classifiable ancestor strictly above magnification
    # (or above the aperture, if no magnification was found). A date
    # directory marks the boundary of a test-session container — once we
    # hit one, we stop walking, so resized-only top-level trees
    # (.../<date>/<mag-resized>/...) correctly report ``lens=""``.
    lens_search_start = (
        magnification_idx + 1 if magnification_idx >= 0 else aperture_idx + 1
    )
    lens = ""
    for i in range(lens_search_start, len(ancestors)):
        name = ancestors[i]
        if _is_date(name):
            break
        if _is_aperture(name) or _is_focal(name) or _is_magnification(name):
            continue
        lens = name
        break

    pretty, value = parse_magnification(magnification) if magnification else ("", 0.0)
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
