import pytest

from konsistent.core.case_utils import (
    derive_camel_to_pascal_map,
    invert_map,
    split_words,
    to_camel_case,
    to_constant_case,
    to_kebab_case,
    to_pascal_case,
    to_snake_case,
)


class TestSplitWords:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("test-utils", ["test", "utils"]),
            ("test_utils", ["test", "utils"]),
            ("testUtils", ["test", "Utils"]),
            ("openai", ["openai"]),
            ("--foo--", ["foo"]),
        ],
    )
    def test_splits(self, value: str, expected: list[str]) -> None:
        assert split_words(value) == expected


class TestToPascalCase:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("openai", "Openai"),
            ("test-utils", "TestUtils"),
            ("testUtils", "TestUtils"),
        ],
    )
    def test_converts(self, value: str, expected: str) -> None:
        assert to_pascal_case(value) == expected


class TestToCamelCase:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Openai", "openai"),
            ("test-utils", "testUtils"),
            ("", ""),
        ],
    )
    def test_converts(self, value: str, expected: str) -> None:
        assert to_camel_case(value) == expected


class TestToKebabCase:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("testUtils", "test-utils"),
            ("test-utils", "test-utils"),
        ],
    )
    def test_converts(self, value: str, expected: str) -> None:
        assert to_kebab_case(value) == expected


class TestToSnakeCase:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("test-utils", "test_utils"),
            ("testUtils", "test_utils"),
        ],
    )
    def test_converts(self, value: str, expected: str) -> None:
        assert to_snake_case(value) == expected


class TestToConstantCase:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("test-utils", "TEST_UTILS"),
            ("test_utils", "TEST_UTILS"),
            ("testUtils", "TEST_UTILS"),
        ],
    )
    def test_converts(self, value: str, expected: str) -> None:
        assert to_constant_case(value) == expected


class TestInvertMap:
    def test_none_stays_none(self) -> None:
        assert invert_map(None) is None

    def test_empty_stays_empty(self) -> None:
        assert invert_map({}) == {}

    def test_inverts_entries(self) -> None:
        assert invert_map({"openai": "OpenAI"}) == {"OpenAI": "openai"}


class TestDeriveCamelToPascalMap:
    def test_none_when_no_maps(self) -> None:
        assert derive_camel_to_pascal_map() is None

    def test_derives_camel_key_from_pascal_map(self) -> None:
        result = derive_camel_to_pascal_map(kebab_to_pascal_map={"openai": "OpenAI"})
        assert result == {"openai": "OpenAI"}

    def test_derives_pascal_value_from_camel_map(self) -> None:
        result = derive_camel_to_pascal_map(kebab_to_camel_map={"openai": "openAI"})
        assert result == {"openAI": "Openai"}

    def test_combines_both_maps_via_shared_kebab_keys(self) -> None:
        result = derive_camel_to_pascal_map(
            kebab_to_pascal_map={"openai": "OpenAI"},
            kebab_to_camel_map={"openai": "openAI"},
        )
        assert result == {"openAI": "OpenAI"}

    def test_pascal_to_camel_inverts_the_derived_map(self) -> None:
        derived = derive_camel_to_pascal_map(
            kebab_to_pascal_map={"openai": "OpenAI"},
            kebab_to_camel_map={"openai": "openAI"},
        )
        assert invert_map(derived) == {"OpenAI": "openAI"}
