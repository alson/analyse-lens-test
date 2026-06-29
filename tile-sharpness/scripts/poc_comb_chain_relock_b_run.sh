#!/usr/bin/env bash
# Stage Relock Phase B: sharded re-anchored comb-amplitude extraction. Run on nufan.
set -u
ROOT=/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness
PY=~/.cache/uv-venvs/tile-sharpness/bin/python
cd "$ROOT"
CFG="${CFG:-$ROOT/scripts/poc_comb_chain_subset.csv}"
OUTDIR="${OUTDIR:-$ROOT/scripts/poc_comb_chain_out/relock}"
mkdir -p "$OUTDIR"
N=${N:-8}
for i in $(seq 0 $((N-1))); do
  SHARD="$i/$N" RANK_CONFIGS="$CFG" RANK_OUT="$OUTDIR/relock_shard_$i.csv" \
    PYTHONPATH="$ROOT/src" $PY -u scripts/poc_comb_chain_relock_b_extract.py \
    > "$OUTDIR/relock_shard_$i.log" 2>&1 &
done
wait
head -1 "$OUTDIR/relock_shard_0.csv" > "$OUTDIR/relock_all.csv"
for i in $(seq 0 $((N-1))); do tail -n +2 "$OUTDIR/relock_shard_$i.csv" >> "$OUTDIR/relock_all.csv"; done
echo "RELOCK_DONE rows=$(($(wc -l < "$OUTDIR/relock_all.csv")-1))"
