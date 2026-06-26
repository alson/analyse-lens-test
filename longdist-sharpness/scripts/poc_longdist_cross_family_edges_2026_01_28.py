"""Cross-family edge comparison: combine 100-400 + Z TCs vs 300 PF + F-mount TCs.

Reads the field-sweep summary CSVs from the two POCs and emits:
- combined_edge_table.md / .csv: one row per (combo, position) at the combo's
  best CENTER aperture, with both cy/mm-subject and the distant-subject
  figure of merit (sensor_cy_per_px * f_eff).
- combined_field_curves_FOM.png: field curves in FOM units (distance-
  normalised) so the two families can be put on the same y-axis.

Best CENTER aperture is the aperture that maximises cutoff at x=0.50 for
each combo -- that's the natural "what aperture would you pick?" choice.
Then we read the off-axis numbers at THAT aperture: edge performance
that you actually get when shooting at the centre-optimal stop.

This is the cross-family-fair view of edge sharpness because (a) sensor
cy/pixel is scene/distance-independent on the lens-MTF side, and (b)
multiplying by f_eff is what governs subject-detail at fixed distance
(see prior discussion). Within-family interpretation in cy/mm-subject
is also emitted for context.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
OUT = SCRIPTS / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)

Z7_PIXEL_PITCH_MM = 4.35e-3

# (family, csv_path, focus_distance_mm)
FAMILY_SOURCES = [
    ("Z100-400",    SCRIPTS / "poc_longdist_100_400_field_2026_01_28_out" / "summary.csv", 84_000.0),
    ("300 PF",      SCRIPTS / "poc_longdist_300pf_field_2026_01_28_out"   / "summary.csv", 31_620.0),
]

CONFIG_ORDER = [
    ("Z100-400_bare",   "Z 100-400 bare 400mm"),
    ("Z100-400_TC14",   "Z 100-400 + Z TC1.4x (560mm)"),
    ("Z100-400_TC20",   "Z 100-400 + Z TC2.0x (800mm)"),
    ("PF_300",          "300 PF bare 300mm"),
    ("PF_TC14eI",       "300 PF + TC-14e I (420mm)"),
    ("PF_TC14eIII",     "300 PF + TC-14e III (420mm)"),
    ("PF_TC17eII",      "300 PF + TC-17e II (500mm)"),
    ("PF_TC20eIII",     "300 PF + TC-20e III (600mm)"),
]

FAMILY_OF = {
    "Z100-400_bare": ("Z100-400", 84_000.0, 400.0),
    "Z100-400_TC14": ("Z100-400", 84_000.0, 560.0),
    "Z100-400_TC20": ("Z100-400", 84_000.0, 800.0),
    "PF_300":        ("300 PF", 31_620.0, 300.0),
    "PF_TC14eI":     ("300 PF", 31_620.0, 420.0),
    "PF_TC14eIII":   ("300 PF", 31_620.0, 420.0),
    "PF_TC17eII":    ("300 PF", 31_620.0, 500.0),
    "PF_TC20eIII":   ("300 PF", 31_620.0, 600.0),
}

COLOURS = {
    "Z100-400_bare":  "tab:blue",
    "Z100-400_TC14":  "tab:orange",
    "Z100-400_TC20":  "tab:red",
    "PF_300":         "tab:green",
    "PF_TC14eI":      "tab:olive",
    "PF_TC14eIII":    "tab:cyan",
    "PF_TC17eII":     "tab:purple",
    "PF_TC20eIII":    "tab:pink",
}

FIELD_POSITIONS = [0.18, 0.34, 0.50, 0.66, 0.82]


@dataclass
class Row:
    config: str
    aperture: str
    f_eff: float
    pos: float
    cutoff_subj: float
    distance_mm: float

    @property
    def sensor_cy_per_px(self) -> float:
        M = self.f_eff / self.distance_mm
        return self.cutoff_subj * Z7_PIXEL_PITCH_MM / M

    @property
    def fom(self) -> float:
        """sensor_cy_per_px * f_eff -- proportional to subject cy/mm at a
        chosen fixed distance."""
        return self.sensor_cy_per_px * self.f_eff


def load_family(csv_path: Path, distance_mm: float) -> list[Row]:
    rows: list[Row] = []
    with csv_path.open() as fh:
        rdr = csv.DictReader(fh)
        for r in rdr:
            rows.append(Row(
                config=r["config"], aperture=r["aperture"], f_eff=float(r["f_eff_mm"]),
                pos=float(r["position_frac"]),
                cutoff_subj=float(r["cutoff_cy_per_mm_subject"]),
                distance_mm=distance_mm,
            ))
    return rows


def best_centre_aperture(rows: list[Row], config: str) -> str:
    candidates = [r for r in rows if r.config == config and abs(r.pos - 0.50) < 1e-6]
    if not candidates:
        return ""
    return max(candidates, key=lambda r: r.cutoff_subj).aperture


def main() -> int:
    all_rows: list[Row] = []
    for family, path, dist in FAMILY_SOURCES:
        if not path.exists():
            print(f"missing: {path}")
            continue
        all_rows.extend(load_family(path, dist))

    # For each combo: best centre aperture, plus all field positions at that aperture
    chosen: dict[str, list[Row]] = {}
    for cfg, _disp in CONFIG_ORDER:
        ap = best_centre_aperture(all_rows, cfg)
        if not ap:
            continue
        chosen[cfg] = [r for r in all_rows if r.config == cfg and r.aperture == ap]

    # Build combined edge table
    lines = [
        "# Cross-family edge comparison — best centre-aperture per combo (2026-01-28)",
        "",
        "Each row: cutoff at x=0.18 (far left), x=0.50 (centre), x=0.82 (far right).",
        "`cy/mm-subj` reflects each family's own shooting distance (84m vs 31.62m).",
        "`FOM = sensor cy/px * f_eff` is the distance-invariant figure of merit:",
        "proportional to subject cy/mm at any fixed distance, so the right number",
        "for the 'bird across the inlet' use case.",
        "",
        "## cy/mm-subject (within-family interpretation)",
        "",
        "| Combo | f_eff | F# | x=0.18 | centre | x=0.82 | edge / centre |",
        "|---|---|---|---|---|---|---|",
    ]
    for cfg, disp in CONFIG_ORDER:
        if cfg not in chosen:
            continue
        rows = chosen[cfg]
        by_pos = {round(r.pos, 2): r for r in rows}
        c018 = by_pos.get(0.18); c050 = by_pos.get(0.50); c082 = by_pos.get(0.82)
        if not (c018 and c050 and c082):
            continue
        edge_avg = (c018.cutoff_subj + c082.cutoff_subj) / 2
        ratio = edge_avg / c050.cutoff_subj if c050.cutoff_subj > 0 else float("nan")
        lines.append(
            f"| {disp} | {c050.f_eff:.0f}mm | {c050.aperture} | "
            f"{c018.cutoff_subj:.2f} | **{c050.cutoff_subj:.2f}** | {c082.cutoff_subj:.2f} | "
            f"{ratio:.2f} |"
        )

    lines += [
        "",
        "## FOM = sensor cy/px × f_eff (cross-family, distance-fair)",
        "",
        "Distance-normalised: this is what you actually get at the subject when",
        "the distance is fixed (more = more subject detail per mm).",
        "",
        "| Combo | f_eff | F# | x=0.18 | centre | x=0.82 | edge / centre |",
        "|---|---|---|---|---|---|---|",
    ]
    for cfg, disp in CONFIG_ORDER:
        if cfg not in chosen:
            continue
        rows = chosen[cfg]
        by_pos = {round(r.pos, 2): r for r in rows}
        c018 = by_pos.get(0.18); c050 = by_pos.get(0.50); c082 = by_pos.get(0.82)
        if not (c018 and c050 and c082):
            continue
        edge_avg = (c018.fom + c082.fom) / 2
        ratio = edge_avg / c050.fom if c050.fom > 0 else float("nan")
        lines.append(
            f"| {disp} | {c050.f_eff:.0f}mm | {c050.aperture} | "
            f"{c018.fom:.0f} | **{c050.fom:.0f}** | {c082.fom:.0f} | "
            f"{ratio:.2f} |"
        )

    lines += [
        "",
        "## Reading the edge / centre column",
        "",
        "- 1.00 = edges as sharp as centre. Long-tele on planar distant scene rarely",
        "  achieves this (off-axis aberrations + slight field curvature).",
        "- 0.70-0.90 is typical for a good long-tele on a flat-ish distant subject.",
        "- < 0.60 = soft edges -- avoid leaving important detail there.",
        "- > 1.00 can happen on 3D scenes because the sharpest tile in an edge slice",
        "  may sit on a branch that happens to be closer to the focal plane than",
        "  whatever the centre tile landed on. This is a known artefact of the 'pick",
        "  the sharpest tile per slice' protocol on 3D subjects. Treat such cases",
        "  as 'edge is at least as sharp as centre, possibly more'.",
        "",
        "## Caveats",
        "",
        "- Field positions are picked by gradient-energy maximum in a per-position",
        "  search box: they correspond to wherever the lens's focal plane hit a",
        "  sharp subject element in that slice. Not a controlled flat target.",
        "- Different shooting distance per family (84m vs 31.62m) -- the FOM column",
        "  normalises that on the lens-MTF side; residual scene-statistics bias may",
        "  remain in the cy/mm-subj column.",
    ]
    out_md = OUT / "combined_edge_table.md"
    out_md.write_text("\n".join(lines) + "\n")

    # CSV
    with (OUT / "combined_edge_table.csv").open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["combo", "display", "f_eff_mm", "aperture", "position_frac",
                     "cutoff_cy_per_mm_subj", "sensor_cy_per_px", "fom_sensor_cy_px_times_f_eff"])
        for cfg, disp in CONFIG_ORDER:
            if cfg not in chosen:
                continue
            for r in sorted(chosen[cfg], key=lambda r: r.pos):
                wr.writerow([cfg, disp, r.f_eff, r.aperture, r.pos,
                             r.cutoff_subj, r.sensor_cy_per_px, r.fom])

    # Plot field curves in FOM units (cross-family)
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5))
    ax_subj, ax_fom = axes
    for cfg, disp in CONFIG_ORDER:
        if cfg not in chosen:
            continue
        rows_sorted = sorted(chosen[cfg], key=lambda r: r.pos)
        xs = [r.pos for r in rows_sorted]
        ys_subj = [r.cutoff_subj for r in rows_sorted]
        ys_fom  = [r.fom for r in rows_sorted]
        ap = rows_sorted[0].aperture
        lbl = f"{disp}  {ap}"
        ax_subj.plot(xs, ys_subj, marker="o", lw=1.8, color=COLOURS.get(cfg, "k"), label=lbl)
        ax_fom .plot(xs, ys_fom,  marker="o", lw=1.8, color=COLOURS.get(cfg, "k"), label=lbl)

    for ax in axes:
        ax.set_xlabel("field x (fraction of image width)")
        ax.set_xticks(FIELD_POSITIONS)
        ax.set_xticklabels([f"{p:.2f}" for p in FIELD_POSITIONS])
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8, loc="upper left")
    ax_subj.set_ylabel("cutoff (cy/mm subject)")
    ax_subj.set_title("Within-family (cy/mm subject)\nfair across configs of the same family")
    ax_fom.set_ylabel("FOM = sensor cy/px × f_eff (mm)")
    ax_fom.set_title("Cross-family (FOM)\nfair across families; proportional to subject cy/mm at fixed distance")
    fig.suptitle("Cross-family edge performance, best centre-aperture per combo (2026-01-28)")
    fig.tight_layout()
    fig.savefig(OUT / "combined_field_curves.png", dpi=120)
    plt.close(fig)

    print(f"Wrote {OUT}/combined_edge_table.{{md,csv}}, combined_field_curves.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
