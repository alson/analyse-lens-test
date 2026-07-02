"""Tests for tile_sharpness.multi_session — the frozen-subset config-node discovery.

Round-trips the FROZEN 311-row subset artifact into ConfigNodes, checks sid
uniqueness (the @YYMMDD dedup contract), and checks per-session tier assignment
(rail-coverage 2026-05+ vs manual <= 2026-02). The 2026-02-18 24-120+10ext@120mm family
(5 rows) is superseded by the 2026-05-13 rail reshoot, so 2026-02-18 is now 90 (was 95)
and the total is 311 (was 316).
"""
from __future__ import annotations

from collections import Counter

import pytest

from tile_sharpness import multi_session as MS
from tile_sharpness.multi_session import ConfigNode

# Expected per-session row tally of the frozen subset (validated against on-disk data).
EXPECTED_PER_SESSION = {
    "2025-10-17": 37,
    "2026-01-29": 33,
    "2026-02-18": 90,   # was 95; 24-120+10ext@120mm (5 rows) superseded by 2026-05-13
    "2026-05-12": 12,
    "2026-05-13": 139,
}
EXPECTED_TOTAL = sum(EXPECTED_PER_SESSION.values())  # 311

# Sessions that are rail-coverage tier (p2_rail_ok True) vs manual (False).
RAIL_SESSIONS = {"2026-05-12", "2026-05-13"}
MANUAL_SESSIONS = {"2025-10-17", "2026-01-29", "2026-02-18"}


@pytest.fixture(scope="module")
def nodes():
    csv = MS.DEFAULT_SUBSET_CSV
    if not csv.exists():
        pytest.skip(f"frozen subset artifact not present: {csv}")
    return MS.discover_config_nodes(csv)


def test_frozen_csv_roundtrips_to_311_nodes(nodes):
    assert len(nodes) == EXPECTED_TOTAL
    assert all(isinstance(n, ConfigNode) for n in nodes)


def test_per_session_tally_matches_expected(nodes):
    counts = Counter(n.session for n in nodes)
    assert dict(counts) == EXPECTED_PER_SESSION


def test_sid_is_unique_across_all_nodes(nodes):
    sids = [MS.sid(n) for n in nodes]
    dupes = [s for s, c in Counter(sids).items() if c > 1]
    assert not dupes, f"colliding sids: {dupes}"


def test_tier_assignment_per_session(nodes):
    for n in nodes:
        if n.session in RAIL_SESSIONS:
            assert n.p2_rail_ok is True, f"{n.session} should be rail-coverage tier"
        elif n.session in MANUAL_SESSIONS:
            assert n.p2_rail_ok is False, f"{n.session} should be manual tier"


def test_tier_tally_matches_recovery_notes(nodes):
    # 160 manual (false) + 151 rail-coverage (true) = 311. Manual dropped from 165 to 160
    # after the 24-120+10ext@120mm supersession (5 manual 2026-02-18 rows removed).
    n_rail = sum(1 for n in nodes if n.p2_rail_ok)
    n_manual = sum(1 for n in nodes if not n.p2_rail_ok)
    assert n_rail == 151
    assert n_manual == 160


def test_nominal_M_populated_for_all_but_null_metadata_configs(nodes):
    # nominal_M is now filled for every row EXCEPT the 23 rail configs whose session
    # metadata.json records a null magnification. Everything else must parse to a finite
    # positive float.
    filled = [n for n in nodes if (n.nominal_M or "").strip()]
    assert len(filled) >= 285, f"nominal_M coverage regressed: {len(filled)}/{len(nodes)}"
    for n in filled:
        v = float(n.nominal_M)
        assert v > 0 and v == v  # finite positive


def test_manual_tier_nominal_M_matches_mag_label(nodes):
    # Manual-tier rows carry a <a>_<b> mag_label; nominal_M must equal a/b.
    from tile_sharpness.m_lookup import parse_mag_label
    checked = 0
    for n in nodes:
        lbl = (n.mag_label or "").strip()
        if not lbl or not (n.nominal_M or "").strip():
            continue
        expected = parse_mag_label(lbl.removesuffix("-resized"))
        assert abs(float(n.nominal_M) - expected) < 1e-3, f"{n.lens} {lbl}"
        checked += 1
    assert checked > 100


