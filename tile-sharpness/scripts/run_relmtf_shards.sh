#!/usr/bin/env bash
# Launch the relmtf-extract stage as N thread-pinned shards on nufan, then wait.
# Usage: run_relmtf_shards.sh <out_dir> [N]
set -euo pipefail
OUT="${1:?out dir}"; N="${2:-16}"
SUBSET="data/cross_m_relative_mtf_subset_multisession.csv"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p "$OUT"
pids=()
for i in $(seq 0 $((N-1))); do
  taskset -c "$i" uv run --no-sync tile-sharpness relmtf-extract \
      --subset "$SUBSET" --out "$OUT" --shard "$i/$N" \
      >"$OUT/launch_shard_$i.log" 2>&1 &
  pids+=($!)
done
echo "launched $N shards -> $OUT"
rc=0
for p in "${pids[@]}"; do wait "$p" || rc=1; done
echo "all shards done rc=$rc"
exit $rc
