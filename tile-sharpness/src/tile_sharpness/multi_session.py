"""Multi-session config-node discovery for the cross-M relative-MTF pipeline.

This module houses the multi-session bookkeeping that lets the (session-agnostic)
cross-M relative-MTF estimator run over the expanded Z7 multi-session subset without
the single-session driver's assumptions. It reads the FROZEN subset artifact
``data/cross_m_relative_mtf_subset_multisession.csv`` (316 config-node rows, one per
(session, lens, mag, aperture) focus sweep) into :class:`ConfigNode` records and gives
each a collision-free short id.

Two orthogonal per-config properties travel with every node:

* **tier** (:func:`tile_sharpness.cross_m_relative_mtf.p2_rail_available`) — whether
  the frame axis is a REGISTERED constant-step defocus rail (rail-coverage tier,
  2026-05+) vs a manual unregistered axis (<= 2026-02). Gates whether P2 through-focus
  FWHM is trustworthy for the config. Read from the ``p2_rail_ok`` CSV column.
* **effective aperture** — deferred to a later phase; the node carries ``aperture``
  (the MARKED f-number) + ``session`` + ``lens`` + ``sample`` so an
  ``EffectiveApertureLookup`` (from ``rail_calibration``) can resolve ``effective_f_exact``
  later, else fall back to the directory aperture. Never analytical (1 + M/p).

Naming (:func:`sid` / :func:`human`) ports the recovered driver's short_id/sid logic:
a compact abbreviated lens id + mag + aperture, suffixed with a ``@YYMMDD`` session tag
for every NON-baseline session so the same (lens, mag, aperture) recurring across
sessions does not collide on the chain key. The validated 2026-01-29 baseline keeps its
canonical (untagged) sids so the reference groups + order-regression check are
unchanged. Supersession is applied UPSTREAM in the frozen CSV (see
``scripts/build_relmtf_subset.py``), so discovery here does not need to dedup — but
:func:`sid` remains collision-free by construction across the enumerated sessions.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from tile_sharpness.cross_m_relative_mtf import p2_rail_available

#: The 2026-01-29 validated baseline session keeps canonical (untagged) sids.
BASELINE_SESSION = "2026-01-29"

#: Path to the frozen subset artifact, relative to the package's repo root
#: (``.../tile-sharpness/data/...``). Callers normally pass an explicit path.
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUBSET_CSV = _REPO_ROOT / "data" / "cross_m_relative_mtf_subset_multisession.csv"


@dataclass(frozen=True)
class ConfigNode:
    """One (session, lens, mag, aperture) focus-sweep config node.

    Fields mirror the frozen subset CSV columns plus the derived tier flag.
    ``session`` == the CSV ``date`` column (the capture session, e.g. ``2026-05-13``).
    ``aperture`` is the MARKED f-number string (e.g. ``"F8"``); ``nominal_M`` / ``focal``
    may be empty strings for sessions that did not encode them (registered M is
    recovered downstream). ``p2_rail_ok`` is the derived tier flag
    (:func:`tile_sharpness.cross_m_relative_mtf.p2_rail_available` over the raw CSV
    ``p2_rail_ok`` string). ``sample`` is one representative jpg in the sweep dir; the
    sweep directory is ``Path(sample).parent``.
    """

    session: str
    lens: str
    mag_label: str
    nominal_M: str
    focal: str
    aperture: str
    n_shots: int
    p2_rail_ok: bool
    sample: str

    @property
    def sweep_dir(self) -> Path:
        """The sweep directory (parent of the representative ``sample`` jpg)."""
        return Path(self.sample).parent


def discover_config_nodes(subset_csv: Path = DEFAULT_SUBSET_CSV) -> list[ConfigNode]:
    """Read the frozen subset CSV into a list of :class:`ConfigNode` (row order).

    ``subset_csv`` defaults to the frozen artifact. Each row's raw ``p2_rail_ok``
    string is passed through :func:`p2_rail_available` to derive the boolean tier flag.
    ``n_shots`` is parsed to int (0 if absent/blank).
    """
    subset_csv = Path(subset_csv)
    nodes: list[ConfigNode] = []
    with open(subset_csv, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                n_shots = int(r.get("n_shots") or 0)
            except ValueError:
                n_shots = 0
            nodes.append(ConfigNode(
                session=(r.get("date") or "").strip(),
                lens=r.get("lens", ""),
                mag_label=r.get("mag_label", ""),
                nominal_M=(r.get("nominal_M") or "").strip(),
                focal=(r.get("focal") or "").strip(),
                aperture=r.get("aperture", ""),
                n_shots=n_shots,
                p2_rail_ok=p2_rail_available(r.get("p2_rail_ok")),
                sample=r.get("sample", ""),
            ))
    return nodes


def _short_lens(lens: str) -> str:
    """Abbreviate a lens display name to a compact base + accessory tag.

    Ported from the recovered driver's ``short_id`` lens-abbreviation table.
    """
    base = (lens.split(" + ")[0]
            .replace("NIKKOR Z MC 105mm f_2.8 VR S", "Z105")
            .replace("Nikon AF Micro-Nikkor 200mm f_4D IF-ED", "AF200")
            .replace("Sigma Macro 105mm F2.8 EX DG OS HSM", "S105")
            .replace("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "S150")
            .replace("NIKKOR Z 100-400mm f_4.5-5.6 VR S", "Z100400")
            .replace("Nikon AF Micro-Nikkor 60mm f_2.8D", "AF60")
            .replace("Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED", "Z70180")
            .replace("Nikon Micro-Nikkor 55mm f_2.8 AIS", "V55f28")
            .replace("Nikon Micro-Nikkor Auto 55mm f_3.5", "V55f35"))
    acc = ""
    if " + " in lens:
        acc = "+" + (lens.split(" + ", 1)[1]
                     .replace(" ", "")
                     .replace("Olympus", "")
                     .replace("Canon", "C")
                     .replace("Nikon", "")
                     .replace("KenkoPro300DG1.4x", "Kenko14")
                     .replace("extension", "ext")
                     .replace("RaynoxM-", "R")
                     .replace("EVO", ""))
    return f"{base}{acc}"


def sid(node: ConfigNode) -> str:
    """Collision-free short id for a config node (``@YYMMDD`` session-tag dedup).

    ``<abbrev-lens>_<mag_label>_<aperture>`` with spaces/slashes stripped; every
    NON-baseline session is suffixed with a compact ``@YYMMDD`` session tag so the same
    (lens, mag, aperture) recurring across sessions (e.g. ``S105_1_1_F8`` in both
    2026-01-29 and 2025-10-17) does not collide on the chain key. The validated
    2026-01-29 baseline keeps its canonical (untagged) sids so the reference groups +
    order-regression check are unchanged. Ported from the recovered driver's
    ``short_id``/``sid`` logic.
    """
    core = f"{_short_lens(node.lens)}_{node.mag_label}_{node.aperture}"
    core = core.replace(" ", "").replace("/", "")
    session = (node.session or "").strip()
    if session and session != BASELINE_SESSION:
        core = f"{core}@{session.replace('-', '')[2:]}"  # @YYMMDD
    return core


def human(node: ConfigNode) -> str:
    """Human-readable config id: ``<lens> | <mag> | <aperture>`` (+ date if non-baseline).

    Ported from the recovered driver's ``config_id``: the full lens display name, mag
    label, and aperture, with the session date appended for every non-baseline session.
    """
    session = (node.session or "").strip()
    tag = f" | {session}" if session and session != BASELINE_SESSION else ""
    return f"{node.lens} | {node.mag_label} | {node.aperture}{tag}"
