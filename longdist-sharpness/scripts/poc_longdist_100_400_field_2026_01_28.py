"""POC: Z 100-400 + Z TCs at 5 horizontal field positions (2026-01-28).

Sibling to ``poc_longdist_300pf_field_2026_01_28.py`` -- same metric,
same 5-position layout, applied to the Z 100-400 family at 400mm
focal-length setting so the two families can be put side-by-side
on edge performance.

FocusDistance = 84.0 m across all 100-400 shots (vs 31.62 m for the
300 PF family). Sensor cy/pixel and (sensor cy/pixel * f_eff) are
scene-independent, so they are the right cross-family measures.
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
FOCUS_DISTANCE_MM = 84_000.0
LAMBDA_MM = 550e-6

TILE = 256
SEARCH_STEP = 64
# §5.3: lowered REF_BAND_SUBJ from (0.01, 0.20) to (0.01, 0.10) so soft
# tiles whose cutoff falls inside the old ref band are now measurable.
# Smoothing + last-crossing live inside find_cutoff_from_spec.
REF_BAND_SUBJ = (0.01, 0.10)
CUTOFF_THRESHOLD = 0.05

FIELD_POSITIONS = [0.18, 0.34, 0.50, 0.66, 0.82]
FIELD_BOX_W_FRAC = 0.15
FIELD_BOX_H_FRAC = 0.20


CONFIGS = [
    ("Z100-400_bare",  "NIKKOR Z 100-400mm f_4.5-5.6 VR S",            "400.0 mm", 400.0),
    ("Z100-400_TC14",  "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x",  "400.0 mm", 560.0),
    ("Z100-400_TC20",  "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-2.0x",  "400.0 mm", 800.0),
]


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


def field_boxes(image_shape: tuple[int, int]):
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
    luma_cache = [(jp, load_luma(jp)) for jp in jpegs]
    H, W = luma_cache[0][1].shape
    M = f_eff / FOCUS_DISTANCE_MM
    sensor_cy_per_px = np.arange(TILE // 2 + 1) / TILE
    subject_cy_per_mm = sensor_cy_per_px / Z7_PIXEL_PITCH_MM * M

    measurements: list[FieldMeasurement] = []
    for fx, (y0, x0, bh, bw) in field_boxes((H, W)):
        best = None
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


def plot_field_curves(rows: list[FieldMeasurement], out_path: Path, title: str) -> None:
    by_cfg: dict[str, list[FieldMeasurement]] = {}
    for r in rows:
        by_cfg.setdefault(r.config_label, []).append(r)
    configs = [c for c, _, _, _ in CONFIGS if c in by_cfg]
    n = len(configs)
    fig, axes = plt.subplots(1, n, figsize=(4.6 * n, 4.5), sharey=True)
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
            ax.plot(xs, ys, marker="o", label=ap, lw=1.5)
        ax.set_title(cfg)
        ax.set_xlabel("field x (fraction)")
        ax.set_xticks(FIELD_POSITIONS)
        ax.set_xticklabels([f"{p:.2f}" for p in FIELD_POSITIONS], fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8, loc="upper right")
    axes[0].set_ylabel("cutoff (cy/mm subject)")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def write_summary(rows: list[FieldMeasurement], out_csv: Path, out_md: Path) -> None:
    with out_csv.open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["config", "aperture", "f_eff_mm", "position_frac", "cutoff_cy_per_mm_subject", "grad_score", "best_jpeg", "ref_band_amplitude", "tile_y", "tile_x"])
        for r in rows:
            wr.writerow([r.config_label, r.aperture, r.f_eff, r.position_frac, r.cutoff_subject, r.grad_score, r.best_jpeg, r.ref_amp, r.tile_pos[0], r.tile_pos[1]])

    by_key: dict[tuple[str, str, float], dict[float, float]] = {}
    for r in rows:
        by_key.setdefault((r.config_label, r.aperture, r.f_eff), {})[r.position_frac] = r.cutoff_subject

    lines = [
        "# Z 100-400 family — field-position cutoff sweep (2026-01-28)",
        "",
        f"FocusDistance = 84.0 m. 5 horizontal positions at x = {FIELD_POSITIONS}.",
        "Same metric/protocol as poc_longdist_300pf_field_2026_01_28 -- center value",
        "must match the previous center-only run within sampling noise.",
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

    out_md.write_text("\n".join(lines) + "\n")


def main() -> int:
    print(f"output dir: {OUT}")
    rows: list[FieldMeasurement] = []
    for cfg in CONFIGS:
        label, lens, focal, f_eff = cfg
        cfg_dir = DATA_ROOT / lens / focal
        if not cfg_dir.is_dir():
            continue
        for ap in apertures_for(cfg_dir):
            ms = measure(cfg, ap)
            if ms is None:
                continue
            rows.extend(ms)
            center = next((m for m in ms if abs(m.position_frac - 0.50) < 1e-6), None)
            if center:
                print(f"[{label} {ap}] center={center.cutoff_subject:.3f}  range="
                      f"{min(m.cutoff_subject for m in ms):.3f}..{max(m.cutoff_subject for m in ms):.3f}")
    plot_field_curves(rows, OUT / "field_curves_all.png",
                      "Z 100-400 + Z TCs - field-position cutoff (cy/mm subject)\n"
                      "(2026-01-28 shrubbery, FocusDistance=84m)")
    write_summary(rows, OUT / "summary.csv", OUT / "summary.md")
    print(f"\nWrote {OUT}/summary.{{csv,md}} + field_curves_all.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
