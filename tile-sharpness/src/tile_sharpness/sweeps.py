"""Sweep discovery for the two macro-lens-test dataset families.

A *sweep* is one ordered series of shots taken at constant rail step,
constant aperture, constant lens+diopter configuration. Two on-disk
layouts feed in:

* **Newer rig (``~/macro-lens-test-output/``).** Each session has a
  ``shots.csv`` with explicit ``rail_step``, ``rail_position_mm``,
  ``aperture``, ``filename`` and ``phase`` columns. We group rows by
  ``(lens_config_slug, aperture)`` and keep ``phase == "sweep"``.
  JPEGs are full FINE quality.
* **Older manual sweeps (``~/shared/files/pics/digikam/test-raw-data/``).**
  JPEGs are organised by ``<lens+diopter>/<mag>/<focal>/<aperture>/``.
  Filenames are ``seq|lens|mag|focal|aperture|datetime.jpg`` — seq is
  global, sequential within the leaf directory means constant rail
  step. ``rail_position_mm`` is unknown (``None``).

The two families produce slightly different JPEG qualities; absolute
metric values are not comparable across families. Per-tile peak +
argmax comparisons within a sweep are.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Shot:
    path: Path
    rail_step: int
    rail_position_mm: float | None


@dataclass
class Sweep:
    label: str
    family: str
    lens: str
    aperture: str
    shots: list[Shot] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.family}/{self.label}"


NEWER_ROOT = Path.home() / "macro-lens-test-output"
OLDER_ROOTS = [
    Path.home() / "shared/files/pics/digikam/test-raw-data/2026-01-29",
    Path.home() / "shared/files/pics/digikam/test-raw-data/2026-02-18",
]

_FILENAME_RE = re.compile(
    r"^(?P<seq>\d+)\|(?P<lens>[^|]+)\|(?P<mag>[^|]+)\|(?P<focal>[^|]+)\|"
    r"(?P<aperture>F[\d.]+)\|.*\.jpg$",
    re.IGNORECASE,
)


def discover_newer(root: Path = NEWER_ROOT) -> list[Sweep]:
    sweeps: list[Sweep] = []
    if not root.exists():
        return sweeps
    for session in sorted(root.iterdir()):
        shots_csv = session / "shots.csv"
        if not shots_csv.exists():
            continue
        try:
            rows = list(csv.DictReader(shots_csv.open()))
        except (OSError, csv.Error):
            continue
        sweep_rows = [r for r in rows if r.get("phase") == "sweep"]
        grouped: dict[tuple[str, str], list[dict]] = {}
        for r in sweep_rows:
            key = (r.get("lens_config_slug") or "", r.get("aperture") or "")
            grouped.setdefault(key, []).append(r)
        for (lens, aperture), entries in grouped.items():
            entries.sort(key=lambda r: int(r["rail_step"]))
            lens_dir = session / lens
            shots: list[Shot] = []
            for r in entries:
                fn = r["filename"]
                path = lens_dir / fn
                if not path.exists():
                    continue
                try:
                    rail_mm = float(r.get("rail_position_mm") or "nan")
                except ValueError:
                    rail_mm = None
                shots.append(
                    Shot(
                        path=path,
                        rail_step=int(r["rail_step"]),
                        rail_position_mm=rail_mm if rail_mm == rail_mm else None,  # noqa: PLR0124
                    )
                )
            if len(shots) < 3:
                continue
            label = f"{session.name}__{_slug(lens)}__{aperture.replace('/', '_')}"
            sweeps.append(
                Sweep(
                    label=label,
                    family="newer-rig",
                    lens=lens,
                    aperture=aperture,
                    shots=shots,
                )
            )
    return sweeps


def discover_older(roots: list[Path] = OLDER_ROOTS) -> list[Sweep]:
    """Discover sweeps under the older-data root.

    Two on-disk layouts coexist:

    * Zoom or multi-focal lens combos: ``<lens>/<mag>/<focal>/<aperture>/*.jpg``
    * Bare prime macros (single focal length): ``<lens>/<mag>/<aperture>/*.jpg``

    We dispatch by inspecting whether the third level (under ``<mag>``)
    looks like a focal-length directory ("``<n>.<n> mm``") or like an
    aperture directory ("``F<n>``").
    """
    sweeps: list[Sweep] = []
    for root in roots:
        if not root.exists():
            continue
        for lens_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            if lens_dir.name == "resuls_ignore":
                continue
            for mag_dir in sorted(p for p in lens_dir.iterdir() if p.is_dir()):
                # Resized subdirs (e.g. ``1_1-resized``) are real sweeps —
                # they're zoom/diopter combos upsampled to a common 1:1
                # frame so their content can be compared against native
                # 1:1 macros. Keep them; users filter via substring.
                children = sorted(p for p in mag_dir.iterdir() if p.is_dir())
                # Bare prime layout: aperture dirs directly under mag.
                if children and children[0].name.startswith("F"):
                    for ap_dir in children:
                        if not ap_dir.name.startswith("F"):
                            continue
                        _emit_sweep(
                            sweeps, root, lens_dir, mag_dir, None, ap_dir
                        )
                    continue
                # Zoom / multi-focal layout: focal subdir under mag.
                for focal_dir in children:
                    for ap_dir in sorted(p for p in focal_dir.iterdir() if p.is_dir()):
                        if not ap_dir.name.startswith("F"):
                            continue
                        _emit_sweep(
                            sweeps, root, lens_dir, mag_dir, focal_dir, ap_dir
                        )
    return sweeps


def _emit_sweep(
    sweeps: list[Sweep],
    root: Path,
    lens_dir: Path,
    mag_dir: Path,
    focal_dir: Path | None,
    ap_dir: Path,
) -> None:
    shots = _scan_leaf_dir(ap_dir)
    if len(shots) < 3:
        return
    parts = [
        root.name,
        _slug(lens_dir.name),
        mag_dir.name,
    ]
    if focal_dir is not None:
        parts.append(focal_dir.name.replace(" ", "_"))
    parts.append(ap_dir.name)
    label = "__".join(parts)
    sweeps.append(
        Sweep(
            label=label,
            family=f"older-{root.name}",
            lens=lens_dir.name,
            aperture=ap_dir.name,
            shots=shots,
        )
    )


def _scan_leaf_dir(ap_dir: Path) -> list[Shot]:
    entries: list[tuple[int, Path]] = []
    for path in ap_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() != ".jpg":
            continue
        m = _FILENAME_RE.match(path.name)
        if not m:
            continue
        entries.append((int(m.group("seq")), path))
    entries.sort()
    return [
        Shot(path=path, rail_step=k, rail_position_mm=None)
        for k, (_, path) in enumerate(entries)
    ]


def discover_all() -> list[Sweep]:
    return discover_newer() + discover_older()


def find_sweep(query: str, sweeps: list[Sweep] | None = None) -> Sweep:
    """Resolve a sweep by exact label, ``id``, or unique substring."""
    if sweeps is None:
        sweeps = discover_all()
    matches = [s for s in sweeps if query == s.label or query == s.id]
    if matches:
        return matches[0]
    sub = [s for s in sweeps if query in s.label]
    if len(sub) == 1:
        return sub[0]
    if not sub:
        raise KeyError(f"no sweep matches {query!r}")
    raise KeyError(
        f"{len(sub)} sweeps match {query!r}; first few: "
        + ", ".join(s.id for s in sub[:5])
    )


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._+-]+", "_", s).strip("_")
