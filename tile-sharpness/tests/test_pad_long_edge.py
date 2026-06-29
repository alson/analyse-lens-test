"""Tests for the 2B bright-pad long-edge geometry (pad_long_edge).

These exercise the pure-geometry pad finder, the long-edge sub-pixel refinement,
and the isolation/specular gate on SYNTHETIC images with known geometry — so the
gate's behaviour (the load-bearing piece of the 2B negative result) is pinned.
"""
from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from tile_sharpness.methods import pad_long_edge as ple
from tile_sharpness.methods.lsf import Segment


def _tilted_pad(H=320, W=420, pad_top=130, pad_h=110, tilt_deg=5.0,
                bright=180, dark=40, x_margin=70):
    """A single bright pad on a dark field, long horizontal edges tilted by
    ``tilt_deg`` (the ~5deg wafer grid tilt). Clean open dark field above/below AND
    horizontal margins so the pad does not touch the block boundary (the finder
    rejects boundary-hugging components as off-wafer/cut-off)."""
    img = np.full((H, W), dark, np.float32)
    slope = np.tan(np.radians(tilt_deg))
    xs = np.arange(W)
    top = pad_top + slope * (xs - W / 2)
    bot = top + pad_h
    yy = np.arange(H)[:, None]
    in_x = (xs >= x_margin) & (xs <= W - x_margin)
    mask = (yy >= top[None, :]) & (yy <= bot[None, :]) & in_x[None, :]
    img[mask] = bright
    rng = np.random.default_rng(0)
    img = img + rng.normal(0, 2.0, img.shape).astype(np.float32)   # realistic texture
    img = cv2.GaussianBlur(img, (0, 0), 1.2)        # finite PSF
    return np.clip(img, 0, 255).astype(np.float32)


def test_find_bright_pad_locates_uniform_rect():
    img = _tilted_pad()
    pads = ple.find_bright_pad(img, (0, 0, img.shape[1], img.shape[0]))
    assert pads, "should find the bright pad"
    x0, y0, x1, y1 = pads[0]
    # the uniform-std finder returns the pad CORE (morphology shrinks the full
    # extent); it should be a chunky rectangle centred in the band, not a speck.
    assert (x1 - x0) > 60 and (y1 - y0) > 40
    assert 100 < (y0 + y1) / 2 < 260


def test_refine_pad_hedge_recovers_tilt():
    img = _tilted_pad(tilt_deg=5.0)
    pads = ple.find_bright_pad(img, (0, 0, img.shape[1], img.shape[0]))
    res = ple.refine_pad_hedge(img, pads[0], side="top")
    assert res is not None
    seg, off = res
    assert abs(off - 5.0) < 1.5, f"recovered tilt {off:.2f} != ~5deg"
    assert seg.length_px > 60


def test_isolation_gate_passes_clean_isolated_edge():
    """A pad with wide clean open field on both sides -> large open clearance, no
    specular rim. This is the 'good target' the metric WANTS."""
    img = _tilted_pad(pad_top=140, pad_h=110)
    pads = ple.find_bright_pad(img, (0, 0, img.shape[1], img.shape[0]))
    seg, off = ple.refine_pad_hedge(img, pads[0], side="top")
    pad_clear, open_clear, spec = ple.isolation_clearance(img, seg, pads[0], "top")
    assert open_clear > 24, f"clean open field should give large clearance, got {open_clear}"
    assert not spec, "a clean step has no specular rim"


def test_isolation_gate_flags_specular_rim():
    """Inject a bright rim right at the open side of the edge (a metal-bevel glint,
    the 2B failure mode) and confirm the gate flags it."""
    clean = _tilted_pad(tilt_deg=5.0, pad_top=130)
    pads = ple.find_bright_pad(clean, (0, 0, clean.shape[1], clean.shape[0]))
    seg, off = ple.refine_pad_hedge(clean, pads[0], side="top")
    img = clean.copy()
    slope = np.tan(np.radians(5.0)); W = img.shape[1]
    # paint a bright rim a few px ABOVE the top edge (the open/dark side), with a
    # dark gap between rim and pad — a metal-bevel glint (the 2B failure mode).
    for x in range(70, W - 70):
        ytop = int(130 + slope * (x - W / 2))
        img[max(0, ytop - 8):ytop - 5, x] = 200
    img = cv2.GaussianBlur(img, (0, 0), 0.8)
    _, _, spec = ple.isolation_clearance(img, seg, pads[0], "top")
    assert spec, "a bright rim at the edge must set the specular flag"


def test_isolation_gate_flags_nearby_structure():
    """A competing bright trace close above the open side -> small open clearance.
    Find the edge on the clean pad, THEN add the trace and re-probe the same seg."""
    clean = _tilted_pad(tilt_deg=5.0, pad_top=130)
    pads = ple.find_bright_pad(clean, (0, 0, clean.shape[1], clean.shape[0]))
    seg, off = ple.refine_pad_hedge(clean, pads[0], side="top")
    img = clean.copy()
    slope = np.tan(np.radians(5.0)); W = img.shape[1]
    for x in range(70, W - 70):                    # parallel trace ~18px above edge
        ytop = int(130 + slope * (x - W / 2))
        img[ytop - 20:ytop - 16, x] = 180
    img = cv2.GaussianBlur(img, (0, 0), 1.0)
    _, open_clear, _ = ple.isolation_clearance(img, seg, pads[0], "top")
    assert open_clear < 24, f"nearby trace should cap open clearance, got {open_clear}"
