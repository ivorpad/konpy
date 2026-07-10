from __future__ import annotations

from konpy.core.filesystem import FakeFileSystem, OverlayFileSystem


class TestOverlayFileSystem:
    def test_new_file_appears_in_glob_and_reads_overlay_content(self) -> None:
        base = FakeFileSystem(files=["src/existing.py"], contents={"src/existing.py": "old"})
        file_system = OverlayFileSystem(base, {"src/new.py": "proposed"})

        assert file_system.glob(["src/*.py"]) == ["src/existing.py", "src/new.py"]
        assert file_system.read_file("src/new.py") == "proposed"

    def test_new_file_appears_in_read_dir(self) -> None:
        base = FakeFileSystem(directories=["src"])
        file_system = OverlayFileSystem(base, {"src/new.py": "proposed"})

        assert file_system.read_dir("src") == ["new.py"]

    def test_parent_directories_are_synthesized_for_new_file(self) -> None:
        base = FakeFileSystem()
        file_system = OverlayFileSystem(base, {"src/nested/new.py": "proposed"})

        assert file_system.file_exists("src") is True
        assert file_system.file_exists("src/nested") is True
        assert file_system.is_directory("src") is True
        assert file_system.is_directory("src/nested") is True
        assert file_system.read_dir("") == ["src"]
        assert file_system.read_dir("src") == ["nested"]
        assert file_system.read_dir("src/nested") == ["new.py"]

    def test_overlaid_file_exists_and_is_not_directory(self) -> None:
        file_system = OverlayFileSystem(FakeFileSystem(), {"src/new.py": "proposed"})

        assert file_system.file_exists("src/new.py") is True
        assert file_system.is_directory("src/new.py") is False

    def test_existing_file_content_is_overridden_without_duplicate_glob_entry(self) -> None:
        base = FakeFileSystem(
            files=["src/existing.py"],
            contents={"src/existing.py": "old"},
        )
        file_system = OverlayFileSystem(base, {"src/existing.py": "new"})

        assert file_system.read_file("src/existing.py") == "new"
        assert file_system.glob(["src/*.py"]) == ["src/existing.py"]

    def test_untouched_paths_delegate_to_base(self) -> None:
        base = FakeFileSystem(
            files=["src/existing.py"],
            directories=["docs"],
            contents={"src/existing.py": "old"},
        )
        file_system = OverlayFileSystem(base, {"src/new.py": "new"})

        assert file_system.file_exists("docs") is True
        assert file_system.is_directory("docs") is True
        assert file_system.read_file("src/existing.py") == "old"

    def test_read_dir_dedupes_base_and_overlay_children(self) -> None:
        base = FakeFileSystem(
            files=["src/existing.py"],
            directories=["src"],
            contents={"src/existing.py": "old"},
        )
        file_system = OverlayFileSystem(
            base,
            {"src/existing.py": "new", "src/added.py": "added"},
        )

        assert file_system.read_dir("src") == ["existing.py", "added.py"]
