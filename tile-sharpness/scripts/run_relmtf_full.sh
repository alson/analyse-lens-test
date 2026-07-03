#!/usr/bin/env bash
# Full 311-subset relmtf pipeline, detached & self-completing:
#   extract (N thread-pinned shards) -> recover (fold) -> analyse (rail-coverage + all).
# Writes a DONE (or FAILED) marker so a later check can tell it finished cleanly.
# Launch on nufan with:  setsid nohup bash scripts/run_relmtf_full.sh out_relmtf_311 16 >OUT/full.log 2>&1 &
set -uo pipefail
OUT="${1:?out dir}"; N="${2:-16}"
SUBSET="data/cross_m_relative_mtf_subset_multisession.csv"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p "$OUT"; rm -f "$OUT/DONE" "$OUT/FAILED"

echo "[$(date +%T)] EXTRACT $N shards -> $OUT"
pids=()
for i in $(seq 0 $((N-1))); do
  taskset -c "$i" uv run --no-sync tile-sharpness relmtf-extract \
      --subset "$SUBSET" --out "$OUT" --shard "$i/$N" >"$OUT/ex_shard_$i.log" 2>&1 &
  pids+=($!)
done
rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done
echo "[$(date +%T)] extract rc=$rc"
[ "$rc" -ne 0 ] && { echo FAILED-extract >"$OUT/FAILED"; exit 1; }

echo "[$(date +%T)] RECOVER (fold) -> $OUT"
uv run --no-sync tile-sharpness relmtf-recover --subset "$SUBSET" \
    --out "$OUT" >"$OUT/recover.log" 2>&1 || { echo FAILED-recover >"$OUT/FAILED"; exit 1; }

echo "[$(date +%T)] ANALYSE rail-coverage (headline)"
uv run --no-sync tile-sharpness relmtf-analyse --subset "$SUBSET" \
    --out "$OUT" --tier rail-coverage >"$OUT/analyse_railcoverage.log" 2>&1 \
    || { echo FAILED-analyse-rc >"$OUT/FAILED"; exit 1; }

echo "[$(date +%T)] DONE"; date >"$OUT/DONE"
