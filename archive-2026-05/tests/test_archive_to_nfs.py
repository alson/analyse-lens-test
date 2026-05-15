"""Unit tests for archive_2026_05.archive_to_nfs pure helpers."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pytest

from archive_2026_05 import manifest
from archive_2026_05.archive_to_nfs import (
    archive_12_dir_name,
    build_metadata,
    find_broken_symlinks,
    parse_merged_symlink_target,
    rewrite_merged_symlinks,
    slice_shots_csv,
)
from archive_2026_05.manifest import Entry, calibration_methodology


# ---- archive_12_dir_name --------------------------------------------------


class TestArchive12DirName:
    def test_appends_session_id_in_parens(self) -> None:
        assert archive_12_dir_name(
            "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T",
            "2026-05-13_230021",
        ) == "Sigma APO Macro 150mm F2.8 EX DG OS HSM + 5T (2026-05-13_230021)"

    def test_disambiguates_same_slug_across_sessions(self) -> None:
        # The four ⛔ MC 105 + 61mm dev-era shoots all share a slug;
        # the dir-name function must produce four distinct paths.
        slug = "NIKKOR Z MC 105mm f_2.8 VR S + 61mm extension"
        names = {
            archive_12_dir_name(slug, sid)
            for sid in (
                "2026-05-05_133416", "2026-05-05_175758",
                "2026-05-05_205830", "2026-05-06_175727",
            )
        }
        assert len(names) == 4


# ---- calibration_methodology ----------------------------------------------


class TestCalibrationMethodology:
    def test_pre_cascade_for_early_may(self) -> None:
        assert calibration_methodology("2026-05-06T23:18:05+00:00") == "pre-cascade-fix"

    def test_post_cascade_just_after_cutoff(self) -> None:
        # Cutoff is 2026-05-13T23:00 UTC; one minute after is post.
        assert calibration_methodology("2026-05-13T23:01:00+00:00") == "post-cascade-fix"

    def test_post_cascade_well_after_cutoff(self) -> None:
        assert calibration_methodology("2026-05-15T09:34:55+00:00") == "post-cascade-fix"

    def test_pre_cascade_just_before_cutoff(self) -> None:
        assert calibration_methodology("2026-05-13T22:59:59+00:00") == "pre-cascade-fix"

    def test_empty_returns_unknown(self) -> None:
        assert calibration_methodology("") == "unknown"

    def test_unparseable_returns_unknown(self) -> None:
        assert calibration_methodology("not a date") == "unknown"


# ---- parse_merged_symlink_target ------------------------------------------


class TestParseMergedSymlinkTarget:
    def test_top_level_jpeg(self) -> None:
        # Real shape from merged_100-400-35mm_2026-05-15.
        target = "../../../2026-05-15_093455/NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension/f_11/step_0150.jpg"
        parsed = parse_merged_symlink_target(target)
        assert parsed == (
            "2026-05-15_093455",
            "NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension",
            ["f_11", "step_0150.jpg"],
        )

    def test_cropped_jpeg(self) -> None:
        # Cropped symlinks are 5 levels up instead of 3.
        target = "../../../../../2026-05-15_112642/NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension/f_11/cropped/center/step_0100.jpg"
        parsed = parse_merged_symlink_target(target)
        assert parsed is not None
        sid, slug, rest = parsed
        assert sid == "2026-05-15_112642"
        assert slug == "NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension"
        assert rest == ["f_11", "cropped", "center", "step_0100.jpg"]

    def test_returns_none_for_non_merged_target(self) -> None:
        assert parse_merged_symlink_target("../../foo/bar.jpg") is None

    def test_returns_none_when_no_session_id_in_path(self) -> None:
        assert parse_merged_symlink_target("/absolute/path/no_date/file.jpg") is None


# ---- slice_shots_csv ------------------------------------------------------


def _write_csv(path: Path, header: str, rows: list[str]) -> None:
    path.write_text(
        header + "\n" + "\n".join(rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


class TestSliceShotsCsv:
    def test_keeps_only_matching_slug(self, tmp_path: Path) -> None:
        src = tmp_path / "shots.csv"
        dst = tmp_path / "out.csv"
        _write_csv(
            src,
            "timestamp,session_id,lens_config_slug,rail_step,rail_position_mm,aperture,iso,shutter_speed,fec,median,ev,filename,phase,notes,mag,fring,focal",
            [
                "2026-05-01T00:00:00,SID,Lens A,0,0.0,f/4,100,,0,100,0,a.jpg,sweep,,,,",
                "2026-05-01T00:00:01,SID,Lens B,0,0.0,f/4,100,,0,100,0,b.jpg,sweep,,,,",
                "2026-05-01T00:00:02,SID,Lens A,1,-0.5,f/4,100,,0,100,0,c.jpg,sweep,,,,",
            ],
        )
        rows = slice_shots_csv(src, "Lens A", dst)
        assert rows == 2
        out_lines = dst.read_text().splitlines()
        # header + 2 matching rows
        assert len(out_lines) == 3
        assert out_lines[0].startswith("timestamp,session_id,lens_config_slug")
        assert all("Lens A" in line for line in out_lines[1:])

    def test_header_only_when_no_matches(self, tmp_path: Path) -> None:
        src = tmp_path / "shots.csv"
        dst = tmp_path / "out.csv"
        _write_csv(
            src,
            "timestamp,session_id,lens_config_slug,rail_step",
            ["2026-05-01T00:00:00,SID,Other Lens,0"],
        )
        rows = slice_shots_csv(src, "Lens A", dst)
        assert rows == 0
        assert dst.read_text().splitlines() == ["timestamp,session_id,lens_config_slug,rail_step"]

    def test_raises_when_header_lacks_slug_column(self, tmp_path: Path) -> None:
        src = tmp_path / "shots.csv"
        dst = tmp_path / "out.csv"
        _write_csv(src, "a,b,c", ["1,2,3"])
        with pytest.raises(RuntimeError, match="lens_config_slug"):
            slice_shots_csv(src, "anything", dst)


# ---- build_metadata -------------------------------------------------------


class TestBuildMetadata:
    def test_picks_matching_lens_config_entry(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "2026-05-13_230021"
        session_dir.mkdir()
        (session_dir / "session.json").write_text(json.dumps({
            "session_id": "2026-05-13_230021",
            "started_at": "2026-05-13T23:00:21+00:00",
            "ended_at": "2026-05-14T11:00:00+00:00",
            "lens_configs": [
                {"slug": "Other", "magnification": 1.0, "widest_aperture": 4.0, "sample_plan": {}},
                {"slug": "Sigma 150 + 5T", "magnification": 1.3, "widest_aperture": 2.8, "sample_plan": {"rail_step_mm": 0.046}},
            ],
        }))
        entry = Entry("2026-05-13_230021", "Sigma 150 + 5T", "superseded", "test")
        meta = build_metadata(session_dir, entry)
        assert meta["lens_config"]["magnification"] == 1.3
        assert meta["lens_config"]["sample_plan"] == {"rail_step_mm": 0.046}
        assert meta["lens_config"]["magnification_verified_via_wafer_squares"] is None
        assert meta["role"] == "superseded"
        assert meta["reason"] == "test"
        # Cutoff is exactly 23:00:00; 23:00:21 is post.
        assert meta["calibration_methodology"] == "post-cascade-fix"

    def test_synthesises_lens_config_when_session_lacks_it(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "2026-05-15_093455"
        session_dir.mkdir()
        (session_dir / "session.json").write_text(json.dumps({
            "session_id": "2026-05-15_093455",
            "started_at": "2026-05-15T09:34:55+00:00",
            "lens_configs": [],
        }))
        entry = Entry("2026-05-15_093455", "100-400 + 61mm", "canonical")
        meta = build_metadata(session_dir, entry)
        assert meta["lens_config"]["slug"] == "100-400 + 61mm"
        assert meta["lens_config"]["magnification"] is None
        assert meta["role"] == "canonical"
        assert meta["reason"] is None

    def test_handles_missing_session_json(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "2026-05-99_999999"
        session_dir.mkdir()
        entry = Entry("2026-05-99_999999", "Some lens", "canonical")
        meta = build_metadata(session_dir, entry)
        assert meta["lens_config"]["slug"] == "Some lens"
        assert meta["calibration_methodology"] == "unknown"


# ---- find_broken_symlinks + rewrite_merged_symlinks -----------------------


class TestSymlinkRewriting:
    """Build a miniature NFS layout in tmp_path and exercise the
    symlink rewrite end-to-end. The 2026-05-13 dst is flat-slug
    (matching the existing 2026-01-29 convention) so the symlinks
    sit one level shallower than the source merged tree."""

    def test_rewrites_known_targets_and_leaves_unknown_alone(
        self, tmp_path: Path,
    ) -> None:
        # Build the source-side merge target dir under 2026-05-12.
        slug = "Sample Lens + 1mm"
        sid = "2026-05-15_120000"
        src_session_dir = tmp_path / "2026-05-12" / f"{slug} ({sid})"
        ap_dir = src_session_dir / "f_11"
        ap_dir.mkdir(parents=True)
        (ap_dir / "step_0100.jpg").write_bytes(b"x")
        cropped_dir = ap_dir / "cropped" / "center"
        cropped_dir.mkdir(parents=True)
        (cropped_dir / "step_0100.jpg").write_bytes(b"x")

        # Build the merged-config dir under 2026-05-13 as flat slug.
        # The symlinks have the merge tool's original 3-up / 5-up
        # relative shape — they get rewritten to point at 2026-05-12
        # via the new relative depth (one level shallower than before).
        merged_dst = tmp_path / "2026-05-13" / slug / "f_11"
        merged_dst.mkdir(parents=True)
        (merged_dst / "cropped" / "center").mkdir(parents=True)
        top_link = merged_dst / "cur_step_0100.jpg"
        top_link.symlink_to(f"../../../{sid}/{slug}/f_11/step_0100.jpg")
        crop_link = merged_dst / "cropped" / "center" / "cur_step_0100.jpg"
        crop_link.symlink_to(f"../../../../../{sid}/{slug}/f_11/cropped/center/step_0100.jpg")

        lookup = {(sid, slug): src_session_dir}
        rewrite_merged_symlinks(tmp_path / "2026-05-13" / slug, lookup)

        assert top_link.exists(), f"top link broken: {os.readlink(top_link)}"
        assert crop_link.exists(), f"crop link broken: {os.readlink(crop_link)}"
        new_top = os.readlink(top_link)
        assert "2026-05-12" in new_top and f"({sid})" in new_top
        # Depth check: top-level symlink is at <root>/2026-05-13/<slug>/f_11/
        # → up 3 to reach root → down into 2026-05-12. So 3× '..' prefix.
        assert new_top.startswith("../../../2026-05-12/")

    def test_leaves_non_merged_targets_alone(self, tmp_path: Path) -> None:
        merged_dir = tmp_path / "2026-05-13" / "merged_test"
        merged_dir.mkdir(parents=True)
        sibling = tmp_path / "elsewhere"
        sibling.mkdir()
        target = sibling / "foo.jpg"
        target.write_bytes(b"x")
        link = merged_dir / "foo.jpg"
        # A symlink whose target has no session-id pattern shouldn't
        # be rewritten — leave it as-is.
        link.symlink_to(os.path.relpath(target, link.parent))
        rewrite_merged_symlinks(merged_dir, {})
        assert link.exists()

    def test_find_broken_symlinks_reports_unresolved(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        (root / "good.jpg").write_bytes(b"x")
        (root / "good_link.jpg").symlink_to("good.jpg")
        (root / "bad_link.jpg").symlink_to("nowhere.jpg")
        broken = find_broken_symlinks(root)
        assert [b.name for b in broken] == ["bad_link.jpg"]


# ---- manifest sanity ------------------------------------------------------


class TestManifestSanity:
    def test_every_entry_has_a_known_role(self) -> None:
        roles = {e.role for e in manifest.ENTRIES}
        assert roles <= {"canonical", "superseded", "merge_source", "labeled_duplicate"}

    def test_session_in_skip_list_does_not_also_have_entries(self) -> None:
        # A session can't be both "skip" and have ⭐/⛔ entries.
        offenders = [
            e for e in manifest.ENTRIES if e.session_id in manifest.SKIP_SESSIONS
        ]
        assert not offenders, f"skip-list sessions with entries: {offenders}"

    def test_role_counts_match_audit(self) -> None:
        # Spot-check the totals against the audit doc so a manifest
        # edit that drops/duplicates rows fails fast.
        canonical = manifest.entries_by_role("canonical")
        superseded = manifest.entries_by_role("superseded")
        merge_source = manifest.entries_by_role("merge_source")
        labeled_duplicate = manifest.entries_by_role("labeled_duplicate")
        # 26 canonical + 1 labeled_duplicate = 27 ⭐-tier entries total.
        assert len(canonical) == 26, len(canonical)
        assert len(superseded) == 10, len(superseded)
        assert len(merge_source) == 11, len(merge_source)
        assert len(labeled_duplicate) == 1, len(labeled_duplicate)

    def test_merged_dirs_count(self) -> None:
        assert len(manifest.MERGED_DIRS) == 4
