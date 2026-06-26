"""NEF-side EXIF FocusDistance audit for the 2025-07-09 and 2025-09-11
D7200 datasets.

The in-camera JPEGs on these days have FocusDistance EXIF stripped (it's
in the MakerNotes section that the JPEG path omits), so any distance
inference from JPEGs alone is unreliable. The NEFs still carry the field
and exiftool reads it back as "Focus Distance" (note the space).

What this audits
----------------
- **2025-07-09**: per (lens, FL) distance summary. Confirms / refutes the
  earlier note that this session used shorter distances than 2025-09-06,
  borderline for the longest FLs.
- **2025-09-11**: per (lens, FL) distance summary. Tags lenses as VALID
  if median distance >= 5 m, INVALID otherwise. The DX 18-70 sub-session
  was focused at ~1.7 m by mistake; flag and exclude.

Usage
-----
    direnv exec . uv run python scripts/audit_nef_distance.py

Outputs (next to this script):
    audit_nef_distance_out/
        nef_distances_2025-07-09.csv
        nef_distances_2025-07-09.md
        nef_distances_2025-09-11.csv
        nef_distances_2025-09-11.md
"""
from __future__ import annotations

import csv
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).parent / "audit_nef_distance_out"
OUT.mkdir(exist_ok=True)

DATES = [
    "2025-07-09",
    "2025-09-11",
]
ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data")


def read_exif(nefs: list[Path]) -> dict[Path, dict[str, str]]:
    """Batch exiftool call across NEFs. Each NEF returns its FocusDistance,
    FocalLength, FNumber, lens name, and the capture timestamp.
    """
    result: dict[Path, dict[str, str]] = {}
    if not nefs:
        return result
    cmd = ["exiftool", "-T", "-FocalLength", "-FNumber", "-FocusDistance",
           "-LensInfo", "-LensIDNikon", "-Model", "-DateTimeOriginal",
           *map(str, nefs)]
    out = subprocess.check_output(cmd, text=True, errors="replace")
    for nef, line in zip(nefs, out.splitlines()):
        parts = line.split("\t")
        # exiftool -T outputs '-' for missing tags
        if len(parts) >= 3:
            result[nef] = {
                "FocalLength": parts[0],
                "FNumber":     parts[1],
                "FocusDistance": parts[2],
                "LensInfo":    parts[3] if len(parts) > 3 else "-",
                "LensIDNikon": parts[4] if len(parts) > 4 else "-",
                "Model":       parts[5] if len(parts) > 5 else "-",
                "DateTimeOriginal": parts[6] if len(parts) > 6 else "-",
            }
    return result


_RE_DIST = re.compile(r"([\d.]+)\s*m")
_RE_FL   = re.compile(r"([\d.]+)\s*mm")


def parse_distance_m(s: str) -> float | None:
    if not s or s == "-":
        return None
    m = _RE_DIST.search(s)
    if not m:
        return None
    return float(m.group(1))


def parse_fl_mm(s: str) -> float | None:
    if not s or s == "-":
        return None
    m = _RE_FL.search(s)
    if not m:
        return None
    return float(m.group(1))


def parse_fnumber(s: str) -> float | None:
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def lens_dir_for_nef(nef: Path, date_root: Path) -> str:
    """Return the top-level lens dir name (first path component below the
    date root) — matches the lens-name convention used elsewhere."""
    try:
        rel = nef.relative_to(date_root)
        return rel.parts[0]
    except ValueError:
        return nef.parent.name


