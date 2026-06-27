"""Cross-date long-distance sharpness analysis (v2).

Differences from v1 (``poc_longdist_cross_date_2026_01.py``):

- **No lowest-ISO filter**. All ISO variants are measured; the *sharpest-
  of-ISO* aggregation happens per (lens, FL, aperture, position) at
  post-processing time. This corrects the v1 anomaly where slow-shutter
  low-ISO frames suffering wind shake displaced the actually-sharper
  higher-ISO frames at small apertures.
- **Per-replicate capture.** v1 only stored the best replicate per
  position. v2 stores every replicate so we can compute top / median /
  min / top_vs_median / range_pct for each cell. These are the "is the
  top reading a fluke or consistent?" stats the user requested.

Aggregation per (lens, FL, aperture, position):

  ``top``           = max cutoff across all replicates of all ISO variants
                      → headline number (best the lens delivered)
  ``median``        = median across the pooled replicates (typical reading)
  ``min``           = min across the pool (lower bound; worst replicate)
  ``top_vs_median`` = ratio top / median. >1.10 = top is a flier vs typical;
                      ≈1.00 = top is consistent with typical.
  ``range_pct``     = (top - min) / median * 100; total spread as % of typical.
  ``n_replicates``  = total replicates pooled (across ISO variants)
  ``best_iso_label``= the iso/raw_lens_name that produced the top reading

Note on n_replicates interpretation per
``SHARPNESS_METRICS_LONGDIST.md`` §2.2 / user's clarification:
in 3D scenes, replicates re-trigger AF (or the user shot multiple
ISO variants to dodge wind shake), so more replicates = more depth-
sampling chances. ``top`` is "what the lens delivered when AF / ISO
landed well"; ``median`` and ``min`` track the typical and the worst.

Output dir (next to this script):
    poc_longdist_cross_date_2026_01_v2_out/
        per_date_<date>.{csv,md}        per-cell top/median/min/etc.
        overlap.{csv,md}                cross-date overlap with content-independence
"""
from __future__ import annotations

import csv
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from poc_longdist_algorithms import find_cutoff_from_spec  # noqa: E402

OUT = Path(__file__).parent / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)

