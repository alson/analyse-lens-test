from __future__ import annotations

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend; no Tk/Qt needed
import matplotlib.pyplot as plt  # noqa: E402

from rail_coverage.detect import smooth_sizes  # noqa: E402


def make_chart_png(
    sizes: list[int],
    *,
    peak_idx: int | None = None,
    edge_shots: int = 3,
    width_inches: float = 4.0,
    height_inches: float = 1.2,
    dpi: int = 110,
) -> bytes:
    """Render a sparkline-style chart of file size vs sequence to PNG bytes.

    Pure-ish: returns bytes rather than writing to disk. Always produces a
    figure (closed before return) — safe to call in a loop.
    """
    fig, ax = plt.subplots(figsize=(width_inches, height_inches), dpi=dpi)
    try:
        n = len(sizes)
        if n > 0:
            xs = list(range(n))
            sizes_kb = [s / 1024 for s in sizes]
            ax.plot(xs, sizes_kb, "o", color="#888", markersize=2, alpha=0.5)
            smoothed = smooth_sizes(sizes, window=3)
            if smoothed.size:
                offset = 1  # centred 3-window starts at index 1
                smoothed_xs = list(range(offset, offset + smoothed.size))
                ax.plot(
                    smoothed_xs,
                    smoothed / 1024,
                    "-",
                    color="#1f77b4",
                    linewidth=1.5,
                )
            if peak_idx is not None and 0 <= peak_idx < n:
                ax.axvline(peak_idx, color="#d62728", linewidth=1.0, alpha=0.8)
            # Shade the edge zones so truncation is visually obvious.
            ax.axvspan(-0.5, edge_shots - 0.5, color="#eeeeee", zorder=0)
            ax.axvspan(n - edge_shots - 0.5, n - 0.5, color="#eeeeee", zorder=0)
        ax.set_xticks([])
        ax.set_yticks([])
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(False)
        fig.tight_layout(pad=0.1)
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    finally:
        plt.close(fig)


def write_chart(path: Path, png: bytes) -> None:
    """Write PNG bytes to disk, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
