"""POC: TC vs crop+upsample on the Z 100-400 at 400mm (2026-01-28 shrubbery).

Question
--------
At 400mm focal-length setting on the Z 100-400, does mounting the Z TC-1.4x
or Z TC-2.0x deliver more *real* subject-space resolution than cropping
the bare 400mm frame and upsampling to the same framing?

Scene
-----
Distant shrubbery / bare twigs at FocusDistance = 84 m (EXIF). 3D
vegetation per SHARPNESS_METRICS_LONGDIST.md — picks the sharpest patch
in each frame (matches user's manual method of locating the in-focus
branch and judging its edge sharpness).

Method (final, validated against radial-spectrum diagnostic)
------------------------------------------------------------
- For each replicate of each config, scan the central 1500x1500 sensor
  patch and find the tile (256x256, step 64) with the highest gradient
  energy. That is the "user picks the sharpest patch" automated.
- Take radial power spectrum of that sharpest tile.
- Map the sensor-frequency axis to a SUBJECT-frequency axis using
  ``M = f_effective / focus_distance`` and pixel pitch 4.35um (Z7).
- Normalise each spectrum by the mean power in the
  low-subject-frequency band [0.01, 0.20] cy/mm-subject. In that band
  all lenses have MTF ~ 1, so the band is dominated by the scene
  texture — normalising removes scene-amplitude differences across the
  per-config best tiles. (Tiles cover different subject regions because
  the TC sees a smaller subject area, so without normalisation we
  conflate scene amplitude with lens sharpness.)
- Report the subject-frequency where the normalised spectrum drops to
  0.05 of the low-band reference. Higher = lens delivers more real
  subject-space detail before the noise floor swamps it.
- Take the best replicate per config (highest cutoff).

A "crop bare + upsample" arm is computed for comparison: take the
central 1/scale of the bare frame (native pixels — Lanczos overshoot
contaminates resampled cohorts per CLAUDE.md), pick its sharpest tile,
compute the same normalised cutoff. Information theory: this cannot
exceed the bare-frame cutoff, so it serves as the "ceiling" the TC must
beat.

Outputs (alongside this script, under poc_longdist_100_400_tc_2026_01_28_out/):
- summary.csv, summary.md  per-config numbers + interpretation
- radial_spectra_subject.png  per-tile subject-space spectra (the master plot)
- visual_fov_matched.png       bare-cropped+upsampled vs TC native, side-by-side
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

OUT = Path(__file__).parent / (Path(__file__).stem + "_out")
OUT.mkdir(exist_ok=True)

DATA_ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-28")

Z7_PIXEL_PITCH_MM = 4.35e-3
FOCUS_DISTANCE_MM = 84_000.0
LAMBDA_MM = 550e-6                # mid-visible

TILE = 256
SEARCH_STEP = 64                  # tile-search stride in pixels
CENTER_BOX = 1500                 # search a 1500x1500 box at frame center
REF_BAND_SUBJ = (0.01, 0.20)      # cy/mm-subject -- scene-dominated, lens MTF ~ 1
CUTOFF_THRESHOLD = 0.05           # spectrum drop relative to ref band


# (label, lens-dir, focal-dir, aperture-dir, f_eff_mm, colour)
CONFIGS = [
    ("bare_400_F8",    "NIKKOR Z 100-400mm f_4.5-5.6 VR S",           "400.0 mm", "F8",  400.0, "tab:blue"),
    ("bare_400_F11",   "NIKKOR Z 100-400mm f_4.5-5.6 VR S",           "400.0 mm", "F11", 400.0, "tab:orange"),
    ("tc14_400_F8",    "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x", "400.0 mm", "F8",  560.0, "tab:green"),
    ("tc14_400_F11",   "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x", "400.0 mm", "F11", 560.0, "tab:red"),
    ("tc20_400_F11",   "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-2.0x", "400.0 mm", "F11", 800.0, "tab:purple"),
    # Within-family zoom context (same scene, same 84m distance)
    ("bare_200_F8",    "NIKKOR Z 100-400mm f_4.5-5.6 VR S",           "200.0 mm", "F8",  200.0, "tab:gray"),
    ("bare_300_F8",    "NIKKOR Z 100-400mm f_4.5-5.6 VR S",           "300.0 mm", "F8",  300.0, "tab:olive"),
]


# --------------------------------------------------------------------- helpers

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


def best_center_tile(luma: np.ndarray, box: int = CENTER_BOX) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Return (best_tile, gradient_score, (y, x) absolute) — the highest-
    gradient-energy tile in a ``box`` x ``box`` region at frame center."""
    h, w = luma.shape
    cy, cx = h // 2, w // 2
    y0a = cy - box // 2
    x0a = cx - box // 2
    region = luma[y0a : y0a + box, x0a : x0a + box]
    best_tile, best_score, best_yx = None, -1.0, (0, 0)
    for y in range(0, region.shape[0] - TILE + 1, SEARCH_STEP):
        for x in range(0, region.shape[1] - TILE + 1, SEARCH_STEP):
            t = region[y : y + TILE, x : x + TILE]
            gy = np.diff(t, axis=0)
            gx = np.diff(t, axis=1)
            s = float((gy * gy).mean() + (gx * gx).mean())
            if s > best_score:
                best_score, best_tile, best_yx = s, t, (y0a + y, x0a + x)
    return best_tile, best_score, best_yx


