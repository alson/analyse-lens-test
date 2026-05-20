"""Cross-date long-distance sharpness analysis: 2026-01-18 vs 2026-01-28 vs 2026-01-30.

Uses full-frame JPEGs from ``test-raw-data/<date>/<lens>/<FL>/<aperture>/``
on all three dates (each lens dir's name carries the ISO label on
2026-01-18 / 2026-01-30 — we normalise that out for cross-date matching).
The 5-position horizontal field sweep matches the earlier 2026-01-28
analysis exactly.

Goals
-----
- One sharpness number per (date, lens, FL, aperture, position) using the
  same metric machinery as the prior 2026-01-28 POCs (radial spectrum,
  low-band-normalised cutoff in cy/mm-subject).
- Per-date wide tables (FL x aperture x position).
- Cross-date overlap table for content-independence assessment: for each
  (lens, FL, aperture) shot on multiple dates, report the three dates'
  cutoffs at each position and the across-date spread.

Output dir (next to this script):
    poc_longdist_cross_date_2026_01_out/
        per_date_<date>.csv             one row per (lens, FL, ap, position)
        per_date_<date>.md              wide table view
        overlap.csv                     cross-date overlap rows
        overlap.md                      cross-date analysis with spread/relative variance
"""
from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

OUT = Path(__file__).parent / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)

