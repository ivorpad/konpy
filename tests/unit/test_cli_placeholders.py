from konpy.config.cli_placeholders import normalize_placeholder_arg, parse_cli_placeholders
from konpy.config.errors import Err, Ok


class TestParseCliPlaceholders:
    def test_returns_empty_record_when_no_entries_are_passed(self) -> None:
        result = parse_cli_placeholders(raw=[])
        assert result == Ok({})

    def test_parses_single_name_value_pair(self) -> None:
        result = parse_cli_placeholders(raw=["providerId:openai"])
        assert result == Ok({"providerId": "openai"})

    def test_parses_multiple_pairs_and_preserves_last_wins_ordering(self) -> None:
        result = parse_cli_placeholders(raw=["a:1", "b:2", "a:overridden"])
        assert result == Ok({"a": "overridden", "b": "2"})

    def test_rejects_entry_without_colon(self) -> None:
        result = parse_cli_placeholders(raw=["nocolon"])
        assert isinstance(result, Err)
        assert result.error == 'Invalid --placeholder "nocolon". Expected format "name:value".'

    def test_rejects_entry_that_starts_with_colon(self) -> None:
        result = parse_cli_placeholders(raw=[":value"])
        assert isinstance(result, Err)
        assert result.error == 'Invalid --placeholder ":value". Expected format "name:value".'

    def test_rejects_entry_that_ends_with_colon(self) -> None:
        result = parse_cli_placeholders(raw=["name:"])
        assert isinstance(result, Err)
        assert result.error == 'Invalid --placeholder "name:". Expected format "name:value".'

    def test_rejects_invalid_name(self) -> None:
        result = parse_cli_placeholders(raw=["1bad:value"])
        assert isinstance(result, Err)
        assert result.error == (
            'Invalid --placeholder "1bad:value": name "1bad" must match '
            "[a-zA-Z][a-zA-Z0-9]*."
        )

    def test_rejects_invalid_value(self) -> None:
        result = parse_cli_placeholders(raw=["name:bad value"])
        assert isinstance(result, Err)
        assert result.error == (
            'Invalid --placeholder "name:bad value": value "bad value" must match '
            "[a-zA-Z0-9_-]+."
        )

    def test_splits_on_first_colon_and_validates_whole_value(self) -> None:
        result = parse_cli_placeholders(raw=["name:a:b"])
        assert isinstance(result, Err)
        assert result.error == (
            'Invalid --placeholder "name:a:b": value "a:b" must match [a-zA-Z0-9_-]+.'
        )


class TestNormalizePlaceholderArg:
    def test_returns_empty_array_for_none(self) -> None:
        assert normalize_placeholder_arg(None) == []

    def test_wraps_string_into_single_element_array(self) -> None:
        assert normalize_placeholder_arg("a:1") == ["a:1"]

    def test_returns_string_items_when_already_a_list(self) -> None:
        assert normalize_placeholder_arg(["a:1", "b:2"]) == ["a:1", "b:2"]

    def test_filters_non_string_items_from_lists(self) -> None:
        assert normalize_placeholder_arg(["a:1", 1, None, "b:2"]) == ["a:1", "b:2"]

    def test_returns_empty_array_for_other_values(self) -> None:
        assert normalize_placeholder_arg({"a": "1"}) == []
