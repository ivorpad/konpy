from __future__ import annotations

import textwrap
from collections.abc import Mapping

from konsistent.config.schema import UnusedCodeV1
from konsistent.core.diagnostics import Diagnostic
from konsistent.core.filesystem import FakeFileSystem
from konsistent.unused.engine import run_unused_code, run_unused_code_with_metadata


def fs(contents: Mapping[str, str]) -> FakeFileSystem:
    return FakeFileSystem(
        contents={path: textwrap.dedent(body).strip() + "\n" for path, body in contents.items()}
    )


def run(contents: Mapping[str, str], **overrides: object) -> list[Diagnostic]:
    return run_unused_code(
        config=UnusedCodeV1(**overrides),  # type: ignore[arg-type]
        file_system=fs(contents),
    )


def predicates(diagnostics: list[Diagnostic]) -> dict[str, str]:
    return {diagnostic.message: diagnostic.predicate_name for diagnostic in diagnostics}


class TestDeadDetection:
    def test_reports_dead_function(self) -> None:
        diagnostics = run({"src/mod.py": "def dead():\n    return 1"})

        assert len(diagnostics) == 1
        assert diagnostics[0].predicate_name == "unusedCode.dead"
        assert diagnostics[0].file_path == "src/mod.py"
        assert diagnostics[0].line == 1
        assert diagnostics[0].severity == "warning"

    def test_reports_dead_method_and_class_and_constant(self) -> None:
        diagnostics = run(
            {
                "src/mod.py": """
                DEAD_CONST = 1

                class Dead:
                    def dead_method(self):
                        return 1
                """
            }
        )
        predicate_names = {diagnostic.predicate_name for diagnostic in diagnostics}
        messages = {diagnostic.message for diagnostic in diagnostics}

        assert predicate_names == {"unusedCode.dead"}
        assert any("DEAD_CONST" in message for message in messages)
        assert any('"Dead"' in message for message in messages)
        assert any("Dead.dead_method" in message for message in messages)

    def test_used_function_is_silent(self) -> None:
        diagnostics = run(
            {
                "src/a.py": "def helper():\n    return 1",
                "src/b.py": "from src.a import helper\n\nhelper()",
            }
        )

        assert diagnostics == []


class TestTestOnly:
    def test_test_only_is_distinct_verdict(self) -> None:
        diagnostics = run(
            {
                "src/mod.py": "def only_tested():\n    return 1",
                "tests/test_mod.py": "from src.mod import only_tested\n\nonly_tested()",
            }
        )

        assert len(diagnostics) == 1
        assert diagnostics[0].predicate_name == "unusedCode.testOnly"
        assert "only referenced by tests" in diagnostics[0].message


class TestSilentClasses:
    def test_registry_decorated_function_is_silent(self) -> None:
        diagnostics = run(
            {
                "src/api.py": """
                app = object()

                @app.exception_handler(ValueError)
                def handle(error):
                    return 1

                @pytest.fixture
                def client():
                    return 2

                @field_validator("name")
                def check(cls, value):
                    return value
                """
            }
        )

        assert diagnostics == []

    def test_dunder_and_lifecycle_hooks_silent(self) -> None:
        diagnostics = run(
            {
                "src/mod.py": """
                class Svc:
                    def __init__(self):
                        pass

                    def setUp(self):
                        pass

                use(Svc)
                """
            }
        )

        assert diagnostics == []

    def test_entrypoint_string_in_dockerfile_silences_handler(self) -> None:
        diagnostics = run(
            {
                "src/lambda_function.py": "def handler(event, context):\n    return 1",
                "Dockerfile": 'CMD ["src.lambda_function.handler"]\n',
            }
        )

        assert diagnostics == []

    def test_pydantic_model_field_is_silent(self) -> None:
        diagnostics = run(
            {
                "src/models.py": """
                class Config(BaseModel):
                    name: str
                    age: int

                use(Config)
                """
            }
        )

        assert diagnostics == []

    def test_dataclass_attribute_is_silent(self) -> None:
        diagnostics = run(
            {
                "src/models.py": """
                @dataclass
                class Point:
                    x: int
                    y: int

                use(Point)
                """
            }
        )

        assert diagnostics == []

    def test_allow_list_silences_definition(self) -> None:
        diagnostics = run(
            {"src/mod.py": "def kept_by_decision():\n    return 1"},
            allow=["kept_by_decision"],
        )

        assert diagnostics == []


class TestReferenceEdgeCases:
    def test_all_self_reference_counts_as_used(self) -> None:
        diagnostics = run(
            {"src/mod.py": 'def widget():\n    return 1\n\n__all__ = ["widget"]'}
        )

        assert diagnostics == []

    def test_syntax_error_file_is_skipped(self) -> None:
        diagnostics = run(
            {
                "src/broken.py": "def oops(:\n    pass",
                "src/ok.py": "def dead():\n    return 1",
            }
        )
        # broken file yields no definitions/refs; ok.py still analyzed
        assert [diagnostic.file_path for diagnostic in diagnostics] == ["src/ok.py"]

    def test_name_collision_is_coarse(self) -> None:
        # "shared" defined dead in a.py, but referenced in b.py -> both names
        # share references, so neither is reported (documented under-reporting).
        diagnostics = run(
            {
                "src/a.py": "def shared():\n    return 1",
                "src/b.py": "def shared():\n    return 2\n\nshared()",
            }
        )

        assert diagnostics == []


class TestSeverity:
    def test_severity_override(self) -> None:
        diagnostics = run({"src/mod.py": "def dead():\n    return 1"}, severity="error")

        assert diagnostics[0].severity == "error"


class TestMetadataApi:
    def test_run_unused_code_with_metadata_returns_scanned_python_files(self) -> None:
        file_system = fs(
            {
                "src/a.py": "def used():\n    return 1",
                "tests/test_a.py": "from src.a import used\n\nused()",
                "README.md": "# docs",
            }
        )

        result = run_unused_code_with_metadata(
            config=UnusedCodeV1(),
            file_system=file_system,
        )

        # Test-glob files feed the reference index but can never carry an
        # unused-code diagnostic, so they are not reported as scanned (this
        # keeps them out of suppression-hygiene candidacy in the runner).
        assert result.files_scanned == {"src/a.py"}
        assert "tests/test_a.py" not in result.files_scanned
        assert "README.md" not in result.files_scanned
