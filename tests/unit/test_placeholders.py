import pytest

from konpy.core.placeholders import PlaceholderValue


class TestToString:
    @pytest.mark.parametrize("value", ["openai", "test-utils", "test_utils", "a"])
    def test_returns_raw_value(self, value: str) -> None:
        assert PlaceholderValue(value).to_string() == value


class TestToPascalCase:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("openai", "Openai"),
            ("test-utils", "TestUtils"),
            ("test_utils", "TestUtils"),
            ("testUtils", "TestUtils"),
            ("a", "A"),
            ("my-test-utils", "MyTestUtils"),
        ],
    )
    def test_algorithmic(self, value: str, expected: str) -> None:
        assert PlaceholderValue(value).to_pascal_case() == expected

    def test_uses_kebab_to_pascal_map(self) -> None:
        placeholder = PlaceholderValue("openai", kebab_to_pascal_map={"openai": "OpenAI"})
        assert placeholder.to_pascal_case() == "OpenAI"

    def test_falls_back_when_kebab_map_has_no_entry(self) -> None:
        placeholder = PlaceholderValue("cache", kebab_to_pascal_map={"openai": "OpenAI"})
        assert placeholder.to_pascal_case() == "Cache"

    def test_uses_camel_to_pascal_map(self) -> None:
        placeholder = PlaceholderValue("openAI", camel_to_pascal_map={"openAI": "OpenAI"})
        assert placeholder.to_pascal_case() == "OpenAI"

    def test_prefers_kebab_map_over_camel_map(self) -> None:
        placeholder = PlaceholderValue(
            "openai",
            kebab_to_pascal_map={"openai": "OpenAI"},
            camel_to_pascal_map={"openai": "Openai"},
        )
        assert placeholder.to_pascal_case() == "OpenAI"

    def test_falls_back_when_camel_map_has_no_entry(self) -> None:
        placeholder = PlaceholderValue("testUtils", camel_to_pascal_map={"openAI": "OpenAI"})
        assert placeholder.to_pascal_case() == "TestUtils"


class TestToCamelCase:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Openai", "openai"),
            ("test-utils", "testUtils"),
            ("test_utils", "testUtils"),
            ("A", "a"),
        ],
    )
    def test_algorithmic(self, value: str, expected: str) -> None:
        assert PlaceholderValue(value).to_camel_case() == expected

    def test_uses_kebab_to_camel_map(self) -> None:
        placeholder = PlaceholderValue("openai", kebab_to_camel_map={"openai": "openAI"})
        assert placeholder.to_camel_case() == "openAI"

    def test_falls_back_to_pascal_map_with_lowercased_first_char(self) -> None:
        placeholder = PlaceholderValue("graphql", kebab_to_pascal_map={"graphql": "GraphQL"})
        assert placeholder.to_camel_case() == "graphQL"

    def test_prefers_kebab_to_camel_map_over_pascal_map(self) -> None:
        placeholder = PlaceholderValue(
            "openai",
            kebab_to_pascal_map={"openai": "OpenAI"},
            kebab_to_camel_map={"openai": "openAI"},
        )
        assert placeholder.to_camel_case() == "openAI"

    def test_falls_back_when_no_map_entry(self) -> None:
        placeholder = PlaceholderValue("cache", kebab_to_pascal_map={"openai": "OpenAI"})
        assert placeholder.to_camel_case() == "cache"

    def test_uses_pascal_to_camel_map(self) -> None:
        placeholder = PlaceholderValue("OpenAI", pascal_to_camel_map={"OpenAI": "openAI"})
        assert placeholder.to_camel_case() == "openAI"

    def test_prefers_kebab_to_camel_map_over_pascal_to_camel_map(self) -> None:
        placeholder = PlaceholderValue(
            "openai",
            kebab_to_camel_map={"openai": "openAI"},
            pascal_to_camel_map={"openai": "openai"},
        )
        assert placeholder.to_camel_case() == "openAI"

    def test_falls_back_when_pascal_to_camel_map_has_no_entry(self) -> None:
        placeholder = PlaceholderValue("TestUtils", pascal_to_camel_map={"OpenAI": "openAI"})
        assert placeholder.to_camel_case() == "testUtils"


