"""Precision corpus for the unused-code classifier.

Each fixture pins an EXPECTED VERDICT, not just "some diagnostic exists":
framework presets (pydantic, registry decorators, typer/click), the
protocol-override exemption's local-vs-third-party boundary, entrypoint
strings, `__all__`, reflection via `getattr`, the coarse bare-name
under-reporting for shared method names, and the two reported verdicts
(``dead``, ``test-only``) -- all at DEFAULT ``UnusedCodeV1`` settings unless a
test is specifically about a non-default option.

Mirrors the fixture-building pattern in ``test_unused_engine.py`` (an
in-memory ``FakeFileSystem`` via a ``fs``/``run`` helper pair) rather than
introducing a new one.
"""

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


class TestPydanticModelSurface:
    def test_model_fields_and_validators_are_silent(self) -> None:
        # EXPECTATION: BaseModel attributes get the "model-field" verdict and
        # @field_validator/@model_validator methods get the "registered"
        # verdict -- both silent regardless of call sites. Zero diagnostics.
        diagnostics = run(
            {
                "src/models.py": """
                from pydantic import BaseModel, field_validator, model_validator

                class User(BaseModel):
                    name: str
                    age: int

                    @field_validator("name")
                    def check_name(cls, value):
                        return value

                    @model_validator(mode="after")
                    def check_age(self):
                        return self

                use(User)
                """
            }
        )

        assert diagnostics == []


class TestRegistryDecoratedRouteRegistration:
    def test_fastapi_style_router_registration_is_silent(self) -> None:
        # EXPECTATION: handlers registered via a `router.*`/`app.*` decorator
        # (the registry_decorators preset) never need an explicit call site.
        diagnostics = run(
            {
                "src/api.py": """
                router = object()

                @router.get("/users")
                def list_users():
                    return []

                @router.post("/users")
                def create_user():
                    return {}
                """
            }
        )

        assert diagnostics == []


class TestPytestFixtureImplicitReference:
    def test_fixture_in_test_glob_file_is_never_scanned(self) -> None:
        # EXPECTATION: pytest injects fixtures by parameter name, with no
        # explicit call site -- but the mechanism that actually keeps this
        # silent is structural: test-glob files are never scanned for
        # *definitions* at all (engine.py collects definitions only from
        # `prod_trees`), so a fixture defined in a test file can never carry
        # a diagnostic regardless of how (or whether) it is referenced.
        result = run_unused_code_with_metadata(
            config=UnusedCodeV1(),
            file_system=fs(
                {
                    "tests/conftest.py": """
                    import pytest

                    @pytest.fixture
                    def client():
                        return object()
                    """,
                    "tests/test_svc.py": """
                    def test_it(client):
                        client
                    """,
                }
            ),
        )

        assert result.diagnostics == []
        assert "tests/conftest.py" not in result.files_scanned
        assert "tests/test_svc.py" not in result.files_scanned


class TestTyperClickCallbackRegistration:
    def test_typer_callback_and_command_are_silent(self) -> None:
        # EXPECTATION: @app.callback()/@app.command() match the
        # registry_decorators preset ("app.*") -- silent regardless of call
        # sites.
        diagnostics = run(
            {
                "src/cli.py": """
                import typer

                app = typer.Typer()

                @app.callback()
                def main_callback():
                    pass

                @app.command()
                def greet():
                    pass
                """
            }
        )

        assert diagnostics == []


class TestProtocolAbcSubclassMethods:
    def test_local_abc_base_subclass_method_is_reportable(self) -> None:
        # EXPECTATION (documented under-reporting boundary): the
        # protocol-override exemption only fires when a class base's import
        # root resolves OUTSIDE the repo. A local ABC base's subclass method
        # stays fully reportable as dead.
        diagnostics = run(
            {
                "src/base.py": "from abc import ABC\n\nclass Base(ABC):\n    pass\n",
                "src/impl.py": """
                from src.base import Base

                class Impl(Base):
                    def run(self) -> None:
                        return None

                use(Impl)
                """,
            }
        )

        assert [d.message for d in diagnostics] == [
            'Unused definition "Impl.run" is never referenced'
        ]

    def test_local_protocol_base_subclass_method_is_reportable(self) -> None:
        # Same boundary, Protocol flavor: Protocol resolves to a local import
        # root here (defined in-repo), so no exemption applies.
        diagnostics = run(
            {
                "src/proto.py": (
                    "from typing import Protocol\n\nclass Greeter(Protocol):\n    pass\n"
                ),
                "src/greeting.py": """
                from src.proto import Greeter

                class EnglishGreeter(Greeter):
                    def greet(self) -> str:
                        return "hello"

                use(EnglishGreeter)
                """,
            }
        )

        assert [d.message for d in diagnostics] == [
            'Unused definition "EnglishGreeter.greet" is never referenced'
        ]

    def test_imported_third_party_base_subclass_method_is_silent(self) -> None:
        # EXPECTATION: a public method on a class subclassing an imported,
        # non-stdlib, non-local base gets the silent protocol-override
        # exemption (the library dispatches to it by name, e.g. an ABC/
        # Protocol implementation from a third-party package).
        diagnostics = run(
            {
                "src/agent.py": """
                import framework

                class Handler(framework.BaseHandler):
                    def handle_event(self):
                        return 1

                use(Handler)
                """
            }
        )

        assert diagnostics == []