DATE_SOURCES = [
    ("2026-01-18", Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-18")),
    ("2026-01-28", Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-28")),
    ("2026-01-30", Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-30")),
]

Z7_PIXEL_PITCH_MM = 4.35e-3
LAMBDA_MM = 550e-6
FOCUS_DISTANCE_BY_LENS_KIND = {"Z100-400": 84_000.0, "PF300": 31_620.0}


def distance_class(focal_mm: float, distance_mm: float) -> str:
    """Per Reikan Focal's two-tier rule
    (https://blog.reikanfocal.com/faq/ideal-distance-for-afma-auto-focus-calibration/).
    For FL ≥ 300 mm the at-distance minimum is 20× FL; for FL < 300 mm
    it is 50× FL. 100× FL is the classic "infinity" threshold; above
    300× FL is well-past-infinity."""
    if focal_mm <= 0 or distance_mm <= 0:
        return "unknown"
    ratio = distance_mm / focal_mm
    min_ratio = 20.0 if focal_mm >= 300.0 else 50.0
    if ratio < min_ratio:
        return "below Focal min"
    if ratio < 100.0:
        return "meets Focal min, <100×FL"
    if ratio < 300.0:
        return "infinity-class"
    return "well past infinity"

TILE = 256
SEARCH_STEP = 64
FIELD_POSITIONS = [0.18, 0.34, 0.50, 0.66, 0.82]
FIELD_BOX_W_FRAC = 0.15
FIELD_BOX_H_FRAC = 0.20

# §5.3: lowered REF_BAND_SUBJ from (0.01, 0.20) to (0.01, 0.10) plus
# smoothing + last-crossing inside find_cutoff_from_spec.
REF_BAND_SUBJ = (0.01, 0.10)
CUTOFF_THRESHOLD = 0.05


# --------------------------------------------------------------------- config classification

_RE_ISO   = re.compile(r"\s+ISO\d+(\s|$)")
_RE_FL    = re.compile(r"^(\d+(?:\.\d+)?)\s*mm$")
_RE_APER  = re.compile(r"^F(\d+(?:\.\d+)?)$")

def lens_kind(name: str) -> str | None:
    if "100-400" in name:
        return "Z100-400"
    if "300mm f_4E PF" in name:
        return "PF300"
    return None

def normalise_lens_name(name: str) -> str:
    n = _RE_ISO.sub(" ", name).strip()
    n = re.sub(r"\s+", " ", n)
    mapping = [
        ("NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x", "Z 100-400 + Z TC-1.4x"),
        ("NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-2.0x", "Z 100-400 + Z TC-2.0x"),
        ("NIKKOR Z 100-400mm f_4.5-5.6 VR S",            "Z 100-400 bare"),
        ("Nikon AF-S Nikkor 300mm f_4E PF ED VR + Kenko Pro 300 DG 1.4x", "300 PF + Kenko Pro 300 1.4x"),
        ("Nikon AF-S Nikkor 300mm f_4E PF ED VR + TC-14e III", "300 PF + TC-14e III"),
        ("Nikon AF-S Nikkor 300mm f_4E PF ED VR + TC-14e I",   "300 PF + TC-14e I"),
        ("Nikon AF-S Nikkor 300mm f_4E PF ED VR + TC-17e II",  "300 PF + TC-17e II"),
        ("Nikon AF-S Nikkor 300mm f_4E PF ED VR + TC-20e III", "300 PF + TC-20e III"),
        ("Nikon AF-S Nikkor 300mm f_4E PF ED VR",              "300 PF bare"),
    ]
    for prefix, short in mapping:
        if n.startswith(prefix):
            return short
    return n


def iso_of(name: str) -> int:
    m = re.search(r"ISO(\d+)", name)
    return int(m.group(1)) if m else 0


# --------------------------------------------------------------------- discovery

@dataclass
class Config:
    date: str
    raw_lens_name: str
    norm_lens: str
    lens_kind: str
    focal_mm: float
    aperture: str
    aperture_f: float
    jpegs: list[Path] = field(default_factory=list)

    @property
    def M(self) -> float:
        return self.focal_mm / FOCUS_DISTANCE_BY_LENS_KIND[self.lens_kind]

    @property
    def iso(self) -> int:
        return iso_of(self.raw_lens_name)


def discover_configs(date: str, root: Path) -> list[Config]:
    out: list[Config] = []
    if not root.is_dir():
        return out
    for lens in sorted(root.iterdir()):
        if not lens.is_dir():
            continue
        kind = lens_kind(lens.name)
        if kind is None:
            continue
        norm = normalise_lens_name(lens.name)
        for fl in sorted(lens.iterdir()):
            if not fl.is_dir():
                continue
            mf = _RE_FL.match(fl.name)
            if not mf:
                continue
            focal = float(mf.group(1))
            for ap in sorted(fl.iterdir()):
                if not ap.is_dir():
                    continue
                ma = _RE_APER.match(ap.name)
                if not ma:
                    continue
                ap_f = float(ma.group(1))
                jpegs = sorted(ap.glob("*.jpg"))
                if not jpegs:
                    continue
                out.append(Config(
                    date=date, raw_lens_name=lens.name, norm_lens=norm,
                    lens_kind=kind, focal_mm=focal,
                    aperture=ap.name, aperture_f=ap_f, jpegs=jpegs,
                ))
    return out


# --------------------------------------------------------------------- metric

def load_luma(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("L"), dtype=np.float32)


def radial_spectrum(tile: np.ndarray) -> np.ndarray:
    tile = tile - tile.mean()
    n = tile.shape[0]
    w = np.hanning(n)
    tile = tile * np.outer(w, w)
    F = np.fft.fftshift(np.fft.fft2(tile))
    P = (F.real ** 2 + F.imag ** 2)
    cy, cx = n // 2, n // 2
    y, x = np.indices(P.shape)
    r = np.sqrt((y - cy) ** 2 + (x - cx) ** 2).astype(np.int32)
    rmax = n // 2
    radial = np.bincount(r.ravel(), P.ravel(), minlength=rmax + 1)[: rmax + 1]
    counts = np.bincount(r.ravel(), minlength=rmax + 1)[: rmax + 1]
    counts = np.maximum(counts, 1)
    return radial / counts


def best_tile_in_box(luma: np.ndarray, y0: int, x0: int, h: int, w: int) -> tuple[np.ndarray, float]:
    region = luma[y0:y0+h, x0:x0+w]
    best, best_score = None, -1.0
    for y in range(0, region.shape[0] - TILE + 1, SEARCH_STEP):
        for x in range(0, region.shape[1] - TILE + 1, SEARCH_STEP):
            t = region[y:y+TILE, x:x+TILE]
            gy = np.diff(t, axis=0); gx = np.diff(t, axis=1)
            s = float((gy * gy).mean() + (gx * gx).mean())
            if s > best_score:
                best_score, best = s, t
    return best, best_score


def field_boxes(shape: tuple[int, int]):
    H, W = shape
    bw = int(W * FIELD_BOX_W_FRAC)
    bh = int(H * FIELD_BOX_H_FRAC)
    y0 = (H - bh) // 2
    out = []
    for fx in FIELD_POSITIONS:
        cx = int(W * fx)
        x0 = max(0, cx - bw // 2)
        if x0 + bw > W:
            x0 = W - bw
        out.append((fx, (y0, x0, bh, bw)))
    return out


def normalised_cutoff_from_tile(tile: np.ndarray, M: float) -> float:
    spec = radial_spectrum(tile)
    n = tile.shape[0]
    sensor_cy_per_px = np.arange(n // 2 + 1) / n
    subject_cy_per_mm = sensor_cy_per_px / Z7_PIXEL_PITCH_MM * M
    cutoff, _ = find_cutoff_from_spec(spec, subject_cy_per_mm,
                                       ref_band=REF_BAND_SUBJ,
                                       threshold=CUTOFF_THRESHOLD)
    return cutoff


# --------------------------------------------------------------------- per-config measurement

@dataclass
class Replicate:
    """One cutoff value at one (config, position, replicate-index)."""
    iso: int
    raw_lens_name: str
    jpeg: str
    position_frac: float
    cutoff: float


def measure_all_replicates(configs: list[Config]) -> dict[tuple, list[Replicate]]:
    """For each config, for each replicate, for each position, compute cutoff.
    Group by (norm_lens, focal_mm, aperture, position_frac) — pools all ISO
    variants together for the v2 sharpest-of-ISO aggregation."""
    grouped: dict[tuple, list[Replicate]] = {}
    total = len(configs)
    for idx, cfg in enumerate(configs, 1):
        print(f"  [{idx}/{total}] {cfg.norm_lens} | {cfg.focal_mm}mm | {cfg.aperture} | ISO{cfg.iso} | "
              f"{len(cfg.jpegs)} repl", flush=True)
        for jp in cfg.jpegs:
            luma = load_luma(jp)
            H, W = luma.shape
            boxes = field_boxes((H, W))
            for fx, (y0, x0, bh, bw) in boxes:
                tile, _ = best_tile_in_box(luma, y0, x0, bh, bw)
                if tile is None:
                    continue
                c = normalised_cutoff_from_tile(tile, cfg.M)
                key = (cfg.norm_lens, cfg.focal_mm, cfg.aperture, cfg.aperture_f, fx, cfg.lens_kind)
                grouped.setdefault(key, []).append(Replicate(
                    iso=cfg.iso, raw_lens_name=cfg.raw_lens_name,
                    jpeg=jp.name, position_frac=fx, cutoff=c,
                ))
    return grouped


# --------------------------------------------------------------------- aggregation

@dataclass
class CellStats:
    norm_lens: str
    focal_mm: float
    aperture: str
    aperture_f: float
    position_frac: float
    lens_kind: str
    n_replicates: int
    isos_present: list[int]
    top: float
    median: float
    minv: float
    top_vs_median: float
    range_pct: float
    best_iso: int
    best_raw_lens_name: str
    best_jpeg: str

    @property
    def M(self) -> float:
        return self.focal_mm / FOCUS_DISTANCE_BY_LENS_KIND[self.lens_kind]

    @property
    def fom(self) -> float:
        return self.top * Z7_PIXEL_PITCH_MM * FOCUS_DISTANCE_BY_LENS_KIND[self.lens_kind]


def aggregate(grouped: dict[tuple, list[Replicate]]) -> list[CellStats]:
    out: list[CellStats] = []
    for key, replicates in grouped.items():
        norm_lens, focal_mm, aperture, aperture_f, position_frac, lens_kind = key
        # Drop NaNs
        valid = [r for r in replicates if not np.isnan(r.cutoff)]
        if not valid:
            continue
        cutoffs = [r.cutoff for r in valid]
        top = max(cutoffs)
        med = float(statistics.median(cutoffs))
        mn  = min(cutoffs)
        tvm = top / med if med > 0 else float("nan")
        rng_pct = (top - mn) / med * 100 if med > 0 else float("nan")
        best_r = max(valid, key=lambda r: r.cutoff)
        out.append(CellStats(
            norm_lens=norm_lens, focal_mm=focal_mm,
            aperture=aperture, aperture_f=aperture_f,
            position_frac=position_frac, lens_kind=lens_kind,
            n_replicates=len(valid),
            isos_present=sorted({r.iso for r in valid}),
            top=top, median=med, minv=mn,
            top_vs_median=tvm, range_pct=rng_pct,
            best_iso=best_r.iso, best_raw_lens_name=best_r.raw_lens_name,
            best_jpeg=best_r.jpeg,
        ))
    out.sort(key=lambda c: (c.norm_lens, c.focal_mm, c.aperture_f, c.position_frac))
    return out


# --------------------------------------------------------------------- writers

def write_per_date(cells: list[CellStats], date: str, out_csv: Path, out_md: Path) -> None:
    """Wide table: one row per (lens, FL, aperture) with 5-position values
    for top, plus a flier-indicator column showing the worst top_vs_median
    across the 5 positions."""
    # CSV: one row per (cell)
    with out_csv.open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["date", "norm_lens", "lens_kind", "focal_mm", "aperture", "aperture_f",
                     "position_frac", "n_replicates", "isos_present",
                     "top", "median", "min", "top_vs_median", "range_pct",
                     "best_iso", "best_raw_lens_name", "best_jpeg", "fom_top"])
        for c in cells:
            wr.writerow([
                date, c.norm_lens, c.lens_kind, c.focal_mm, c.aperture, c.aperture_f,
                c.position_frac, c.n_replicates,
                ",".join(map(str, c.isos_present)),
                f"{c.top:.4f}", f"{c.median:.4f}", f"{c.minv:.4f}",
                f"{c.top_vs_median:.3f}", f"{c.range_pct:.1f}",
                c.best_iso, c.best_raw_lens_name, c.best_jpeg, f"{c.fom:.2f}"
            ])

    # MD: wide table indexed by (lens, FL, aperture); columns = 5 positions of top
    # plus a worst-fluke indicator
    by_lfa: dict[tuple, list[CellStats]] = {}
    for c in cells:
        by_lfa.setdefault((c.norm_lens, c.focal_mm, c.aperture, c.aperture_f), []).append(c)
    lines = [
        f"# Per-date sharpness (v2 — sharpest-of-ISO, replicate spread) — {date}",
        "",
        "**top** = max cutoff across pooled replicates (all ISO variants).",
        "**median**, **min** track the typical and worst within the pool.",
        "**top_vs_median**: if ≈1.00 the top reading is consistent with the typical; if ≥1.10 it is a flier.",
        "**range_pct** = (top - min) / median × 100; total spread relative to typical.",
        "Columns for 5 positions show the top cutoff; final two columns roll up the worst flier-vs-spread across positions.",
        "",
        "| Lens | f_eff | F# | dist class | top@0.18 | top@0.34 | **top@0.50** | top@0.66 | top@0.82 | worst top_vs_med | worst range_pct | n_repl_total | ISOs | best_iso (centre) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (lens, fl, ap, apf), cs in sorted(by_lfa.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][3])):
        by_pos = {c.position_frac: c for c in cs}
        cells_str = []
        worst_tvm = 0.0
        worst_range = 0.0
        for p in FIELD_POSITIONS:
            c = by_pos.get(p)
            if c is None:
                cells_str.append("—")
            else:
                cells_str.append(f"{c.top:.2f}")
                if not np.isnan(c.top_vs_median):
                    worst_tvm = max(worst_tvm, c.top_vs_median)
                if not np.isnan(c.range_pct):
                    worst_range = max(worst_range, c.range_pct)
        centre = by_pos.get(0.50)
        n_total = sum(c.n_replicates for c in cs)
        isos = sorted({i for c in cs for i in c.isos_present})
        best_iso_centre = centre.best_iso if centre else "—"
        dist_mm = FOCUS_DISTANCE_BY_LENS_KIND.get(cs[0].lens_kind, 0)
        dcls = distance_class(fl, dist_mm)
        lines.append(
            f"| {lens} | {fl:.0f} | {ap} | {dcls} | " + " | ".join(f"**{s}**" if i == 2 else s for i, s in enumerate(cells_str)) +
            f" | {worst_tvm:.2f} | {worst_range:.0f}% | {n_total} | {','.join(map(str, isos))} | ISO{best_iso_centre} |"
        )
    out_md.write_text("\n".join(lines) + "\n")


# Cross-date overlap on the top reading
def write_overlap(all_cells_by_date: dict[str, list[CellStats]], dates: list[str], out_csv: Path, out_md: Path) -> None:
    # Index: (norm_lens, focal_mm, aperture) -> date -> dict(position -> CellStats)
    by_key: dict[tuple, dict[str, dict[float, CellStats]]] = {}
    for date, cells in all_cells_by_date.items():
        for c in cells:
            k = (c.norm_lens, c.focal_mm, c.aperture, c.aperture_f)
            by_key.setdefault(k, {}).setdefault(date, {})[c.position_frac] = c

    # Keep only entries appearing on 2+ dates with centre measurement
    rows = []
    for k, by_date in by_key.items():
        centres = {d: pmap.get(0.50) for d, pmap in by_date.items() if pmap.get(0.50) is not None}
        if len(centres) < 2:
            continue
        rows.append((k, by_date, centres))
    rows.sort(key=lambda r: (r[0][0], r[0][1], r[0][3]))

    # CSV
    with out_csv.open("w", newline="") as fh:
        wr = csv.writer(fh)
        header = ["norm_lens", "focal_mm", "aperture"]
        for d in dates:
            header += [f"{d}_top_centre", f"{d}_median_centre", f"{d}_n_repl",
                       f"{d}_top_vs_median", f"{d}_best_iso"]
        header += ["centre_top_mean", "centre_top_stdev_pct", "centre_top_minmax"]
        wr.writerow(header)
        for k, by_date, centres in rows:
            row = list(k[:3])
            for d in dates:
                c = by_date.get(d, {}).get(0.50)
                if c is None:
                    row += ["", "", "", "", ""]
                else:
                    row += [f"{c.top:.4f}", f"{c.median:.4f}", c.n_replicates,
                            f"{c.top_vs_median:.3f}", c.best_iso]
            vals = [c.top for c in centres.values()]
            mean = float(np.mean(vals))
            std = float(np.std(vals, ddof=1)) if len(vals) >= 2 else float("nan")
            std_pct = std / mean * 100 if mean and not np.isnan(std) else float("nan")
            row += [f"{mean:.4f}", f"{std_pct:.2f}", f"{min(vals):.2f}..{max(vals):.2f}"]
            wr.writerow(row)

    # Markdown
    md = [
        "# Cross-date overlap (v2 — sharpest-of-ISO + replicate spread)",
        "",
        "For each (lens, f_eff, F#) shot on 2+ dates: centre top cutoff per",
        "date (now max across all ISO variants AND all replicates), plus the",
        "cross-date stdev of those tops as a percent of the mean.",
        "**top_vs_median** per-date column flags whether each day's top was a",
        "flier (≥1.10) or consistent (≈1.00).",
        "**dist class** is the Reikan two-tier distance bucket "
        "(20×FL min for FL≥300mm, 50×FL otherwise; 100×FL = infinity-class).",
        "",
        "| Lens | f_eff | F# | dist class | "
        + " | ".join(f"{d} top (med, n, tvm, ISO)" for d in dates)
        + " | mean | **stdev%** | min..max |",
        "|---|---|---|---|" + "|".join(["---"] * len(dates)) + "|---|---|---|",
    ]
    for k, by_date, centres in rows:
        cells = []
        for d in dates:
            c = by_date.get(d, {}).get(0.50)
            if c is None:
                cells.append("—")
            else:
                cells.append(f"{c.top:.2f} (med {c.median:.2f}, n {c.n_replicates}, tvm {c.top_vs_median:.2f}, ISO{c.best_iso})")
        vals = [c.top for c in centres.values()]
        mean = float(np.mean(vals))
        std = float(np.std(vals, ddof=1)) if len(vals) >= 2 else float("nan")
        std_pct = std / mean * 100 if mean and not np.isnan(std) else float("nan")
        # Distance class — derived from lens_kind on any cell of this row
        any_cell = next(iter(centres.values()))
        dist_mm = FOCUS_DISTANCE_BY_LENS_KIND.get(any_cell.lens_kind, 0)
        dcls = distance_class(k[1], dist_mm)
        md.append(
            f"| {k[0]} | {k[1]:.0f} | {k[2]} | {dcls} | " + " | ".join(cells) +
            f" | {mean:.2f} | **{std_pct:.1f}%** | {min(vals):.2f}..{max(vals):.2f} |"
        )
    out_md.write_text("\n".join(md) + "\n")


# --------------------------------------------------------------------- main

def main() -> int:
    print(f"output dir: {OUT}")
    all_cells_by_date: dict[str, list[CellStats]] = {}
    dates = []
    for date, root in DATE_SOURCES:
        dates.append(date)
        configs = discover_configs(date, root)
        print(f"[{date}] discovered {len(configs)} configs (no ISO filter in v2)", flush=True)
        grouped = measure_all_replicates(configs)
        cells = aggregate(grouped)
        write_per_date(cells, date, OUT / f"per_date_{date}.csv", OUT / f"per_date_{date}.md")
        all_cells_by_date[date] = cells
        print(f"[{date}] wrote per_date_{date}.{{csv,md}}: {len(cells)} cells", flush=True)

    write_overlap(all_cells_by_date, dates, OUT / "overlap.csv", OUT / "overlap.md")
    print(f"Wrote {OUT}/overlap.{{csv,md}}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
