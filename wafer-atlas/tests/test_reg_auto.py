"""Pytest entry point for the autonomous-registration regression.

The heavy, data-coupled logic lives in ``scripts/test_reg_auto.py`` (next to
``reg_auto.py``, which it loads by relative path). This wrapper makes it
discoverable by a bare ``pytest`` (``testpaths = ["tests"]``) — the repo has no
GitHub Actions / remote, so the pytest suite IS the CI — while skipping cleanly
when the NFS sweep data is absent (a data-less checkout still collects green).

Run on nufan (per-host venv, reads the NFS share):

    export UV_PROJECT_ENVIRONMENT="$HOME/.cache/uv-venvs/wafer-atlas"
    uv run --no-sync pytest
"""
from __future__ import annotations

import importlib.util
import os

import pytest

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
# The regression registers real sweeps decoded from the NFS test-raw-data tree.
_DATA_ROOT = "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29"


@pytest.mark.skipif(
    not os.path.isdir(_DATA_ROOT),
    reason=f"NFS sweep data not available at {_DATA_ROOT} — run on nufan",
)
def test_reg_auto_regression():
    """All dev sweeps + the recovered high-M 2:1 configs must register at their
    expected offsets / distortion model / accuracy / sane atlas-M."""
    spec = importlib.util.spec_from_file_location(
        "_reg_auto_regression", os.path.join(_SCRIPTS, "test_reg_auto.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main() == 0