class TestEntrypointStrings:
    def test_pyproject_console_script_keeps_referenced_symbol_used(self) -> None:
        diagnostics = run(
            {
                "src/cli.py": "def run_cli():\n    return 1",
                "pyproject.toml": """
                [project.scripts]
                mycli = "src.cli:run_cli"
                """,
            }
        )

        assert diagnostics == []

    def test_setup_py_entry_points_text_keeps_referenced_symbol_used(self) -> None:
        diagnostics = run(
            {
                "src/legacy.py": "def legacy_entry():\n    return 1",
                "setup.py": (
                    'setup(\n'
                    '    entry_points={"console_scripts": ["legacycli=src.legacy:legacy_entry"]},\n'
                    ')\n'
                ),
            }
        )

        assert diagnostics == []


class TestSharedMethodNameUnderReporting:
    def test_repeated_method_name_only_one_receiver_called_is_silent(self) -> None:
        # EXPECTATION (documented, deliberate under-reporting): references
        # are indexed by bare name, not qualname, so a call to one class's
        # `process` silences every `process` method in the repo, including
        # `Slow.process` below which is never actually invoked.
        diagnostics = run(
            {
                "src/handlers.py": """
                class Fast:
                    def process(self):
                        return 1

                class Slow:
                    def process(self):
                        return 2

                fast = Fast()
                fast.process()

                use(Slow)
                """
            }
        )

        assert diagnostics == []


class TestAllListingExportsAreUsed:
    def test_all_listed_name_is_used(self) -> None:
        diagnostics = run(
            {
                "src/api.py": """
                def public_helper():
                    return 1

                __all__ = ["public_helper"]
                """
            }
        )

        assert diagnostics == []


class TestReflectionViaGetattrString:
    def test_getattr_string_token_keeps_target_used(self) -> None:
        diagnostics = run(
            {
                "src/dynamic.py": """
                def dynamic_target():
                    return 1

                def dispatch(obj):
                    return getattr(obj, "dynamic_target")

                use(dispatch)
                """
            }
        )

        assert diagnostics == []


class TestGenuinelyDeadDefinitions:
    def test_dead_function_class_and_constant_get_exact_dead_verdicts(self) -> None:
        diagnostics = run(
            {
                "src/dead_stuff.py": """
                DEAD_CONSTANT = 42

                def dead_function():
                    return 1

                class DeadClass:
                    pass
                """
            }
        )

        assert len(diagnostics) == 3
        assert {d.predicate_name for d in diagnostics} == {"unusedCode.dead"}
        messages = {d.message for d in diagnostics}
        assert 'Unused definition "DEAD_CONSTANT" is never referenced' in messages
        assert 'Unused definition "dead_function" is never referenced' in messages
        assert 'Unused definition "DeadClass" is never referenced' in messages


class TestProductionFunctionReferencedOnlyFromTests:
    def test_gets_the_distinct_test_only_verdict(self) -> None:
        diagnostics = run(
            {
                "src/svc.py": "def only_from_tests():\n    return 1",
                "tests/test_svc.py": (
                    "from src.svc import only_from_tests\n\nonly_from_tests()\n"
                ),
            }
        )

        assert len(diagnostics) == 1
        assert diagnostics[0].predicate_name == "unusedCode.testOnly"
        assert diagnostics[0].file_path == "src/svc.py"
        assert diagnostics[0].message == (
            'Definition "only_from_tests" is only referenced by tests'
        )


class TestModelBaseInheritedThroughLocalIntermediate:
    def test_typed_dict_fields_via_local_base_are_silent(self) -> None:
        # EXPECTATION: the model-field exemption sees through a module-local
        # intermediate base -- `PayloadIn(BasePayload)` where
        # `BasePayload(TypedDict)` declares wire-format fields that arrive as
        # `json.loads`'d dicts and are never constructed by kwargs. The
        # claude-agent-sdk hook-input hierarchy is this exact shape.
        diagnostics = run(
            {
                "src/types.py": """
                from typing import TypedDict

                class BasePayload(TypedDict):
                    session_id: str

                class PayloadIn(BasePayload):
                    event_name: str
                    is_interrupt: bool

                use(BasePayload, PayloadIn)
                """
            }
        )

        assert diagnostics == []

    def test_non_model_local_base_stays_reported(self) -> None:
        # EXPECTATION: inheriting from a plain local class exempts nothing --
        # only chains that actually reach a model base qualify.
        diagnostics = run(
            {
                "src/plain.py": """
                class Base:
                    pass

                class Child(Base):
                    dead_attribute = 1

                use(Base, Child)
                """
            }
        )

        assert [d.message for d in diagnostics] == [
            'Unused definition "Child.dead_attribute" is never referenced'
        ]

    def test_cyclic_local_bases_do_not_crash(self) -> None:
        # EXPECTATION: a base cycle (illegal at runtime, but parseable) is
        # closed over without recursion and exempts nothing.
        diagnostics = run(
            {
                "src/cycle.py": """
                class A(B):
                    dead_attribute = 1

                class B(A):
                    pass

                use(A, B)
                """
            }
        )

        assert [d.message for d in diagnostics] == [
            'Unused definition "A.dead_attribute" is never referenced'
        ]
