#!/usr/bin/env bash
# Stage AltEst-2 sharded runner (nufan). Usage: bash poc_altest2_run.sh DRIVER N
#   DRIVER in {patch, psffoc, decon, edge}
set -u
DRIVER="${1:-patch}"
N="${2:-16}"
ROOT=/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness
PY=~/.cache/uv-venvs/tile-sharpness/bin/python
export PYTHONPATH="$ROOT/src"
case "$DRIVER" in
  patch)  SCRIPT="$ROOT/scripts/poc_altest2_patch_driver.py" ;;
  psffoc) SCRIPT="$ROOT/scripts/poc_altest2_psf_focus.py" ;;
  decon)  SCRIPT="$ROOT/scripts/poc_altest2_decon_driver.py" ;;
  edge)   SCRIPT="$ROOT/scripts/poc_altest2_padedge_driver.py" ;;
  *) echo "unknown driver $DRIVER"; exit 1 ;;
esac
OUTDIR="$ROOT/scripts/poc_comb_chain_out/altest2"
mkdir -p "$OUTDIR"
pids=()
for i in $(seq 0 $((N-1))); do
  SHARD="$i/$N" $PY -u "$SCRIPT" > "$OUTDIR/${DRIVER}_shard_${i}_${N}.log" 2>&1 &
  pids+=($!)
done
echo "launched $N shards for $DRIVER (pids ${pids[*]})"
wait "${pids[@]}"
echo "ALL $DRIVER SHARDS DONE"