DATE_SOURCES = [
    ("2026-01-18", Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-18")),
    ("2026-01-28", Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-28")),
    ("2026-01-30", Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-30")),
]

Z7_PIXEL_PITCH_MM = 4.35e-3
LAMBDA_MM = 550e-6

# Focus distance per lens family, in mm. Confirmed identical across all
# three dates by EXIF spot-checks (Z7 focus presets snap to a fixed set).
FOCUS_DISTANCE_BY_LENS_KIND = {
    "Z100-400": 84_000.0,
    "PF300":    31_620.0,
}

# Field-position sweep (matches poc_longdist_*_field_2026_01_28.py)
TILE = 256
SEARCH_STEP = 64
FIELD_POSITIONS = [0.18, 0.34, 0.50, 0.66, 0.82]
FIELD_BOX_W_FRAC = 0.15
FIELD_BOX_H_FRAC = 0.20

REF_BAND_SUBJ = (0.01, 0.20)
CUTOFF_THRESHOLD = 0.05


# --------------------------------------------------------------------- config classification

_RE_ISO   = re.compile(r"\s+ISO\d+(\s|$)")
_RE_FL    = re.compile(r"^(\d+(?:\.\d+)?)\s*mm$")
_RE_APER  = re.compile(r"^F(\d+(?:\.\d+)?)$")

def lens_kind(lens_dir_name: str) -> str | None:
    if "100-400" in lens_dir_name:
        return "Z100-400"
    if "300mm f_4E PF" in lens_dir_name:
        return "PF300"
    return None

def normalise_lens_name(lens_dir_name: str) -> str:
    """Strip ISO suffix and trailing whitespace; return a stable label for cross-date matching."""
    name = _RE_ISO.sub(" ", lens_dir_name).strip()
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name)
    # Friendly short labels
    if name.startswith("NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x"):
        return "Z 100-400 + Z TC-1.4x"
    if name.startswith("NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-2.0x"):
        return "Z 100-400 + Z TC-2.0x"
    if name.startswith("NIKKOR Z 100-400mm f_4.5-5.6 VR S"):
        return "Z 100-400 bare"
    if name.startswith("Nikon AF-S Nikkor 300mm f_4E PF ED VR + Kenko Pro 300 DG 1.4x"):
        return "300 PF + Kenko Pro 300 1.4x"
    if name.startswith("Nikon AF-S Nikkor 300mm f_4E PF ED VR + TC-14e III"):
        return "300 PF + TC-14e III"
    if name.startswith("Nikon AF-S Nikkor 300mm f_4E PF ED VR + TC-14e I"):
        return "300 PF + TC-14e I"
    if name.startswith("Nikon AF-S Nikkor 300mm f_4E PF ED VR + TC-17e II"):
        return "300 PF + TC-17e II"
    if name.startswith("Nikon AF-S Nikkor 300mm f_4E PF ED VR + TC-20e III"):
        return "300 PF + TC-20e III"
    if name.startswith("Nikon AF-S Nikkor 300mm f_4E PF ED VR"):
        return "300 PF bare"
    return name  # unknown — return as-is for diagnostic


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
    def focus_distance_mm(self) -> float:
        return FOCUS_DISTANCE_BY_LENS_KIND[self.lens_kind]

    @property
    def M(self) -> float:
        return self.focal_mm / self.focus_distance_mm


def discover_configs(date: str, root: Path) -> list[Config]:
    out: list[Config] = []
    if not root.is_dir():
        return out
    for lens_dir in sorted(root.iterdir()):
        if not lens_dir.is_dir():
            continue
        kind = lens_kind(lens_dir.name)
        if kind is None:
            continue
        norm = normalise_lens_name(lens_dir.name)
        for fl_dir in sorted(lens_dir.iterdir()):
            if not fl_dir.is_dir():
                continue
            m = _RE_FL.match(fl_dir.name)
            if not m:
                continue
            focal = float(m.group(1))
            for ap_dir in sorted(fl_dir.iterdir()):
                if not ap_dir.is_dir():
                    continue
                m = _RE_APER.match(ap_dir.name)
                if not m:
                    continue
                ap_f = float(m.group(1))
                jpegs = sorted(ap_dir.glob("*.jpg"))
                if not jpegs:
                    continue
                cfg = Config(date=date, raw_lens_name=lens_dir.name, norm_lens=norm,
                             lens_kind=kind, focal_mm=focal,
                             aperture=ap_dir.name, aperture_f=ap_f,
                             jpegs=jpegs)
                out.append(cfg)
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


def field_boxes(image_shape: tuple[int, int]) -> list[tuple[float, tuple[int, int, int, int]]]:
    H, W = image_shape
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
    band = (subject_cy_per_mm >= REF_BAND_SUBJ[0]) & (subject_cy_per_mm <= REF_BAND_SUBJ[1])
    if band.sum() == 0:
        return float("nan")
    ref = spec[band].mean()
    if ref <= 0:
        return float("nan")
    norm = spec / ref
    start = int(np.argmax(subject_cy_per_mm > REF_BAND_SUBJ[1]))
    if start == 0:
        start = 1
    below = np.where(norm[start:] < CUTOFF_THRESHOLD)[0]
    if len(below) == 0:
        return float("nan")
    return float(subject_cy_per_mm[start + below[0]])


# --------------------------------------------------------------------- per-date table writer

@dataclass
class Measurement:
    date: str
    norm_lens: str
    lens_kind: str
    focal_mm: float
    aperture: str
    aperture_f: float
    M: float
    # cutoff per field position (cy/mm subject)
    cutoff_p018: float
    cutoff_p034: float
    cutoff_p050: float   # center
    cutoff_p066: float
    cutoff_p082: float
    raw_lens_name: str
    n_replicates: int

    @property
    def cutoff_center(self) -> float:
        return self.cutoff_p050

    @property
    def cutoff_left(self) -> float:
        return self.cutoff_p018

    @property
    def cutoff_right(self) -> float:
        return self.cutoff_p082

    @property
    def fom_center(self) -> float:
        return self.cutoff_center * Z7_PIXEL_PITCH_MM * FOCUS_DISTANCE_BY_LENS_KIND[self.lens_kind]


def measure_all(configs: list[Config]) -> list[Measurement]:
    """For each config, find the best replicate per position (matching the
    per-family 5-position scripts)."""
    out: list[Measurement] = []
    total = len(configs)
    for idx, cfg in enumerate(configs, 1):
        print(f"  [{idx}/{total}] {cfg.norm_lens} | {cfg.focal_mm}mm | {cfg.aperture} | "
              f"{len(cfg.jpegs)} repl", flush=True)
        M = cfg.M
        # Load each replicate once
        lumas = [load_luma(jp) for jp in cfg.jpegs]
        H, W = lumas[0].shape
        boxes = field_boxes((H, W))
        per_pos_best: dict[float, float] = {}
        for fx, (y0, x0, bh, bw) in boxes:
            best_cutoff = float("nan")
            for luma in lumas:
                tile, score = best_tile_in_box(luma, y0, x0, bh, bw)
                if tile is None:
                    continue
                c = normalised_cutoff_from_tile(tile, M)
                if np.isnan(best_cutoff) or (not np.isnan(c) and c > best_cutoff):
                    best_cutoff = c
            per_pos_best[fx] = best_cutoff
        out.append(Measurement(
            date=cfg.date, norm_lens=cfg.norm_lens, lens_kind=cfg.lens_kind,
            focal_mm=cfg.focal_mm, aperture=cfg.aperture, aperture_f=cfg.aperture_f, M=M,
            cutoff_p018=per_pos_best.get(0.18, float("nan")),
            cutoff_p034=per_pos_best.get(0.34, float("nan")),
            cutoff_p050=per_pos_best.get(0.50, float("nan")),
            cutoff_p066=per_pos_best.get(0.66, float("nan")),
            cutoff_p082=per_pos_best.get(0.82, float("nan")),
            raw_lens_name=cfg.raw_lens_name,
            n_replicates=len(cfg.jpegs),
        ))
    return out


def write_per_date_csv(ms: list[Measurement], date: str, path: Path) -> None:
    rows = sorted(ms, key=lambda m: (m.norm_lens, m.focal_mm, m.aperture_f))
    with path.open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["date", "norm_lens", "lens_kind", "focal_mm", "aperture", "aperture_f",
                     "M", "cutoff_p018", "cutoff_p034", "cutoff_p050",
                     "cutoff_p066", "cutoff_p082", "fom_center", "n_replicates", "raw_lens_name"])
        for m in rows:
            wr.writerow([m.date, m.norm_lens, m.lens_kind, m.focal_mm, m.aperture, m.aperture_f,
                         f"{m.M:.6f}",
                         f"{m.cutoff_p018:.4f}", f"{m.cutoff_p034:.4f}", f"{m.cutoff_p050:.4f}",
                         f"{m.cutoff_p066:.4f}", f"{m.cutoff_p082:.4f}",
                         f"{m.fom_center:.2f}", m.n_replicates, m.raw_lens_name])


def write_per_date_md(ms: list[Measurement], date: str, path: Path) -> None:
    rows = sorted(ms, key=lambda m: (m.norm_lens, m.focal_mm, m.aperture_f))
    lines = [
        f"# Per-date sharpness — {date}",
        "",
        f"Source: full-frame JPEGs from `test-raw-data/{date}/<lens>/<FL>/<aperture>/`,",
        f"5-position horizontal field sweep (x = {FIELD_POSITIONS}), best replicate per",
        "position by gradient-energy maximum.",
        "Sharpness = normalised radial-spectrum cutoff in cy/mm-subject (higher = sharper).",
        "FOM = sensor cy/px x f_eff (distance-fair, only meaningful within the same lens family).",
        "",
        "| Lens | f_eff | F# | M | x=0.18 | x=0.34 | **x=0.50** | x=0.66 | x=0.82 | n_repl | FOM(centre) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in rows:
        def fmt(x): return "—" if np.isnan(x) else f"{x:.2f}"
        lines.append(
            f"| {m.norm_lens} | {m.focal_mm:.0f} mm | {m.aperture} | {m.M:.5f} | "
            f"{fmt(m.cutoff_p018)} | {fmt(m.cutoff_p034)} | **{fmt(m.cutoff_p050)}** | "
            f"{fmt(m.cutoff_p066)} | {fmt(m.cutoff_p082)} | {m.n_replicates} | "
            f"{m.fom_center:.0f} |"
        )
    path.write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------- cross-date overlap

@dataclass
class Overlap:
    norm_lens: str
    focal_mm: float
    aperture: str
    aperture_f: float
    per_date_center: dict[str, float] = field(default_factory=dict)
    per_date_left:   dict[str, float] = field(default_factory=dict)
    per_date_right:  dict[str, float] = field(default_factory=dict)


def build_overlap(all_ms: list[Measurement]) -> list[Overlap]:
    by_key: dict[tuple, Overlap] = {}
    for m in all_ms:
        k = (m.norm_lens, m.focal_mm, m.aperture, m.aperture_f)
        ov = by_key.setdefault(k, Overlap(
            norm_lens=m.norm_lens, focal_mm=m.focal_mm,
            aperture=m.aperture, aperture_f=m.aperture_f,
        ))
        ov.per_date_center[m.date] = m.cutoff_center
        ov.per_date_left[m.date]   = m.cutoff_left
        ov.per_date_right[m.date]  = m.cutoff_right
    # Keep only entries appearing on 2+ dates with at least the centre measured
    out = []
    for ov in by_key.values():
        n_dates_with_center = sum(1 for v in ov.per_date_center.values() if not np.isnan(v))
        if n_dates_with_center >= 2:
            out.append(ov)
    out.sort(key=lambda o: (o.norm_lens, o.focal_mm, o.aperture_f))
    return out


def write_overlap(overlaps: list[Overlap], dates: list[str], path_csv: Path, path_md: Path) -> None:
    # CSV
    with path_csv.open("w", newline="") as fh:
        wr = csv.writer(fh)
        header = ["norm_lens", "focal_mm", "aperture"]
        for d in dates:
            header += [f"{d}_center", f"{d}_left", f"{d}_right"]
        header += ["center_mean", "center_stdev_pct", "center_minmax_spread"]
        wr.writerow(header)
        for ov in overlaps:
            row = [ov.norm_lens, ov.focal_mm, ov.aperture]
            for d in dates:
                row += [
                    f"{ov.per_date_center.get(d, float('nan')):.4f}",
                    f"{ov.per_date_left.get(d,   float('nan')):.4f}",
                    f"{ov.per_date_right.get(d,  float('nan')):.4f}",
                ]
            vals = [v for v in ov.per_date_center.values() if not np.isnan(v)]
            mean = float(np.mean(vals)) if vals else float("nan")
            std  = float(np.std(vals, ddof=1)) if len(vals) >= 2 else float("nan")
            spread = (max(vals) - min(vals)) if len(vals) >= 2 else float("nan")
            std_pct = (std / mean * 100) if mean and not np.isnan(std) else float("nan")
            row += [f"{mean:.4f}", f"{std_pct:.2f}", f"{spread:.4f}"]
            wr.writerow(row)

    # Markdown wide table
    md = [
        "# Cross-date overlap — content-independence check",
        "",
        "For each (lens, f_eff, F#) that was shot on multiple dates, report the centre",
        "cutoff per date plus the across-date spread. A scene-independent metric should",
        "show small spread; a scene-dependent metric will have spread comparable to the",
        "mean. **stdev_pct** is the cross-date standard deviation divided by the mean,",
        "in percent — the headline content-independence number.",
        "",
        "| Lens | f_eff | F# | " + " | ".join(f"{d} c" for d in dates) +
        " | mean | stdev% | min..max |",
        "|---|---|---|" + "|".join(["---"] * (len(dates))) + "|---|---|---|",
    ]
    for ov in overlaps:
        cells = []
        for d in dates:
            v = ov.per_date_center.get(d, float("nan"))
            cells.append("—" if np.isnan(v) else f"{v:.2f}")
        vals = [v for v in ov.per_date_center.values() if not np.isnan(v)]
        if len(vals) >= 2:
            mean = float(np.mean(vals))
            std  = float(np.std(vals, ddof=1))
            std_pct = std / mean * 100 if mean else float("nan")
            mn, mx = min(vals), max(vals)
            md.append(
                f"| {ov.norm_lens} | {ov.focal_mm:.0f} | {ov.aperture} | " +
                " | ".join(cells) +
                f" | {mean:.2f} | **{std_pct:.1f}%** | {mn:.2f}..{mx:.2f} |"
            )
        else:
            md.append(
                f"| {ov.norm_lens} | {ov.focal_mm:.0f} | {ov.aperture} | " +
                " | ".join(cells) + " | — | — | — |"
            )

    # Also include left and right edge tables
    md += [
        "",
        "## Left-edge centre cutoff per date",
        "",
        "| Lens | f_eff | F# | " + " | ".join(dates) + " | stdev% |",
        "|---|---|---|" + "|".join(["---"] * len(dates)) + "|---|",
    ]
    for ov in overlaps:
        cells = []
        vals = []
        for d in dates:
            v = ov.per_date_left.get(d, float("nan"))
            cells.append("—" if np.isnan(v) else f"{v:.2f}")
            if not np.isnan(v):
                vals.append(v)
        if len(vals) >= 2:
            mean = float(np.mean(vals)); std = float(np.std(vals, ddof=1))
            md.append(f"| {ov.norm_lens} | {ov.focal_mm:.0f} | {ov.aperture} | " + " | ".join(cells) + f" | {std/mean*100:.1f}% |")
        else:
            md.append(f"| {ov.norm_lens} | {ov.focal_mm:.0f} | {ov.aperture} | " + " | ".join(cells) + " | — |")

    md += [
        "",
        "## Right-edge centre cutoff per date",
        "",
        "| Lens | f_eff | F# | " + " | ".join(dates) + " | stdev% |",
        "|---|---|---|" + "|".join(["---"] * len(dates)) + "|---|",
    ]
    for ov in overlaps:
        cells = []
        vals = []
        for d in dates:
            v = ov.per_date_right.get(d, float("nan"))
            cells.append("—" if np.isnan(v) else f"{v:.2f}")
            if not np.isnan(v):
                vals.append(v)
        if len(vals) >= 2:
            mean = float(np.mean(vals)); std = float(np.std(vals, ddof=1))
            md.append(f"| {ov.norm_lens} | {ov.focal_mm:.0f} | {ov.aperture} | " + " | ".join(cells) + f" | {std/mean*100:.1f}% |")
        else:
            md.append(f"| {ov.norm_lens} | {ov.focal_mm:.0f} | {ov.aperture} | " + " | ".join(cells) + " | — |")

    path_md.write_text("\n".join(md) + "\n")


# --------------------------------------------------------------------- main

def main() -> int:
    print(f"output dir: {OUT}")
    all_measurements: list[Measurement] = []
    dates = []
    for date, root in DATE_SOURCES:
        dates.append(date)
        configs = discover_configs(date, root)
        print(f"[{date}] discovered {len(configs)} configs", flush=True)
        # Early ISO filter: per (norm_lens, focal, aperture) keep ONLY the
        # config from the lowest-ISO raw_lens_name, so we don't load JPEGs
        # we're going to discard. (2026-01-30 has ISO 1600/4000/8000
        # variants; 2026-01-18 has ISO 100/400/800; we keep the lowest.)
        def iso_of(name: str) -> int:
            mat = re.search(r"ISO(\d+)", name)
            return int(mat.group(1)) if mat else 0
        keep_cfg: dict[tuple, Config] = {}
        for c in configs:
            key = (c.norm_lens, c.focal_mm, c.aperture)
            cur = keep_cfg.get(key)
            if cur is None or iso_of(cur.raw_lens_name) > iso_of(c.raw_lens_name):
                keep_cfg[key] = c
        configs_to_measure = list(keep_cfg.values())
        print(f"[{date}] after lowest-ISO filter: {len(configs_to_measure)} configs", flush=True)
        ms_kept = measure_all(configs_to_measure)
        write_per_date_csv(ms_kept, date, OUT / f"per_date_{date}.csv")
        write_per_date_md(ms_kept, date, OUT / f"per_date_{date}.md")
        all_measurements.extend(ms_kept)
        print(f"[{date}] wrote per_date_{date}.{{csv,md}}: {len(ms_kept)} configs", flush=True)

    overlaps = build_overlap(all_measurements)
    print(f"\nCross-date overlap: {len(overlaps)} (lens, FL, aperture) appear on 2+ dates")
    write_overlap(overlaps, dates, OUT / "overlap.csv", OUT / "overlap.md")
    print(f"Wrote {OUT}/per_date_*.{{csv,md}} and overlap.{{csv,md}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