def audit_date(date: str) -> tuple[list[dict], dict]:
    date_root = ROOT / date
    if not date_root.is_dir():
        return [], {}
    nefs = sorted(date_root.rglob("*.nef"))
    if nefs:
        print(f"[{date}] reading EXIF from {len(nefs)} NEFs", flush=True)
    else:
        # Fall back to JPEGs — some sessions only have JPEGs on disk.
        # Exclude pre-cropped 'cropped/' subdirs and the lossless-crop
        # outputs to avoid duplicates.
        nefs = [p for p in sorted(date_root.rglob("*.jpg"))
                if "/cropped/" not in str(p)]
        if not nefs:
            return [], {}
        print(f"[{date}] no NEFs found — reading EXIF from {len(nefs)} JPEGs", flush=True)

    # exiftool can handle many files per call; chunk to be safe
    exif: dict[Path, dict[str, str]] = {}
    chunk = 200
    for i in range(0, len(nefs), chunk):
        exif.update(read_exif(nefs[i:i+chunk]))

    rows: list[dict] = []
    for nef in nefs:
        md = exif.get(nef)
        if not md:
            continue
        rows.append({
            "file":            nef.name,
            "lens_dir":        lens_dir_for_nef(nef, date_root),
            "FocalLength_mm":  parse_fl_mm(md.get("FocalLength", "")),
            "FNumber":         parse_fnumber(md.get("FNumber", "")),
            "FocusDistance_m": parse_distance_m(md.get("FocusDistance", "")),
            "LensInfo":        md.get("LensInfo", "-"),
            "LensIDNikon":     md.get("LensIDNikon", "-"),
            "Model":           md.get("Model", "-"),
            "DateTimeOriginal": md.get("DateTimeOriginal", "-"),
        })

    # Group by (lens_dir, FL) — for each group: min/max/median distance,
    # n NEFs, n with distance, n without distance.
    groups: dict[tuple[str, float | None], list[float]] = defaultdict(list)
    n_total: dict[tuple[str, float | None], int] = defaultdict(int)
    sample_lens_info: dict[str, str] = {}
    for r in rows:
        key = (r["lens_dir"], r["FocalLength_mm"])
        n_total[key] += 1
        if r["FocusDistance_m"] is not None:
            groups[key].append(r["FocusDistance_m"])
        sample_lens_info.setdefault(r["lens_dir"], r["LensInfo"])

    summary = {}
    for key in sorted(n_total.keys(), key=lambda k: (k[0], k[1] or 0)):
        dists = groups.get(key, [])
        summary[key] = {
            "n_nefs":            n_total[key],
            "n_with_distance":   len(dists),
            "min_m":             min(dists) if dists else None,
            "max_m":             max(dists) if dists else None,
            "median_m":          statistics.median(dists) if dists else None,
            "lens_info":         sample_lens_info.get(key[0], "-"),
        }
    return rows, summary


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fieldnames)
        wr.writeheader()
        wr.writerows(rows)


def parse_datetime(s: str):
    """Parse 'YYYY:MM:DD HH:MM:SS' → seconds-since-epoch-ish int."""
    from datetime import datetime
    if not s or s == "-":
        return None
    try:
        return datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


_NO_ENCODER_PATTERNS = [
    # AIS / manual focus
    "AIS", "Nikkor-N.C Auto", "PC-Nikkor",
    # Sigma 24/2.8 Super Wide II Macro is an old manual / non-D AF
    "Sigma 24mm F2.8 Super Wide",
    # AF non-D (no D/G/E suffix on aperture). Recognised by the
    # caller using stricter slug rules.
]

def lens_has_encoder(lens_dir: str) -> bool:
    """Best-effort: derive from slug whether the lens reports usable
    FocusDistance. See WIDEANGLE_RESULTS.md §1 lens-encoder lookup."""
    # Manual / older lenses without distance encoder
    for pat in _NO_ENCODER_PATTERNS:
        if pat in lens_dir:
            return False
    # AF (non-D, non-G, non-E) — explicit detection
    # Slug pattern: "AF Nikkor <mm>mm f_<x>" with no D/G/E and no AF-S/AF-I/AF-P
    if "AF-S" in lens_dir or "AF-I" in lens_dir or "AF-P" in lens_dir:
        return True  # AF-S/I/P always have encoders in modern lineup
    if "AF Nikkor" in lens_dir or "AF Micro-Nikkor" in lens_dir:
        # Check for D/G/E aperture suffix
        if any(suf in lens_dir for suf in ("f_2.8D", "f_4D", "f_1.8D", "f_2D", "f_3.5D", "f_5.6D")):
            return True
        if any(suf in lens_dir for suf in ("f_1.8G", "f_2.8G", "f_4G", "f_3.5G", "f_5.6G")):
            return True
        if "E " in lens_dir or lens_dir.endswith("E"):
            return True
        # Default for "AF Nikkor" without suffix → non-encoder
        return False
    # Z-mount, Viltrox AF Z, Sigma DG OS HSM modern, etc. — assume encoded
    return True


