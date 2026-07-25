from __future__ import annotations

import textwrap
from collections.abc import Mapping

from konpy.config.schema import UnusedCodeV1
from konpy.core.diagnostics import Diagnostic
from konpy.core.filesystem import FakeFileSystem
from konpy.unused.engine import run_unused_code, run_unused_code_with_metadata


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


class TestRecursiveDefaults:
    def test_nested_test_dir_functions_never_flagged(self) -> None:
        # claude-agent-sdk keeps tests in e2e-tests/; before the recursive
        # defaults its pytest functions leaked into the production lane.
        diagnostics = run(
            {
                "src/mod.py": "def only_tested():\n    return 1",
                "e2e-tests/test_mod.py": """
                from src.mod import only_tested

                def test_it():
                    only_tested()
                """,
            }
        )

        assert len(diagnostics) == 1
        assert diagnostics[0].predicate_name == "unusedCode.testOnly"
        assert diagnostics[0].file_path == "src/mod.py"

    def test_nested_tests_directory_matches_default_globs(self) -> None:
        result = run_unused_code_with_metadata(
            config=UnusedCodeV1(),
            file_system=fs(
                {
                    "pkg/mod.py": "def used():\n    return 1",
                    "pkg/tests/helper.py": "from pkg.mod import used\n\nused()",
                }
            ),
        )

        assert result.files_scanned == {"pkg/mod.py"}
        assert [d.predicate_name for d in result.diagnostics] == ["unusedCode.testOnly"]

    def test_nested_pyproject_console_script_is_entrypoint(self) -> None:
        # Console scripts in examples/*/pyproject.toml were invisible before
        # entrypoint scanning went recursive.
        diagnostics = run(
            {
                "examples/app/main.py": "def run():\n    return 1",
                "examples/app/pyproject.toml": """
                [project.scripts]
                cli = "examples.app.main:run"
                """,
            }
        )

        assert diagnostics == []


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


class TestVendoredDirsAreAlwaysExcluded:
    def test_vendored_setup_py_cannot_mask_dead_code(self) -> None:
        # Recursive entrypoint globs must not tokenize vendored trees: a
        # dependency's setup.py containing the word "process" would silently
        # flip the dead verdict to the silent entrypoint verdict.
        diagnostics = run(
            {
                "mypkg/app.py": "def process():\n    return 1",
                "node_modules/some_dep/setup.py": "# helpers to process modules\n",
            }
        )

        assert [d.message for d in diagnostics] == [
            'Unused definition "process" is never referenced'
        ]

    def test_vendored_python_files_are_not_scanned(self) -> None:
        result = run_unused_code_with_metadata(
            config=UnusedCodeV1(),
            file_system=fs(
                {
                    "src/mod.py": "def used():\n    return 1\n\nused()",
                    "build/lib/stale.py": "def stale_orphan():\n    return 2",
                }
            ),
        )

        assert result.diagnostics == []
        assert result.files_scanned == {"src/mod.py"}


class TestProtocolOverrideExemption:
    def test_public_method_on_imported_library_base_is_silent(self) -> None:
        # hermes shape: acp.Agent JSON-RPC dispatch methods are invoked by the
        # library, never referenced in-repo.
        diagnostics = run(
            {
                "src/agent.py": """
                import acp

                class MyAgent(acp.Agent):
                    def on_message(self):
                        return 1

                    def _private_helper(self):
                        return 2

                use(MyAgent)
                """
            }
        )

        assert [d.message for d in diagnostics] == [
            'Unused definition "MyAgent._private_helper" is never referenced'
        ]

    def test_method_on_repo_local_base_is_still_reported(self) -> None:
        diagnostics = run(
            {
                "src/base.py": "class Base:\n    pass",
                "src/impl.py": """
                from src.base import Base

                class Impl(Base):
                    def dead_method(self):
                        return 1

                use(Impl)
                """,
            }
        )

        assert any("Impl.dead_method" in d.message for d in diagnostics)

    def test_non_src_layout_local_base_is_still_reported(self) -> None:
        # A `source/` (or any non-src/lib) layout root: the topmost package
        # directory carrying an __init__.py identifies "pkg" as repo-local,
        # so its subclass methods stay reportable.
        diagnostics = run(
            {
                "source/pkg/__init__.py": "",
                "source/pkg/base.py": "class Agent:\n    pass",
                "source/pkg/impl.py": """
                from pkg.base import Agent

                class Impl(Agent):
                    def dead_method(self):
                        return 1

                use(Impl)
                """,
            }
        )

        assert any("Impl.dead_method" in d.message for d in diagnostics)

    def test_star_imported_base_still_gets_the_exemption(self) -> None:
        # `from framework import *` hides the base's origin; the exemption
        # must still fire rather than flagging a framework-dispatched method.
        diagnostics = run(
            {
                "src/agent.py": """
                from thirdparty_framework import *

                class Impl(Agent):
                    def on_message(self):
                        return 1

                use(Impl)
                """
            }
        )

        assert diagnostics == []


class TestReferenceOnly:
    def test_reference_only_files_never_carry_diagnostics(self) -> None:
        result = run_unused_code_with_metadata(
            config=UnusedCodeV1(),
            file_system=fs({"gen/client.py": "def orphan_stub():\n    return 1"}),
            reference_only=["gen/client.py"],
        )

        assert result.diagnostics == []
        assert result.files_scanned == set()

    def test_reference_from_reference_only_file_keeps_definition_used(self) -> None:
        # Unlike an exclude, a reference-only file still feeds the index:
        # hand-written code called only from generated code stays used.
        result = run_unused_code_with_metadata(
            config=UnusedCodeV1(),
            file_system=fs(
                {
                    "src/helpers.py": "def hand_written():\n    return 1",
                    "gen/client.py": "from src.helpers import hand_written\n\nhand_written()",
                }
            ),
            reference_only=["gen/client.py"],
        )

        assert result.diagnostics == []
        assert result.files_scanned == {"src/helpers.py"}


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
