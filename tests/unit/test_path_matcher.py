from konpy.core.filesystem import FakeFileSystem
from konpy.core.path_matcher import has_placeholders, match_paths, pattern_to_glob


def create_mock_file_system(
    *,
    glob_results: dict[tuple[str, ...], list[str]] | None = None,
    files: set[str] | None = None,
    directories: set[str] | None = None,
) -> FakeFileSystem:
    return FakeFileSystem(
        glob_results=glob_results,
        files=files or set(),
        directories=directories or set(),
    )


class TestHasPlaceholders:
    def test_returns_true_for_patterns_with_placeholders(self) -> None:
        assert has_placeholders("packages/{name}/src") is True

    def test_returns_false_for_patterns_without_placeholders(self) -> None:
        assert has_placeholders("packages/*/src") is False

    def test_returns_true_for_patterns_with_constrained_placeholders(self) -> None:
        assert has_placeholders("packages/{name:segments(2)}/src") is True

    def test_returns_true_for_patterns_with_regex_constraint_args(self) -> None:
        assert has_placeholders("packages/{name:matches(^[a-z]+ai$)}/src") is True


class TestPatternToGlob:
    def test_replaces_placeholders_with_star(self) -> None:
        assert pattern_to_glob("packages/{name}/src") == "packages/*/src"

    def test_replaces_multiple_placeholders(self) -> None:
        assert pattern_to_glob("{scope}/{name}/index.ts") == "*/*/index.ts"

    def test_leaves_non_placeholder_patterns_unchanged(self) -> None:
        assert pattern_to_glob("src/**/*.ts") == "src/**/*.ts"

    def test_replaces_constrained_placeholders_with_star(self) -> None:
        assert pattern_to_glob("{name:segments(2)}/src") == "*/src"

    def test_replaces_placeholders_with_regex_constraint_args_with_star(self) -> None:
        assert pattern_to_glob("{name:matches(^[a-z]+ai$)}/src") == "*/src"


