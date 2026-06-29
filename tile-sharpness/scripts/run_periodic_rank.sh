#!/usr/bin/env bash
# Sharded periodic-FFT ranking over the F8 config set. Run on nufan (16 cores).
set -u
WT=/home/alson/shared/projects/personal/fotografie/analyse-lens-test/.claude/worktrees/periodic-fft
PY=~/.cache/uv-venvs/tile-sharpness/bin/python
cd "$WT/tile-sharpness"
CFG="$WT/tile-sharpness/scripts/periodic_rank_configs.csv"
OUTDIR="$WT/tile-sharpness/out_periodic_fft"
mkdir -p "$OUTDIR"
N=${N:-6}
for i in $(seq 0 $((N-1))); do
  SHARD="$i/$N" RANK_CONFIGS="$CFG" RANK_OUT="$OUTDIR/rank_shard_$i.csv" \
    PYTHONPATH="$WT/tile-sharpness/src" $PY -u scripts/atlas_periodic_fft.py \
    > "$OUTDIR/shard_$i.log" 2>&1 &
done
wait
# concatenate shards (header once)
head -1 "$OUTDIR/rank_shard_0.csv" > "$OUTDIR/rank_all.csv"
for i in $(seq 0 $((N-1))); do tail -n +2 "$OUTDIR/rank_shard_$i.csv" >> "$OUTDIR/rank_all.csv"; done
echo "RANK_DONE rows=$(($(wc -l < "$OUTDIR/rank_all.csv")-1))"
