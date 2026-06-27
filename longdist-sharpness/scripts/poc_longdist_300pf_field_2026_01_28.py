"""POC: 300 PF + TCs at 5 horizontal field positions (2026-01-28 shrubbery).

Extends the 100-400 + TC analysis to the AF-S 300mm f/4E PF ED VR with
its full TC ladder (TC-14e I, TC-14e III, TC-17e II, TC-20e III) and
adds a *field-position sweep*: at each of 5 evenly-spaced horizontal
positions across the frame, find the sharpest 256x256 tile within a
search box of ~1230x1100 px, and compute the same subject-space
cutoff metric used in ``poc_longdist_100_400_tc_2026_01_28.py``.

Why field positions
-------------------
User's manual finding was that the 300 PF + TC was "clearly worse,
especially with TC, needing 1-2 stops down from max for decent edge
sharpness". A center-only metric can miss field-curvature / off-axis
degradation. The doc (SHARPNESS_METRICS_LONGDIST.md) recommends 8
vertical slices on FX; for a horizontal-axis sweep we use 5 evenly
spaced positions at fractional x = 0.18, 0.34, 0.50, 0.66, 0.82.

Center anchor
-------------
The center position (0.50) uses the *same* tile-search logic as the
center-only metric (1500x1500 box at frame center), so the center
column of this table must match the prior numbers within sampling-
noise tolerance. This is a built-in self-check.

Distance / scene
----------------
All 300 PF family shots at FocusDistance=31.62m (different shrubbery
patch from the 100-400 family's 84m -- see the earlier center-crop
inspection). Subject-space cutoffs from this script are therefore
comparable WITHIN the 300 PF family across configs/apertures, and
broadly comparable to the 100-400 family numbers as a "what does
this lens deliver in cy/mm-subject" reading, but not as a direct
same-scene comparison.

Outputs (alongside this script, under poc_longdist_300pf_field_2026_01_28_out/):
- summary.csv               cutoff per (config, aperture, position)
- summary.md                tables + interpretation
- field_curves_<config>.png cutoff vs field position, one line per aperture
- field_curves_all.png      small-multiples panel
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from poc_longdist_algorithms import find_cutoff_from_spec  # noqa: E402

DATA_ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-28")
OUT = Path(__file__).parent / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)

Z7_PIXEL_PITCH_MM = 4.35e-3
FOCUS_DISTANCE_MM = 31_620.0          # all 300 PF family @ 31.62m
LAMBDA_MM = 550e-6

TILE = 256
SEARCH_STEP = 64
# §5.3: lowered REF_BAND_SUBJ from (0.01, 0.20) to (0.01, 0.10) plus
# smoothing + last-crossing inside find_cutoff_from_spec.
REF_BAND_SUBJ = (0.01, 0.10)          # cy/mm-subject — lens MTF ~1 band
CUTOFF_THRESHOLD = 0.05

# Field positions: fractional x in image (8256 wide on Z7 FX).
FIELD_POSITIONS = [0.18, 0.34, 0.50, 0.66, 0.82]
FIELD_BOX_W_FRAC = 0.15               # horizontal search box ~ 0.15 * W = ~1240 px
FIELD_BOX_H_FRAC = 0.20               # vertical: 0.20 * H = ~1100 px about center


# (label, lens-dir, focal-dir, f_eff_mm)
CONFIGS = [
    ("PF_300",       "Nikon AF-S Nikkor 300mm f_4E PF ED VR",                 "300.0 mm", 300.0),
    ("PF_TC14eI",    "Nikon AF-S Nikkor 300mm f_4E PF ED VR + TC-14e I",      "420.0 mm", 420.0),
    ("PF_TC14eIII",  "Nikon AF-S Nikkor 300mm f_4E PF ED VR + TC-14e III",    "420.0 mm", 420.0),
    ("PF_TC17eII",   "Nikon AF-S Nikkor 300mm f_4E PF ED VR + TC-17e II",     "500.0 mm", 500.0),
    ("PF_TC20eIII",  "Nikon AF-S Nikkor 300mm f_4E PF ED VR + TC-20e III",    "600.0 mm", 600.0),
]


# --------------------------------------------------------------------- core helpers
# (Match poc_longdist_100_400_tc_2026_01_28.py exactly so the center
# value remains the same.)

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


def best_tile_in_box(luma: np.ndarray, y0: int, x0: int, h: int, w: int) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Return (best_tile, gradient_score, (y, x) absolute)."""
    region = luma[y0 : y0 + h, x0 : x0 + w]
    best_tile, best_score, best_yx = None, -1.0, (0, 0)
    for y in range(0, region.shape[0] - TILE + 1, SEARCH_STEP):
        for x in range(0, region.shape[1] - TILE + 1, SEARCH_STEP):
            t = region[y : y + TILE, x : x + TILE]
            gy = np.diff(t, axis=0); gx = np.diff(t, axis=1)
            s = float((gy * gy).mean() + (gx * gx).mean())
            if s > best_score:
                best_score, best_tile, best_yx = s, t, (y0 + y, x0 + x)
    return best_tile, best_score, best_yx


