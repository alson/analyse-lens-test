"""POC: pad-grid 2D-FFT amplitude as a low-M complement to maze-FFT.

Background
----------
The production pipeline has two signals: scribe-LSF (works at every M
but under-reads at low M because the scribe is only a few px wide on
sensor) and maze-FFT at 13 um pitch (gated off below M=0.7 since the
maze period aliases on the Z7 sensor). Task 2 (100-400mm @ M=0.385,
F11) is the problem case — LSF reads MTF50 ~10.4 lp/mm vs ~33 lp/mm
target, and the maze gate is closed.

This POC searches for a wafer feature with an intermediate physical
pitch (between scribe = 5000 um and maze = 13 um) that still resolves
at M=0.385: f_sensor = M * pitch_px_um / pitch_subject_um. At
M=0.385, sensor pitch 4.35 um, a 60 um subject pitch gives a sensor
period of 5.3 px (f = 0.188 cy/px) — safely below Nyquist.

Approach
--------
1. Radial power spectrum on shot 137 (LSF argmax) centre tile to find
   the dominant peak between 0.02 and 0.20 cy/px (subject pitch 8.4 -
   84 um at this M).
2. Build pad_grid_amp(image, M, pitch_um) analogous to maze_amp: mean
   |FFT| in an annulus around f = M * 4.35 / pitch_um.
3. Sweep all 142 shots over centre + 4 off-axis on-target tiles;
   compare argmax to LSF and filesize argmaxes; check argmax std-dev.

Usage:
    direnv exec . uv run python scripts/poc_pad_grid_fft.py                   # full sweep at the dominant radial peak
    direnv exec . uv run python scripts/poc_pad_grid_fft.py --discover-only   # pitch discovery only
    direnv exec . uv run python scripts/poc_pad_grid_fft.py --pitch-um=18.37  # override pitch

Output:
    scripts/poc_pad_grid_fft_out/
      radial_spectrum.{csv,png}        — 1-D radial power spectrum
      fft2d_{overview,zoom,deviation_zoom}.png  — produced by sibling script
      pad_fft_per_shot.csv             — pad-FFT amp per shot per tile
      pad_fft_curves.png               — pad / lsf / filesize overlay

Result summary (Task 2, 100-400 @ M=0.385 F11, 142 shots; see
``poc_pad_grid_fft_REPORT.md``):

  * No clean radial peak — 1-D spectrum is monotonic 1/f-like. Useful
    candidate pitches come from the 2-D FFT deviation map: a pad-grid
    fundamental at ~76 µm subject pitch and a strong 4th harmonic at
    18.4 µm.
  * Pad-FFT at 18.37 µm: centre argmax=119, LSF argmax=137. Mismatch
    -18 shots. Argmax std-dev across 5 tiles = 6.31. LSF argmax shot
    sits within 0.5-3.3 % of pad-FFT max.
  * Pad-FFT at 70.45 µm: centre argmax=99 (-38 vs LSF). Curves show
    heavy Talbot-self-imaging ringing; argmax unstable across tiles in
    a different way (tight std-dev=2.71 but ~38 shots off LSF).
  * Verdict: viable as a low-M peak-value sharpness signal (decentering
    via peak ratios), NOT a drop-in argmax replacement.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Add src/ to path so we can import the helpers without installing.
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from tile_sharpness.methods.maze_fft import SENSOR_PITCH_UM_Z7
from tile_sharpness.phase1 import _decode_gray, _crop_box  # noqa: E402
from tile_sharpness.sweeps import Shot, Sweep, discover_all, find_sweep  # noqa: E402


SWEEP_QUERY = "older-2026-01-29/2026-01-29__NIKKOR_Z_100-400mm_f_4.5-5.6_VR_S__1_2.60__F11"
M_TASK2 = 0.3846153846153846

# Optional local JPEG cache. If a file with the same basename exists
# under LOCAL_JPEG_DIR we read it from there instead of the NFS-backed
# original path. Avoids the ~3-minute-per-frame NFS stall observed
# 2026-05-17 on bumblebee.
LOCAL_JPEG_DIR = Path("/tmp/poc_jpegs")

# ROI size for FFT analysis. Maze ROI is 256 px at this M (M-driven
# scaling); we use 1024 px for the pad/grid candidates so we have
# enough cycles of a ~60 um pitch (period ~5 px -> 200 cycles) and so
# the annulus has many bins. Keep it small enough that the per-shot
# loop stays cheap (1024 x 1024 FFT is ~80 ms on this hardware).
ROI_PX = 1024

# Sharp shot per peaks_v2 — used for pitch discovery.
PITCH_DISCOVERY_SHOT = 137

# Centre + 4 mildly-off-axis on-target tiles (per peaks_v2 inspection).
TILES = [
    (0, 0, 4128, 2752, "centre"),
    (-1, 0, 3104, 2752, "left-mid"),
    (1, 0, 5152, 2752, "right-mid"),
    (0, -1, 4128, 1728, "above-mid"),
    (0, 1, 4128, 3776, "below-mid"),
]

OUT_DIR = Path(__file__).resolve().parent / "poc_pad_grid_fft_out"


# ---------------------------------------------------------------------------
# FFT helpers
# ---------------------------------------------------------------------------

def radial_spectrum(image_2d: np.ndarray, n_bins: int = 200) -> tuple[np.ndarray, np.ndarray]:
    """Hann-windowed 2D-FFT, radially binned amplitude vs frequency.

    Returns ``(freq_cy_per_px, mean_abs_fft)``. Frequency bins span
    ``[0, 0.5]``. Mean amplitude in each annulus (per-bin pixel mean).
    """
    h, w = image_2d.shape
    arr = image_2d.astype(np.float64) - image_2d.mean()
    win = np.outer(np.hanning(h), np.hanning(w))
    f = np.fft.fftshift(np.fft.fft2(arr * win))
    amp = np.abs(f)
    fy = np.fft.fftshift(np.fft.fftfreq(h))
    fx = np.fft.fftshift(np.fft.fftfreq(w))
    fxx, fyy = np.meshgrid(fx, fy)
    r = np.sqrt(fxx * fxx + fyy * fyy)
    edges = np.linspace(0.0, 0.5, n_bins + 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    means = np.empty(n_bins)
    flat_r = r.ravel()
    flat_a = amp.ravel()
    idx = np.digitize(flat_r, edges) - 1
    for k in range(n_bins):
        mask = idx == k
        means[k] = flat_a[mask].mean() if mask.any() else 0.0
    return centres, means


def pad_grid_amp(
    image_2d: np.ndarray,
    M: float,
    pitch_um: float,
    *,
    sensor_pitch_um: float = SENSOR_PITCH_UM_Z7,
    half_bandwidth: float = 0.015,
) -> float | None:
    """Mean |FFT| amplitude in an annulus around f = M * sensor_pitch / pitch_um.

    Direct analogue of ``maze_amp``: mean-subtract, Hann-window,
    fftshift, sum amplitudes within +/- half_bandwidth of the centre
    frequency, divide by ROI area.

    Returns None if the band overlaps Nyquist (aliasing) or DC.
    """
    if image_2d.ndim != 2:
        raise ValueError(f"expected 2-D image, got shape {image_2d.shape}")
    h, w = image_2d.shape
    if h < 8 or w < 8:
        return 0.0
    if M <= 0 or pitch_um <= 0:
        return None
    freq = M * sensor_pitch_um / pitch_um  # cycles per sensor pixel
    nyquist = 0.5
    if freq + half_bandwidth > nyquist:
        return None
    if freq - half_bandwidth <= 0:
        return None

    arr = image_2d.astype(np.float64) - image_2d.mean()
    win = np.outer(np.hanning(h), np.hanning(w))
    f = np.fft.fftshift(np.fft.fft2(arr * win))
    amp = np.abs(f)
    fy = np.fft.fftshift(np.fft.fftfreq(h))
    fx = np.fft.fftshift(np.fft.fftfreq(w))
    fxx, fyy = np.meshgrid(fx, fy)
    r = np.sqrt(fxx * fxx + fyy * fyy)
    mask = (r >= freq - half_bandwidth) & (r <= freq + half_bandwidth)
    if not mask.any():
        return 0.0
    return float(amp[mask].sum() / (h * w))


# ---------------------------------------------------------------------------
# Pitch discovery
# ---------------------------------------------------------------------------

def _centre_crop(image: np.ndarray, cx: int, cy: int, size: int) -> np.ndarray:
    half = size // 2
    return _crop_box(image, (cx - half, cy - half, cx + half, cy + half))


def _shot_path(shot) -> Path:
    """Use the local cache copy if present, else the original NFS path."""
    cached = LOCAL_JPEG_DIR / shot.path.name
    return cached if cached.exists() else shot.path


def _build_sweep_from_cache(cache_dir: Path) -> Sweep:
    """Construct a synthetic Sweep from JPEGs in the local cache dir.

    Bypasses the ``discover_all()`` walk over NFS dirs, which can stall
    for minutes on bumblebee. JPEG filenames carry their sequence
    number as the leading ``NNNNN|`` prefix.
    """
    paths = sorted(cache_dir.glob("*.jpg"))
    shots = [
        Shot(path=p, rail_step=int(p.name.split("|", 1)[0]), rail_position_mm=None)
        for p in paths
    ]
    return Sweep(
        label=SWEEP_QUERY.split("/", 1)[1],
        family=SWEEP_QUERY.split("/", 1)[0],
        lens="NIKKOR Z 100-400mm f_4.5-5.6 VR S",
        aperture="F11",
        shots=shots,
    )


def discover_pitch(sweep, out_dir: Path) -> tuple[float, list[tuple[float, float]]]:
    """Find dominant non-DC peak in radial spectrum; return its subject-space pitch.

    Returns ``(chosen_pitch_um, peak_list)`` where peak_list is
    ``[(freq_cy_per_px, pitch_um), ...]`` for the top peaks in the
    target frequency band [0.02, 0.20].
    """
    shot = sweep.shots[PITCH_DISCOVERY_SHOT]
    full = _decode_gray(_shot_path(shot))
    cx, cy = TILES[0][2], TILES[0][3]
    crop = _centre_crop(full, cx, cy, ROI_PX)
    freqs, amps = radial_spectrum(crop)

    # Search peaks in [0.02, 0.20] cy/px (avoid DC bleed; stay below
    # maze fundamental for M=1.0 ~= 0.33).
    band = (freqs >= 0.02) & (freqs <= 0.20)
    # Simple local-maxima search.
    peaks: list[tuple[float, float]] = []
    in_band_idx = np.where(band)[0]
    for i in in_band_idx:
        if i == 0 or i == len(freqs) - 1:
            continue
        if amps[i] > amps[i - 1] and amps[i] >= amps[i + 1]:
            peaks.append((float(freqs[i]), float(amps[i])))
    # Sort by amplitude descending, keep top 5.
    peaks.sort(key=lambda p: p[1], reverse=True)
    top = peaks[:5]

    # Save CSV.
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "radial_spectrum.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["freq_cy_per_px", "mean_abs_fft", "subject_pitch_um_at_M0.385"])
        for fr, am in zip(freqs, amps):
            pitch = (M_TASK2 * SENSOR_PITCH_UM_Z7 / fr) if fr > 0 else float("inf")
            w.writerow([f"{fr:.6f}", f"{am:.4f}", f"{pitch:.3f}"])

    # Plot.
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.semilogy(freqs, amps, lw=0.9)
    ax.set_xlabel("spatial frequency (cy/px, sensor)")
    ax.set_ylabel("mean |FFT| amplitude")
    ax.set_title(
        f"Radial power spectrum — centre tile, shot {PITCH_DISCOVERY_SHOT}, "
        f"{ROI_PX}x{ROI_PX} crop"
    )
    ax.axvspan(0.02, 0.20, alpha=0.10, color="orange", label="search band")
    for fr, am in top[:3]:
        pitch_um = M_TASK2 * SENSOR_PITCH_UM_Z7 / fr
        ax.axvline(fr, color="red", lw=0.6, alpha=0.5)
        ax.annotate(
            f"{fr:.3f} cy/px\n{pitch_um:.1f} um",
            (fr, am),
            xytext=(5, 0),
            textcoords="offset points",
            fontsize=8,
        )
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "radial_spectrum.png", dpi=120)
    plt.close(fig)

    # Translate peaks to subject pitches.
    peak_pitch_list = [(fr, M_TASK2 * SENSOR_PITCH_UM_Z7 / fr) for fr, _ in top]
    chosen_pitch = peak_pitch_list[0][1] if peak_pitch_list else 60.0
    return chosen_pitch, peak_pitch_list


# ---------------------------------------------------------------------------
# Per-shot sweep
# ---------------------------------------------------------------------------

def run_per_shot(sweep, pitch_um: float, out_dir: Path) -> dict[str, list[float]]:
    """For each tile, compute pad_grid_amp across all 142 shots.

    Returns dict ``{label: [amp_per_shot, ...]}``.
    """
    n_shots = len(sweep.shots)
    curves: dict[str, list[float]] = {label: [float("nan")] * n_shots for *_, label in TILES}
    # Decode each shot once, score all 5 tiles, move on.
    for k, shot in enumerate(sweep.shots):
        full = _decode_gray(_shot_path(shot))
        for ix, iy, cx, cy, label in TILES:
            crop = _centre_crop(full, cx, cy, ROI_PX)
            val = pad_grid_amp(crop, M_TASK2, pitch_um)
            curves[label][k] = float("nan") if val is None else val
        if k % 20 == 0 or k == n_shots - 1:
            print(f"  scored shot {k + 1}/{n_shots}", flush=True)

    # Save CSV.
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "pad_fft_per_shot.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["shot_idx"] + [t[4] for t in TILES])
        for k in range(n_shots):
            w.writerow([k] + [f"{curves[t[4]][k]:.6f}" for t in TILES])

    return curves


# ---------------------------------------------------------------------------
# Comparison vs LSF / filesize
# ---------------------------------------------------------------------------

def load_per_shot_csv(csv_path: Path) -> dict[tuple[int, int], dict[str, list]]:
    """Load per_shot_per_tile.csv -> {(ix,iy): {col: [vals_per_shot]}}.

    Filters to the Task 2 sweep only.
    """
    by_tile: dict[tuple[int, int], list[dict]] = {}
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if "100-400" not in row["sweep"]:
                continue
            key = (int(row["tile_ix"]), int(row["tile_iy"]))
            by_tile.setdefault(key, []).append(row)
    out = {}
    for key, rows in by_tile.items():
        rows.sort(key=lambda r: int(r["shot_idx"]))
        lsf = []
        fs = []
        for r in rows:
            v = r.get("lsf_peak_amp", "")
            try:
                lsf.append(float(v) if v not in ("", None) else float("nan"))
            except ValueError:
                lsf.append(float("nan"))
            v = r.get("filesize_bytes", "")
            try:
                fs.append(float(v) if v not in ("", None) else float("nan"))
            except ValueError:
                fs.append(float("nan"))
        out[key] = {"lsf": lsf, "filesize": fs}
    return out


def argmax_nan_safe(xs: list[float]) -> int:
    arr = np.array(xs)
    if not np.isfinite(arr).any():
        return -1
    arr = np.where(np.isfinite(arr), arr, -np.inf)
    return int(np.argmax(arr))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    discover_only = "--discover-only" in sys.argv
    pitch_override = None
    for a in sys.argv:
        if a.startswith("--pitch-um="):
            pitch_override = float(a.split("=", 1)[1])
    print(f"Loading sweep {SWEEP_QUERY}", flush=True)
    if LOCAL_JPEG_DIR.exists() and any(LOCAL_JPEG_DIR.glob("*.jpg")):
        print(f"  using local JPEG cache at {LOCAL_JPEG_DIR}", flush=True)
        sweep = _build_sweep_from_cache(LOCAL_JPEG_DIR)
    else:
        sweeps = discover_all()
        sweep = find_sweep(SWEEP_QUERY, sweeps)
    print(f"  {len(sweep.shots)} shots", flush=True)

    # 1) Pitch discovery.
    print("Step 1: pitch discovery on shot 137 centre tile", flush=True)
    chosen_pitch, top_peaks = discover_pitch(sweep, OUT_DIR)
    print("  Top radial-spectrum peaks (freq cy/px -> subject pitch um at M=0.385):")
    for fr, pitch in top_peaks:
        print(f"    {fr:.4f} cy/px -> {pitch:.2f} um")
    print(f"  Chosen pitch (dominant peak): {chosen_pitch:.2f} um")

    if pitch_override is not None:
        print(f"  --pitch-um override applied: {pitch_override:.2f} um", flush=True)
        chosen_pitch = pitch_override
    if discover_only:
        print("--discover-only: stopping after pitch discovery.")
        print(f"\nOutputs in {OUT_DIR}/")
        return

    # 2) Per-shot sweep using the discovered pitch.
    print(
        f"Step 2: pad-grid FFT amplitude per shot, "
        f"pitch={chosen_pitch:.2f} um -> "
        f"f={M_TASK2 * SENSOR_PITCH_UM_Z7 / chosen_pitch:.4f} cy/px",
        flush=True,
    )
    curves = run_per_shot(sweep, chosen_pitch, OUT_DIR)

    # 3) Compare to LSF + filesize argmaxes.
    print("Step 3: argmax comparison vs production LSF & filesize", flush=True)
    psv2 = load_per_shot_csv(REPO / "out_task2" / "per_shot_per_tile.csv")

    rows = []
    for ix, iy, cx, cy, label in TILES:
        pad_curve = curves[label]
        pad_argmax = argmax_nan_safe(pad_curve)
        key = (ix, iy)
        lsf_argmax = -1
        fs_argmax = -1
        if key in psv2:
            lsf_argmax = argmax_nan_safe(psv2[key]["lsf"])
            fs_argmax = argmax_nan_safe(psv2[key]["filesize"])
        rows.append((label, ix, iy, pad_argmax, lsf_argmax, fs_argmax,
                     pad_curve[pad_argmax] if pad_argmax >= 0 else float("nan")))

    print()
    print(f"  {'tile':<12s} {'(ix,iy)':<8s} {'pad_argmax':>10s} {'lsf_argmax':>10s} {'fs_argmax':>10s} {'pad_peak':>12s}")
    for label, ix, iy, pa, la, fa, pv in rows:
        print(f"  {label:<12s} {f'({ix},{iy})':<8s} {pa:>10d} {la:>10d} {fa:>10d} {pv:>12.3f}")

    pad_argmaxes = [r[3] for r in rows if r[3] >= 0]
    pad_std = float(np.std(pad_argmaxes)) if pad_argmaxes else float("nan")
    pad_centre = rows[0][3]
    lsf_centre = rows[0][4]
    centre_match = "MATCH" if pad_centre == lsf_centre else (
        f"close (delta={pad_centre - lsf_centre} shots)"
        if abs(pad_centre - lsf_centre) <= 3 else
        f"MISMATCH (delta={pad_centre - lsf_centre} shots)"
    )

    print()
    print(f"HEADLINE:")
    print(f"  chosen pitch:        {chosen_pitch:.2f} um")
    print(f"  centre pad argmax:   {pad_centre}  (LSF argmax: {lsf_centre}, {centre_match})")
    print(f"  pad argmax std-dev:  {pad_std:.2f} shots across {len(pad_argmaxes)} tiles")

    # 4) Plot curves.
    fig, axes = plt.subplots(len(TILES), 1, figsize=(10, 2.5 * len(TILES)), sharex=True)
    if len(TILES) == 1:
        axes = [axes]
    for ax, (label, ix, iy, pa, la, fa, pv) in zip(axes, rows):
        key = (ix, iy)
        n = len(curves[label])
        x = np.arange(n)
        ax.plot(x, curves[label], "b-", lw=0.8, label="pad-FFT")
        ax.axvline(pa, color="b", lw=0.8, alpha=0.6)
        if key in psv2:
            lsf = np.array(psv2[key]["lsf"])
            fs = np.array(psv2[key]["filesize"])
            # Normalise each to its max for visual comparison.
            ax2 = ax.twinx()
            if np.isfinite(lsf).any():
                ax2.plot(x, lsf, "g-", lw=0.6, alpha=0.7, label="lsf_peak_amp")
                ax2.axvline(la, color="g", lw=0.8, alpha=0.4, ls="--")
            ax2.plot(x, fs, "r-", lw=0.5, alpha=0.5, label="filesize")
            ax2.axvline(fa, color="r", lw=0.8, alpha=0.3, ls=":")
            ax2.legend(loc="upper right", fontsize=7)
        ax.set_title(f"{label} ({ix},{iy})  pad_argmax={pa}  lsf={la}  fs={fa}", fontsize=9)
        ax.set_ylabel("pad-FFT amp")
        ax.legend(loc="upper left", fontsize=7)
    axes[-1].set_xlabel("shot index")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "pad_fft_curves.png", dpi=110)
    plt.close(fig)

    print(f"\nOutputs in {OUT_DIR}/")


if __name__ == "__main__":
    main()