class TestToKebabCase:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Openai", "openai"),
            ("test-utils", "test-utils"),
            ("testUtils", "test-utils"),
            ("test_utils", "test-utils"),
        ],
    )
    def test_algorithmic(self, value: str, expected: str) -> None:
        assert PlaceholderValue(value).to_kebab_case() == expected

    def test_uses_pascal_to_kebab_map(self) -> None:
        placeholder = PlaceholderValue("OpenAI", pascal_to_kebab_map={"OpenAI": "openai"})
        assert placeholder.to_kebab_case() == "openai"

    def test_uses_camel_to_kebab_map(self) -> None:
        placeholder = PlaceholderValue("openAI", camel_to_kebab_map={"openAI": "openai"})
        assert placeholder.to_kebab_case() == "openai"

    def test_prefers_pascal_map_over_camel_map(self) -> None:
        placeholder = PlaceholderValue(
            "OpenAI",
            pascal_to_kebab_map={"OpenAI": "openai"},
            camel_to_kebab_map={"OpenAI": "open-ai"},
        )
        assert placeholder.to_kebab_case() == "openai"

    def test_falls_back_when_no_map_entry(self) -> None:
        placeholder = PlaceholderValue("cache", pascal_to_kebab_map={"OpenAI": "openai"})
        assert placeholder.to_kebab_case() == "cache"


class TestToFlatCase:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("openai", "openai"),
            ("test-utils", "testutils"),
            ("test_utils", "testutils"),
            ("testUtils", "testutils"),
            ("TestUtils", "testutils"),
            ("A", "a"),
        ],
    )
    def test_flattens(self, value: str, expected: str) -> None:
        assert PlaceholderValue(value).to_flat_case() == expected


class TestToNthSegment:
    @pytest.mark.parametrize(
        ("value", "n", "expected"),
        [
            ("foo-bar-baz", 0, "foo"),
            ("foo-bar-baz", 1, "bar"),
            ("foo-bar-baz", 2, "baz"),
            ("foo-bar", 5, ""),
            ("openai", 0, "openai"),
            ("openai", 1, ""),
        ],
    )
    def test_segments(self, value: str, n: int, expected: str) -> None:
        assert PlaceholderValue(value).to_nth_segment(n) == expected


class TestToNthSegmentPascalCase:
    def test_capitalizes_segment(self) -> None:
        assert PlaceholderValue("foo-bar").to_nth_segment_pascal_case(0) == "Foo"

    def test_capitalizes_second_segment(self) -> None:
        assert PlaceholderValue("foo-bar").to_nth_segment_pascal_case(1) == "Bar"

    def test_uses_kebab_to_pascal_map(self) -> None:
        placeholder = PlaceholderValue(
            "openai-graphql", kebab_to_pascal_map={"openai": "OpenAI"}
        )
        assert placeholder.to_nth_segment_pascal_case(0) == "OpenAI"

    def test_falls_back_when_no_map_entry(self) -> None:
        placeholder = PlaceholderValue(
            "openai-graphql", kebab_to_pascal_map={"graphql": "GraphQL"}
        )
        assert placeholder.to_nth_segment_pascal_case(0) == "Openai"

    def test_empty_when_out_of_bounds(self) -> None:
        assert PlaceholderValue("foo-bar").to_nth_segment_pascal_case(5) == ""


