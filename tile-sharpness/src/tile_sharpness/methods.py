"""Per-method sharpness scorers.

Each scorer returns ``float | None`` for one tile JPEG path. ``None``
means the algorithm couldn't score this tile (too few edges, fit
failed, etc.); callers treat it as "no opinion" and skip it from the
peak/argmax aggregation.

The ``MethodSpec`` registry records each method's orientation —
``"higher_is_sharper"`` or ``"lower_is_sharper"`` — so the aggregation
step can pick the right argmax direction without per-method branches.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pywt
from PIL import Image
from scipy.fft import dctn
from scipy.ndimage import laplace, sobel
from scipy.stats import kurtosis
from skimage.feature import canny


Scorer = Callable[[Path], float | None]


@dataclass(frozen=True)
class MethodSpec:
    key: str
    label: str
    scorer: Scorer
    orientation: str  # "higher_is_sharper" or "lower_is_sharper"

    def is_sharper(self, a: float, b: float) -> bool:
        return a > b if self.orientation == "higher_is_sharper" else a < b


# --------------------------------------------------------------------------
# Method 0 — JPEG byte size (existing proxy, kept for comparison)
# --------------------------------------------------------------------------

def score_filesize(tile_path: Path) -> float | None:
    try:
        return float(tile_path.stat().st_size)
    except OSError:
        return None


# --------------------------------------------------------------------------
# Method 1 — Slanted-edge MTF via mtf_mapper running on nufan over SSH
#
# The local Arch host has libopencv 4.13; the locally-built mtf_mapper
# was linked against 4.10 and is no longer runnable here. Nufan
# (Ubuntu 25.10) has 4.10 and we built mtf_mapper there in-tree. The
# binary path is identical on both hosts because the workspace lives
# on the shared mount. Tile JPEGs are also on the shared mount (see
# crop.DEFAULT_CACHE_ROOT) so no data shuttling is needed.
#
# Wafer tiles don't contain isolated chart-style "black objects"
# against a bright background, so mtf_mapper's default
# component-finding step fails ("No black objects found"). We pass
# ``--single-roi`` to make it treat the whole tile as one ROI and
# extract the dominant slanted-edge SFR. Output format (one line per
# edge, whitespace separated):
# ``<group_id> <x> <y> <mtf50_cy_per_px> <px> <py>``. ``--single-roi``
# emits one real edge and three saturated ``1.000000`` markers per
# tile; we drop those and use the single valid MTF50.
# --------------------------------------------------------------------------

MTF_MAPPER_HOST = "nufan"
MTF_MAPPER_BIN_PATH = (
    "/home/alson/shared/projects/personal/fotografie/"
    "MTF mapper/workspace/mtfmapper/bin/mtf_mapper"
)
MTF_MAPPER_REMOTE_TMP = "/tmp/tile-sharpness-mtfm"

# ControlMaster keeps one SSH connection alive across calls, turning
# subsequent invocations into channel-multiplexed calls (no fresh TCP
# handshake / no fresh auth). Without this, every per-tile call pays
# ~500 ms of SSH startup. With it, steady-state cost drops to the
# mtf_mapper compute time + a few ms of channel demux.
_SSH_OPTS = [
    "-o", "ControlMaster=auto",
    "-o", f"ControlPath=/tmp/tile-sharpness-ssh-%r@%h:%p",
    "-o", "ControlPersist=120s",
    "-o", "BatchMode=yes",
]


def _parse_edge_mtf_values(text: str) -> list[float]:
    """Parse mtf_mapper's ``edge_mtf_values.txt`` text.

    Each non-empty, non-comment line is
    ``<group_id> <x> <y> <mtf50> <px> <py>``. We return the MTF50
    column; saturated 1.0 markers (edges where mtf_mapper couldn't
    resolve a finite cutoff) are dropped because they distort the
    median upward.
    """
    values: list[float] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            mtf50 = float(parts[3])
        except ValueError:
            continue
        if not (0.0 < mtf50 < 1.0):
            continue
        values.append(mtf50)
    return values


def score_mtfmapper(tile_path: Path) -> float | None:
    """Run mtf_mapper on ``tile_path`` over SSH to nufan."""
    # One remote tmpdir per call so concurrent worker threads can't
    # collide on the same edge_mtf_values.txt.
    remote_cmd = (
        f"mkdir -p {MTF_MAPPER_REMOTE_TMP} && "
        f"d=$(mktemp -d -p {MTF_MAPPER_REMOTE_TMP}) && "
        f'"{MTF_MAPPER_BIN_PATH}" -q --single-roi "{tile_path}" "$d" '
        f">/dev/null 2>&1 && "
        f'cat "$d/edge_mtf_values.txt" 2>/dev/null; '
        f'rm -rf "$d"'
    )
    try:
        proc = subprocess.run(
            ["ssh", *_SSH_OPTS, MTF_MAPPER_HOST, remote_cmd],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    values = _parse_edge_mtf_values(proc.stdout)
    if not values:
        return None
    return float(np.median(values))


# --------------------------------------------------------------------------
# Method 2 — Radial power-spectrum high-band ratio
#
# The original SHARPNESS_METRICS.md §2 proposed a parametric
# ``P(f) = A · f^(-α) · |MTF(f)|² + N₀`` fit. In practice on the wafer
# JPEGs the four-parameter fit is unstable: σ saturates at the
# physical lower bound (~Nyquist) on most in-focus tiles, leaving the
# fitted MTF50 identical across the frame and unable to discriminate
# between tiles. We fall back to a simpler high-band-vs-low-band
# energy ratio on the same radial spectrum, which is robust, has no
# free parameters, and tracks the same essential signal: how much
# detail survives near Nyquist relative to the scene's mid-frequency
# content.
#
# Returns ``E_high / E_low`` where the integration bands are
# ``[0.10, 0.20]`` and ``[0.30, 0.45]`` cycles/pixel respectively.
# Higher = sharper. This is a relative metric, not absolute MTF50.
# --------------------------------------------------------------------------

def _radial_average(power: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Average ``power`` over annuli centred on the DC component.

    Returns ``(freqs, P)`` where ``freqs`` are the bin centres in
    cycles/pixel (``0 ≤ f ≤ 0.5`` for Nyquist-limited inputs).
    """
    h, w = power.shape
    cy, cx = h // 2, w // 2
    y, x = np.indices((h, w))
    r = np.hypot(x - cx, y - cy).astype(int)
    r_max = min(cy, cx)
    radial_sum = np.bincount(r.ravel(), weights=power.ravel())
    counts = np.bincount(r.ravel())
    counts[counts == 0] = 1
    P = (radial_sum / counts)[: r_max + 1]
    freqs = np.arange(P.size) / (2.0 * r_max)
    return freqs, P