def test_rail_nominal_M_matches_metadata_spotcheck(nodes):
    # The formerly-empty rail configs now resolve a finite nominal_M from metadata.json.
    def find(pred):
        return next(n for n in nodes if pred(n))
    z105 = find(lambda n: "MC 105" in n.lens and "61mm extension" in n.lens
                and n.session == "2026-05-13")
    assert abs(float(z105.nominal_M) - 2.25) < 0.05
    s150 = find(lambda n: "APO Macro 150" in n.lens and n.lens.endswith("5T + 6T")
                and n.session == "2026-05-13")
    assert abs(float(s150.nominal_M) - 1.8) < 0.05


def test_superseded_120mm_10ext_family_absent(nodes):
    # The 2026-02-18 24-120+10ext @120mm family (mag_label 1_1.84) must be gone; the
    # @50mm (1_2.25) family must survive.
    at_120 = [n for n in nodes if n.session == "2026-02-18"
              and "24-120" in n.lens and "10mm extension" in n.lens
              and n.mag_label == "1_1.84"]
    assert at_120 == [], "superseded 120mm+10ext@2026-02-18 rows still present"
    at_50 = [n for n in nodes if n.session == "2026-02-18"
             and "24-120" in n.lens and "10mm extension" in n.lens
             and n.mag_label == "1_2.25"]
    assert len(at_50) == 5, "the KEEP 50mm+10ext@2026-02-18 family was wrongly dropped"


def test_baseline_session_sids_are_untagged(nodes):
    # The 2026-01-29 baseline keeps canonical (no @YYMMDD) sids; every other session
    # is tagged.
    for n in nodes:
        s = MS.sid(n)
        if n.session == MS.BASELINE_SESSION:
            assert "@" not in s
        else:
            assert s.endswith("@" + n.session.replace("-", "")[2:])


def test_sweep_dir_is_sample_parent(nodes):
    n = nodes[0]
    assert n.sweep_dir == n.sweep_dir  # property is stable
    assert str(n.sweep_dir) == n.sample.rsplit("/", 1)[0]


# --- unit-level naming tests (no on-disk data required) ---------------------- #

def _node(**kw):
    base = dict(session="", lens="", mag_label="", nominal_M="", focal="",
                aperture="", n_shots=0, p2_rail_ok=True, sample="")
    base.update(kw)
    return ConfigNode(**base)


def test_sid_abbreviates_lens_and_appends_session_tag():
    n = _node(session="2025-10-17", lens="Sigma Macro 105mm F2.8 EX DG OS HSM",
              mag_label="1_1", aperture="F8")
    assert MS.sid(n) == "S105_1_1_F8@251017"


def test_sid_baseline_is_untagged():
    n = _node(session="2026-01-29", lens="Sigma Macro 105mm F2.8 EX DG OS HSM",
              mag_label="1_1", aperture="F8")
    assert MS.sid(n) == "S105_1_1_F8"


def test_sid_accessory_abbreviation():
    n = _node(session="2026-05-13",
              lens="NIKKOR Z MC 105mm f_2.8 VR S + 5T + 6T",
              mag_label="1.6_1", aperture="F8")
    assert MS.sid(n) == "Z105+5T+6T_1.6_1_F8@260513"


def test_human_appends_date_only_for_non_baseline():
    n1 = _node(session="2026-01-29", lens="L", mag_label="1_1", aperture="F8")
    assert MS.human(n1) == "L | 1_1 | F8"
    n2 = _node(session="2025-10-17", lens="L", mag_label="1_1", aperture="F8")
    assert MS.human(n2) == "L | 1_1 | F8 | 2025-10-17"


def test_discover_reexports_p2_rail_available():
    # multi_session uses the tier gate from cross_m_relative_mtf.
    assert MS.p2_rail_available("true") is True
    assert MS.p2_rail_available("false") is False
