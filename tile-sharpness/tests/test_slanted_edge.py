"""Tests for the super-resolved slanted-edge MTF50 estimator, covering both the
groove (two-wall) back-compat path and the new single-STEP path used for bond-pad
reflectance edges (REPORT_taskAD §E.4 → pad-edge metric)."""
import numpy as np
import pytest
from scipy.ndimage import gaussian_filter
from scipy.special import erf

from tile_sharpness.methods.lsf import Segment
from tile_sharpness.methods.slanted_edge import (
    mtf50_erf,
    mtf50_step_erf,
    mtf50_step_iso,
    mtf50_auto,
    superres_esf,
    _MTF50_PER_INV_SIGMA,
    _is_trough,
    _trim_to_dominant_step,
    _step_quality_ok,
)

ANGLE_DEG = 5.0
SIZE = 400


def _slanted_step(sigma_blur: float, contrast: float = 120.0, bg: float = 60.0,
                  rising: bool = True, size: int = SIZE, noise: float = 0.6) -> np.ndarray:
    """A single straight metal->substrate STEP edge, slanted ANGLE_DEG off vertical,
    blurred by `sigma_blur` px. Bright on one side, dark on the other."""
    rng = np.random.default_rng(0)
    yy, xx = np.indices((size, size)).astype(np.float64)
    cx = size / 2
    a = np.deg2rad(ANGLE_DEG)
    # signed perpendicular distance to a near-vertical line through cx
    perp = (xx - cx) * np.cos(a) + (yy - size / 2) * np.sin(a)
    step = (perp > 0).astype(np.float64)
    if not rising:
        step = 1.0 - step
    img = bg + contrast * step
    img = gaussian_filter(img, sigma=sigma_blur)
    img += rng.normal(0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.float32)


def _slanted_trough(sigma_blur: float, depth: float = 120.0, bg: float = 200.0,
                    width: float = 3.0, size: int = SIZE, noise: float = 0.6) -> np.ndarray:
    """A dark slanted GROOVE (trough) through the centre — groove back-compat case."""
    rng = np.random.default_rng(1)
    yy, xx = np.indices((size, size)).astype(np.float64)
    cx = size / 2
    a = np.deg2rad(ANGLE_DEG)
    perp = (xx - cx) * np.cos(a) + (yy - size / 2) * np.sin(a)
    img = bg - depth * np.exp(-0.5 * (perp / width) ** 2)
    img = gaussian_filter(img, sigma=sigma_blur)
    img += rng.normal(0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.float32)


def _seg():
    """Segment lying ALONG the synthetic edge. The edge normal is (cos a, sin a)
    (gradient of `perp`), so the edge line runs along (-sin a, cos a) — a
    near-vertical line tilted ANGLE_DEG off the y axis."""
    a = np.deg2rad(ANGLE_DEG)
    cx, cy = SIZE / 2, SIZE / 2
    half = SIZE * 0.4
    ux, uy = -np.sin(a), np.cos(a)            # unit vector along the edge
    return Segment(x0=cx - half * ux, y0=cy - half * uy,
                   x1=cx + half * ux, y1=cy + half * uy)


def test_step_erf_recovers_known_sigma():
    """erf-fit MTF50 of a blurred step matches the Gaussian-equivalent analytic
    value 0.18739/sigma within tolerance."""
    sigma = 2.0
    img = _slanted_step(sigma_blur=sigma)
    m = mtf50_step_erf(img, _seg(), half_window_px=30)
    assert m is not None
    expected = _MTF50_PER_INV_SIGMA / sigma
    assert abs(m - expected) / expected < 0.20


def test_step_erf_sharp_gt_soft():
    sharp = mtf50_step_erf(_slanted_step(1.0), _seg(), half_window_px=30)
    soft = mtf50_step_erf(_slanted_step(3.5), _seg(), half_window_px=30)
    assert sharp is not None and soft is not None
    assert sharp > soft


def test_step_erf_direction_invariant():
    """Rising and falling steps of the same blur read the same MTF50."""
    rising = mtf50_step_erf(_slanted_step(2.0, rising=True), _seg(), half_window_px=30)
    falling = mtf50_step_erf(_slanted_step(2.0, rising=False), _seg(), half_window_px=30)
    assert rising is not None and falling is not None
    assert abs(rising - falling) / rising < 0.10


