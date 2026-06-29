import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from tile_sharpness.methods.lsf import (
    Segment,
    cross_section,
    detect_scribe,
    detect_scribe_hough,
    lsf_mtf50,
    lsf_peak_amp,
)


def _make_scribe_image(
    size: int = 512, scribe_sigma: float = 1.0, scribe_depth: float = 80.0,
    angle_deg: float = 4.5, scribe_width_px: float = 3.0,
) -> np.ndarray:
    """Build a synthetic ROI: bright background with one dark slanted line."""
    rng = np.random.default_rng(0)
    img = np.full((size, size), 200.0, dtype=np.float64)
    # Add a slanted dark line through the centre.
    yy, xx = np.indices(img.shape)
    cx, cy = size // 2, size // 2
    a = np.deg2rad(angle_deg)
    # Perpendicular distance to a line through (cx, cy) with direction (cos a, sin a).
    perp = (xx - cx) * np.sin(a) - (yy - cy) * np.cos(a)
    profile = np.exp(-0.5 * (perp / scribe_width_px) ** 2)
    img -= scribe_depth * profile
    # Apply optical blur (LSF width to be measured).
    img = gaussian_filter(img, sigma=scribe_sigma)
    img += rng.normal(0, 1.0, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def test_detect_scribe_finds_dark_line():
    img = _make_scribe_image(size=512, scribe_sigma=1.0, angle_deg=4.5)
    seg = detect_scribe(img, min_length_ratio=0.5, min_length_px=100)
    assert seg is not None
    # Length should span most of the ROI.
    assert seg.length_px > 0.6 * 512
    # Angle should be near ±4.5° (LSD may flip endpoints; compare against |sin|).
    angle = abs(seg.angle_rad) * 180 / np.pi
    angle = min(angle, 180 - angle)
    assert angle < 12.0  # within 12° of horizontal


def test_detect_scribe_returns_none_on_blank():
    img = np.full((512, 512), 200, dtype=np.uint8)
    rng = np.random.default_rng(0)
    img = (img + rng.normal(0, 1.0, img.shape)).clip(0, 255).astype(np.uint8)
    seg = detect_scribe(img, min_length_ratio=0.5, min_length_px=100)
    assert seg is None


def test_cross_section_recovers_lsf_width():
    # Sharp scribe (sigma=1.0) → narrow cross-section
    sharp = _make_scribe_image(scribe_sigma=1.0)
    seg_sharp = detect_scribe(sharp, min_length_ratio=0.5, min_length_px=100)
    assert seg_sharp is not None
    profile_sharp = cross_section(sharp, seg_sharp, half_window_px=16)
    # Profile minimum at centre, recovers toward edges
    centre_idx = profile_sharp.size // 2
    assert profile_sharp[centre_idx] < profile_sharp[0] - 10
    assert profile_sharp[centre_idx] < profile_sharp[-1] - 10


def test_lsf_peak_amp_handles_zero_profile():
    assert lsf_peak_amp(np.zeros(49)) == 0.0


def test_lsf_mtf50_handles_zero_profile():
    assert lsf_mtf50(np.zeros(49)) is None


# -------------------------------------------------------------------------
# Real-fixture tests for the ESF→LSF MTF50 path.
#
# Synthetic Gaussian-line scribes are a poor model for the wafer scribe
# geometry (no flat trough bottom, no well-defined edges), so they don't
# discriminate sharp vs blurred under the per-edge ESF→LSF method. The
# fixtures are 49-sample cross-section profiles extracted from real LSF
# ROIs of the wafer dataset (2026-01-29 sweeps), pre-computed via the
# production scribe-detect → cross_section path. Saving the profile not
# the source JPEG keeps fixtures small (~400 B each) and avoids
# re-exercising scribe detection in unit tests.
# -------------------------------------------------------------------------

import pathlib
_FIXTURE_DIR = pathlib.Path(__file__).parent / "data"


def _load_profile(name: str) -> np.ndarray:
    return np.load(_FIXTURE_DIR / f"{name}.npy")


def test_sharp_profile_has_higher_lsf_mtf50_than_soft_AF200():
    """AF 200/4D 1:1 F11 centre: maze-argmax shot vs defocused-edge shot."""
    sharp = _load_profile("AF200_F11_centre_sharp")
    soft = _load_profile("AF200_F11_centre_soft")
    mtf_sharp = lsf_mtf50(sharp)
    mtf_soft = lsf_mtf50(soft)
    assert mtf_sharp is not None
    assert mtf_soft is not None
    assert mtf_sharp > mtf_soft
    # Sanity: sharp shot should give ~30-60 lp/mm subject on Z7 at M=1.0
    # (0.13 - 0.26 cy/px). Soft shot well below that.
    assert 0.10 < mtf_sharp < 0.40
    assert mtf_soft < 0.20


def test_sharp_profile_has_higher_lsf_mtf50_than_soft_AIS():
    """AIS 287318 1:1 F8 centre: FFT-pick shot vs defocused-edge shot."""
    sharp = _load_profile("AIS287318_F8_centre_sharp")
    soft = _load_profile("AIS287318_F8_centre_soft")
    mtf_sharp = lsf_mtf50(sharp)
    mtf_soft = lsf_mtf50(soft)
    assert mtf_sharp is not None
    assert mtf_soft is not None
    assert mtf_sharp > mtf_soft


def test_sharp_profile_has_higher_lsf_peak_amp_than_soft_AF200():
    sharp = _load_profile("AF200_F11_centre_sharp")
    soft = _load_profile("AF200_F11_centre_soft")
    amp_sharp = lsf_peak_amp(sharp)
    amp_soft = lsf_peak_amp(soft)
    # Empirically ~4-5× ratio on this fixture pair.
    assert amp_sharp > 2 * amp_soft


def test_lsf_mtf50_per_edge_averaging_not_dominated_by_either_side():
    """Sanity: the averaged MTF50 sits between the per-edge MTF50 values."""
    from tile_sharpness.methods.lsf import _split_to_edge_lsfs, _mtf50_from_lsf
    sharp = _load_profile("AF200_F11_centre_sharp")
    pair = _split_to_edge_lsfs(sharp)
    assert pair is not None
    mtf_left = _mtf50_from_lsf(pair[0])
    mtf_right = _mtf50_from_lsf(pair[1])
    mtf_avg = lsf_mtf50(sharp)
    assert mtf_left is not None and mtf_right is not None and mtf_avg is not None
    # Average should be exactly the arithmetic mean of L and R.
    assert abs(mtf_avg - (mtf_left + mtf_right) / 2) < 1e-9


def test_lsf_mtf50_combine_min_takes_lower_edge():
    """combine='min' returns the lower per-edge MTF50 (the conservative, more
    physical edge) — the 2026-06-28 over-read mitigation. Must equal min(L,R),
    be <= the mean, and preserve sharp>soft ordering."""
    from tile_sharpness.methods.lsf import _split_to_edge_lsfs, _mtf50_from_lsf
    sharp = _load_profile("AF200_F11_centre_sharp")
    soft = _load_profile("AF200_F11_centre_soft")
    pair = _split_to_edge_lsfs(sharp)
    edges = [_mtf50_from_lsf(p) for p in pair]
    m_min = lsf_mtf50(sharp, combine="min")
    m_mean = lsf_mtf50(sharp)
    assert abs(m_min - min(edges)) < 1e-9
    assert m_min <= m_mean + 1e-9
    assert lsf_mtf50(sharp, combine="min") > lsf_mtf50(soft, combine="min")


def test_lsf_mtf50_rejects_off_centre_trough():
    """If the trough centre is too close to the window edge, return None."""
    # Build a profile whose minimum is in the first few samples (degenerate).
    profile = np.linspace(120.0, 200.0, 49)  # monotonic — argmin at idx 0
    assert lsf_mtf50(profile) is None
    assert lsf_peak_amp(profile) == 0.0


def _make_fragmented_scribe_image(
    size: int = 1024, n_fragments: int = 6, gap_px: int = 25,
    scribe_sigma: float = 1.2, scribe_depth: float = 80.0,
    scribe_width_px: float = 2.0, angle_deg: float = 4.5,
) -> np.ndarray:
    """A slanted dark line broken into ``n_fragments`` collinear pieces.

    Simulates the wafer-scribe behaviour where LSD finds short
    fragments but the underlying scribe spans the whole ROI.
    """
    rng = np.random.default_rng(1)
    img = np.full((size, size), 200.0, dtype=np.float64)
    yy, xx = np.indices(img.shape)
    cx, cy = size // 2, size // 2
    a = np.deg2rad(angle_deg)
    perp = (xx - cx) * np.sin(a) - (yy - cy) * np.cos(a)
    para = (xx - cx) * np.cos(a) + (yy - cy) * np.sin(a)

    # Build a mask that turns the dark band ON only inside fragment ranges.
    span = size  # ±size/2 along the line, enough to cover the rotated diagonal
    fragment_len = span // (n_fragments * 2)
    on = np.zeros_like(img, dtype=bool)
    start = -span // 2
    for k in range(n_fragments):
        end = start + fragment_len
        on |= (para >= start) & (para <= end)
        start = end + gap_px

    profile = np.exp(-0.5 * (perp / scribe_width_px) ** 2)
    img[on] -= scribe_depth * profile[on]
    from scipy.ndimage import gaussian_filter
    img = gaussian_filter(img, sigma=scribe_sigma)
    img += rng.normal(0, 1.0, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


# The Hough defaults (threshold=150, hough_min_length=250) are tuned for
# wafer ROIs that have hundreds of thousands of Canny edges from the maze
# pattern. Synthetic ROIs with only a single scribe yield <2k edges and
# need looser parameters. The tests below pass relaxed thresholds so they
# verify the algorithmic behaviour without baking in the wafer-specific
# defaults.
_HOUGH_TEST_KWARGS = dict(
    hough_threshold=50, hough_min_length=80, hough_max_gap=15,
    min_spanned_length_px=300,
)


def test_hough_fallback_recovers_fragmented_scribe():
    """LSD finds short fragments; Hough fallback spans the whole ROI."""
    img = _make_fragmented_scribe_image(size=1024, n_fragments=6)
    # Force the LSD-only path to use a tight length cutoff so it fails.
    seg_lsd_only = detect_scribe(
        img, min_length_ratio=0.6, min_length_px=600, hough_fallback=False,
    )
    assert seg_lsd_only is None, "LSD shouldn't span the fragments alone"

    seg = detect_scribe_hough(img, **_HOUGH_TEST_KWARGS)
    assert seg is not None
    # Span should be longer than any single fragment (~85 px each here).
    assert seg.length_px > 300


def test_hough_directly_on_fragmented_scribe():
    img = _make_fragmented_scribe_image(size=1024, n_fragments=6)
    seg = detect_scribe_hough(img, **_HOUGH_TEST_KWARGS)
    assert seg is not None
    assert seg.length_px > 300
    # Angle near ±4.5°.
    angle = abs(seg.angle_rad) * 180 / np.pi
    angle = min(angle, 180 - angle)
    assert angle < 12.0


def test_hough_returns_none_on_blank():
    rng = np.random.default_rng(0)
    img = (np.full((512, 512), 200.0) + rng.normal(0, 1.0, (512, 512))).clip(0, 255).astype(np.uint8)
    assert detect_scribe_hough(img, **_HOUGH_TEST_KWARGS) is None


def test_hough_rejects_bright_lines():
    """A BRIGHT slanted line (white scratch on dark background) must not match."""
    rng = np.random.default_rng(0)
    img = np.full((512, 512), 50.0, dtype=np.float64)
    yy, xx = np.indices(img.shape)
    a = np.deg2rad(4.5)
    perp = (xx - 256) * np.sin(a) - (yy - 256) * np.cos(a)
    img += 100.0 * np.exp(-0.5 * (perp / 2.0) ** 2)
    img += rng.normal(0, 1.0, img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    assert detect_scribe_hough(img, **_HOUGH_TEST_KWARGS) is None


def test_detect_scribe_disables_hough_when_requested():
    img = _make_fragmented_scribe_image(size=1024, n_fragments=6)
    seg = detect_scribe(
        img, min_length_ratio=0.6, min_length_px=600, hough_fallback=False,
    )
    assert seg is None