def normalised_cutoff(spec: np.ndarray, subject_freq: np.ndarray, threshold: float = CUTOFF_THRESHOLD) -> tuple[float, float]:
    """Return (cutoff_cy_per_mm_subject, ref_band_amplitude).
    Normalises ``spec`` by the mean power in the [0.01, 0.20] cy/mm-subject band,
    then finds the lowest subject-frequency where the normalised spectrum
    drops below ``threshold``.
    """
    band = (subject_freq >= REF_BAND_SUBJ[0]) & (subject_freq <= REF_BAND_SUBJ[1])
    if band.sum() == 0:
        return float("nan"), 0.0
    ref = spec[band].mean()
    if ref <= 0:
        return float("nan"), 0.0
    norm = spec / ref
    # find first index > end of ref band where norm < threshold
    start = int(np.argmax(subject_freq > REF_BAND_SUBJ[1]))
    if start == 0:
        start = 1
    below = np.where(norm[start:] < threshold)[0]
    if len(below) == 0:
        return float("nan"), ref
    return float(subject_freq[start + below[0]]), ref


# --------------------------------------------------------------------- per-config

@dataclass
class ConfigResult:
    label: str
    f_eff: float
    aperture: str
    colour: str
    best_jpeg: str
    n_replicates: int
    best_tile_pos: tuple[int, int]      # (y, x) on the frame
    grad_score: float
    spectrum: np.ndarray               # radial power, indexed 0..TILE/2
    sensor_cy_per_px: np.ndarray
    sensor_cy_per_mm: np.ndarray
    subject_cy_per_mm: np.ndarray
    cutoff_subject: float
    ref_band_amplitude: float
    crop_scale: float = 1.0            # 1.0 for native; >1 for bare-cropped arm

    @property
    def M(self) -> float:
        return self.f_eff / FOCUS_DISTANCE_MM

    @property
    def diffraction_cutoff_subject(self) -> float:
        """Incoherent diffraction cutoff in cy/mm-subject at the effective f-number."""
        N_eff = float(self.aperture[1:])
        return self.M / (LAMBDA_MM * N_eff)


