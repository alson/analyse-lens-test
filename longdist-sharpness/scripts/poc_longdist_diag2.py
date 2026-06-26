"""Diagnostic v2: radial spectra plotted in subject-frequency space (cy/mm
subject), where higher = finer real-world detail resolved. Picks the
sharpest center tile per config (matches user's manual method).
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

DATA_ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-28")
OUT = Path(__file__).parent / "poc_longdist_100_400_tc_2026_01_28_out"
OUT.mkdir(exist_ok=True)

TILE = 256
Z7_PIXEL_PITCH_MM = 4.35e-3
FOCUS_DISTANCE_MM = 84_000.0


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


def best_center_tile(luma: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
    h, w = luma.shape
    cy, cx = h // 2, w // 2
    box = luma[cy - 750 : cy + 750, cx - 750 : cx + 750]
    best = None
    best_pos = (0, 0)
    best_score = -1
    for y in range(0, box.shape[0] - TILE + 1, 64):
        for x in range(0, box.shape[1] - TILE + 1, 64):
            t = box[y : y + TILE, x : x + TILE]
            gy = np.diff(t, axis=0)
            gx = np.diff(t, axis=1)
            score = (gy * gy).mean() + (gx * gx).mean()
            if score > best_score:
                best_score = score
                best = t
                best_pos = (y, x)
    return best, best_pos


def best_replicate(d: Path) -> tuple[Path, np.ndarray, tuple[int, int]]:
    best_p, best_t, best_pos, best_score = None, None, None, -1
    for jp in sorted(d.glob("*.jpg")):
        luma = load_luma(jp)
        t, pos = best_center_tile(luma)
        gy = np.diff(t, axis=0); gx = np.diff(t, axis=1)
        s = (gy * gy).mean() + (gx * gx).mean()
        if s > best_score:
            best_score, best_p, best_t, best_pos = s, jp, t, pos
    return best_p, best_t, best_pos


# (label, rel-path, f_eff_mm, colour)
CONFIGS = [
    ("bare 400  F8 (M=0.00476)",  "NIKKOR Z 100-400mm f_4.5-5.6 VR S/400.0 mm/F8", 400.0, "tab:blue"),
    ("bare 400  F11 (M=0.00476)", "NIKKOR Z 100-400mm f_4.5-5.6 VR S/400.0 mm/F11",400.0, "tab:orange"),
    ("+TC14 400 F8 (eff=560, M=0.00667)",  "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x/400.0 mm/F8",560.0, "tab:green"),
    ("+TC14 400 F11 (eff=560, M=0.00667)", "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x/400.0 mm/F11",560.0, "tab:red"),
    ("+TC20 400 F11 (eff=800, M=0.00952)", "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-2.0x/400.0 mm/F11",800.0, "tab:purple"),
]


fig, axes = plt.subplots(1, 2, figsize=(15, 6))
ax_sensor, ax_subject = axes

# Collect data
data = {}
for label, rel, f_eff, colour in CONFIGS:
    d = DATA_ROOT / rel
    p, tile, pos = best_replicate(d)
    spec = radial_spectrum(tile)
    M = f_eff / FOCUS_DISTANCE_MM
    sensor_cy_per_px = np.arange(TILE // 2 + 1) / TILE
    sensor_cy_per_mm = sensor_cy_per_px / Z7_PIXEL_PITCH_MM
    subject_cy_per_mm = sensor_cy_per_mm * M
    data[label] = (sensor_cy_per_px, subject_cy_per_mm, spec, colour, p.name)

# Normalize each spectrum so the integrals up to a common subject-freq match,
# i.e., remove tile-amplitude / scene-texture differences. Pick a low subject
# frequency band (say up to 1 cy/mm-subject) as the reference: that's domain
# the *scene* contributes equally to (the lens is essentially flat MTF there).

REF_SUBJ = 0.2  # cy/mm subject -- low-freq band assumed scene-dominated, lens-MTF~1

# Find normalization factor for each curve
for label, (s_px, s_subj, spec, colour, fname) in data.items():
    # integrate power up to REF_SUBJ in subject-freq
    mask = (s_subj >= 0.01) & (s_subj <= REF_SUBJ)
    if mask.sum() == 0:
        norm = 1.0
    else:
        norm = spec[mask].sum()
    spec_n = spec / max(norm, 1e-12)
    ax_sensor.loglog(s_px[1:], spec_n[1:], label=label, color=colour)
    ax_subject.loglog(s_subj[1:], spec_n[1:], label=label, color=colour)

# Diffraction limits at the *effective* aperture, for reference
# f_cutoff_subject_cy_per_mm = M / (lambda * N_eff)  (incoherent cutoff at the subject)
# Use lambda = 550 nm = 550e-6 mm.
LAMBDA_MM = 550e-6
for f_eff_mm, N_eff, colour, style in [
    (400.0, 8, "tab:blue", ":"),
    (400.0, 11, "tab:orange", ":"),
    (560.0, 8, "tab:green", ":"),
    (560.0, 11, "tab:red", ":"),
    (800.0, 11, "tab:purple", ":"),
]:
    M = f_eff_mm / FOCUS_DISTANCE_MM
    f_subj_cutoff = M / (LAMBDA_MM * N_eff)
    ax_subject.axvline(f_subj_cutoff, color=colour, ls=style, alpha=0.4)

ax_sensor.set_xlabel("sensor frequency (cy / sensor-pixel)")
ax_sensor.set_ylabel("radial power (normalised at f_subj=0..0.2 cy/mm)")
ax_sensor.set_title("Radial power spectrum vs sensor frequency\n(sharpest center tile per config)")
ax_sensor.grid(True, alpha=0.3, which="both")
ax_sensor.legend(fontsize=8, loc="lower left")

ax_subject.set_xlabel("subject frequency (cy / mm subject)")
ax_subject.set_ylabel("radial power (normalised at low subject freq)")
ax_subject.set_title("Same spectra in SUBJECT space\n(dotted lines = diffraction cutoff at each (f_eff, N_eff))")
ax_subject.grid(True, alpha=0.3, which="both")
ax_subject.legend(fontsize=8, loc="lower left")

fig.tight_layout()
out_path = OUT / "diag_radial_spectra_subject.png"
fig.savefig(out_path, dpi=120)
print(f"wrote {out_path}")

# Compute MTF50-equivalent: find subject-frequency where power drops to
# 0.25 (= 0.5^2 of the low-freq normalised peak, mapping to "MTF=0.5" if
# the natural-scene spectrum were flat -- a rough proxy).
print(f"\nSubject-space cutoff (drops to 0.05 of low-f norm):")
for label, (s_px, s_subj, spec, colour, fname) in data.items():
    mask = (s_subj >= 0.01) & (s_subj <= 0.2)
    norm = spec[mask].sum() / max(mask.sum(), 1)  # mean power in ref band
    spec_n = spec / max(norm, 1e-12)
    # find first idx where it drops below 0.05
    below = np.where(spec_n[1:] < 0.05)[0]
    if len(below) == 0:
        cutoff = float("nan")
    else:
        cutoff = s_subj[1:][below[0]]
    print(f"  {label:42s}  cutoff @ 0.05 = {cutoff:.2f} cy/mm-subject   best={fname}")
