"""Unit tests for sort_to_lens_tree."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from archive_2026_05.sort_to_lens_tree import (
    FilenameParts,
    apply_plan,
    parse_digikam_filename,
    plan_sort,
)


# ---- Filename parsing -----------------------------------------------------


class TestParseDigikamFilename:
    def test_canonical_2026_01_29_filename(self) -> None:
        parts = parse_digikam_filename(
            "03211|Sigma APO Macro 150mm F2.8 EX DG OS HSM|1_1|150.0 mm|F11|alm-20260130-212359-655.jpg"
        )
        assert parts is not None
        assert parts.seq == "03211"
        assert parts.slug == "Sigma APO Macro 150mm F2.8 EX DG OS HSM"
        assert parts.mag == "1_1"
        assert parts.focal == "150.0 mm"
        assert parts.aperture == "F11"
        assert parts.orig == "alm-20260130-212359-655.jpg"

    def test_2026_05_runner_filename(self) -> None:
        # Step 3 produces these from the runner's step_NNNN.jpg files.
        parts = parse_digikam_filename(
            "00001|NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension|1_2.1|400.0 mm|F8|step_0127.jpg"
        )
        assert parts is not None
        assert parts.slug == "NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension"
        assert parts.mag == "1_2.1"
        assert parts.aperture == "F8"
        assert parts.orig == "step_0127.jpg"

    def test_replica_suffix_preserved(self) -> None:
        # Runner replicas use step_NNNN_b.jpg / step_NNNN_c.jpg.
        parts = parse_digikam_filename(
            "00042|MyLens|1.3_1|150.0 mm|F11|step_0127_b.jpg"
        )
        assert parts is not None
        assert parts.orig == "step_0127_b.jpg"

    def test_non_digikam_returns_none(self) -> None:
        assert parse_digikam_filename("step_0127.jpg") is None
        assert parse_digikam_filename("bogus.jpg") is None


# ---- End-to-end sort on a synthetic slug ---------------------------------


def _populate_slug(
    slug_dir: Path, mag: str, focal: str, apertures: list[str],
    *, files_per_aperture: int = 2,
) -> None:
    """Build a slug dir in the post-step-3 shape:
    <slug>/F<n>/<renamed>.jpg  + <slug>/F<n>/cropped/center/<renamed>.jpg
    """
    slug = slug_dir.name
    slug_dir.mkdir(parents=True, exist_ok=True)
    csv_path = slug_dir / "shots.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "aperture", "rail_position_mm"])
        seq = 1
        for ap in apertures:
            f_dir = slug_dir / ap
            f_dir.mkdir()
            crop_dir = f_dir / "cropped" / "center"
            crop_dir.mkdir(parents=True)
            for i in range(files_per_aperture):
                basename = (
                    f"{seq:05d}|{slug}|{mag}|{focal}|{ap}|step_{100 + i:04d}.jpg"
                )
                (f_dir / basename).write_bytes(b"jpeg")
                (crop_dir / basename).write_bytes(b"crop")
                writer.writerow([f"{ap}/{basename}", f"f/{ap[1:]}", -0.1 * seq])
                seq += 1
    (slug_dir / "metadata.json").write_text('{"slug": "%s"}' % slug)


class TestSortEndToEnd:
    def test_single_mag_slug_gets_sorted(self, tmp_path: Path) -> None:
        slug = "MyLens + 5T"
        slug_dir = tmp_path / "2026-05-13" / slug
        _populate_slug(slug_dir, mag="1.3_1", focal="150.0 mm",
                       apertures=["F11", "F8"])
        plan = plan_sort(slug_dir)
        assert plan is not None
        assert plan.mag == "1.3_1"
        assert plan.focal == "150.0 mm"
        apply_plan(plan, dry_run=False)
        # Target layout exists.
        target = slug_dir / "1.3_1" / "150.0 mm"
        assert (target / "F11").is_dir()
        assert (target / "F8").is_dir()
        # F-dirs are no longer at the slug level.
        assert not (slug_dir / "F11").exists()
        assert not (slug_dir / "F8").exists()
        # cropped/ rode along.
        assert any((target / "F11" / "cropped" / "center").glob("*.jpg"))
        # shots.csv moved + paths updated with prefix.
        moved_csv = target / "shots.csv"
        assert moved_csv.is_file()
        assert not (slug_dir / "shots.csv").exists()
        with moved_csv.open() as f:
            rows = list(csv.DictReader(f))
        assert all(r["filename"].startswith("1.3_1/150.0 mm/") for r in rows)
        # metadata.json moved.
        assert (target / "metadata.json").is_file()
        assert not (slug_dir / "metadata.json").exists()

    def test_dry_run_makes_no_changes(self, tmp_path: Path) -> None:
        slug_dir = tmp_path / "2026-05-13" / "X"
        _populate_slug(slug_dir, "1_1", "100.0 mm", ["F8"])
        original_listing = sorted(p.relative_to(slug_dir).as_posix()
                                  for p in slug_dir.rglob("*"))
        plan = plan_sort(slug_dir)
        apply_plan(plan, dry_run=True)
        new_listing = sorted(p.relative_to(slug_dir).as_posix()
                             for p in slug_dir.rglob("*"))
        assert new_listing == original_listing

    def test_already_sorted_is_noop(self, tmp_path: Path) -> None:
        # Build a slug that's already at <mag>/<focal>/F<n>/ shape;
        # plan_sort should return None.
        slug_dir = tmp_path / "2026-05-13" / "X"
        f_dir = slug_dir / "1_1" / "100.0 mm" / "F8"
        f_dir.mkdir(parents=True)
        (f_dir / "00001|X|1_1|100.0 mm|F8|step_0001.jpg").write_bytes(b"x")
        plan = plan_sort(slug_dir)
        assert plan is None

    def test_refuses_mixed_mag(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        slug_dir = tmp_path / "2026-05-13" / "X"
        (slug_dir / "F11").mkdir(parents=True)
        (slug_dir / "F8").mkdir()
        (slug_dir / "F11" / "00001|X|1_1|100.0 mm|F11|a.jpg").write_bytes(b"x")
        (slug_dir / "F8" / "00002|X|1.3_1|100.0 mm|F8|b.jpg").write_bytes(b"x")
        plan = plan_sort(slug_dir)
        assert plan is None
        captured = capsys.readouterr()
        assert "mixed" in captured.err.lower()
