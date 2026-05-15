"""Routing manifest derived from analyse-lens-test/merge-audit-2026-05.md.

Each ``Entry`` is a (session_id, lens-config-slug) pair plus its
``role`` — one of:

* ``canonical``: ⭐ pick; goes to 2026-05-13 (session-grouped
  intermediate; later sorted into ``<lens>/<mag>/<focal>/<F>/``).
* ``superseded``: ⛔ kept-for-traceability; goes to 2026-05-12 (flat
  ``<slug> (<session_id>)/`` dirs).
* ``merge_source``: contributes to a merged dir; also goes to
  2026-05-12 (the merged dir's symlinks point at this).
* ``labeled_duplicate``: deliberate by-design duplicate (e.g.
  ``+ Canon 500D (duplicate)``); routed as canonical.

If the audit doc is updated, this manifest must be updated to match
and the script re-run. The audit doc is the human-readable
source-of-truth; this module is the machine-readable view.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


CASCADE_FIX_CUTOFF = dt.datetime(2026, 5, 13, 23, 0, tzinfo=dt.timezone.utc)
"""Per audit D4: sessions whose ``started_at`` is before this
timestamp get ``calibration_methodology: 'pre-cascade-fix'`` in their
metadata. Cutoff sits between commits 578e9f1 (21:06 UTC, silent-FEC
fix) and a9a5070 (22:57 UTC, snap-error refinement) on 2026-05-13."""


# Aborted / empty / "test" runs per the audit's skip list. The
# archive script ignores these entirely.
SKIP_SESSIONS: frozenset[str] = frozenset([
    "2026-05-05_125142", "2026-05-05_132309", "2026-05-05_132950",
    "2026-05-05_141959", "2026-05-05_153748", "2026-05-05_155939",
    "2026-05-05_160542", "2026-05-05_161412", "2026-05-05_164532",
    "2026-05-05_171022", "2026-05-05_172105", "2026-05-05_181637",
    "2026-05-05_181932", "2026-05-05_183757", "2026-05-05_203701",
    "2026-05-05_210946", "2026-05-05_211044", "2026-05-05_211909",
    "2026-05-06_174107", "2026-05-06_174749", "2026-05-06_194546",
    "2026-05-07_163258", "2026-05-12_200117", "2026-05-13_172557",
    "2026-05-13_172948", "2026-05-14_114807", "2026-05-14_122853",
])


MERGED_DIRS: tuple[str, ...] = (
    "merged_24-120_2026-05-08",
    "merged_viltrox-85_2026-05-10",
    "merged_100-400-6T_2026-05-14",
    "merged_100-400-35mm_2026-05-15",
)
"""Merged session directories. Copied to 2026-05-13/ with their
relative symlinks rewritten to point at 2026-05-12/<slug> (<sid>)/."""


@dataclass(frozen=True)
class Entry:
    """One (session, lens-config) pair to archive."""
    session_id: str
    slug: str
    role: str  # "canonical" | "superseded" | "merge_source" | "labeled_duplicate"
    reason: str = ""


# Order roughly chronological for readability. Stable enumeration
# isn't load-bearing; the archive script doesn't depend on it.
ENTRIES: tuple[Entry, ...] = (
    # ⛔ MC 105 + 61mm dev-era shoots — all superseded by 06_231805.
    Entry("2026-05-05_133416", "NIKKOR Z MC 105mm f_2.8 VR S + 61mm extension",
          "superseded", "dev-era; superseded by 2026-05-06_231805"),
    Entry("2026-05-05_175758", "NIKKOR Z MC 105mm f_2.8 VR S + 61mm extension",
          "superseded", "dev-era; superseded by 2026-05-06_231805"),
    Entry("2026-05-05_205830", "NIKKOR Z MC 105mm f_2.8 VR S + 61mm extension",
          "superseded", "dev-era; superseded by 2026-05-06_231805"),
    Entry("2026-05-06_175727", "NIKKOR Z MC 105mm f_2.8 VR S + 61mm extension",
          "superseded", "pre-cascade; superseded by 2026-05-06_231805"),
    Entry("2026-05-06_225632", "NIKKOR Z MC 105mm f_2.8 VR S + 5T + 6T",
          "superseded", "abandoned redo of 2026-05-06_200150"),

    # ⭐ MC 105 canonical shoots.
    Entry("2026-05-06_231805", "NIKKOR Z MC 105mm f_2.8 VR S + 61mm extension",
          "canonical"),
    Entry("2026-05-06_200150", "NIKKOR Z MC 105mm f_2.8 VR S + 5T + 6T",
          "canonical"),
    Entry("2026-05-06_200150", "NIKKOR Z MC 105mm f_2.8 VR S + 6T + 5T",
          "canonical"),
    Entry("2026-05-07_082105", "NIKKOR Z MC 105mm f_2.8 VR S + 45mm extension",
          "canonical"),
    Entry("2026-05-07_163659", "NIKKOR Z MC 105mm f_2.8 VR S + 35mm extension",
          "canonical"),

    # ⛔ small early 24-120 + 61mm shoots; superseded by merged_24-120.
    Entry("2026-05-08_170101", "NIKKOR Z 24-120mm f_4 S + 61mm extension",
          "superseded", "early shoot; superseded by merged_24-120_2026-05-08"),
    Entry("2026-05-08_173604", "NIKKOR Z 24-120mm f_4 S + 61mm extension",
          "superseded", "small abandoned shoot"),
    Entry("2026-05-08_174545", "NIKKOR Z 24-120mm f_4 S + 61mm extension",
          "superseded", "small abandoned shoot"),

    # Merge sources for merged_24-120_2026-05-08.
    Entry("2026-05-08_175556", "NIKKOR Z 24-120mm f_4 S + 61mm extension",
          "merge_source", "feeds merged_24-120_2026-05-08 (anchor, offset 0.0)"),
    Entry("2026-05-08_201054", "NIKKOR Z 24-120mm f_4 S + 61mm extension",
          "merge_source", "feeds merged_24-120_2026-05-08 (offset -2.93 mm)"),

    # Merge sources for merged_viltrox-85_2026-05-10. The "ext1"/"ext2"/
    # "ext3" labels reflect per-source slug variants the user typed at
    # session start — all consolidated into one output slug at merge.
    Entry("2026-05-10_164247", "Viltrox 85mm f_2 EVO + 61mm extension",
          "merge_source", "feeds merged_viltrox-85_2026-05-10 as 'orig'"),
    Entry("2026-05-10_205515", "Viltrox 85mm extension",
          "merge_source", "feeds merged_viltrox-85_2026-05-10 as 'ext1'"),
    Entry("2026-05-10_212105", "Viltrox 85mm extension2",
          "merge_source", "feeds merged_viltrox-85_2026-05-10 as 'ext2'"),
    Entry("2026-05-10_212105", "Viltrox 85mm extension3",
          "merge_source", "feeds merged_viltrox-85_2026-05-10 as 'ext3'"),

    # ⭐ Standalone canonical shoots (May 11-12-13-14-15).
    Entry("2026-05-11_161129", "NIKKOR Z 24-120mm f_4 S + 45mm extension",
          "canonical"),
    Entry("2026-05-11_185420", "NIKKOR Z 24-120mm f_4 S + 35mm extension",
          "canonical"),
    Entry("2026-05-11_185420", "Viltrox 85mm f_2 EVO + 45mm extension",
          "canonical"),
    Entry("2026-05-11_220431", "Viltrox 85mm f_2 EVO + 26mm extension",
          "canonical"),
    Entry("2026-05-11_220431", "NIKKOR Z 24-120mm f_4 S + 10mm extension",
          "canonical"),
    Entry("2026-05-12_000950", "NIKKOR Z 24-120mm f_4 S",
          "canonical"),
    Entry("2026-05-12_201123", "Nikon Micro-Nikkor 55mm f_2.8 AIS — serial 287318",
          "canonical"),
    Entry("2026-05-12_214838", "Sigma Macro 105mm F2.8 EX DG OS HSM + 5T + 6T",
          "canonical"),
    Entry("2026-05-13_173213", "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T + 6T",
          "canonical"),

    # 2026-05-13_230021 — 4-config overnight: 3 canonical + the +5T
    # config superseded by 2026-05-14_132004 (audit D2.d).
    Entry("2026-05-13_230021", "Sigma APO Macro 150mm F2.8 EX DG OS HSM",
          "canonical"),
    Entry("2026-05-13_230021", "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 6T",
          "canonical"),
    Entry("2026-05-13_230021", "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 6T + 5T",
          "canonical"),
    Entry("2026-05-13_230021", "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T",
          "superseded", "21 reshoot rows flagged; user redid as 2026-05-14_132004"),

    # ⭐ Sigma 150 + 5T canonical pick (audit D2.d).
    Entry("2026-05-14_132004", "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T",
          "canonical"),

    Entry("2026-05-14_135837", "Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 6T + 5T",
          "canonical"),
    Entry("2026-05-14_151018", "Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED + 5T + 6T",
          "canonical"),
    Entry("2026-05-14_151018", "Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED",
          "canonical"),

    # Merge sources for merged_100-400-6T_2026-05-14.
    Entry("2026-05-14_174547", "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T",
          "merge_source", "feeds merged_100-400-6T_2026-05-14 as 'r1'"),
    Entry("2026-05-14_184841", "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T",
          "merge_source", "feeds merged_100-400-6T_2026-05-14 as 'r2' (anchor, offset -1.4)"),
    Entry("2026-05-14_194528", "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T",
          "merge_source", "feeds merged_100-400-6T_2026-05-14 as 'r3' (offset -3.9)"),

    # ⭐ Canon 500D variants (+ labeled duplicate).
    Entry("2026-05-14_203311", "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D",
          "canonical"),

    # ⛔ 500D + 61mm: superseded by 14_222616 c1 (audit D2.c; truncated bell).
    Entry("2026-05-14_213530", "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D + 61mm extension",
          "superseded", "truncated bell; superseded by 2026-05-14_222616 c1"),

    Entry("2026-05-14_222616", "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D + 35mm extension",
          "canonical"),
    Entry("2026-05-14_222616", "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D + 61mm extension",
          "canonical"),
    Entry("2026-05-14_222616", "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D (duplicate)",
          "labeled_duplicate", "deliberate-by-design re-shoot of 500D bare alongside the 14_203311 canonical"),

    # 2026-05-15_093455 splits: 35mm is a merge source, 61mm is the
    # sole shoot of that config (audit D1).
    Entry("2026-05-15_093455", "NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension",
          "merge_source", "feeds merged_100-400-35mm_2026-05-15 (anchor, offset 0.0)"),
    Entry("2026-05-15_093455", "NIKKOR Z 100-400mm f_4.5-5.6 VR S + 61mm extension",
          "canonical"),
    Entry("2026-05-15_112642", "NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension",
          "merge_source", "feeds merged_100-400-35mm_2026-05-15 (offset, offset 0.0)"),
    Entry("2026-05-15_121418", "NIKKOR Z 100-400mm f_4.5-5.6 VR S",
          "canonical"),
)


def entries_by_role(role: str) -> tuple[Entry, ...]:
    """Filter ENTRIES by role."""
    return tuple(e for e in ENTRIES if e.role == role)


def calibration_methodology(started_at_iso: str) -> str:
    """Return 'pre-cascade-fix' or 'post-cascade-fix' per audit D4
    cutoff. Falls back to 'unknown' for empty / unparseable input.
    """
    if not started_at_iso:
        return "unknown"
    try:
        started = dt.datetime.fromisoformat(started_at_iso)
    except ValueError:
        return "unknown"
    return "pre-cascade-fix" if started < CASCADE_FIX_CUTOFF else "post-cascade-fix"
