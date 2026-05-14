#!/bin/bash
# Retrospective full rebuild of cropped/ and *-resized/ trees for
# 2026-01-29 and 2026-02-18. Designed to run unattended on nufan via
# nohup; survives SSH disconnects and prints to a log file.
#
# Prereqs (Ubuntu): apt install python3 libturbojpeg0 graphicsmagick
# (graphicsmagick is only needed for the legacy gm-based scripts the
# main flow no longer uses — drop it if you trust the new pipeline.)
# Plus uv: curl -LsSf https://astral.sh/uv/install.sh | sh
#
# Usage:
#   cd ~/shared/projects/personal/fotografie/analyse-lens-test/resize-bulk
#   nohup ./rebuild_all.sh > /tmp/rebuild_$(date +%Y%m%dT%H%M%S).log 2>&1 &
#   tail -f /tmp/rebuild_*.log

set -euo pipefail

ROOTS=(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29"
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-02-18"
)
HERE="$(cd "$(dirname "$0")" && pwd)"
ANALYSE_LENS_TEST="$(dirname "$HERE")"
RAIL_COVERAGE="$ANALYSE_LENS_TEST/rail-coverage"
LOG_PREFIX="[rebuild $(date -u +%FT%TZ)]"

# Make uv reachable when launched by nohup from a non-login shell on
# Ubuntu — Astral's installer puts the binary in ~/.local/bin which
# isn't on PATH by default for non-interactive SSH sessions.
export PATH="$HOME/.local/bin:$PATH"

say() { echo "$LOG_PREFIX $*"; }

# --- 1. Prereqs check --------------------------------------------------------

say "checking prereqs"
need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "MISSING: $1 — install before running" >&2
        return 1
    fi
}
need_cmd uv
need_cmd find
need_cmd xargs
# libturbojpeg0 has no CLI; check via Python instead, once uv has set up env.

# --- 2. Sync resize-bulk venv ------------------------------------------------

say "syncing resize-bulk env"
cd "$HERE"
uv sync

say "verifying PyTurboJPEG can find libturbojpeg.so"
uv run python -c "from turbojpeg import TurboJPEG; TurboJPEG()" || {
    echo "PyTurboJPEG initialisation failed — apt install libturbojpeg0" >&2
    exit 2
}

say "syncing rail-coverage env"
cd "$RAIL_COVERAGE"
uv sync

# --- 3. Wipe stale cropped/ and *-resized/ trees ----------------------------

say "wiping stale crop / resized trees in roots"
for root in "${ROOTS[@]}"; do
    say "  wiping cropped/ under $root"
    find "$root" -type d -name 'cropped' -print0 \
        | xargs -0 -P 16 -I{} rm -rf "{}"
    say "  wiping *-resized/ under $root"
    find "$root" -maxdepth 4 -type d -name '*-resized' -print0 \
        | xargs -0 -P 16 -I{} rm -rf "{}"
done

# --- 4. Re-crop every native aperture folder --------------------------------

say "re-cropping native aperture folders"
mapfile -t NATIVE_DIRS < <(
    for root in "${ROOTS[@]}"; do
        find "$root" -mindepth 2 -maxdepth 4 -type d \
            -regextype posix-extended -regex '.*/F[0-9]+(\.[0-9]+)?$' \
            -not -path '*-resized*' \
            -not -path '*cropped*'
    done
)
say "  found ${#NATIVE_DIRS[@]} native aperture folders"

# Each aperture folder gets its own lossless 17-crop split. Run them
# serially per folder (the Python tool internally uses a thread pool);
# parallelism across folders eats NFS bandwidth without speedup.
# Continue past individual failures so one bad folder doesn't stop a
# multi-hour rebuild — the failure is logged and shows up in the
# end-of-run summary.
i=0
failures=0
for ap_dir in "${NATIVE_DIRS[@]}"; do
    i=$((i + 1))
    if [ $((i % 25)) -eq 0 ] || [ "$i" -eq 1 ] || [ "$i" -eq "${#NATIVE_DIRS[@]}" ]; then
        say "  [$i/${#NATIVE_DIRS[@]}] $ap_dir"
    fi
    if ! (cd "$ap_dir" && "$ANALYSE_LENS_TEST/make-17-crops.sh" >/dev/null 2>&1); then
        say "  FAILED: $ap_dir"
        failures=$((failures + 1))
    fi
done
say "  re-crop done: $((i - failures)) ok, $failures failed"

# --- 5. Generate resized trees ----------------------------------------------

say "generating *-resized trees via resize_bulk"
cd "$HERE"
# resize_bulk.py returns exit code 2 when *any* worker errors (even one
# missing source file out of thousands). Trap that so set -e doesn't
# abort the loop after the first root — the second root is still worth
# running, and rescan/summary downstream still produce a useful report
# from whatever data did land.
for root in "${ROOTS[@]}"; do
    say "  $root"
    if ! PYTHONUNBUFFERED=1 uv run python resize_bulk.py "$root" --workers 8; then
        say "  WARNING: resize_bulk reported errors for $root (exit $?)"
    fi
done

# --- 6. Refresh rail-coverage scan-cache ------------------------------------

say "rescanning rail-coverage"
cd "$RAIL_COVERAGE"
uv run rail-coverage \
    "${ROOTS[@]}" \
    --out output \
    --cache output/scan-cache.json \
    --rescan \
    --quiet

# --- 7. Regenerate summary tables -------------------------------------------

say "regenerating summary tables"
cd "$HERE"
uv run python summarise.py > "$HERE/RESIZED_COMPARISON_$(date +%Y%m%d).txt" || true

say "done"