def test_step_iso_agrees_with_erf():
    img = _slanted_step(2.0)
    e = mtf50_step_erf(img, _seg(), half_window_px=30)
    i = mtf50_step_iso(img, _seg(), half_window_px=30)
    assert e is not None and i is not None
    assert abs(e - i) / e < 0.30


def test_is_trough_discriminates_step_vs_groove():
    seg = _seg()
    step_esf = superres_esf(_slanted_step(2.0), seg, half_window_px=30)
    trough_esf = superres_esf(_slanted_trough(2.0), seg, half_window_px=30)
    assert step_esf is not None and trough_esf is not None
    assert not _is_trough(step_esf[1])
    assert _is_trough(trough_esf[1])


def test_auto_dispatch_step():
    """mtf50_auto on a single step uses the single-erf path and matches it."""
    img = _slanted_step(2.0)
    a = mtf50_auto(img, _seg(), half_window_px=30)
    s = mtf50_step_erf(img, _seg(), half_window_px=30)
    assert a is not None and s is not None
    assert abs(a - s) < 1e-9


def test_auto_dispatch_groove_matches_mtf50_erf():
    """mtf50_auto on a groove falls through to the two-wall path == mtf50_erf."""
    img = _slanted_trough(2.0)
    a = mtf50_auto(img, _seg(), half_window_px=30, combine="min")
    g = mtf50_erf(img, _seg(), half_window_px=30, combine="min")
    assert a is not None and g is not None
    assert abs(a - g) < 1e-9


def test_groove_path_unchanged_backcompat():
    """mtf50_erf still measures a groove (sharp>soft) — back-compat preserved."""
    sharp = mtf50_erf(_slanted_trough(1.0), _seg(), half_window_px=30, combine="min")
    soft = mtf50_erf(_slanted_trough(3.5), _seg(), half_window_px=30, combine="min")
    assert sharp is not None and soft is not None
    assert sharp > soft


def _slanted_ridge(sigma_blur: float, amp: float = 120.0, bg: float = 40.0,
                   width: float = 2.0, size: int = SIZE, noise: float = 0.6) -> np.ndarray:
    """A thin BRIGHT slanted line (rise-then-fall ridge) — the pad-array artefact
    the step-quality gate must reject (it is NOT a single reflectance step)."""
    rng = np.random.default_rng(2)
    yy, xx = np.indices((size, size)).astype(np.float64)
    cx = size / 2
    a = np.deg2rad(ANGLE_DEG)
    perp = (xx - cx) * np.cos(a) + (yy - size / 2) * np.sin(a)
    img = bg + amp * np.exp(-0.5 * (perp / width) ** 2)
    img = gaussian_filter(img, sigma=sigma_blur)
    img += rng.normal(0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.float32)


def test_quality_gate_rejects_bright_ridge():
    """A bright trace ridge (the dominant pad-array artefact) must be rejected by
    the step quality gate -> mtf50_step_erf returns None, not a sigma-floor over-read."""
    img = _slanted_ridge(2.0)
    assert mtf50_step_erf(img, _seg(), half_window_px=30) is None


def test_quality_gate_rejects_low_contrast_noise():
    """A near-flat noisy patch (no real edge) must be rejected."""
    rng = np.random.default_rng(3)
    img = (np.full((SIZE, SIZE), 120.0) + rng.normal(0, 1.5, (SIZE, SIZE))).astype(np.float32)
    assert mtf50_step_erf(img, _seg(), half_window_px=30) is None


def test_quality_gate_accepts_clean_step():
    """A genuine clean step passes the gate and returns a finite MTF50."""
    img = _slanted_step(2.0)
    assert mtf50_step_erf(img, _seg(), half_window_px=30) is not None


def test_step_quality_ok_helper():
    """The gate runs on the FULL super-res window (a ridge looks monotone once
    trimmed, so the rise-then-fall is only visible before trimming)."""
    seg = _seg()
    sc, se = superres_esf(_slanted_step(2.0), seg, half_window_px=30)
    rc, re_ = superres_esf(_slanted_ridge(2.0), seg, half_window_px=30)
    assert _step_quality_ok(sc, se)
    assert not _step_quality_ok(rc, re_)


def test_trim_drops_second_step():
    """A window holding two steps (small pad next to a neighbour) is trimmed to the
    dominant one, so the fit isn't biased by the second transition."""
    # build an ESF: flat, big rising step, flat, small step
    d = np.linspace(-30, 30, 240)
    esf = 60 + 120 * (0.5 * (1 + erf((d - (-5)) / (1.5 * np.sqrt(2)))))
    esf += 20 * (0.5 * (1 + erf((d - 18) / (1.5 * np.sqrt(2)))))  # second smaller step
    c2, e2 = _trim_to_dominant_step(d, esf)
    # trimmed window should exclude the far second step location (d~18)
    assert c2.max() < 16


