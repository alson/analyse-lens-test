#!/usr/bin/env bash
# D7200 atlas-anchored centre/corner subject-MTF50 cohort run, detached & self-completing.
# Runs scripts/atlas_corner_d7200.py in N thread-pinned round-robin shards over the
# frozen D7200 subset, merges the per-shard CSVs into atlas_corner_d7200.csv, writes a
# DONE (or FAILED) marker. This is the "characterise-style" centre + 4-corner subject
# lp/mm + uniformity view, MINUS field curvature (rail-dependent, unavailable on the
# manual-tier D7200). Registration (atlas reg_auto) is the cost — ~1.5-2 min/config,
# hence the sharding.
# CAVEATS: OLPF depresses D7200 absolute MTF50 (within-camera/relative trustworthy,
# cross-camera absolute NOT); scribe-LSF MTF50 over-reads the diffraction ceiling at low
# contrast (trust centre + glass-limited corners; use the physics ceiling elsewhere).
#   setsid nohup bash scripts/run_atlas_corner_d7200.sh out_atlas_corner_d7200 16 \
#       >out_atlas_corner_d7200/full.log 2>&1 &
set -uo pipefail
OUT="${1:?out dir}"; N="${2:-16}"
SUBSET="data/cross_m_relative_mtf_subset_d7200.csv"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p "$OUT"; rm -f "$OUT/DONE" "$OUT/FAILED" "$OUT"/atlas_corner_d7200_shard_*.csv

echo "[$(date +%T)] ATLAS-CORNER $N shards -> $OUT (D7200)"
pids=()
for i in $(seq 0 $((N-1))); do
  taskset -c "$i" uv run --no-sync python scripts/atlas_corner_d7200.py \
      --subset "$SUBSET" --out "$OUT" --shard "$i/$N" >"$OUT/shard_$i.log" 2>&1 &
  pids+=($!)
done
rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done
echo "[$(date +%T)] shards rc=$rc"
[ "$rc" -ne 0 ] && { echo FAILED-shards >"$OUT/FAILED"; exit 1; }

# merge: header from shard 0, then all shard data rows
MERGED="$OUT/atlas_corner_d7200.csv"
first=$(ls "$OUT"/atlas_corner_d7200_shard_*.csv 2>/dev/null | head -1)
[ -z "$first" ] && { echo FAILED-no-shard-csv >"$OUT/FAILED"; exit 1; }
head -1 "$first" >"$MERGED"
for f in "$OUT"/atlas_corner_d7200_shard_*.csv; do tail -n +2 "$f" >>"$MERGED"; done
echo "[$(date +%T)] merged $(($(wc -l < "$MERGED")-1)) configs -> $MERGED"
echo "[$(date +%T)] DONE"; date >"$OUT/DONE"
