#!/usr/bin/env bash
# Stage T_n step-1: sharded saturation-channel comb-amplitude extraction. Run on nufan.
set -u
ROOT=/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness
PY=~/.cache/uv-venvs/tile-sharpness/bin/python
cd "$ROOT"
CFG="${CFG:-$ROOT/scripts/poc_comb_chain_subset.csv}"
OUTDIR="${OUTDIR:-$ROOT/scripts/poc_comb_chain_out}"
mkdir -p "$OUTDIR"
N=${N:-8}
for i in $(seq 0 $((N-1))); do
  SHARD="$i/$N" RANK_CONFIGS="$CFG" RANK_OUT="$OUTDIR/tn_shard_$i.csv" \
    PYTHONPATH="$ROOT/src" $PY -u scripts/poc_comb_chain_tn_extract.py \
    > "$OUTDIR/tn_shard_$i.log" 2>&1 &
done
wait
head -1 "$OUTDIR/tn_shard_0.csv" > "$OUTDIR/tn_all.csv"
for i in $(seq 0 $((N-1))); do tail -n +2 "$OUTDIR/tn_shard_$i.csv" >> "$OUTDIR/tn_all.csv"; done
echo "TN_DONE rows=$(($(wc -l < "$OUTDIR/tn_all.csv")-1))"