# --- re-centred long-edge path (longedge task) -----------------------------

from tile_sharpness.methods.slanted_edge import (   # noqa: E402
    mtf50_long_edge,
    superres_esf_recentred,
)


def _wavy_step(sigma_blur: float, amp: float = 3.0, contrast: float = 120.0,
               bg: float = 60.0, size: int = SIZE, noise: float = 0.6) -> np.ndarray:
    """A NON-straight near-vertical step whose centre BOWS smoothly by +-amp px
    across the image (a low-order curve a robust polynomial can track) — the
    wafer-bar failure mode that makes a fixed-line ESF softer the longer the edge,
    but which re-centring removes."""
    rng = np.random.default_rng(2)
    yy, xx = np.indices((size, size)).astype(np.float64)
    cx = size / 2
    s = (yy - size / 2) / (size / 2)          # -1..1
    edge_x = cx + amp * (s ** 2 - 0.5) + 0.6 * amp * s   # smooth quadratic+linear bow
    img = bg + contrast * (xx > edge_x).astype(np.float64)
    img = gaussian_filter(img, sigma=sigma_blur)
    img += rng.normal(0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.float32)


def _vert_seg(size: int = SIZE):
    """A straight near-vertical seed segment down the image centre."""
    return Segment(x0=size / 2, y0=size * 0.1, x1=size / 2, y1=size * 0.9)


def test_recentred_recovers_known_sigma():
    """On a clean straight slanted step the recentred ESF recovers MTF50=0.187/sigma."""
    sigma = 2.0
    m = mtf50_long_edge(_slanted_step(sigma), _seg(), half_window_px=16)
    assert m is not None
    assert m == pytest.approx(_MTF50_PER_INV_SIGMA / sigma, rel=0.18)


def test_recentred_sharp_gt_soft():
    sharp = mtf50_long_edge(_slanted_step(1.0), _seg(), half_window_px=16)
    soft = mtf50_long_edge(_slanted_step(3.5), _seg(), half_window_px=16)
    assert sharp is not None and soft is not None
    assert sharp > soft


def test_recentred_length_invariant_on_wavy_edge():
    """The core longedge finding: on a non-straight edge the recentred MTF50 stays
    ~constant with edge length, whereas a fixed-line ESF softens. Here we check the
    recentred reading at a short vs long sub-segment agrees within tolerance and
    stays near the true 0.187/sigma."""
    from tile_sharpness.methods.long_edge import subsegment
    img = _wavy_step(sigma_blur=2.0)
    seg = _vert_seg()
    short = mtf50_long_edge(img, subsegment(seg, 60), half_window_px=16)
    long = mtf50_long_edge(img, subsegment(seg, 300), half_window_px=16)
    assert short is not None and long is not None
    true = _MTF50_PER_INV_SIGMA / 2.0
    # both near truth (a fixed-line ESF would read the long one far softer)
    assert short == pytest.approx(true, rel=0.30)
    assert long == pytest.approx(true, rel=0.30)
    assert abs(short - long) < 0.4 * true


def test_recentred_beats_fixedline_on_wavy_long_edge():
    """Re-centring never reads the wandering long edge SOFTER than the fixed-line
    ESF (it removes, not adds, edge-position smear) and stays near the true MTF50.
    On real wafer bars the per-row scatter is jagged (~±4 px) and the gap is large;
    here a smooth synthetic bow gives a modest but correctly-signed gap."""
    img = _wavy_step(sigma_blur=2.0)
    seg = _vert_seg()
    true = _MTF50_PER_INV_SIGMA / 2.0
    rc = mtf50_long_edge(img, seg, half_window_px=16)
    fl = mtf50_step_erf(img, seg, half_window_px=16)
    assert rc is not None
    assert rc == pytest.approx(true, rel=0.30)
    # re-centring is never softer than the fixed-line read on a non-straight edge
    assert (fl is None) or (rc >= fl * 0.98)


def test_recentred_low_contrast_returns_none():
    flat = np.full((SIZE, SIZE), 60.0, np.float32)
    flat += np.random.default_rng(3).normal(0, 0.6, flat.shape)
    assert mtf50_long_edge(flat, _vert_seg(), half_window_px=16) is None