class TestMatchPaths:
    def test_handles_patterns_without_placeholders(self) -> None:
        file_system = create_mock_file_system(
            glob_results={("src/**/*.ts",): ["src/index.ts", "src/utils.ts"]}
        )

        results = match_paths(patterns=["src/**/*.ts"], file_system=file_system)

        assert len(results) == 2
        assert results[0].placeholders == {}

    def test_extracts_single_placeholder(self) -> None:
        file_system = create_mock_file_system(
            glob_results={
                ("plugins/*/index.ts",): [
                    "plugins/auth/index.ts",
                    "plugins/storage/index.ts",
                ]
            }
        )

        results = match_paths(
            patterns=["plugins/{pluginName}/index.ts"],
            file_system=file_system,
        )

        assert len(results) == 2
        assert results[0].placeholders["pluginName"].to_string() == "auth"
        assert results[1].placeholders["pluginName"].to_string() == "storage"

    def test_extracts_multiple_placeholders(self) -> None:
        file_system = create_mock_file_system(
            glob_results={("*/*/src",): ["packages/openai/src"]}
        )

        results = match_paths(patterns=["{scope}/{name}/src"], file_system=file_system)

        assert len(results) == 1
        assert results[0].placeholders["scope"].to_string() == "packages"
        assert results[0].placeholders["name"].to_string() == "openai"

    def test_rejects_values_with_dots_or_special_chars(self) -> None:
        file_system = create_mock_file_system(
            glob_results={("plugins/*",): ["plugins/auth.v2"]}
        )

        results = match_paths(patterns=["plugins/{name}"], file_system=file_system)

        assert len(results) == 0

    def test_enforces_multi_placeholder_consistency(self) -> None:
        file_system = create_mock_file_system(glob_results={("*/*",): ["foo/bar"]})

        results = match_paths(patterns=["{name}/{name}"], file_system=file_system)

        assert len(results) == 0

    def test_allows_consistent_multi_placeholder_values(self) -> None:
        file_system = create_mock_file_system(glob_results={("*/*",): ["auth/auth"]})

        results = match_paths(patterns=["{name}/{name}"], file_system=file_system)

        assert len(results) == 1
        assert results[0].placeholders["name"].to_string() == "auth"

    def test_repeated_placeholder_within_one_segment_uses_last_capture(self) -> None:
        file_system = create_mock_file_system(glob_results={("*a*",): ["bac"]})

        results = match_paths(patterns=["{name}a{name}"], file_system=file_system)

        assert len(results) == 1
        assert results[0].placeholders["name"].to_string() == "c"

    def test_negation_filters_out_specific_paths(self) -> None:
        file_system = create_mock_file_system(
            glob_results={
                ("packages/*/src/index.ts",): [
                    "packages/cli/src/index.ts",
                    "packages/core/src/index.ts",
                    "packages/test-utils/src/index.ts",
                ],
                ("packages/test-utils/src/index.ts",): [
                    "packages/test-utils/src/index.ts",
                ],
            }
        )

        results = match_paths(
            patterns=[
                "packages/{packageName}/src/index.ts",
                "!packages/test-utils/src/index.ts",
            ],
            file_system=file_system,
        )

        assert len(results) == 2
        assert results[0].path == "packages/cli/src/index.ts"
        assert results[1].path == "packages/core/src/index.ts"

    def test_negation_with_placeholders_resolves_and_excludes(self) -> None:
        file_system = create_mock_file_system(
            glob_results={
                ("plugins/*/index.ts",): [
                    "plugins/auth/index.ts",
                    "plugins/storage/index.ts",
                    "plugins/debug/index.ts",
                ],
                ("plugins/debug/index.ts",): ["plugins/debug/index.ts"],
            }
        )

        results = match_paths(
            patterns=[
                "plugins/{pluginName}/index.ts",
                "!plugins/{pluginName}/index.ts",
            ],
            file_system=file_system,
        )

        assert len(results) == 0

    def test_negation_of_directory_excludes_files_within_it(self) -> None:
        file_system = create_mock_file_system(
            glob_results={
                ("packages/*/src/index.ts",): [
                    "packages/ai/src/index.ts",
                    "packages/openai/src/index.ts",
                    "packages/anthropic/src/index.ts",
                ],
                ("packages/ai",): ["packages/ai"],
            }
        )

        results = match_paths(
            patterns=["packages/{providerId}/src/index.ts", "!packages/ai"],
            file_system=file_system,
        )

        assert len(results) == 2
        assert results[0].path == "packages/openai/src/index.ts"
        assert results[1].path == "packages/anthropic/src/index.ts"

    def test_negation_with_no_positive_matches_returns_empty(self) -> None:
        file_system = create_mock_file_system(
            glob_results={("src/nothing.ts",): ["src/nothing.ts"]}
        )

        results = match_paths(patterns=["!src/nothing.ts"], file_system=file_system)

        assert len(results) == 0

    def test_segments_1_constraint_filters_out_multi_segment_values(self) -> None:
        file_system = create_mock_file_system(
            glob_results={
                ("src/openai-*-model.ts",): [
                    "src/openai-chat-model.ts",
                    "src/openai-chat-language-model.ts",
                    "src/openai-image-model.ts",
                ]
            }
        )

        results = match_paths(
            patterns=["src/openai-{modelKind:segments(1)}-model.ts"],
            file_system=file_system,
        )

        assert len(results) == 2
        assert results[0].placeholders["modelKind"].to_string() == "chat"
        assert results[1].placeholders["modelKind"].to_string() == "image"

    def test_segments_2_constraint_filters_out_single_segment_values(self) -> None:
        file_system = create_mock_file_system(
            glob_results={
                ("src/openai-*-model.ts",): [
                    "src/openai-chat-model.ts",
                    "src/openai-chat-language-model.ts",
                    "src/openai-image-model.ts",
                ]
            }
        )

        results = match_paths(
            patterns=["src/openai-{modelKind:segments(2)}-model.ts"],
            file_system=file_system,
        )

        assert len(results) == 1
        assert results[0].placeholders["modelKind"].to_string() == "chat-language"

    def test_constraint_on_one_placeholder_does_not_affect_others(self) -> None:
        file_system = create_mock_file_system(
            glob_results={
                ("plugins/*/models/*",): [
                    "plugins/auth/models/user-role",
                ]
            }
        )

        results = match_paths(
            patterns=["plugins/{pluginName}/models/{modelName:segments(2)}"],
            file_system=file_system,
        )

        assert len(results) == 1
        assert results[0].placeholders["pluginName"].to_string() == "auth"
        assert results[0].placeholders["modelName"].to_string() == "user-role"

    def test_matches_regex_constraint_filters_values_matching_the_regex(self) -> None:
        file_system = create_mock_file_system(
            glob_results={
                ("packages/*",): [
                    "packages/openai",
                    "packages/mistralai",
                    "packages/google",
                ]
            }
        )

        results = match_paths(
            patterns=["packages/{providerId:matches(^[a-z]+ai$)}"],
            file_system=file_system,
        )

        assert len(results) == 2
        assert results[0].placeholders["providerId"].to_string() == "openai"
        assert results[1].placeholders["providerId"].to_string() == "mistralai"

    def test_matches_regex_rejects_values_that_do_not_match(self) -> None:
        file_system = create_mock_file_system(
            glob_results={("packages/*",): ["packages/google"]}
        )

        results = match_paths(
            patterns=["packages/{providerId:matches(^[a-z]+ai$)}"],
            file_system=file_system,
        )

        assert len(results) == 0

    def test_glob_wildcard_segment_alongside_constrained_placeholder(self) -> None:
        file_system = create_mock_file_system(
            glob_results={
                ("src/*/openai-*-model.ts",): [
                    "src/chat/openai-chat-model.ts",
                    "src/responses/openai-responses-language-model.ts",
                    "src/image/openai-image-model.ts",
                ]
            }
        )

        segment_1 = match_paths(
            patterns=["src/*/openai-{modelKind:segments(1)}-model.ts"],
            file_system=file_system,
        )

        assert len(segment_1) == 2
        assert segment_1[0].placeholders["modelKind"].to_string() == "chat"
        assert segment_1[1].placeholders["modelKind"].to_string() == "image"

        segment_2 = match_paths(
            patterns=["src/*/openai-{modelKind:segments(2)}-model.ts"],
            file_system=file_system,
        )

        assert len(segment_2) == 1
        assert segment_2[0].placeholders["modelKind"].to_string() == "responses-language"

    def test_glob_wildcard_segment_without_placeholders_still_matches(self) -> None:
        file_system = create_mock_file_system(
            glob_results={
                ("src/*/index.ts",): [
                    "src/utils/index.ts",
                    "src/core/index.ts",
                ]
            }
        )

        results = match_paths(patterns=["src/*/index.ts"], file_system=file_system)

        assert len(results) == 2

    def test_unconstrained_placeholders_still_work_normally(self) -> None:
        file_system = create_mock_file_system(
            glob_results={
                ("src/openai-*-model.ts",): [
                    "src/openai-chat-model.ts",
                    "src/openai-chat-language-model.ts",
                ]
            }
        )

        results = match_paths(
            patterns=["src/openai-{modelKind}-model.ts"],
            file_system=file_system,
        )

        assert len(results) == 2
