#!/usr/bin/env bash
# Stage Preproc — cause isolation. Sharded re-extraction of the per-axis re-anchored comb
# (saturation channel) under a CUMULATIVE ladder of LINEAR / MTF-preserving pre-processing
# steps, plus a fixed-focus variant and a NEGATIVE-CONTROL nonlinear clip. Run on nufan.
#
# Each ablation arm writes out/preproc/<tag>_all.csv. Analysis is poc_comb_chain_preproc_analyse.py.
set -u
ROOT=/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness
PY=~/.cache/uv-venvs/tile-sharpness/bin/python
cd "$ROOT"
CFG="${CFG:-$ROOT/scripts/poc_comb_chain_subset.csv}"
OUTDIR="${OUTDIR:-$ROOT/scripts/poc_comb_chain_out/preproc}"
mkdir -p "$OUTDIR"
N=${N:-8}

# arm tag | PREPROC value | FOCUS
#   baseline          : ""                       argmax  (reproduce Relock ~0.64 / ratio ~1.46)
#   flat              : flat                      argmax
#   flat_spec         : flat,specmask            argmax
#   flat_spec_win     : flat,specmask,phasewin   argmax  (full LINEAR stack)
#   flat_spec_win_foc : flat,specmask,phasewin   fixed   (+ consistent cross-config focus)
#   clip_NEGCTRL      : flat,specmask,clip        argmax  (INVALID nonlinear control)
run_arm() {
  local tag="$1" preproc="$2" focus="$3"
  echo "### ARM $tag  PREPROC='$preproc' FOCUS=$focus ###"
  for i in $(seq 0 $((N-1))); do
    SHARD="$i/$N" PREPROC="$preproc" FOCUS="$focus" RANK_CONFIGS="$CFG" \
      RANK_OUT="$OUTDIR/${tag}_shard_$i.csv" \
      PYTHONPATH="$ROOT/src" $PY -u scripts/poc_comb_chain_preproc_extract.py \
      > "$OUTDIR/${tag}_shard_$i.log" 2>&1 &
  done
  wait
  head -1 "$OUTDIR/${tag}_shard_0.csv" > "$OUTDIR/${tag}_all.csv"
  for i in $(seq 0 $((N-1))); do tail -n +2 "$OUTDIR/${tag}_shard_$i.csv" >> "$OUTDIR/${tag}_all.csv"; done
  echo "  $tag rows=$(($(wc -l < "$OUTDIR/${tag}_all.csv")-1))"
}

run_arm baseline          ""                      argmax
run_arm flat              "flat"                  argmax
run_arm flat_spec         "flat,specmask"         argmax
run_arm flat_spec_win     "flat,specmask,phasewin" argmax
run_arm flat_spec_win_foc "flat,specmask,phasewin" fixed
run_arm clip_NEGCTRL      "flat,specmask,clip"    argmax

echo "PREPROC_ALL_DONE"