LOW_BAND = (0.10, 0.20)
HIGH_BAND = (0.30, 0.45)


def score_radial_fft(tile_path: Path) -> float | None:
    try:
        img = Image.open(tile_path).convert("L")
    except OSError:
        return None
    arr = np.asarray(img, dtype=np.float32)
    arr = arr - arr.mean()
    h, w = arr.shape
    win_y = np.hanning(h)[:, None]
    win_x = np.hanning(w)[None, :]
    arr *= win_y * win_x
    spec = np.fft.fftshift(np.fft.fft2(arr))
    power = np.abs(spec) ** 2
    freqs, P = _radial_average(power)
    if P.size < 10 or not np.all(np.isfinite(P)):
        return None
    lo_mask = (freqs >= LOW_BAND[0]) & (freqs < LOW_BAND[1])
    hi_mask = (freqs >= HIGH_BAND[0]) & (freqs < HIGH_BAND[1])
    if not lo_mask.any() or not hi_mask.any():
        return None
    e_low = float(P[lo_mask].sum())
    e_high = float(P[hi_mask].sum())
    if e_low <= 0:
        return None
    return e_high / e_low


# --------------------------------------------------------------------------
# Method 4 — Marziliano edge width (no-reference, edge-profile decay)
# --------------------------------------------------------------------------