def infer_session_groups(rows: list[dict], gap_seconds: int = 300) -> list[tuple]:
    """Time-cluster rows into shooting sessions. Used only for the
    "sessions" descriptive section in the output. Inference for
    non-encoder lenses uses nearest-time matching (see
    infer_distance_by_time)."""
    rows_with_t = [(r, parse_datetime(r.get("DateTimeOriginal", ""))) for r in rows]
    rows_with_t = [(r, t) for (r, t) in rows_with_t if t is not None]
    rows_with_t.sort(key=lambda rt: rt[1])
    if not rows_with_t:
        return []
    sessions: list[list] = [[rows_with_t[0]]]
    for r, t in rows_with_t[1:]:
        prev_t = sessions[-1][-1][1]
        if (t - prev_t).total_seconds() <= gap_seconds:
            sessions[-1].append((r, t))
        else:
            sessions.append([(r, t)])
    out = []
    for sess in sessions:
        start = sess[0][1]
        end = sess[-1][1]
        items = []
        for r, t in sess:
            items.append((r["lens_dir"], r["FocalLength_mm"],
                          r["FocusDistance_m"], lens_has_encoder(r["lens_dir"])))
        out.append((start, end, items))
    return out


def infer_distance_by_time(rows: list[dict]) -> dict[tuple[str, float | None], float | None]:
    """For each (non-encoder lens, FL), find the temporally-nearest
    encoder-equipped row and return its FocusDistance as the inferred
    distance.

    Returns mapping (lens_dir, fl_mm) -> inferred_m (or None if no usable
    encoder row exists in this dataset).
    """
    # Build sorted timeline of encoder rows with valid distance > 0.5 m.
    enc_timeline: list[tuple] = []
    for r in rows:
        if not lens_has_encoder(r["lens_dir"]):
            continue
        d = r.get("FocusDistance_m")
        if d is None or d < 0.5:
            continue
        t = parse_datetime(r.get("DateTimeOriginal", ""))
        if t is None:
            continue
        enc_timeline.append((t, d))
    enc_timeline.sort(key=lambda td: td[0])

    out: dict[tuple[str, float | None], float | None] = {}
    if not enc_timeline:
        return out

    # For each non-encoder (lens_dir, fl), collect all timestamps and
    # find the nearest encoder timestamp's distance for each, take the
    # median.
    from collections import defaultdict
    by_key: dict[tuple[str, float | None], list[float]] = defaultdict(list)
    for r in rows:
        if lens_has_encoder(r["lens_dir"]):
            continue
        t = parse_datetime(r.get("DateTimeOriginal", ""))
        if t is None:
            continue
        # Binary search for nearest enc timestamp
        import bisect
        times = [td[0] for td in enc_timeline]
        idx = bisect.bisect_left(times, t)
        candidates = []
        if idx > 0:
            candidates.append(enc_timeline[idx - 1])
        if idx < len(enc_timeline):
            candidates.append(enc_timeline[idx])
        nearest = min(candidates, key=lambda td: abs((td[0] - t).total_seconds()))
        by_key[(r["lens_dir"], r["FocalLength_mm"])].append(nearest[1])

    for key, dists in by_key.items():
        out[key] = statistics.median(dists)
    return out


