import pytest

from konsistent.core.constraints import (
    PlaceholderConstraint,
    parse_placeholder_constraint,
    validate_matches_constraint,
    validate_placeholder_constraint,
    validate_segments_constraint,
)


class TestParsePlaceholderConstraint:
    def test_parses_constraint_with_argument(self) -> None:
        assert parse_placeholder_constraint("segments(2)") == PlaceholderConstraint(
            name="segments", arg="2"
        )

    def test_parses_constraint_without_argument(self) -> None:
        assert parse_placeholder_constraint("segments") == PlaceholderConstraint(
            name="segments", arg=None
        )

    def test_parses_alphanumeric_argument(self) -> None:
        assert parse_placeholder_constraint("pattern(abc123)") == PlaceholderConstraint(
            name="pattern", arg="abc123"
        )

    def test_parses_regex_shaped_argument(self) -> None:
        assert parse_placeholder_constraint("matches(^[a-z]+ai$)") == PlaceholderConstraint(
            name="matches", arg="^[a-z]+ai$"
        )

    def test_parses_argument_containing_parens(self) -> None:
        assert parse_placeholder_constraint("extract(^([a-z]+)ai$)") == PlaceholderConstraint(
            name="extract", arg="^([a-z]+)ai$"
        )

    def test_parses_empty_argument(self) -> None:
        assert parse_placeholder_constraint("matches()") == PlaceholderConstraint(
            name="matches", arg=""
        )

    def test_none_for_empty_string(self) -> None:
        assert parse_placeholder_constraint("") is None

    def test_none_for_invalid_format(self) -> None:
        assert parse_placeholder_constraint("(2)") is None

    def test_none_for_unclosed_parenthesis(self) -> None:
        assert parse_placeholder_constraint("segments(2") is None


class TestValidatePlaceholderConstraint:
    def test_dispatches_to_segments(self) -> None:
        constraint = PlaceholderConstraint(name="segments", arg="2")
        assert validate_placeholder_constraint("chat-language", constraint) is True

    def test_segments_failure(self) -> None:
        constraint = PlaceholderConstraint(name="segments", arg="2")
        assert validate_placeholder_constraint("chat", constraint) is False

    def test_dispatches_to_matches_true(self) -> None:
        constraint = PlaceholderConstraint(name="matches", arg="^[a-z]+ai$")
        assert validate_placeholder_constraint("openai", constraint) is True

    def test_dispatches_to_matches_false(self) -> None:
        constraint = PlaceholderConstraint(name="matches", arg="^[a-z]+ai$")
        assert validate_placeholder_constraint("google", constraint) is False

    def test_unknown_constraint_names_are_permissive(self) -> None:
        constraint = PlaceholderConstraint(name="unknownConstraint", arg="1")
        assert validate_placeholder_constraint("anything", constraint) is True


class TestValidateMatchesConstraint:
    def test_true_on_match(self) -> None:
        assert validate_matches_constraint("openai", "^[a-z]+ai$") is True

    def test_false_on_no_match(self) -> None:
        assert validate_matches_constraint("google", "^[a-z]+ai$") is False

    def test_partial_match_when_not_anchored(self) -> None:
        assert validate_matches_constraint("openai-v2", "ai") is True

    def test_false_when_arg_is_none(self) -> None:
        assert validate_matches_constraint("openai", None) is False

    def test_false_when_regex_invalid(self) -> None:
        assert validate_matches_constraint("openai", "[invalid") is False

    def test_empty_value_matches_empty_allowing_regex(self) -> None:
        assert validate_matches_constraint("", "^$") is True

    def test_case_sensitive_by_default(self) -> None:
        assert validate_matches_constraint("OpenAI", "^[a-z]+ai$") is False


class TestValidateSegmentsConstraint:
    @pytest.mark.parametrize(
        ("value", "arg", "expected"),
        [
            ("chat-language", "2", True),
            ("chat", "2", False),
            ("chat-language-model", "2", False),
            ("chat", "1", True),
            ("chat", None, False),
            ("chat", "abc", False),
            ("chat", "0", False),
            ("chat", "-1", False),
            ("chat_language", "2", True),
            ("chatLanguage", "2", True),
        ],
    )
    def test_segments(self, value: str, arg: str | None, expected: bool) -> None:
        assert validate_segments_constraint(value, arg) is expected
