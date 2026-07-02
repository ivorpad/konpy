from pathlib import Path

import pytest

from konsistent.core import filesystem as filesystem_module
from konsistent.core.filesystem import FakeFileSystem, RealFileSystem


def write(path: Path, value: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


class TestRealFileSystemGlobCaching:
    def test_resolves_same_ordered_patterns_only_once(self, tmp_path: Path, monkeypatch) -> None:
        calls: list[list[str]] = []

        def fake_glob(patterns: list[str], *, root_dir: str, flags: int) -> list[str]:
            calls.append(patterns)
            assert root_dir == str(tmp_path)
            assert flags == filesystem_module._GLOB_FLAGS
            return ["src/index.py"]

        monkeypatch.setattr(filesystem_module.wcglob, "glob", fake_glob)

        file_system = RealFileSystem(cwd=tmp_path)
        first = file_system.glob(["src/**/*.py"])
        second = file_system.glob(["src/**/*.py"])

        assert first == ["src/index.py"]
        assert second == ["src/index.py"]
        assert calls == [["src/**/*.py"]]

    def test_different_patterns_are_cached_separately(self, tmp_path: Path, monkeypatch) -> None:
        calls: list[list[str]] = []

        def fake_glob(patterns: list[str], *, root_dir: str, flags: int) -> list[str]:
            calls.append(patterns)
            return ["src/index.py"]

        monkeypatch.setattr(filesystem_module.wcglob, "glob", fake_glob)

        file_system = RealFileSystem(cwd=tmp_path)
        file_system.glob(["src/**/*.py"])
        file_system.glob(["lib/**/*.py"])

        assert calls == [["src/**/*.py"], ["lib/**/*.py"]]

    def test_reordered_patterns_use_a_different_cache_key(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        calls: list[list[str]] = []

        def fake_glob(patterns: list[str], *, root_dir: str, flags: int) -> list[str]:
            calls.append(patterns)
            return ["src/index.py"]

        monkeypatch.setattr(filesystem_module.wcglob, "glob", fake_glob)

        file_system = RealFileSystem(cwd=tmp_path)
        file_system.glob(["src/**/*.py", "lib/**/*.py"])
        file_system.glob(["lib/**/*.py", "src/**/*.py"])

        assert calls == [
            ["src/**/*.py", "lib/**/*.py"],
            ["lib/**/*.py", "src/**/*.py"],
        ]

    def test_returned_list_mutation_does_not_corrupt_cache(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        def fake_glob(patterns: list[str], *, root_dir: str, flags: int) -> list[str]:
            return ["src/index.py"]

        monkeypatch.setattr(filesystem_module.wcglob, "glob", fake_glob)

        file_system = RealFileSystem(cwd=tmp_path)
        first = file_system.glob(["src/**/*.py"])
        first.append("mutated.py")

        assert file_system.glob(["src/**/*.py"]) == ["src/index.py"]


class TestRealFileSystemGlobBehavior:
    def test_globstar_matches_nested_files(self, tmp_path: Path) -> None:
        write(tmp_path / "src" / "index.py")
        write(tmp_path / "src" / "nested" / "helper.py")

        result = RealFileSystem(cwd=tmp_path).glob(["src/**/*.py"])

        assert "src/index.py" in result
        assert "src/nested/helper.py" in result

    def test_brace_expansion(self, tmp_path: Path) -> None:
        write(tmp_path / "src" / "guide.md")
        write(tmp_path / "docs" / "guide.md")
        write(tmp_path / "tests" / "guide.md")

        result = RealFileSystem(cwd=tmp_path).glob(["{src,docs}/*.md"])

        assert set(result) == {"src/guide.md", "docs/guide.md"}

    def test_star_does_not_cross_slash(self, tmp_path: Path) -> None:
        write(tmp_path / "src" / "index.py")
        write(tmp_path / "src" / "nested" / "helper.py")

        result = RealFileSystem(cwd=tmp_path).glob(["src/*.py"])

        assert "src/index.py" in result
        assert "src/nested/helper.py" not in result

    def test_includes_directories_and_files(self, tmp_path: Path) -> None:
        (tmp_path / "packages" / "core").mkdir(parents=True)
        write(tmp_path / "packages" / "README.md")

        result = RealFileSystem(cwd=tmp_path).glob(["packages/*"])

        assert "packages/core" in result
        assert "packages/README.md" in result

    def test_dotfiles_are_excluded_unless_pattern_says_so(self, tmp_path: Path) -> None:
        write(tmp_path / "src" / "index.py")
        write(tmp_path / "src" / ".hidden.py")

        file_system = RealFileSystem(cwd=tmp_path)

        assert "src/.hidden.py" not in file_system.glob(["src/*.py"])
        assert file_system.glob(["src/.*.py"]) == ["src/.hidden.py"]

    def test_trailing_slash_directory_result_is_normalized(self, tmp_path: Path) -> None:
        (tmp_path / "packages" / "core").mkdir(parents=True)

        result = RealFileSystem(cwd=tmp_path).glob(["packages/core/"])

        assert result == ["packages/core"]

    def test_bare_directory_pattern_does_not_expand_contents(self, tmp_path: Path) -> None:
        write(tmp_path / "src" / "index.py")

        result = RealFileSystem(cwd=tmp_path).glob(["src"])

        assert result == ["src"]


class TestRealFileSystemOperations:
    def test_file_exists_read_dir_and_read_file(self, tmp_path: Path) -> None:
        write(tmp_path / "src" / "index.py", "print('hello')\n")

        file_system = RealFileSystem(cwd=tmp_path)

        assert file_system.file_exists("src/index.py") is True
        assert file_system.file_exists("src/missing.py") is False
        assert file_system.read_dir("src") == ["index.py"]
        assert file_system.read_file("src/index.py") == "print('hello')\n"

    def test_is_directory_false_for_missing_path(self, tmp_path: Path) -> None:
        file_system = RealFileSystem(cwd=tmp_path)

        assert file_system.is_directory("missing") is False


class TestFakeFileSystem:
    def test_explicit_glob_results_are_returned_by_ordered_pattern_key(self) -> None:
        file_system = FakeFileSystem(
            glob_results={("src/**/*.py",): ["src/index.py", "src/utils.py"]}
        )

        assert file_system.glob(["src/**/*.py"]) == ["src/index.py", "src/utils.py"]
        assert file_system.glob(["src/*.py"]) == []

    def test_fallback_glob_matches_files_and_directories(self) -> None:
        file_system = FakeFileSystem(
            files=["src/index.py", "src/nested/helper.py"],
            directories=["src", "src/nested"],
        )

        assert file_system.glob(["src/*"]) == ["src/index.py", "src/nested"]

    def test_file_operations(self) -> None:
        file_system = FakeFileSystem(
            files=["src/index.py"],
            directories=["src"],
            contents={"src/index.py": "hello"},
        )

        assert file_system.file_exists("src/index.py") is True
        assert file_system.file_exists("src") is True
        assert file_system.is_directory("src") is True
        assert file_system.read_dir("src") == ["index.py"]
        assert file_system.read_file("src/index.py") == "hello"

    def test_read_file_raises_for_missing_file(self) -> None:
        file_system = FakeFileSystem()

        with pytest.raises(FileNotFoundError):
            file_system.read_file("missing.py")
