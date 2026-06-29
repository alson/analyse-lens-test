"""Consolidate the three studies into the report tables.

Reads study_material_glint.csv, study_edge_vs_fft.csv (merged shards) and
study_bare_vs_tc.csv and prints:
  (2) the same-feature edge<->FFT reconciliation table + the pinned calibration k,
  (3) the bare-vs-TC k-normalised ranking + TC-tolerance ratios.
Pure post-processing; no image work.
"""
from __future__ import annotations
import csv, glob, math
from pathlib import Path
import statistics as st

HERE = Path(__file__).resolve().parent
PER = 0.18739  # MTF50 = PER / sigma (cy/px)


def mtf_at(m50, f):
    s = PER / float(m50)
    return math.exp(-2.0 * (math.pi * s * f) ** 2)


def load_evf():
    rows = []
    for fn in sorted(glob.glob(str(HERE / "study_edge_vs_fft_*of6.csv"))):
        rows += list(csv.DictReader(open(fn)))
    return rows


def fnum(r, k):
    v = r.get(k)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def part2():
    rows = load_evf()
    print("=" * 92)
    print("(2) SAME-FEATURE / SAME-FREQUENCY edge<->FFT on the 6B serpent")
    print("=" * 92)
    hdr = f"{'config':46s} {'M':5s} {'f_serp':6s} {'edge_n':6s} {'naive':6s} {'CLEAN':6s} {'C_fft':6s}"
    print(hdr)
    pair = {}
    kfeats = []
    for r in sorted(rows, key=lambda r: r['config']):
        en = r.get('edge_n', '')
        cons = fnum(r, 'edge_cons_cypx'); naive = fnum(r, 'edge_naive_med_cypx')
        C = fnum(r, 'C_fft'); f = fnum(r, 'f_serpent_cypx')
        print(f"{r['config'][:46]:46s} {r.get('M',''):5s} {r.get('f_serpent_cypx',''):6s} "
              f"{str(en):6s} {('%.4f'%naive) if naive else '-':6s} "
              f"{('%.4f'%cons) if cons else '-':6s} {('%.4f'%C) if C else '-':6s}")
        if cons and C and f:
            k = C / mtf_at(cons, f)
            kfeats.append((r['config'], k))
        if 'Sigma APO Macro 150' in r['config'] and 'TC-1401' in r['config']:
            pair['150'] = (naive, cons, C)
        if 'Sigma Macro 105' in r['config'] and 'TC-1401' in r['config']:
            pair['105'] = (naive, cons, C)

    print("\n--- RECONCILIATION (Sigma150+TC vs Sigma105+TC, same serpent, M~1.0) ---")
    if '150' in pair and '105' in pair:
        n150, c150, C150 = pair['150']; n105, c105, C105 = pair['105']
        print(f"  naive edge median : 150={n150:.4f}  105={n105:.4f}  -> "
              f"{'150>105 (ARTEFACT)' if n150 > n105 else '105>150'}")
        print(f"  CLEANED edge      : 150={c150:.4f}  105={c105:.4f}  -> "
              f"{'150>105' if c150 > c105 else '105>150 (matches FFT)'}")
        print(f"  FFT contrast C    : 150={C150:.4f}  105={C105:.4f}  -> "
              f"{'150>105' if C150 > C105 else '105>150'}")

    print("\n--- CALIBRATION k_feature = C_fft / MTF_edge(f_serpent), cleaned-edge anchor ---")
    for cfg, k in kfeats:
        print(f"  {cfg[:54]:54s} k={k:.4f}")
    kv = [k for _, k in kfeats]
    if kv:
        print(f"  => k_feature median={st.median(kv):.4f} mean={st.mean(kv):.4f} "
              f"range=[{min(kv):.4f},{max(kv):.4f}] n={len(kv)}")
        print(f"     (vs the naive full-depth square-wave k_intrinsic ~0.6: ~{0.6/st.median(kv):.0f}x smaller — "
              f"the matte serpent's low modulation depth IS the apparent edge/FFT gap)")


def part3():
    shards = sorted(glob.glob(str(HERE / "study_bare_vs_tc_*of*.csv")))
    fn = HERE / "study_bare_vs_tc.csv"
    rows = []
    if shards:
        for s in shards:
            rows += list(csv.DictReader(open(s)))
    elif fn.exists():
        rows = list(csv.DictReader(open(fn)))
    else:
        print("\n(3) study_bare_vs_tc CSVs not found yet"); return
    print("\n" + "=" * 92)
    print("(3) CONTROLLED bare-vs-TC, k-normalised contrast at common subject frequency")
    print("=" * 92)
    by = {}
    for r in rows:
        ok = r.get('ok') in ('True', 'true', True)
        m = r.get('mtf_at_common')
        print(f"  [{r.get('group',''):8s}] {r['config'][:48]:48s} "
              f"M={r.get('M',''):5s} -> {'MISSING ('+r.get('reason','')+')' if not ok else m}")
        if ok and m not in (None, ''):
            by[r['config']] = (r.get('group'), float(m), r.get('M'))

    def find(sub, grp):
        for k, (g, v, M) in by.items():
            if sub in k and g == grp:
                return v
        return None

    print("\n--- bare ranking @ common f (k-normalised contrast; higher = sharper) ---")
    bare = [(k, v) for k, (g, v, M) in by.items() if g == 'bare']
    for k, v in sorted(bare, key=lambda x: -x[1]):
        print(f"  {k[:50]:50s} {v:.4f}")

    print("\n--- TC-tolerance (serpent route, drop bare -> +TC) ---")
    for lens, sub in [("Sigma 105", "Sigma Macro 105mm"), ("Sigma 150", "Sigma APO Macro 150mm")]:
        b = find(sub, 'bare'); t14 = find(sub, 'TC-1401'); t20 = find(sub, 'TC-2001')
        def ratio(x):
            return f"{x/b:.2f}" if (x and b) else ("MISSING" if x is None else "-")
        print(f"  {lens}: bare={b if b else '-'}  +TC14={t14 if t14 else '-'} (x{ratio(t14)})  "
              f"+TC20={t20 if t20 else '-'} (x{ratio(t20)})")
    print("  CAVEAT: bare Sigma 105 frames a DIFFERENT serpent instance (die 9F vs 6B/6D),")
    print("  low SNR (1-3), and 105+TC-2001 reg-fails -> serpent route unreliable for this")
    print("  ranking. The robust answer is the broad magenta cross-check below.")
    _part3_magenta()


def _part3_magenta():
    import subprocess
    print("\n--- ROBUST cross-check: broad periodic-FFT magenta pads at common f ---")
    try:
        out = subprocess.run(["python", str(HERE / "study_bare_vs_tc_magenta.py")],
                             capture_output=True, text=True, timeout=120)
        print(out.stdout)
    except Exception as e:  # pragma: no cover
        print(f"  (magenta cross-check unavailable: {e})")


if __name__ == "__main__":
    part2()
    part3()
