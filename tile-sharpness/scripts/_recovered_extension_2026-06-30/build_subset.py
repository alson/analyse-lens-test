#!/usr/bin/env python
"""Build the expanded Z7 multi-session subset CSV (additive on the original 38).

Aperture-complete: for the NEW sessions every available aperture folder per
(lens, mag) becomes its own (lens, mag, aperture) node — wide-open through smallest
(teleconverter/extension configs often have no F8; we sweep whatever exists). The
original validated 38 rows are carried verbatim (they already encode the curated
baseline + the 2026-01-29 relative-order regression check).

Columns add ``p2_rail_ok`` (per-config through-focus availability — TRUE only for the
rail-coverage tier 2026-05-12/13; FALSE for the whole manual tier 2025-10-17 /
2026-01-29 / 2026-02-18). The ``aperture`` field carries the MARKED f-number so
optics.effective_fnumber derives the working N_eff from the registered M; for the
2026-05 rail sessions the aperture FOLDER is the effective f-number, so the marked N
is recovered from effective_apertures.csv (reported_f).
"""
import csv
import glob
import os
import re

TS = "/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness"
ORIG = os.path.join(TS, "scripts", "cross_m_relative_mtf_subset.csv")
ROOT = "/home/alson/shared/files/pics/digikam/test-raw-data"
OUT = os.path.join(TS, "scripts", "cross_m_relative_mtf_subset_multisession.csv")

FIELDS = ["date", "lens", "mag_label", "nominal_M", "focal", "aperture",
          "n_shots", "sample", "p2_rail_ok"]

MIN_SHOTS = 20  # a real focus sweep; fewer -> a stray capture, skip.
rows = []


def one_jpg(d):
    js = sorted(glob.glob(os.path.join(glob.escape(d), "*.jpg"))
                + glob.glob(os.path.join(glob.escape(d), "*.JPG")))
    return (js[0] if js else None), len(js)


def ap_dir_to_marked(name):
    """'F8'/'F8.5'/'f_5_6'/'f_8'/'8'/'6_3' -> float marked f-number, or None."""
    s = name
    s = re.sub(r"^[Ff]_?", "", s)
    s = s.replace("_", ".")
    try:
        return float(s)
    except ValueError:
        return None


# ---- 1) original 38 verbatim -> MANUAL tier (P2 off) + supersession -----------
SUPERSEDED = {
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM", "F8"),
    ("Nikon AF Zoom-Micro Nikkor 70-180mm f_4.5-5.6D ED", "F8"),
    ("Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T + 6T", "F8"),
    ("Nikon Micro-Nikkor 55mm f_2.8 AIS 287318", "F8"),
    ("NIKKOR Z MC 105mm f_2.8 VR S + 5T + 6T", "F8"),
}
superseded_dropped = []
with open(ORIG) as fh:
    for r in csv.DictReader(fh):
        if (r["lens"], r["aperture"]) in SUPERSEDED:
            superseded_dropped.append(f"{r['lens']} | {r['mag_label']} | {r['aperture']}")
            continue
        r["p2_rail_ok"] = "false"  # manual tier
        rows.append(r)
print(f"original 38 -> manual tier (P2 off): kept {len(rows)}, "
      f"superseded-dropped {len(superseded_dropped)}")
for s in superseded_dropped:
    print(f"  SUPERSEDED by 2026-05 reshoot: {s}")


def add_rows(date, lens, mag_label, focal, apdir, rail_ok, marked=None):
    samp, n = one_jpg(apdir)
    if not samp or n < MIN_SHOTS:
        return 0
    ap_name = os.path.basename(apdir)
    if marked is None:
        marked = ap_dir_to_marked(ap_name)
    if marked is None:
        return 0
    rows.append(dict(date=date, lens=lens, mag_label=mag_label, nominal_M="",
                     focal=focal, aperture=f"F{marked:g}", n_shots=str(n),
                     sample=samp, p2_rail_ok=("true" if rail_ok else "false")))
    return 1


# ---- 2) 2025-10-17 (manual): <lens>/<aperture>/ — ALL apertures --------------
S = os.path.join(ROOT, "2025-10-17")
n1017 = 0
for lensdir in sorted(glob.glob(os.path.join(S, "*"))):
    if not os.path.isdir(lensdir):
        continue
    lens = os.path.basename(lensdir)
    if lens.lower().startswith("results") or "ignore" in lens.lower():
        continue
    for apdir in sorted(glob.glob(os.path.join(lensdir, "F*"))):
        if not os.path.isdir(apdir):
            continue
        # focal from a sample filename
        samp, _ = one_jpg(apdir)
        focal = ""
        if samp:
            for t in os.path.basename(samp).split("|"):
                if t.strip().endswith("mm"):
                    focal = t.replace("mm", "").strip()
                    break
        n1017 += add_rows("2025-10-17", lens, "1_1", focal, apdir, rail_ok=False)
print(f"2025-10-17 (manual, all apertures): {n1017} config-nodes")


