from __future__ import annotations

from pathlib import Path

import pytest

from rail_coverage.labels import (
    aperture_sort_key,
    parse_magnification,
    parse_scenario_label,
    slugify,
)


class TestParseMagnification:
    @pytest.mark.parametrize(
        "folder,pretty,value",
        [
            ("1_1", "1:1", 1.0),
            ("1.4_1", "1.4:1", 1.4),
            ("1_1.33", "1:1.33", pytest.approx(1 / 1.33)),
            ("2_1", "2:1", 2.0),
            ("1_1-resized", "1:1 (resized)", 1.0),
            ("2_1-resized", "2:1 (resized)", 2.0),
        ],
    )
    def test_round_trip(self, folder: str, pretty: str, value: float):
        p, v = parse_magnification(folder)
        assert p == pretty
        assert v == value

    def test_unparseable_falls_back(self):
        assert parse_magnification("garbage") == ("garbage", 0.0)
        assert parse_magnification("foo_bar") == ("foo_bar", 0.0)
        assert parse_magnification("1_0") == ("1_0", 0.0)


class TestParseScenarioLabel:
    def test_four_level_layout(self):
        path = Path("/data/Sigma APO Macro 150mm/1_1/210.0 mm/F8/cropped")
        lbl = parse_scenario_label(path)
        assert lbl.lens == "Sigma APO Macro 150mm"
        assert lbl.magnification == "1_1"
        assert lbl.magnification_pretty == "1:1"
        assert lbl.focal_length == "210.0 mm"
        assert lbl.aperture == "F8"
        assert lbl.magnification_value == 1.0

    def test_three_level_layout_no_focal_length(self):
        # Real path from the 2026-01-29 dataset — no focal-length subdir
        path = Path(
            "/data/2026-01-29/Sigma APO Macro 150mm F2.8 EX DG OS HSM/1_1/F8/cropped"
        )
        lbl = parse_scenario_label(path)
        assert lbl.lens == "Sigma APO Macro 150mm F2.8 EX DG OS HSM"
        assert lbl.magnification == "1_1"
        assert lbl.focal_length == ""
        assert lbl.aperture == "F8"

    def test_three_level_layout_with_decimal_mag(self):
        path = Path("/data/some-date/Nikon 70-180mm/1_1.33/F11/cropped")
        lbl = parse_scenario_label(path)
        assert lbl.lens == "Nikon 70-180mm"
        assert lbl.magnification == "1_1.33"
        assert lbl.focal_length == ""
        assert lbl.aperture == "F11"

    def test_resized_suffix_in_pretty(self):
        path = Path("/data/Lens/1_1-resized/100mm/F8/cropped")
        lbl = parse_scenario_label(path)
        assert lbl.magnification_pretty == "1:1 (resized)"

    def test_rejects_non_cropped_path(self):
        with pytest.raises(ValueError, match="cropped"):
            parse_scenario_label(Path("/data/something/else"))

    def test_shallow_path_raises(self):
        with pytest.raises(ValueError, match="not deep enough"):
            parse_scenario_label(Path("/cropped"))


class TestApertureSortKey:
    def test_numeric_sort(self):
        apertures = ["F11", "F2.8", "F8", "F5.6", "F16"]
        assert sorted(apertures, key=aperture_sort_key) == [
            "F2.8",
            "F5.6",
            "F8",
            "F11",
            "F16",
        ]

    def test_unparseable_sorts_last(self):
        apertures = ["F8", "weird", "F2.8"]
        assert sorted(apertures, key=aperture_sort_key) == ["F2.8", "F8", "weird"]


class TestSlugify:
    def test_replaces_separators(self):
        s = slugify(Path("/foo/Sigma APO Macro 150mm/1_1/F8/cropped"))
        assert "/" not in s
        assert " " not in s
        # all chars are alnum / _ / . / -
        assert all(c.isalnum() or c in "._-" for c in s)

    def test_idempotent_for_clean_input(self):
        s = slugify(Path("simple"))
        assert s == "simple"