def _marziliano_widths(arr: np.ndarray, edges: np.ndarray) -> list[float]:
    """Per-edge perpendicular widths between bracketing local extrema.

    For each edge pixel we project the local image profile along the
    gradient direction; the edge width is the distance between the
    most-recent local maximum and the next local minimum (or vice
    versa) along that direction.
    """
    gy, gx = np.gradient(arr.astype(np.float32))
    ang = np.arctan2(gy, gx)
    h, w = arr.shape
    widths: list[float] = []

    ys, xs = np.nonzero(edges)
    # Quantise the per-edge direction to the nearest of 4 axes to keep
    # the line walk cheap. Vertical/horizontal/diagonals cover the
    # MTF-relevant orientations.
    for y, x in zip(ys, xs, strict=True):
        a = ang[y, x]
        a4 = (round((a / np.pi) * 4) % 4)
        if a4 == 0:  # horizontal gradient → walk along x
            dx, dy = 1, 0
        elif a4 == 1:  # \ diagonal
            dx, dy = 1, 1
        elif a4 == 2:  # vertical gradient → walk along y
            dx, dy = 0, 1
        else:  # / diagonal
            dx, dy = 1, -1

        def _walk(sign: int) -> int:
            # Walk away from the edge in `sign` (±1) direction until the
            # next local extremum (sign change in the derivative). Cap
            # the search at 12 pixels — past that the edge has clearly
            # decayed and we don't care for ranking purposes.
            prev = arr[y, x]
            slope_sign = 0
            for k in range(1, 13):
                ny = y + sign * dy * k
                nx = x + sign * dx * k
                if ny < 0 or ny >= h or nx < 0 or nx >= w:
                    return k
                cur = arr[ny, nx]
                delta = cur - prev
                if slope_sign != 0 and delta * slope_sign < 0:
                    return k
                if delta != 0:
                    slope_sign = 1 if delta > 0 else -1
                prev = cur
            return 12

        left = _walk(-1)
        right = _walk(+1)
        widths.append(float(left + right))
    return widths


def score_edge_decay(tile_path: Path) -> float | None:
    try:
        img = Image.open(tile_path).convert("L")
    except OSError:
        return None
    arr = np.asarray(img, dtype=np.float32)
    edges = canny(arr / 255.0, sigma=1.0)
    if edges.sum() < 50:
        return None
    # Subsample edges for speed — Marziliano width is a noise-robust
    # median over many edges; 5000 is plenty.
    ys, xs = np.nonzero(edges)
    if ys.size > 5000:
        rng = np.random.default_rng(0)
        idx = rng.choice(ys.size, 5000, replace=False)
        thinned = np.zeros_like(edges)
        thinned[ys[idx], xs[idx]] = True
        edges = thinned
    widths = _marziliano_widths(arr, edges)
    if not widths:
        return None
    return float(np.median(widths))


# --------------------------------------------------------------------------
# Method 5 — Variance of Laplacian (autofocus classic)
#
# Content-dependent — included as a baseline that we expect to fail at
# cross-frame comparison, so we can quantify how much.
# --------------------------------------------------------------------------

def _decode_gray(tile_path: Path) -> np.ndarray | None:
    try:
        img = Image.open(tile_path).convert("L")
    except OSError:
        return None
    return np.asarray(img, dtype=np.float32)


def score_laplacian_var(tile_path: Path) -> float | None:
    arr = _decode_gray(tile_path)
    if arr is None:
        return None
    lap = laplace(arr)
    return float(lap.var())


# --------------------------------------------------------------------------
# Method 6 — Tenengrad (Sobel gradient magnitude sum)
#
# Another autofocus classic. Different bias from Laplacian variance —
# Sobel emphasises step edges, Laplacian emphasises zero-crossings.
# --------------------------------------------------------------------------

def score_tenengrad(tile_path: Path) -> float | None:
    arr = _decode_gray(tile_path)
    if arr is None:
        return None
    gx = sobel(arr, axis=1)
    gy = sobel(arr, axis=0)
    return float(np.mean(gx * gx + gy * gy))


