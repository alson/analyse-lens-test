#!/usr/bin/env bash
# Sharded A1 comb-spectrum run over the spanning subset. Run on nufan (16 cores).
set -u
ROOT=/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness
PY=~/.cache/uv-venvs/tile-sharpness/bin/python
cd "$ROOT"
CFG="${CFG:-$ROOT/scripts/poc_comb_chain_subset.csv}"
OUTDIR="${OUTDIR:-$ROOT/scripts/poc_comb_chain_out}"
mkdir -p "$OUTDIR"
N=${N:-8}
for i in $(seq 0 $((N-1))); do
  SHARD="$i/$N" RANK_CONFIGS="$CFG" RANK_OUT="$OUTDIR/a1_shard_$i.csv" \
    PYTHONPATH="$ROOT/src" $PY -u scripts/poc_comb_chain_a1_driver.py \
    > "$OUTDIR/a1_shard_$i.log" 2>&1 &
done
wait
head -1 "$OUTDIR/a1_shard_0.csv" > "$OUTDIR/a1_all.csv"
for i in $(seq 0 $((N-1))); do tail -n +2 "$OUTDIR/a1_shard_$i.csv" >> "$OUTDIR/a1_all.csv"; done
echo "A1_DONE rows=$(($(wc -l < "$OUTDIR/a1_all.csv")-1))"