# ---- 2b) 2026-02-18 (manual): <lens>/<mag>/<focal>/<aperture>/ — ALL aps ------
# exclude *-resized mag dirs (upscaled crops) and cropped/ tile dirs; full frames
# live directly in the aperture dir. Bare 24-120 superseded by 2026-05-13 reshoot.
S18 = os.path.join(ROOT, "2026-02-18")
SUPERSEDED_0218_LENSES = {"NIKKOR Z 24-120mm f_4 S"}  # bare -> reshot in 05-13
n18 = 0
for lensdir in sorted(glob.glob(os.path.join(S18, "*"))):
    if not os.path.isdir(lensdir):
        continue
    lens = os.path.basename(lensdir)
    if lens in SUPERSEDED_0218_LENSES:
        continue
    for magdir in sorted(glob.glob(os.path.join(lensdir, "*"))):
        if not os.path.isdir(magdir):
            continue
        mag = os.path.basename(magdir)
        if mag.endswith("-resized"):
            continue
        for focaldir in sorted(glob.glob(os.path.join(magdir, "*"))):
            if not os.path.isdir(focaldir):
                continue
            focal = os.path.basename(focaldir).replace("mm", "").strip()
            for apdir in sorted(glob.glob(os.path.join(focaldir, "F*"))):
                if not os.path.isdir(apdir) or os.path.basename(apdir) == "cropped":
                    continue
                n18 += add_rows("2026-02-18", lens, mag, focal, apdir, rail_ok=False)
print(f"2026-02-18 (manual, all apertures): {n18} config-nodes")


# ---- 3) rail sessions 2026-05-12 / 2026-05-13 (rail tier, P2 on) -------------
# aperture FOLDER is the effective f-number; recover the MARKED reported_f from
# effective_apertures.csv. Enumerate ALL aperture folders per lens.
def load_eff(session):
    p = os.path.join(ROOT, session, "effective_apertures.csv")
    out = {}
    if not os.path.exists(p):
        return out
    with open(p) as fh:
        for r in csv.DictReader(fh):
            try:
                rep = float(r["reported_f"])
            except (ValueError, KeyError):
                continue
            # map by (slug, F_dir_name) -> reported_f
            out[(r["slug"], r.get("F_dir_name", ""))] = (rep, r.get("focal_mm", ""))
    return out


def enum_rail(session, rail_ok=True, exclude_substr=("(duplicate)",)):
    eff = load_eff(session)
    added = 0
    for lensdir in sorted(glob.glob(os.path.join(ROOT, session, "*"))):
        if not os.path.isdir(lensdir):
            continue
        lens_raw = os.path.basename(lensdir)
        if any(x in lens_raw for x in exclude_substr):
            continue
        # clean display lens name (strip timestamp suffix on 05-12 dirs)
        lens = lens_raw.split(" (20")[0]
        for apdir in sorted(glob.glob(os.path.join(lensdir, "*"))):
            if not os.path.isdir(apdir):
                continue
            apname = os.path.basename(apdir)
            if apname in ("calibration", "probe", "cropped") or apname.startswith("."):
                continue
            if ap_dir_to_marked(apname) is None:
                continue
            key = (lens_raw, apname)
            marked, focal = eff.get(key, (ap_dir_to_marked(apname), ""))
            added += add_rows(session, lens, "", focal, apdir, rail_ok=rail_ok,
                              marked=marked)
    return added


n13 = enum_rail("2026-05-13", rail_ok=True)
print(f"2026-05-13 (rail, all apertures): {n13} config-nodes")
# 2026-05-12: timestamped repeat-takes of mostly the same configs as 05-13. To avoid
# double-counting, include ONLY lens families unique to 05-12 (Viltrox 85 takes +
# 100-400+Canon500D+61mm + the MC105+5T+6T rail take), and only their best take.
UNIQUE_0512 = [
    "Viltrox 85mm f_2 EVO + 61mm extension (2026-05-10_164247)",
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Canon 500D + 61mm extension (2026-05-14_213530)",
    "NIKKOR Z MC 105mm f_2.8 VR S + 5T + 6T (2026-05-06_225632)",
]
eff12 = load_eff("2026-05-12")
n12 = 0
for lens_raw in UNIQUE_0512:
    lensdir = os.path.join(ROOT, "2026-05-12", lens_raw)
    if not os.path.isdir(lensdir):
        print(f"  MISS 05-12 dir {lens_raw}")
        continue
    lens = lens_raw.split(" (20")[0]
    for apdir in sorted(glob.glob(os.path.join(lensdir, "*"))):
        if not os.path.isdir(apdir):
            continue
        apname = os.path.basename(apdir)
        if apname in ("calibration", "probe", "cropped") or ap_dir_to_marked(apname) is None:
            continue
        marked, focal = eff12.get((lens_raw, apname), (ap_dir_to_marked(apname), ""))
        n12 += add_rows("2026-05-12", lens, "", focal, apdir, rail_ok=True, marked=marked)
print(f"2026-05-12 (rail, unique families, all apertures): {n12} config-nodes")

# ---- write -------------------------------------------------------------------
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in FIELDS})
print(f"WROTE {OUT}: {len(rows)} total config-nodes")
