from __future__ import annotations

from konpy.core.filesystem import FakeFileSystem
from konpy.infer.scan import collect_file_records
from konpy.unused.engine import DEFAULT_INCLUDE, DEFAULT_TEST_GLOBS


def scan(
    *,
    files: list[str] | None = None,
    contents: dict[str, str] | None = None,
    include: tuple[str, ...] = DEFAULT_INCLUDE,
    exclude: tuple[str, ...] = (),
    test_globs: tuple[str, ...] = DEFAULT_TEST_GLOBS,
):
    fs = FakeFileSystem(files=files or [], contents=contents or {})
    return collect_file_records(
        file_system=fs,
        include=include,
        exclude=exclude,
        test_globs=test_globs,
    )


class TestCollectFileRecords:
    def test_empty_repo(self) -> None:
        records, unparsable, unreadable = scan()

        assert records == []
        assert unparsable == 0
        assert unreadable == 0

    def test_syntax_error_file_is_excluded_and_counted(self) -> None:
        records, unparsable, unreadable = scan(contents={"src/broken.py": "def (:\n"})

        assert records == []
        assert unparsable == 1
        assert unreadable == 0

    def test_unreadable_file_is_excluded_and_counted(self) -> None:
        records, unparsable, unreadable = scan(files=["src/ghost.py"])

        assert records == []
        assert unparsable == 0
        assert unreadable == 1

    def test_is_test_true_for_default_test_glob(self) -> None:
        records, _, _ = scan(
            contents={
                "tests/unit/test_x.py": "",
                "src/x.py": "",
            }
        )
        by_path = {record.path: record for record in records}

        assert by_path["tests/unit/test_x.py"].is_test is True
        assert by_path["src/x.py"].is_test is False

    def test_custom_test_glob_flips_is_test(self) -> None:
        records, _, _ = scan(
            contents={"spec_foo.py": ""},
            test_globs=("spec_*.py",),
        )

        assert records[0].is_test is True

    def test_directory_stem_and_is_init_for_nested_path(self) -> None:
        records, _, _ = scan(contents={"a/b/c.py": ""})

        record = records[0]
        assert record.directory == "a/b"
        assert record.stem == "c"
        assert record.is_init is False

    def test_directory_stem_and_is_init_for_root_init(self) -> None:
        records, _, _ = scan(contents={"__init__.py": ""})

        record = records[0]
        assert record.directory == ""
        assert record.stem == "__init__"
        assert record.is_init is True

    def test_exclude_removes_matched_path(self) -> None:
        records, _, _ = scan(
            contents={"src/a.py": "", "src/b.py": ""},
            exclude=("src/b.py",),
        )

        paths = [record.path for record in records]
        assert paths == ["src/a.py"]
