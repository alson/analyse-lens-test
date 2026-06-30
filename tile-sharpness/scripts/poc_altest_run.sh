#!/usr/bin/env bash
# Stage AltEst sharded runner (nufan). Usage:
#   bash poc_altest_run.sh DRIVER N   where DRIVER in {patch, psffoc}
# Env CL0/RL0/CL1/RL1 set the common in-FOV atlas rect (from poc_altest_fov.py).
set -u
DRIVER="${1:-patch}"
N="${2:-8}"
ROOT=/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness
PY=~/.cache/uv-venvs/tile-sharpness/bin/python
export PYTHONPATH="$ROOT/src"
case "$DRIVER" in
  patch)  SCRIPT="$ROOT/scripts/poc_altest_patch_driver.py" ;;
  psffoc) SCRIPT="$ROOT/scripts/poc_altest_psf_focus.py" ;;
  edge)   SCRIPT="$ROOT/scripts/poc_altest_edge.py" ;;
  *) echo "unknown driver $DRIVER"; exit 1 ;;
esac
OUTDIR="$ROOT/scripts/poc_comb_chain_out/altest"
mkdir -p "$OUTDIR"
pids=()
for i in $(seq 0 $((N-1))); do
  SHARD="$i/$N" $PY -u "$SCRIPT" > "$OUTDIR/${DRIVER}_shard_${i}_${N}.log" 2>&1 &
  pids+=($!)
done
echo "launched $N shards for $DRIVER (pids ${pids[*]})"
wait "${pids[@]}"
echo "ALL $DRIVER SHARDS DONE"