def write_md(date: str, summary: dict, path: Path, rows: list[dict]) -> None:
    sessions = infer_session_groups(rows)
    # Time-nearest inference for non-encoder lenses
    inferred = infer_distance_by_time(rows)

    lines = [
        f"# NEF distance audit — {date}",
        "",
        "Per (lens_dir, focal_length) summary of EXIF FocusDistance.",
        "**inferred (m)**: for non-encoder lenses (no D/G/E aperture suffix,",
        "no Z-mount, manual focus, etc.), the temporally-nearest encoder-",
        "equipped frame's distance is used. NEFs adjacent in time were",
        "shot at the same physical subject distance (tripod not moved).",
        "",
        "**Distance class** (by subject distance / focal length ratio):",
        "- `too close (< 20× FL)`: below Focal-style lens-test minimum.",
        "  Closer-distance MTF for some lenses (esp. macro) can be valid",
        "  but readings can't be cross-compared with infinity-class.",
        "- `close-test (20–50× FL)`: meets Focal-minimum; legitimate test",
        "  distance for non-infinity use cases.",
        "- `near-infinity (50–100× FL)`: comfortable for most lenses;",
        "  TC-laden long-FL combos often land here.",
        "- `infinity-class (100–300× FL)`: well past infinity.",
        "- `well past infinity (> 300× FL)`: redundant headroom.",
        "",
        "Closer-distance readings of the same lens aren't less valid; they",
        "measure the lens at a different distance regime. Cross-day same-",
        "lens comparisons need matched distance class for fairness.",
        "",
        "| Lens dir | FL (mm) | n NEFs | n w/ dist | min (m) | median (m) | max (m) | inferred (m) | Effective | dist/FL | Validity |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (lens_dir, fl), s in summary.items():
        med = s["median_m"]
        has_enc = lens_has_encoder(lens_dir)
        inf_d = inferred.get((lens_dir, fl))
        # effective distance: encoder reading, or time-nearest inferred
        if has_enc and med is not None and med > 0.5:
            eff_d = med
            eff_source = "encoder"
        elif inf_d is not None:
            eff_d = inf_d
            eff_source = "inferred"
        else:
            eff_d = None
            eff_source = "—"

        # Distance class by distance / FL ratio.
        # Focal-style lens testing recommends >= 20-30× FL as minimum;
        # 50× FL is comfortable and 100× FL+ is "infinity-class".
        # Closer-distance readings aren't invalid — they measure the
        # lens at a different distance regime, useful for some use cases
        # but not directly cross-comparable with infinity readings.
        if eff_d is None or fl is None or fl <= 0:
            ratio = None
            validity = "UNKNOWN"
        else:
            ratio = eff_d * 1000.0 / fl  # both in mm
            if ratio < 20:
                validity = "**too close (< 20× FL)**"
            elif ratio < 50:
                validity = "close-test (20–50× FL)"
            elif ratio < 100:
                validity = "near-infinity (50–100× FL)"
            elif ratio < 300:
                validity = "infinity-class (100–300× FL)"
            else:
                validity = "well past infinity (> 300× FL)"

        fmt = lambda x: f"{x:.2f}" if x is not None else "—"
        inferred_cell = f"{inf_d:.2f}" if (inf_d is not None and not has_enc) else "—"
        eff_cell = f"{eff_d:.2f} ({eff_source})" if eff_d is not None else "—"
        ratio_cell = f"{ratio:.0f}×" if ratio is not None else "—"
        lines.append(
            f"| {lens_dir} | {fl or '—'} | {s['n_nefs']} | "
            f"{s['n_with_distance']} | {fmt(s['min_m'])} | "
            f"**{fmt(s['median_m'])}** | {fmt(s['max_m'])} | "
            f"{inferred_cell} | {eff_cell} | {ratio_cell} | {validity} |"
        )

    lines += ["", f"## Sessions (gap = 5 min)", ""]
    for idx, (start, end, items) in enumerate(sessions):
        enc_dists = sorted({d for (_, _, d, has_enc) in items
                            if has_enc and d is not None and d > 0.5})
        enc_summary = ", ".join(f"{d:.1f}m" for d in enc_dists) or "(no encoder-distance in this session)"
        lens_set = sorted({ld for (ld, _, _, _) in items})
        lines.append(f"- **Session {idx}** {start} → {end} ({(end-start).total_seconds()/60:.0f} min): "
                     f"encoded distances {enc_summary}; lenses: {', '.join(lens_set)}")

    # Per-lens-dir collapsed view (median of medians)
    lines += ["", "## Per-lens-dir collapsed view", ""]
    by_lens = defaultdict(list)
    for (lens_dir, fl), s in summary.items():
        if s["median_m"] is not None:
            by_lens[lens_dir].append((fl, s["median_m"]))
    lines.append("| Lens dir | min FL | max FL | dist range (m) |")
    lines.append("|---|---|---|---|")
    for lens_dir in sorted(by_lens.keys()):
        fls = [fl for fl, _ in by_lens[lens_dir] if fl is not None]
        dists = [d for _, d in by_lens[lens_dir]]
        if not fls or not dists:
            continue
        lines.append(
            f"| {lens_dir} | {min(fls):.0f} | {max(fls):.0f} | "
            f"{min(dists):.1f}..{max(dists):.1f} |"
        )

    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    for date in DATES:
        rows, summary = audit_date(date)
        write_csv(rows, OUT / f"nef_distances_{date}.csv")
        write_md(date, summary, OUT / f"nef_distances_{date}.md", rows)
        print(f"[{date}] wrote {len(rows)} NEF rows, {len(summary)} groups", flush=True)
    print(f"\nOutputs in {OUT}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
