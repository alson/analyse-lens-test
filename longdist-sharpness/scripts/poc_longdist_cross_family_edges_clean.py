"""Cross-family edge comparison — CLEAN re-derivation (2026-01-30 + 2026-01-18).

This re-derives the §6a/§6b/§6c headline tables that were originally computed
on **2026-01-28** by ``poc_longdist_cross_family_edges_2026_01_28.py``. That
session is now EXCLUDED: every telephoto frame on 2026-01-28 was shot ISO 8000
at 16:05–16:34 (sun gone), centre luma-std ≈ 16 — roughly half the contrast of
the clean sessions — so its radial_cutoff readings are session-wide low-SNR.
See ``docs/LONGDIST_TELE_RESULTS.md`` §3.

Methodology is mirrored EXACTLY from the 2026-01-28 script:
- best-CENTRE aperture = the aperture maximising the centre (x=0.50) cutoff;
- ``sensor_cy_per_px = cutoff_subj × pixel_pitch / M`` with ``M = f_eff/distance``;
- ``FOM = sensor_cy_per_px × f_eff`` (= ``cutoff_subj × pixel_pitch × distance``);
- 5 field positions x ∈ {0.18, 0.34, 0.50, 0.66, 0.82};
- edge/centre = mean(x=0.18, x=0.82) / centre.

What changed vs the old script: instead of the single-day field-sweep
``summary.csv`` files, the field-position cutoffs are sourced from the
already-computed **v2 per_date CSVs**
(``poc_longdist_cross_date_v2_2026_01_out/per_date_<date>.csv``), using the
``top`` statistic (= max cutoff across all pooled replicates / ISO variants,
the analogue of the old "best tile in box" per position). The v2 metric is the
same §5.3 ``find_cutoff_from_spec`` + ``REF_BAND_SUBJ`` machinery, so ``top`` is
in cy/mm-subject, and ``fom_top`` is ``top × pitch × distance`` (verified to
match a fresh recompute to rounding). ``focal_mm`` is the EXIF-effective FL
(= f_eff). The per-date shooting distance is the same per-lens-family distance
the v2 script uses (84.0 m Z 100-400, 31.62 m 300 PF).

CRITICAL constraint: every family comparison is kept WITHIN a single date so
the cy/mm-subject (and FOM) numbers share a shooting distance.
- Z 100-400 family + 300 PF + F-mount TCs + Kenko → 2026-01-30
- 300 PF + TC-20e III (sold before 01-30; only clean source is 01-18 ISO 100)
  + a bare-300 / Z 100-400 bare cross-check → 2026-01-18

Output dir (next to this script):
    poc_longdist_cross_family_edges_clean_out/
        combined_edge_table_2026-01-30.{md,csv}
        combined_edge_table_2026-01-18.{md,csv}
        headline_6a_6b_6c.md         old→new §6a / §6b / §6c summary
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
V2_OUT = SCRIPTS / "poc_longdist_cross_date_v2_2026_01_out"
OUT = SCRIPTS / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)

Z7_PIXEL_PITCH_MM = 4.35e-3
FOCUS_DISTANCE_BY_LENS_KIND = {"Z100-400": 84_000.0, "PF300": 31_620.0}

FIELD_POSITIONS = [0.18, 0.34, 0.50, 0.66, 0.82]

# Per-date combo lists. Each entry: (display, norm_lens, focal_mm_str, lens_kind).
# focal_mm picks the combo's native full-extension effective FL, matching the
# old script's FAMILY_OF mapping (bare-400, Z TC-1.4×→560, Z TC-2.0×→800;
# 300 PF→300, TC-14e→420, TC-17e→500, TC-20e III→600, Kenko→420).
COMBOS_BY_DATE: dict[str, list[tuple[str, str, str, str]]] = {
    "2026-01-30": [
        ("Z 100-400 bare 400mm",         "Z 100-400 bare",             "400.0", "Z100-400"),
        ("Z 100-400 + Z TC-1.4x 560mm",  "Z 100-400 + Z TC-1.4x",      "560.0", "Z100-400"),
        ("Z 100-400 + Z TC-2.0x 800mm",  "Z 100-400 + Z TC-2.0x",      "800.0", "Z100-400"),
        ("300 PF bare 300mm",            "300 PF bare",                "300.0", "PF300"),
        ("300 PF + TC-14e I 420mm",      "300 PF + TC-14e I",          "420.0", "PF300"),
        ("300 PF + TC-14e III 420mm",    "300 PF + TC-14e III",        "420.0", "PF300"),
        ("300 PF + TC-17e II 500mm",     "300 PF + TC-17e II",         "500.0", "PF300"),
        ("300 PF + Kenko Pro 300 1.4x 420mm", "300 PF + Kenko Pro 300 1.4x", "420.0", "PF300"),
    ],
    "2026-01-18": [
        # 300 PF + TC-20e III is the headline combo here (only clean source).
        ("300 PF bare 300mm",            "300 PF bare",                "300.0", "PF300"),
        ("300 PF + TC-14e III 420mm",    "300 PF + TC-14e III",        "420.0", "PF300"),
        ("300 PF + TC-17e II 500mm",     "300 PF + TC-17e II",         "500.0", "PF300"),
        ("300 PF + TC-20e III 600mm",    "300 PF + TC-20e III",        "600.0", "PF300"),
        ("Z 100-400 bare 400mm",         "Z 100-400 bare",             "400.0", "Z100-400"),
    ],
}


@dataclass
class Cell:
    norm_lens: str
    focal_mm: float
    aperture: str
    aperture_f: float
    position_frac: float
    lens_kind: str
    top: float          # cutoff in cy/mm-subject
    fom_top: float      # = top × pitch × distance

    @property
    def sensor_cy_per_px(self) -> float:
        M = self.focal_mm / FOCUS_DISTANCE_BY_LENS_KIND[self.lens_kind]
        return self.top * Z7_PIXEL_PITCH_MM / M


def load_per_date(date: str) -> list[Cell]:
    path = V2_OUT / f"per_date_{date}.csv"
    cells: list[Cell] = []
    with path.open() as fh:
        for r in csv.DictReader(fh):
            cells.append(Cell(
                norm_lens=r["norm_lens"],
                focal_mm=float(r["focal_mm"]),
                aperture=r["aperture"],
                aperture_f=float(r["aperture_f"]),
                position_frac=float(r["position_frac"]),
                lens_kind=r["lens_kind"],
                top=float(r["top"]),
                fom_top=float(r["fom_top"]),
            ))
    return cells


def best_centre_aperture(cells: list[Cell], norm_lens: str, focal_mm: str) -> str:
    cands = [c for c in cells
             if c.norm_lens == norm_lens and f"{c.focal_mm:.1f}" == focal_mm
             and abs(c.position_frac - 0.50) < 1e-6]
    if not cands:
        return ""
    return max(cands, key=lambda c: c.top).aperture


def chosen_rows(cells: list[Cell], norm_lens: str, focal_mm: str, aperture: str) -> dict[float, Cell]:
    rows = [c for c in cells
            if c.norm_lens == norm_lens and f"{c.focal_mm:.1f}" == focal_mm
            and c.aperture == aperture]
    return {round(c.position_frac, 2): c for c in rows}


@dataclass
class ComboResult:
    display: str
    f_eff: float
    aperture: str
    by_pos: dict[float, Cell]

    def _g(self, p: float):
        return self.by_pos.get(p)

    @property
    def centre(self) -> Cell | None:
        return self._g(0.50)

    def subj_edge_centre(self) -> float:
        c018, c050, c082 = self._g(0.18), self._g(0.50), self._g(0.82)
        if not (c018 and c050 and c082) or c050.top <= 0:
            return float("nan")
        return (c018.top + c082.top) / 2 / c050.top

    def fom_edge_centre(self) -> float:
        c018, c050, c082 = self._g(0.18), self._g(0.50), self._g(0.82)
        if not (c018 and c050 and c082) or c050.fom_top <= 0:
            return float("nan")
        return (c018.fom_top + c082.fom_top) / 2 / c050.fom_top


def build_combo_results(date: str) -> list[ComboResult]:
    cells = load_per_date(date)
    out: list[ComboResult] = []
    for disp, nl, fl, _kind in COMBOS_BY_DATE[date]:
        ap = best_centre_aperture(cells, nl, fl)
        if not ap:
            print(f"  [{date}] MISSING: {disp}")
            continue
        by_pos = chosen_rows(cells, nl, fl, ap)
        out.append(ComboResult(display=disp, f_eff=float(fl), aperture=ap, by_pos=by_pos))
    return out


def write_edge_table(date: str, results: list[ComboResult]) -> None:
    md = [
        f"# Cross-family edge comparison — best centre-aperture per combo ({date}, CLEAN)",
        "",
        "Re-derivation of the old 2026-01-28 §6 tables on a clean date. "
        "2026-01-28 is excluded (session-wide ISO 8000, low-SNR — see "
        "`LONGDIST_TELE_RESULTS.md` §3). Field-position cutoffs sourced from "
        f"`poc_longdist_cross_date_v2_2026_01_out/per_date_{date}.csv` (`top` "
        "statistic = max across pooled replicates / ISO variants).",
        "",
        "Each row: cutoff at x=0.18 / centre (x=0.50) / x=0.82, at the aperture "
        "that maximises the centre cutoff. `cy/mm-subj` shares this date's "
        "shooting distance per family; `FOM = sensor cy/px × f_eff = "
        "cutoff_subj × pitch × distance` is the distance-fair figure of merit.",
        "",
        "## cy/mm-subject (within-family interpretation)",
        "",
        "| Combo | f_eff | F# | x=0.18 | centre | x=0.82 | edge / centre |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        c018, c050, c082 = r._g(0.18), r._g(0.50), r._g(0.82)
        if not (c018 and c050 and c082):
            continue
        md.append(
            f"| {r.display} | {r.f_eff:.0f}mm | {r.aperture} | "
            f"{c018.top:.2f} | **{c050.top:.2f}** | {c082.top:.2f} | "
            f"{r.subj_edge_centre():.2f} |"
        )
    md += [
        "",
        "## FOM = sensor cy/px × f_eff (cross-family, distance-fair)",
        "",
        "| Combo | f_eff | F# | x=0.18 | centre | x=0.82 | edge / centre |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        c018, c050, c082 = r._g(0.18), r._g(0.50), r._g(0.82)
        if not (c018 and c050 and c082):
            continue
        md.append(
            f"| {r.display} | {r.f_eff:.0f}mm | {r.aperture} | "
            f"{c018.fom_top:.0f} | **{c050.fom_top:.0f}** | {c082.fom_top:.0f} | "
            f"{r.fom_edge_centre():.2f} |"
        )
    (OUT / f"combined_edge_table_{date}.md").write_text("\n".join(md) + "\n")

    with (OUT / f"combined_edge_table_{date}.csv").open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["date", "combo", "f_eff_mm", "aperture", "position_frac",
                     "cutoff_cy_per_mm_subj", "sensor_cy_per_px", "fom"])
        for r in results:
            for p in FIELD_POSITIONS:
                c = r._g(p)
                if c is None:
                    continue
                wr.writerow([date, r.display, r.f_eff, r.aperture, p,
                             f"{c.top:.4f}", f"{c.sensor_cy_per_px:.5f}", f"{c.fom_top:.2f}"])


def write_headline(res30: list[ComboResult], res18: list[ComboResult]) -> None:
    def find(results, key):
        for r in results:
            if r.display.startswith(key):
                return r
        return None

    md = [
        "# §6a / §6b / §6c — CLEAN re-derivation (old→new)",
        "",
        "Old numbers were all from 2026-01-28 (now excluded as session-wide",
        "ISO-8000 low-SNR). New numbers re-derived within a single clean date.",
        "",
        "## §6a — TC vs cropping the bare 400 mm frame (Z 100-400 family, 2026-01-30)",
        "",
        "Bare-400 centre cutoff is the cropping ceiling (crop+upsample adds no",
        "information). Compared against the Z TCs at their native effective FL.",
        "",
    ]
    bare = find(res30, "Z 100-400 bare 400mm")
    tc14 = find(res30, "Z 100-400 + Z TC-1.4x")
    tc20 = find(res30, "Z 100-400 + Z TC-2.0x")
    if bare and tc14 and tc20 and bare.centre:
        b = bare.centre.top
        g14 = (tc14.centre.top / b - 1) * 100 if tc14.centre else float("nan")
        g20 = (tc20.centre.top / b - 1) * 100 if tc20.centre else float("nan")
        md += [
            "| Comparison (84 m) | bare-cropped ceiling | TC chain centre | gain |",
            "|---|---|---|---|",
            f"| 560 mm effective | {b:.2f} (bare 400 {bare.aperture}) | "
            f"{tc14.centre.top:.2f} (TC-1.4× {tc14.aperture}) | **{g14:+.0f}%** |",
            f"| 800 mm effective | {b:.2f} (bare 400 {bare.aperture}) | "
            f"{tc20.centre.top:.2f} (TC-2.0× {tc20.aperture}) | **{g20:+.0f}%** |",
            "",
            "OLD (2026-01-28): TC-1.4× **+24%**, TC-2.0× **+65%**.",
            "",
        ]
    md += [
        "## §6b — FOM ranking at each combo's best-centre aperture",
        "",
        "Sorted by FOM (= sensor cy/px × f_eff). Within-date only; the Z 100-400",
        "family + F-mount-TC families are all on 2026-01-30; TC-20e III is on",
        "2026-01-18 (kept on its own date, distances differ so FOM is the fair",
        "cross-family number but absolute level is not cross-date-comparable).",
        "",
        "| FOM | Combo | f_eff | F# | date |",
        "|---|---|---|---|---|",
    ]
    ranked = []
    for date, results in [("2026-01-30", res30), ("2026-01-18", res18)]:
        for r in results:
            if r.centre:
                ranked.append((r.centre.fom_top, r.display, r.f_eff, r.aperture, date))
    for fom, disp, fl, ap, date in sorted(ranked, reverse=True):
        md.append(f"| {fom:.0f} | {disp} | {fl:.0f}mm | {ap} | {date} |")
    md += [
        "",
        "OLD (2026-01-28): Z 100-400 + Z TC-2.0× @ 800 f/11 dominated (FOM 103);",
        "every F-mount TC on the 300 PF net-negative vs bare; Kenko competitive.",
        "",
        "## §6c — edge / centre per combo (best-centre aperture)",
        "",
        "| Combo | date | F# | edge/centre (cy/mm) | edge/centre (FOM) |",
        "|---|---|---|---|---|",
    ]
    for date, results in [("2026-01-30", res30), ("2026-01-18", res18)]:
        for r in results:
            md.append(f"| {r.display} | {date} | {r.aperture} | "
                      f"{r.subj_edge_centre():.2f} | {r.fom_edge_centre():.2f} |")
    md += [
        "",
        "OLD (2026-01-28): Z family flat 1.05–1.12; 300 PF bare 0.60;",
        "**300 PF + TC-20e III = 1.24** (the anomaly).",
        "",
        "NOTE on the TC-20e III anomaly: it is sourced clean from 2026-01-18",
        "ISO 100 here (TC-20e III was sold before 2026-01-30). The edge>centre",
        "pattern PERSISTS on clean data (see table) — so it is NOT a 2026-01-28",
        "low-SNR artefact. It is the 'pick-the-sharpest-tile on a 3D scene'",
        "protocol artefact combined with the TC-20e III's genuinely soft on-axis",
        "delivery: the centre cutoff is consistently the lowest of the 5 slices.",
    ]
    (OUT / "headline_6a_6b_6c.md").write_text("\n".join(md) + "\n")


def main() -> int:
    print(f"output dir: {OUT}")
    res30 = build_combo_results("2026-01-30")
    res18 = build_combo_results("2026-01-18")
    write_edge_table("2026-01-30", res30)
    write_edge_table("2026-01-18", res18)
    write_headline(res30, res18)
    print("Wrote combined_edge_table_{2026-01-30,2026-01-18}.{md,csv} + headline_6a_6b_6c.md")

    # Echo the headline to stdout for the run log.
    print((OUT / "headline_6a_6b_6c.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
