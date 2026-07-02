from konsistent.core.context import build_context
from konsistent.core.filesystem import FakeFileSystem
from konsistent.core.path_matcher import MatchedPath
from konsistent.core.placeholders import PlaceholderValue


class TestBuildContext:
    def test_uses_matched_path_as_base_path_when_match_is_directory(self) -> None:
        file_system = FakeFileSystem(
            files=["packages/openai/README.md"],
            directories=["packages/openai"],
        )
        matched = MatchedPath(path="packages/openai", placeholders={})

        context = build_context(matched=matched, file_system=file_system)

        assert context.path == "packages/openai"
        assert context.base_path == "packages/openai"
        assert context.file_exists("README.md") is True

    def test_uses_dirname_as_base_path_when_match_is_file(self) -> None:
        file_system = FakeFileSystem(
            files=["packages/openai/src/index.py", "packages/openai/src/provider.py"],
            directories=["packages/openai/src"],
        )
        matched = MatchedPath(path="packages/openai/src/index.py", placeholders={})

        context = build_context(matched=matched, file_system=file_system)

        assert context.base_path == "packages/openai/src"
        assert context.file_exists("provider.py") is True

    def test_root_level_file_uses_empty_base_path(self) -> None:
        file_system = FakeFileSystem(files=["pyproject.toml", "README.md"])
        matched = MatchedPath(path="pyproject.toml", placeholders={})

        context = build_context(matched=matched, file_system=file_system)

        assert context.base_path == ""
        assert context.file_exists("README.md") is True

    def test_read_dir_resolves_relative_to_base_path(self) -> None:
        file_system = FakeFileSystem(
            files=["packages/openai/src/index.py", "packages/openai/src/provider.py"],
            directories=["packages/openai/src"],
        )
        matched = MatchedPath(path="packages/openai/src", placeholders={})

        context = build_context(matched=matched, file_system=file_system)

        assert context.read_dir("") == ["index.py", "provider.py"]

    def test_resolve_template_delegates_to_template_resolver(self) -> None:
        file_system = FakeFileSystem(directories=["packages/openai"])
        matched = MatchedPath(
            path="packages/openai",
            placeholders={
                "providerId": PlaceholderValue(
                    "openai",
                    kebab_to_pascal_map={"openai": "OpenAI"},
                )
            },
        )

        context = build_context(matched=matched, file_system=file_system)

        assert context.resolve_template("${providerId.toPascalCase()}Provider") == "OpenAIProvider"