class TestToNthSegmentCamelCase:
    def test_lowercases_single_word_segment(self) -> None:
        assert PlaceholderValue("Foo-bar").to_nth_segment_camel_case(0) == "foo"

    def test_uses_kebab_to_camel_map(self) -> None:
        placeholder = PlaceholderValue("openai-graphql", kebab_to_camel_map={"openai": "openAI"})
        assert placeholder.to_nth_segment_camel_case(0) == "openAI"

    def test_falls_back_to_pascal_map_with_lowercased_first_char(self) -> None:
        placeholder = PlaceholderValue(
            "openai-graphql", kebab_to_pascal_map={"graphql": "GraphQL"}
        )
        assert placeholder.to_nth_segment_camel_case(1) == "graphQL"

    def test_empty_when_out_of_bounds(self) -> None:
        assert PlaceholderValue("foo-bar").to_nth_segment_camel_case(5) == ""


class TestToSnakeCase:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Openai", "openai"),
            ("test-utils", "test_utils"),
            ("test_utils", "test_utils"),
            ("testUtils", "test_utils"),
        ],
    )
    def test_algorithmic(self, value: str, expected: str) -> None:
        assert PlaceholderValue(value).to_snake_case() == expected

    def test_uses_pascal_to_kebab_map(self) -> None:
        placeholder = PlaceholderValue("OpenAI", pascal_to_kebab_map={"OpenAI": "openai"})
        assert placeholder.to_snake_case() == "openai"

    def test_uses_camel_to_kebab_map(self) -> None:
        placeholder = PlaceholderValue("openAI", camel_to_kebab_map={"openAI": "openai"})
        assert placeholder.to_snake_case() == "openai"

    def test_converts_hyphens_in_mapped_value(self) -> None:
        placeholder = PlaceholderValue("GraphQL", pascal_to_kebab_map={"GraphQL": "graph-ql"})
        assert placeholder.to_snake_case() == "graph_ql"

    def test_falls_back_when_no_map_entry(self) -> None:
        placeholder = PlaceholderValue("cache", pascal_to_kebab_map={"OpenAI": "openai"})
        assert placeholder.to_snake_case() == "cache"


class TestToConstantCase:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Openai", "OPENAI"),
            ("test-utils", "TEST_UTILS"),
            ("test_utils", "TEST_UTILS"),
            ("testUtils", "TEST_UTILS"),
        ],
    )
    def test_algorithmic(self, value: str, expected: str) -> None:
        assert PlaceholderValue(value).to_constant_case() == expected

    def test_uses_pascal_to_kebab_map(self) -> None:
        placeholder = PlaceholderValue("GraphQL", pascal_to_kebab_map={"GraphQL": "graphql"})
        assert placeholder.to_constant_case() == "GRAPHQL"

    def test_uses_camel_to_kebab_map(self) -> None:
        placeholder = PlaceholderValue("graphQL", camel_to_kebab_map={"graphQL": "graphql"})
        assert placeholder.to_constant_case() == "GRAPHQL"

    def test_converts_hyphens_in_mapped_value(self) -> None:
        placeholder = PlaceholderValue("GraphQL", pascal_to_kebab_map={"GraphQL": "graph-ql"})
        assert placeholder.to_constant_case() == "GRAPH_QL"


class TestExtract:
    def test_first_capture_group(self) -> None:
        assert PlaceholderValue("openai").extract("^([a-z]+)ai$") == "open"

    def test_full_match_when_no_subgroups(self) -> None:
        assert PlaceholderValue("openai").extract("^[a-z]+ai$") == "openai"

    def test_empty_when_no_match(self) -> None:
        assert PlaceholderValue("google").extract("^([a-z]+)ai$") == ""

    def test_first_group_when_multiple_subgroups(self) -> None:
        assert PlaceholderValue("openai-chat").extract("^([a-z]+)-([a-z]+)$") == "openai"

    def test_empty_when_regex_invalid(self) -> None:
        assert PlaceholderValue("openai").extract("[invalid") == ""

    def test_partial_match_when_not_anchored(self) -> None:
        assert PlaceholderValue("openai-v2").extract("([a-z]+)ai") == "open"

    def test_empty_when_match_captures_empty_group(self) -> None:
        assert PlaceholderValue("openai").extract("^([a-z]*)open([a-z]+)$") == ""
