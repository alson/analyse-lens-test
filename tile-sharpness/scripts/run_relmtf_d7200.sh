#!/usr/bin/env bash
# D7200 relmtf pipeline (Phase 2), detached & self-completing:
#   extract (N thread-pinned shards) -> recover (fold) -> analyse --tier all.
# D7200 is MANUAL tier (p2_rail_ok=false), so the headline rail-coverage view is
# empty; --tier all gives the within-D7200 relative ranking. NB: subject-lp/mm and
# physical-mm columns still use the Z7 pitch until the Phase-4 per-camera analyse
# pitch lands; the RELATIVE fixed-f_px ranking is pitch-independent and valid.
# Writes a DONE (or FAILED) marker.
#   setsid nohup bash scripts/run_relmtf_d7200.sh out_relmtf_d7200 16 >out_relmtf_d7200/full.log 2>&1 &
set -uo pipefail
OUT="${1:?out dir}"; N="${2:-16}"
SUBSET="data/cross_m_relative_mtf_subset_d7200.csv"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p "$OUT"; rm -f "$OUT/DONE" "$OUT/FAILED"

echo "[$(date +%T)] EXTRACT $N shards -> $OUT (D7200)"
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

echo "[$(date +%T)] ANALYSE --tier all (D7200 manual tier)"
uv run --no-sync tile-sharpness relmtf-analyse --subset "$SUBSET" \
    --out "$OUT" --tier all >"$OUT/analyse_all.log" 2>&1 \
    || { echo FAILED-analyse >"$OUT/FAILED"; exit 1; }

echo "[$(date +%T)] DONE"; date >"$OUT/DONE"