# --------------------------------------------------------------------------
# Method 7 — Local 8×8 DCT AC-coefficient kurtosis (Ferzli-Karam variant)
#
# Approach: for each non-overlapping 8×8 block, compute the 2D DCT and
# the excess kurtosis of the 63 AC coefficients (skip DC). A blurred
# block concentrates energy in a few low-frequency AC coefficients,
# leaving most coefficients near zero — that's a heavy-tailed,
# peaked-at-zero distribution with HIGH kurtosis. A sharp block
# spreads energy across many AC coefficients — broader distribution,
# LOWER kurtosis. Averaged across all blocks. Lower = sharper.
# --------------------------------------------------------------------------

def score_dct_kurtosis(tile_path: Path) -> float | None:
    arr = _decode_gray(tile_path)
    if arr is None:
        return None
    h, w = arr.shape
    bh, bw = h // 8, w // 8
    if bh < 8 or bw < 8:
        return None
    arr = arr[: bh * 8, : bw * 8]
    blocks = (
        arr.reshape(bh, 8, bw, 8)
        .swapaxes(1, 2)
        .reshape(bh * bw, 8, 8)
    )
    dct = dctn(blocks, axes=(1, 2), norm="ortho")
    ac = dct.reshape(bh * bw, 64)[:, 1:]
    k = kurtosis(ac, axis=1, fisher=True, bias=False)
    return float(np.nanmean(k))


# --------------------------------------------------------------------------
# Method 8 — Wavelet detail/approximation energy ratio
#
# 3-level Daubechies-2 wavelet decomposition. Energy in detail
# subbands (LH, HL, HH) at the finest scale, divided by energy in the
# approximation (LL) subband at the coarsest scale. Higher = more
# energy in fine detail = sharper. Content-normalised by the LL term,
# so it's less framing-dependent than raw FFT band ratios.
# Doc §6 calls this "strictly better than raw JPEG file size".
# --------------------------------------------------------------------------

def score_wavelet_ratio(tile_path: Path) -> float | None:
    arr = _decode_gray(tile_path)
    if arr is None:
        return None
    coeffs = pywt.wavedec2(arr, "db2", level=3)
    cA = coeffs[0]
    detail_l1 = coeffs[-1]  # finest level: (LH, HL, HH)
    detail_energy = sum(float(np.sum(d * d)) for d in detail_l1)
    approx_energy = float(np.sum(cA * cA))
    if approx_energy <= 0:
        return None
    return detail_energy / approx_energy


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

METHODS: dict[str, MethodSpec] = {
    "filesize": MethodSpec(
        key="filesize",
        label="JPEG bytes",
        scorer=score_filesize,
        orientation="higher_is_sharper",
    ),
    "mtfmapper": MethodSpec(
        key="mtfmapper",
        label="Slanted-edge MTF50",
        scorer=score_mtfmapper,
        orientation="higher_is_sharper",
    ),
    "radial_fft": MethodSpec(
        key="radial_fft",
        label="High/Low PSD band ratio",
        scorer=score_radial_fft,
        orientation="higher_is_sharper",
    ),
    "edge_decay": MethodSpec(
        key="edge_decay",
        label="Marziliano width",
        scorer=score_edge_decay,
        orientation="lower_is_sharper",
    ),
    "laplacian_var": MethodSpec(
        key="laplacian_var",
        label="Variance of Laplacian",
        scorer=score_laplacian_var,
        orientation="higher_is_sharper",
    ),
    "tenengrad": MethodSpec(
        key="tenengrad",
        label="Tenengrad (Sobel² mean)",
        scorer=score_tenengrad,
        orientation="higher_is_sharper",
    ),
    "dct_kurtosis": MethodSpec(
        key="dct_kurtosis",
        label="Local DCT-AC kurtosis",
        scorer=score_dct_kurtosis,
        orientation="lower_is_sharper",
    ),
    "wavelet_ratio": MethodSpec(
        key="wavelet_ratio",
        label="Wavelet detail/approx",
        scorer=score_wavelet_ratio,
        orientation="higher_is_sharper",
    ),
}


def mtf_mapper_available() -> bool:
    """Probe the SSH path: is mtf_mapper runnable on the remote host?"""
    try:
        proc = subprocess.run(
            ["ssh", *_SSH_OPTS, "-o", "ConnectTimeout=5",
             MTF_MAPPER_HOST, f'test -x "{MTF_MAPPER_BIN_PATH}"'],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0
