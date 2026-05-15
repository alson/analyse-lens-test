"""Tile-grid sharpness POC.

Validates three candidate sharpness metrics (slanted-edge MTF, radial
FFT fit, edge-profile decay) against the legacy JPEG-size proxy by
analysing focus sweeps tile-by-tile and comparing cross-method
agreement on peak metric and focus-plane argmax. See the project
README and the parent ``SHARPNESS_METRICS.md`` for context.
"""

__all__ = []