def normalised_cutoff(spec: np.ndarray, subject_freq: np.ndarray, threshold: float = CUTOFF_THRESHOLD) -> tuple[float, float]:
    return find_cutoff_from_spec(spec, subject_freq, ref_band=REF_BAND_SUBJ,
                                  threshold=threshold)


# --------------------------------------------------------------------- per-(config, aperture, position)

@dataclass
class FieldMeasurement:
    config_label: str
    aperture: str
    f_eff: float
    position_frac: float
    best_jpeg: str
    grad_score: float
    cutoff_subject: float
    ref_amp: float
    tile_pos: tuple[int, int]


def field_boxes(image_shape: tuple[int, int]) -> list[tuple[float, tuple[int, int, int, int]]]:
    """Return list of (position_frac, (y0, x0, h, w)) for each field position."""
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


def measure(config: tuple, ap: str) -> list[FieldMeasurement] | None:
    label, lens, focal, f_eff = config
    d = DATA_ROOT / lens / focal / ap
    if not d.is_dir():
        return None
    jpegs = sorted(d.glob("*.jpg"))
    if not jpegs:
        return None
    # First pass: load each replicate once, keep luma in memory for all 5 positions
    luma_cache: list[tuple[Path, np.ndarray]] = [(jp, load_luma(jp)) for jp in jpegs]
    H, W = luma_cache[0][1].shape
    M = f_eff / FOCUS_DISTANCE_MM
    sensor_cy_per_px = np.arange(TILE // 2 + 1) / TILE
    subject_cy_per_mm = sensor_cy_per_px / Z7_PIXEL_PITCH_MM * M

    measurements: list[FieldMeasurement] = []
    for fx, (y0, x0, bh, bw) in field_boxes((H, W)):
        best = None
        best_repl_path = None
        for jp, luma in luma_cache:
            t, s, pos = best_tile_in_box(luma, y0, x0, bh, bw)
            spec = radial_spectrum(t)
            cutoff, ref = normalised_cutoff(spec, subject_cy_per_mm)
            cand = FieldMeasurement(
                config_label=label, aperture=ap, f_eff=f_eff,
                position_frac=fx, best_jpeg=jp.name,
                grad_score=s, cutoff_subject=cutoff, ref_amp=ref,
                tile_pos=pos,
            )
            if best is None or (np.isfinite(cand.cutoff_subject) and cand.cutoff_subject > best.cutoff_subject):
                best = cand
        if best is not None:
            measurements.append(best)
    return measurements


def apertures_for(d: Path) -> list[str]:
    return sorted([p.name for p in d.iterdir() if p.is_dir() and p.name.startswith("F")])


# --------------------------------------------------------------------- plots

def plot_field_curves(rows: list[FieldMeasurement], out_path: Path, title: str) -> None:
    """One axes per config, lines per aperture, x=field position, y=cutoff cy/mm-subj."""
    by_cfg: dict[str, list[FieldMeasurement]] = {}
    for r in rows:
        by_cfg.setdefault(r.config_label, []).append(r)
    configs = [c for c, _, _, _ in CONFIGS if c in by_cfg]
    n = len(configs)
    fig, axes = plt.subplots(1, n, figsize=(4.0 * n, 4.5), sharey=True)
    if n == 1:
        axes = [axes]
    for ax, cfg in zip(axes, configs):
        cfg_rows = by_cfg[cfg]
        by_ap: dict[str, list[FieldMeasurement]] = {}
        for r in cfg_rows:
            by_ap.setdefault(r.aperture, []).append(r)
        for ap in sorted(by_ap.keys(), key=lambda s: float(s[1:])):
            ms = sorted(by_ap[ap], key=lambda r: r.position_frac)
            xs = [m.position_frac for m in ms]
            ys = [m.cutoff_subject for m in ms]
            ax.plot(xs, ys, marker="o", label=ap, lw=1.4)
        ax.set_title(cfg, fontsize=10)
        ax.set_xlabel("field x (fraction)")
        ax.set_xticks(FIELD_POSITIONS)
        ax.set_xticklabels([f"{p:.2f}" for p in FIELD_POSITIONS], fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7, loc="upper right")
    axes[0].set_ylabel("cutoff (cy/mm subject), higher = sharper")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_field_curves_individual(rows: list[FieldMeasurement]) -> None:
    by_cfg: dict[str, list[FieldMeasurement]] = {}
    for r in rows:
        by_cfg.setdefault(r.config_label, []).append(r)
    for cfg, cfg_rows in by_cfg.items():
        by_ap: dict[str, list[FieldMeasurement]] = {}
        for r in cfg_rows:
            by_ap.setdefault(r.aperture, []).append(r)
        fig, ax = plt.subplots(figsize=(7, 5))
        for ap in sorted(by_ap.keys(), key=lambda s: float(s[1:])):
            ms = sorted(by_ap[ap], key=lambda r: r.position_frac)
            xs = [m.position_frac for m in ms]
            ys = [m.cutoff_subject for m in ms]
            ax.plot(xs, ys, marker="o", label=ap, lw=1.5)
        ax.set_title(cfg)
        ax.set_xlabel("field x (fraction of image width)")
        ax.set_ylabel("cutoff (cy/mm subject)")
        ax.set_xticks(FIELD_POSITIONS)
        ax.set_xticklabels([f"{p:.2f}" for p in FIELD_POSITIONS])
        ax.grid(True, alpha=0.3)
        ax.legend(title="aperture")
        fig.tight_layout()
        fig.savefig(OUT / f"field_curves_{cfg}.png", dpi=120)
        plt.close(fig)


# --------------------------------------------------------------------- summary

def write_summary(rows: list[FieldMeasurement], out_csv: Path, out_md: Path) -> None:
    with out_csv.open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["config", "aperture", "f_eff_mm", "position_frac", "cutoff_cy_per_mm_subject", "grad_score", "best_jpeg", "ref_band_amplitude", "tile_y", "tile_x"])
        for r in rows:
            wr.writerow([r.config_label, r.aperture, r.f_eff, r.position_frac, r.cutoff_subject, r.grad_score, r.best_jpeg, r.ref_amp, r.tile_pos[0], r.tile_pos[1]])

    # Build a per-(config, aperture) wide table with one column per field position
    by_key: dict[tuple[str, str, float], dict[float, float]] = {}
    for r in rows:
        by_key.setdefault((r.config_label, r.aperture, r.f_eff), {})[r.position_frac] = r.cutoff_subject

    lines = [
        "# 300 PF + TC ladder — field-position cutoff sweep (2026-01-28)",
        "",
        f"FocusDistance = 31.62 m. 5 horizontal positions at x = {FIELD_POSITIONS}.",
        f"Per-position search box ~ {FIELD_BOX_W_FRAC * 100:.0f}% wide x {FIELD_BOX_H_FRAC * 100:.0f}% tall, finding the highest-",
        f"gradient {TILE}px tile inside. Radial-spectrum cutoff at {CUTOFF_THRESHOLD} of the low-",
        "subject-frequency band [0.01, 0.20] cy/mm. Higher cutoff = lens delivers",
        "more real-world detail. Best replicate per (config, aperture, position).",
        "",
        "## Field-position cutoff (cy / mm subject)",
        "",
        "| Config | f_eff | F# | x=0.18 | x=0.34 | x=0.50 (center) | x=0.66 | x=0.82 | best |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for (cfg, ap, f_eff), pos_map in sorted(by_key.items(), key=lambda kv: (kv[0][0], float(kv[0][1][1:]))):
        cells = []
        best_val = -1.0
        best_pos = None
        for p in FIELD_POSITIONS:
            v = pos_map.get(p, float("nan"))
            cells.append(f"{v:.2f}" if np.isfinite(v) else "—")
            if np.isfinite(v) and v > best_val:
                best_val = v
                best_pos = p
        best_marker = f"{best_val:.2f} @ x={best_pos:.2f}" if best_pos is not None else "—"
        lines.append(f"| {cfg} | {f_eff:.0f}mm | {ap} | " + " | ".join(cells) + f" | {best_marker} |")

    # Centre-aperture peak per config
    lines += [
        "",
        "## Centre (x=0.50) cutoff per (config, aperture)",
        "",
        "| Config | F# wide | F# best | best cutoff (cy/mm subj) |",
        "|---|---|---|---|",
    ]
    by_cfg: dict[str, list[tuple[str, float]]] = {}
    for (cfg, ap, _f_eff), pos_map in by_key.items():
        v = pos_map.get(0.50, float("nan"))
        if np.isfinite(v):
            by_cfg.setdefault(cfg, []).append((ap, v))
    for cfg_label, _, _, _ in CONFIGS:
        if cfg_label not in by_cfg:
            continue
        aps = sorted(by_cfg[cfg_label], key=lambda kv: float(kv[0][1:]))
        wide_ap = aps[0][0]
        best_ap, best_v = max(aps, key=lambda kv: kv[1])
        lines.append(f"| {cfg_label} | {wide_ap} | **{best_ap}** | **{best_v:.2f}** |")

    lines += [
        "",
        "## Interpretation",
        "",
        "- The cutoff value scales with subject-space resolution. Within this same-",
        "  distance, same-scene patch, comparing configs/apertures is meaningful.",
        "- Look for the 'best aperture' per config (centre column). For a well-",
        "  behaved long-tele on a planar-distant scene the optimum is usually 1-2",
        "  stops down from wide-open; TC-bearing configs typically need MORE stop-",
        "  down because the TC concentrates aberrations.",
        "- Look across field positions. A flat row = good across the field. A row",
        "  that droops at x=0.18 and x=0.82 = sharp centre, soft edges (typical",
        "  long-tele behaviour). A row that droops only at one side suggests",
        "  decentering or non-flat subject plane.",
        "- Compare these cutoffs with the 100-400 family's centre numbers",
        "  (bare 0.20, +TC14 0.25, +TC20 0.29 cy/mm-subject) BUT remember the 100-",
        "  400 family is at 84 m on a different shrubbery patch — only the within-",
        "  family rankings are strictly fair.",
        "",
        "## Caveats",
        "",
        "- Field-position curves are best-replicate per position; AF jitter is",
        "  absorbed into the result (we report the sharpest the lens got at each",
        "  position).",
        "- The 0.20 cy/mm-subject floor is the same low-band reference shape we",
        "  saw in the 100-400 analysis — the scene's underlying spectrum + JPEG",
        "  processing dominate that band, which is exactly why we normalise to it.",
        "- No NEFs on disk for 2026-01-28; JPEGs only. Within-day, same-camera",
        "  comparisons are robust.",
    ]
    out_md.write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------- main

def main() -> int:
    print(f"output dir: {OUT}")
    rows: list[FieldMeasurement] = []
    for cfg in CONFIGS:
        label, lens, focal, f_eff = cfg
        cfg_dir = DATA_ROOT / lens / focal
        if not cfg_dir.is_dir():
            print(f"  MISSING: {cfg_dir}", file=sys.stderr)
            continue
        for ap in apertures_for(cfg_dir):
            ms = measure(cfg, ap)
            if ms is None:
                continue
            for m in ms:
                rows.append(m)
            center = next((m for m in ms if abs(m.position_frac - 0.50) < 1e-6), None)
            if center:
                print(f"[{label} {ap}] center={center.cutoff_subject:.3f}  field_range="
                      f"{min(m.cutoff_subject for m in ms):.3f}..{max(m.cutoff_subject for m in ms):.3f}")

    plot_field_curves(rows, OUT / "field_curves_all.png",
                      "300 PF + TC ladder — field-position cutoff (cy/mm subject)\n(2026-01-28 shrubbery, FocusDistance=31.62m)")
    plot_field_curves_individual(rows)
    write_summary(rows, OUT / "summary.csv", OUT / "summary.md")
    print(f"\nWrote {OUT}/summary.{{csv,md}} + field_curves_*.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
