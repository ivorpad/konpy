from konpy.core.placeholders import PlaceholderValue
from konpy.core.templates import resolve_template


def make_placeholders(
    values: dict[str, str],
    *,
    kebab_to_pascal_map: dict[str, str] | None = None,
    kebab_to_camel_map: dict[str, str] | None = None,
) -> dict[str, PlaceholderValue]:
    return {
        key: PlaceholderValue(
            value,
            kebab_to_pascal_map=kebab_to_pascal_map,
            kebab_to_camel_map=kebab_to_camel_map,
        )
        for key, value in values.items()
    }


class TestResolveTemplate:
    def test_resolves_bare_name(self) -> None:
        result = resolve_template("${name}.py", make_placeholders({"name": "openai"}))
        assert result == "openai.py"

    def test_resolves_to_pascal_case(self) -> None:
        result = resolve_template(
            "${name.toPascalCase()}Provider.py", make_placeholders({"name": "openai"})
        )
        assert result == "OpenaiProvider.py"

    def test_resolves_to_camel_case(self) -> None:
        result = resolve_template(
            "${name.toCamelCase()}.py", make_placeholders({"name": "test-utils"})
        )
        assert result == "testUtils.py"

    def test_resolves_to_kebab_case(self) -> None:
        result = resolve_template(
            "${name.toKebabCase()}-provider.py", make_placeholders({"name": "testUtils"})
        )
        assert result == "test-utils-provider.py"

    def test_resolves_to_snake_case(self) -> None:
        result = resolve_template(
            "${name.toSnakeCase()}_config.py", make_placeholders({"name": "test-utils"})
        )
        assert result == "test_utils_config.py"

    def test_resolves_to_constant_case(self) -> None:
        result = resolve_template(
            "${name.toConstantCase()}_CONFIG.py", make_placeholders({"name": "test-utils"})
        )
        assert result == "TEST_UTILS_CONFIG.py"

    def test_resolves_to_flat_case(self) -> None:
        result = resolve_template(
            "${name.toFlatCase()}-config.py", make_placeholders({"name": "test-utils"})
        )
        assert result == "testutils-config.py"

    def test_leaves_unknown_placeholder_unchanged(self) -> None:
        result = resolve_template("${unknown}.py", make_placeholders({"name": "openai"}))
        assert result == "${unknown}.py"

    def test_leaves_unknown_method_unchanged(self) -> None:
        result = resolve_template(
            "${name.toTitleCase()}.py", make_placeholders({"name": "openai"})
        )
        assert result == "${name.toTitleCase()}.py"

    def test_resolves_multiple_placeholders(self) -> None:
        result = resolve_template(
            "${scope.toPascalCase()}${name.toPascalCase()}.py",
            make_placeholders({"scope": "core", "name": "openai"}),
        )
        assert result == "CoreOpenai.py"

    def test_returns_template_as_is_without_placeholders(self) -> None:
        result = resolve_template("index.py", make_placeholders({"name": "openai"}))
        assert result == "index.py"

    def test_to_pascal_case_uses_kebab_to_pascal_map(self) -> None:
        result = resolve_template(
            "${name.toPascalCase()}Provider.py",
            make_placeholders({"name": "openai"}, kebab_to_pascal_map={"openai": "OpenAI"}),
        )
        assert result == "OpenAIProvider.py"

    def test_resolves_to_nth_segment_0(self) -> None:
        result = resolve_template(
            "${name.toNthSegment(0)}-provider.py", make_placeholders({"name": "openai-chat"})
        )
        assert result == "openai-provider.py"

    def test_resolves_to_nth_segment_1(self) -> None:
        result = resolve_template(
            "${name.toNthSegment(1)}.py", make_placeholders({"name": "openai-chat"})
        )
        assert result == "chat.py"

    def test_resolves_to_nth_segment_pascal_case(self) -> None:
        result = resolve_template(
            "${name.toNthSegmentPascalCase(0)}Provider.py",
            make_placeholders({"name": "openai-chat"}),
        )
        assert result == "OpenaiProvider.py"

    def test_resolves_to_nth_segment_camel_case(self) -> None:
        result = resolve_template(
            "create${name.toNthSegmentCamelCase(1)}.py",
            make_placeholders({"name": "openai-Chat"}),
        )
        assert result == "createchat.py"

    def test_to_nth_segment_out_of_bounds_is_empty(self) -> None:
        result = resolve_template(
            "${name.toNthSegment(5)}.py", make_placeholders({"name": "openai"})
        )
        assert result == ".py"

    def test_to_nth_segment_pascal_case_uses_map(self) -> None:
        result = resolve_template(
            "${name.toNthSegmentPascalCase(0)}Provider.py",
            make_placeholders({"name": "openai-chat"}, kebab_to_pascal_map={"openai": "OpenAI"}),
        )
        assert result == "OpenAIProvider.py"

    def test_to_pascal_case_falls_back_to_kebab_map(self) -> None:
        result = resolve_template(
            "create${name.toPascalCase()}",
            make_placeholders({"name": "graphql"}, kebab_to_pascal_map={"graphql": "GraphQL"}),
        )
        assert result == "createGraphQL"

    def test_extract_first_capture_group(self) -> None:
        result = resolve_template(
            "${name.extract(^([a-z]+)ai$)}-stem.py", make_placeholders({"name": "openai"})
        )
        assert result == "open-stem.py"

    def test_extract_full_match_without_subgroups(self) -> None:
        result = resolve_template(
            "${name.extract(^[a-z]+ai$)}.py", make_placeholders({"name": "openai"})
        )
        assert result == "openai.py"

    def test_extract_empty_when_no_match(self) -> None:
        result = resolve_template(
            "${name.extract(^([a-z]+)ai$)}.py", make_placeholders({"name": "google"})
        )
        assert result == ".py"

    def test_numeric_arg_parsing(self) -> None:
        result = resolve_template(
            "${name.toNthSegment(0)}-x.py", make_placeholders({"name": "openai-chat"})
        )
        assert result == "openai-x.py"
