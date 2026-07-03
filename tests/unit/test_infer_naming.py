from __future__ import annotations

from konpy.infer.naming import slugify, top_level_segment


class TestSlugify:
    def test_empty_string_is_root(self) -> None:
        assert slugify("") == "root"

    def test_nested_path(self) -> None:
        assert slugify("src/konpy/services") == "src-konpy-services"

    def test_collapses_and_strips_separators(self) -> None:
        assert slugify("Src//Foo_Bar") == "src-foo-bar"

    def test_leading_and_trailing_separators_stripped(self) -> None:
        assert slugify("/src/foo/") == "src-foo"


class TestTopLevelSegment:
    def test_nested_path(self) -> None:
        assert top_level_segment("src/x.py") == "src"

    def test_root_file(self) -> None:
        assert top_level_segment("x.py") == ""