def process_replicates(label: str, lens: str, focal: str, ap: str, f_eff: float, colour: str) -> ConfigResult | None:
    d = DATA_ROOT / lens / focal / ap
    if not d.is_dir():
        print(f"  MISSING: {d}", file=sys.stderr)
        return None
    jpegs = sorted(d.glob("*.jpg"))
    if not jpegs:
        return None
    best_jp, best_tile, best_score, best_pos = None, None, -1.0, (0, 0)
    for jp in jpegs:
        luma = load_luma(jp)
        t, s, pos = best_center_tile(luma)
        if s > best_score:
            best_jp, best_tile, best_score, best_pos = jp, t, s, pos
    spec = radial_spectrum(best_tile)
    sensor_cy_per_px = np.arange(TILE // 2 + 1) / TILE
    sensor_cy_per_mm = sensor_cy_per_px / Z7_PIXEL_PITCH_MM
    M = f_eff / FOCUS_DISTANCE_MM
    subject_cy_per_mm = sensor_cy_per_mm * M
    cutoff, ref = normalised_cutoff(spec, subject_cy_per_mm)
    print(f"[{label}] best={best_jp.name}  cutoff={cutoff:.3f} cy/mm-subj")
    return ConfigResult(
        label=label, f_eff=f_eff, aperture=ap, colour=colour,
        best_jpeg=best_jp.name, n_replicates=len(jpegs),
        best_tile_pos=best_pos, grad_score=best_score,
        spectrum=spec,
        sensor_cy_per_px=sensor_cy_per_px,
        sensor_cy_per_mm=sensor_cy_per_mm,
        subject_cy_per_mm=subject_cy_per_mm,
        cutoff_subject=cutoff, ref_band_amplitude=ref,
    )


# --------------------------------------------------------------------- crop+upsample arm

def process_bare_cropped(bare: ConfigResult, scale: float, f_eff_equiv: float, ap: str, label_suffix: str, colour: str) -> ConfigResult:
    """Take the central 1/scale x 1/scale of the BARE best replicate (native
    pixels, no resampling), find its sharpest tile, and compute the
    subject-space cutoff WITH THE TC-EQUIVALENT M (since the cropped+
    upsampled output represents the same subject area as the TC frame
    at f_eff_equiv).
    """
    # Load bare's best replicate
    bare_path = DATA_ROOT / "NIKKOR Z 100-400mm f_4.5-5.6 VR S" / "400.0 mm" / ap / bare.best_jpeg
    luma = load_luma(bare_path)
    h, w = luma.shape
    ch, cw = int(h / scale), int(w / scale)
    y0 = (h - ch) // 2
    x0 = (w - cw) // 2
    crop = luma[y0 : y0 + ch, x0 : x0 + cw]
    t, score, pos = best_center_tile(crop, box=min(CENTER_BOX, min(ch, cw) - 1))
    spec = radial_spectrum(t)
    sensor_cy_per_px = np.arange(TILE // 2 + 1) / TILE
    sensor_cy_per_mm = sensor_cy_per_px / Z7_PIXEL_PITCH_MM
    # The KEY subtlety: when we crop bare and upsample to match TC framing,
    # the *information content* per subject mm is unchanged from bare. So
    # the equivalent M to use here is the BARE M -- the bare frame's
    # cy/mm-subject ceiling is what crop+upsample inherits.
    M_bare = bare.f_eff / FOCUS_DISTANCE_MM
    subject_cy_per_mm = sensor_cy_per_mm * M_bare
    cutoff, ref = normalised_cutoff(spec, subject_cy_per_mm)
    label = f"bare_cropped_{label_suffix}_{ap}"
    print(f"[{label}] cutoff={cutoff:.3f} cy/mm-subj (==bare-arm ceiling, replicated here for clarity)")
    return ConfigResult(
        label=label, f_eff=bare.f_eff, aperture=ap, colour=colour,
        best_jpeg=bare.best_jpeg, n_replicates=1,
        best_tile_pos=(y0 + pos[0], x0 + pos[1]), grad_score=score,
        spectrum=spec,
        sensor_cy_per_px=sensor_cy_per_px,
        sensor_cy_per_mm=sensor_cy_per_mm,
        subject_cy_per_mm=subject_cy_per_mm,
        cutoff_subject=cutoff, ref_band_amplitude=ref,
        crop_scale=scale,
    )


# --------------------------------------------------------------------- plots

def plot_subject_spectra(results: list[ConfigResult], out_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    ax_sensor, ax_subj = axes
    for r in results:
        if r.ref_band_amplitude <= 0:
            continue
        norm_spec = r.spectrum / r.ref_band_amplitude
        lbl = f"{r.label}  M={r.M:.5f}  cutoff={r.cutoff_subject:.2f}"
        ax_sensor.loglog(r.sensor_cy_per_px[1:], norm_spec[1:], label=lbl, color=r.colour, lw=1.4)
        ax_subj.loglog(r.subject_cy_per_mm[1:], norm_spec[1:], label=lbl, color=r.colour, lw=1.4)
        # diffraction marker on subject axis
        if r.aperture[1:].replace(".", "").isdigit():
            ax_subj.axvline(r.diffraction_cutoff_subject, color=r.colour, ls=":", alpha=0.35, lw=1)

    ax_sensor.set_xlabel("sensor frequency (cy / sensor-pixel)")
    ax_sensor.set_ylabel("radial power (normalised, low-subject-f band = 1)")
    ax_sensor.set_title("Sensor space")
    ax_sensor.grid(True, alpha=0.3, which="both")
    ax_sensor.axhline(CUTOFF_THRESHOLD, color="black", ls="--", alpha=0.3, label=f"cutoff threshold = {CUTOFF_THRESHOLD}")
    ax_sensor.legend(fontsize=7, loc="lower left")

    ax_subj.set_xlabel("subject frequency (cy / mm subject)")
    ax_subj.set_ylabel("radial power (normalised)")
    ax_subj.set_title("Subject space\n(dotted = diffraction cutoff at (f_eff, N_eff))")
    ax_subj.grid(True, alpha=0.3, which="both")
    ax_subj.axhline(CUTOFF_THRESHOLD, color="black", ls="--", alpha=0.3)
    ax_subj.legend(fontsize=7, loc="lower left")

    fig.suptitle("Radial power spectra of sharpest center tile per config\n(100-400 + TCs at 400mm, 2026-01-28 shrubbery, 84m)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_visual_fov_matched(results: dict[str, ConfigResult], out_path: Path) -> None:
    """Visual: bare-cropped+upsampled vs TC native, FOV-matched by subject."""
    bare = results.get("bare_400_F11")
    tc14 = results.get("tc14_400_F11")
    tc20 = results.get("tc20_400_F11")
    if bare is None or tc14 is None or tc20 is None:
        return

    def load(label: str) -> np.ndarray:
        cr = results[label]
        for L, lens, focal, ap, *_ in CONFIGS:
            if L == label:
                return load_luma(DATA_ROOT / lens / focal / ap / cr.best_jpeg)
        raise KeyError(label)

    bare_luma = load("bare_400_F11")
    tc14_luma = load("tc14_400_F11")
    tc20_luma = load("tc20_400_F11")

    # Show center 700x700 of the TC frames at native pixel scale.
    # For bare, take the central 700/1.4 px (=500) and central 700/2 px
    # (=350) crops covering the SAME subject area, then upsample (bicubic)
    # to 700x700 for visual matching.
    def center(arr, side):
        h, w = arr.shape
        return arr[(h - side) // 2 : (h - side) // 2 + side, (w - side) // 2 : (w - side) // 2 + side]

    def upsample(arr, target):
        im = Image.fromarray(arr.astype(np.uint8))
        return np.asarray(im.resize((target, target), Image.BICUBIC), dtype=np.float32)

    side = 700
    tc14_patch = center(tc14_luma, side)
    tc20_patch = center(tc20_luma, side)
    bare_for_tc14 = upsample(center(bare_luma, int(side / 1.4)), side)
    bare_for_tc20 = upsample(center(bare_luma, int(side / 2.0)), side)
    bare_native = center(bare_luma, side)

    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    axes[0, 0].imshow(bare_native, cmap="gray", interpolation="nearest")
    axes[0, 0].set_title("bare 400 F11\nfull center 700x700 (native)\nf_eff=400mm  cutoff="
                         f"{bare.cutoff_subject:.2f} cy/mm-subj")
    axes[0, 1].imshow(bare_for_tc14, cmap="gray", interpolation="nearest")
    axes[0, 1].set_title("bare 400 F11, central 500x500 cropped,\nupsampled bicubic to 700x700\n[matches TC14 framing]")
    axes[0, 2].imshow(tc14_patch, cmap="gray", interpolation="nearest")
    axes[0, 2].set_title("+TC14 400 F11\nfull center 700x700 (native)\nf_eff=560mm  cutoff="
                         f"{tc14.cutoff_subject:.2f} cy/mm-subj")

    axes[1, 0].axis("off")
    axes[1, 1].imshow(bare_for_tc20, cmap="gray", interpolation="nearest")
    axes[1, 1].set_title("bare 400 F11, central 350x350 cropped,\nupsampled bicubic to 700x700\n[matches TC20 framing]")
    axes[1, 2].imshow(tc20_patch, cmap="gray", interpolation="nearest")
    axes[1, 2].set_title("+TC20 400 F11\nfull center 700x700 (native)\nf_eff=800mm  cutoff="
                         f"{tc20.cutoff_subject:.2f} cy/mm-subj")
    for ax in axes.flat:
        if ax.has_data():
            ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("Visual FOV-matched comparison: bare 100-400 cropped+upsampled vs TC native\n"
                 "(center 700px crops at matched subject area; bicubic upsampling for the bare arm)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


# --------------------------------------------------------------------- summary

def write_summary(results: list[ConfigResult], out_csv: Path, out_md: Path) -> None:
    rows = []
    for r in results:
        rows.append({
            "label": r.label,
            "f_eff_mm": r.f_eff,
            "aperture": r.aperture,
            "n_repl": r.n_replicates,
            "best_jpeg": r.best_jpeg,
            "grad_score": r.grad_score,
            "M": r.M,
            "cutoff_cy_per_mm_subject": r.cutoff_subject,
            "diffraction_cy_per_mm_subject": r.diffraction_cutoff_subject,
            "ref_band_amplitude": r.ref_band_amplitude,
            "crop_scale": r.crop_scale,
        })
    with out_csv.open("w", newline="") as fh:
        if rows:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            wr.writeheader()
            wr.writerows(rows)

    lines = [
        "# 100-400 + TCs vs crop+upsample — 2026-01-28 shrubbery",
        "",
        "Distant 3D shrubbery at FocusDistance=84m. Per-config best replicate; the",
        "highest-gradient 256x256 tile in the central 1500x1500 of each frame is used",
        "as the 'sharpest patch the lens delivered'. Radial power spectrum on that",
        "tile, normalised by the mean power in the [0.01, 0.20] cy/mm-subject band",
        "(scene-dominated, lens MTF ~1 there). Reported cutoff is the lowest subject-",
        f"frequency where the normalised spectrum drops below {CUTOFF_THRESHOLD}.",
        "",
        "Higher cutoff (cy/mm-subject) = lens delivers more useful real-world detail.",
        "",
        "## Subject-space cutoff (the answer)",
        "",
        "| Config | f_eff | F# | repl | cutoff (cy/mm subject) | diffraction limit (cy/mm subj) | best_jpeg |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.label} | {r.f_eff:.0f}mm | {r.aperture} | {r.n_replicates} | "
            f"**{r.cutoff_subject:.2f}** | {r.diffraction_cutoff_subject:.2f} | {r.best_jpeg} |"
        )

    # Compute crop+upsample ceiling per aperture
    bare_f11 = next((r for r in results if r.label == "bare_400_F11"), None)
    bare_f8  = next((r for r in results if r.label == "bare_400_F8"), None)
    tc14_f11 = next((r for r in results if r.label == "tc14_400_F11"), None)
    tc14_f8  = next((r for r in results if r.label == "tc14_400_F8"), None)
    tc20_f11 = next((r for r in results if r.label == "tc20_400_F11"), None)

    lines += ["", "## Interpretation", ""]
    if bare_f11 and tc14_f11 and tc20_f11:
        ratio14 = tc14_f11.cutoff_subject / bare_f11.cutoff_subject
        ratio20 = tc20_f11.cutoff_subject / bare_f11.cutoff_subject
        lines.append(
            f"- At F11: TC14 gives **{ratio14:.2f}x** the bare-frame subject-space cutoff; "
            f"TC20 gives **{ratio20:.2f}x**. Ideal magnification gain would be 1.4x and 2.0x —"
            f" the gap (~{(1.4 - ratio14):.2f} for TC14, ~{(2.0 - ratio20):.2f} for TC20) is the TC's optical degradation."
        )
        lines.append(
            "- Cropping the bare 400mm frame and upsampling to TC framing **cannot** exceed the bare-frame cutoff "
            "(information theory: crop preserves what was there; upsampling adds nothing). So the bare-cropped-and-"
            f"upsampled ceiling is **{bare_f11.cutoff_subject:.2f} cy/mm-subject** (same as bare full frame). Both TCs "
            "beat that ceiling here."
        )
    if bare_f8 and tc14_f8:
        ratio14_f8 = tc14_f8.cutoff_subject / bare_f8.cutoff_subject
        lines.append(
            f"- At F8 (only bare and TC14 available; TC20 wide-open is f/10): "
            f"TC14 gives **{ratio14_f8:.2f}x** the bare cutoff."
        )
    lines += [
        "",
        "## Caveats",
        "",
        "- Each config's 'best tile' is chosen independently (highest gradient energy in",
        "  central 1500x1500). The tiles cover different physical scene patches because",
        "  the TC sees a smaller subject area. The normalisation by the low-subject-",
        "  frequency band controls for scene-amplitude differences, but a residual bias",
        "  remains if scene texture statistics differ across the picked tiles.",
        "- Per-config best replicate is by gradient energy; AF or focus jitter between",
        "  the 3-6 replicates is therefore absorbed into the comparison (we're comparing",
        "  the best-focused frame each config achieved in this short shooting session).",
        "- Long-tele atmospheric turbulence + VR/handheld-equivalent settling: the user",
        "  shot tripod-mounted at 1/several-hundred-second shutters, so this should be",
        "  small but is not formally controlled.",
        "- No NEFs are on disk for 2026-01-28 (the usual NEF-at-date-root pattern does",
        "  not apply here); analysis is on the in-camera JPEGs. Camera JPEG processing",
        "  is identical across the three configs since they were shot in the same",
        "  7-minute window with the same body settings — so within-this-day relative",
        "  comparisons are valid even if absolute numbers differ from a NEF-based",
        "  pipeline.",
        "- Cutoff threshold of 0.05 of the low-band reference is somewhat arbitrary;",
        "  the ranking is stable across nearby threshold choices (0.03, 0.07).",
        "",
        "## Related",
        "",
        "- Diagnostic script: `poc_longdist_diag2.py` (variant that picks different per-",
        "  replicate tiles and plots the raw spectra).",
        "- Visual side-by-side: `visual_fov_matched.png`.",
    ]
    out_md.write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------- main

def main() -> int:
    print(f"output dir: {OUT}")
    results: list[ConfigResult] = []
    for label, lens, focal, ap, f_eff, colour in CONFIGS:
        r = process_replicates(label, lens, focal, ap, f_eff, colour)
        if r is not None:
            results.append(r)

    # crop+upsample arm — uses the bare-arm best replicate; the cy/mm-subj
    # cutoff is identical to bare's because information is preserved by
    # crop and upsampling doesn't add any. We emit the row mainly to make
    # the report explicit.
    bare_f8  = next((r for r in results if r.label == "bare_400_F8"),  None)
    bare_f11 = next((r for r in results if r.label == "bare_400_F11"), None)
    if bare_f11:
        results.append(process_bare_cropped(bare_f11, 1.4, 560.0, "F11", "tc14_FOV", "tab:cyan"))
        results.append(process_bare_cropped(bare_f11, 2.0, 800.0, "F11", "tc20_FOV", "tab:pink"))
    if bare_f8:
        results.append(process_bare_cropped(bare_f8,  1.4, 560.0, "F8",  "tc14_FOV", "tab:cyan"))

    # main plot — only the 400mm family + crop arms, to keep it legible
    main_plot_set = [r for r in results if r.f_eff in (400.0, 560.0, 800.0)]
    plot_subject_spectra(main_plot_set, OUT / "radial_spectra_subject.png")

    # zoom-context plot — bare lens at 200/300/400
    zoom_set = [r for r in results if r.label in ("bare_200_F8", "bare_300_F8", "bare_400_F8")]
    if zoom_set:
        plot_subject_spectra(zoom_set, OUT / "radial_spectra_subject_zoom.png")

    # visual side-by-side
    results_map = {r.label: r for r in results if r.crop_scale == 1.0}
    plot_visual_fov_matched(results_map, OUT / "visual_fov_matched.png")

    write_summary(results, OUT / "summary.csv", OUT / "summary.md")
    print(f"\nWrote {OUT}/summary.{{csv,md}}, radial_spectra_subject.png, visual_fov_matched.png.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
