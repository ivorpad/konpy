from __future__ import annotations

from konpy.config.schema import UnusedCodeV1
from konpy.unused.classifier import ResolvedUnusedConfig, classify
from konpy.unused.definitions import Definition, DefinitionKind
from konpy.unused.engine import resolve_config
from konpy.unused.references import ReferenceIndex, RefStats


def config(**overrides: object) -> ResolvedUnusedConfig:
    return resolve_config(UnusedCodeV1(**overrides))  # type: ignore[arg-type]


def make_definition(
    *,
    name: str,
    kind: DefinitionKind = "function",
    qualname: str | None = None,
    decorators: tuple[str, ...] = (),
    class_bases: tuple[str, ...] = (),
    class_decorators: tuple[str, ...] = (),
    class_base_roots: tuple[str, ...] = (),
) -> Definition:
    return Definition(
        module_path="src/mod.py",
        name=name,
        qualname=qualname or name,
        kind=kind,
        decorators=decorators,
        class_bases=class_bases,
        class_decorators=class_decorators,
        lineno=1,
        col=1,
        class_base_roots=class_base_roots,
    )


def index(**stats: RefStats) -> ReferenceIndex:
    return dict(stats)


class TestReferenceVerdicts:
    def test_no_references_is_dead(self) -> None:
        result = classify(
            definition=make_definition(name="dead_fn"),
            index=index(),
            config=config(),
        )

        assert result.verdict == "dead"

    def test_prod_reference_is_used(self) -> None:
        result = classify(
            definition=make_definition(name="used_fn"),
            index=index(used_fn=RefStats(prod=2)),
            config=config(),
        )

        assert result.verdict == "used"

    def test_test_only_reference(self) -> None:
        result = classify(
            definition=make_definition(name="tested_fn"),
            index=index(tested_fn=RefStats(test=3)),
            config=config(),
        )

        assert result.verdict == "test-only"

    def test_entrypoint_reference_is_silent(self) -> None:
        result = classify(
            definition=make_definition(name="handler"),
            index=index(handler=RefStats(entrypoint=1)),
            config=config(),
        )

        assert result.verdict == "entrypoint"


class TestProtocolOverride:
    def make_method(self, name: str, roots: tuple[str, ...]) -> Definition:
        return make_definition(
            name=name,
            kind="method",
            qualname=f"MyAgent.{name}",
            class_bases=("acp.Agent",),
            class_base_roots=roots,
        )

    def test_public_method_on_imported_third_party_base_is_silent(self) -> None:
        result = classify(
            definition=self.make_method("on_message", ("acp",)),
            index=index(),
            config=config(),
        )

        assert result.verdict == "protocol-override"

    def test_private_method_on_third_party_base_is_still_dead(self) -> None:
        result = classify(
            definition=self.make_method("_helper", ("acp",)),
            index=index(),
            config=config(),
        )

        assert result.verdict == "dead"

    def test_repo_local_base_root_does_not_exempt(self) -> None:
        result = classify(
            definition=self.make_method("dead_method", ("src",)),
            index=index(),
            config=config(),
            local_module_roots=frozenset({"src"}),
        )

        assert result.verdict == "dead"

    def test_stdlib_base_root_does_not_exempt(self) -> None:
        result = classify(
            definition=self.make_method("dead_method", ("abc",)),
            index=index(),
            config=config(),
        )

        assert result.verdict == "dead"

    def test_locally_defined_base_has_no_roots_and_does_not_exempt(self) -> None:
        result = classify(
            definition=self.make_method("dead_method", ()),
            index=index(),
            config=config(),
        )

        assert result.verdict == "dead"


class TestSilencingRules:
    def test_allow_list_by_name(self) -> None:
        result = classify(
            definition=make_definition(name="frozen_adapter"),
            index=index(),
            config=config(allow=["frozen_adapter"]),
        )

        assert result.verdict == "allowed"

    def test_allow_list_by_qualname(self) -> None:
        result = classify(
            definition=make_definition(name="method", qualname="Svc.method", kind="method"),
            index=index(),
            config=config(allow=["Svc.method"]),
        )

        assert result.verdict == "allowed"

    def test_dunder_is_hook(self) -> None:
        result = classify(
            definition=make_definition(name="__enter__", kind="method"),
            index=index(),
            config=config(),
        )

        assert result.verdict == "hook"

    def test_preset_lifecycle_hook(self) -> None:
        result = classify(
            definition=make_definition(name="setUp", kind="method"),
            index=index(),
            config=config(),
        )

        assert result.verdict == "hook"

    def test_registry_decorator_exact(self) -> None:
        result = classify(
            definition=make_definition(name="v", decorators=("field_validator",)),
            index=index(),
            config=config(),
        )

        assert result.verdict == "registered"

    def test_registry_decorator_wildcard(self) -> None:
        result = classify(
            definition=make_definition(name="handle", decorators=("app.exception_handler",)),
            index=index(),
            config=config(),
        )

        assert result.verdict == "registered"

    def test_pytest_fixture_decorator(self) -> None:
        result = classify(
            definition=make_definition(name="client", decorators=("pytest.fixture",)),
            index=index(),
            config=config(),
        )

        assert result.verdict == "registered"

    def test_model_field_via_base(self) -> None:
        result = classify(
            definition=make_definition(
                name="name",
                kind="attribute",
                qualname="Model.name",
                class_bases=("BaseModel",),
            ),
            index=index(),
            config=config(),
        )

        assert result.verdict == "model-field"

    def test_model_field_via_dataclass_decorator(self) -> None:
        result = classify(
            definition=make_definition(
                name="value",
                kind="attribute",
                qualname="Point.value",
                class_decorators=("dataclass",),
            ),
            index=index(),
            config=config(),
        )

        assert result.verdict == "model-field"

    def test_non_model_attribute_can_be_dead(self) -> None:
        result = classify(
            definition=make_definition(
                name="orphan",
                kind="attribute",
                qualname="Plain.orphan",
                class_bases=("object",),
            ),
            index=index(),
            config=config(),
        )

        assert result.verdict == "dead"


class TestCoarseNameMatching:
    def test_two_definitions_sharing_a_name_share_references(self) -> None:
        # A reference to "process" anywhere marks *every* "process" as used.
        # Documented under-reporting; keeps false positives at zero.
        shared_index = index(process=RefStats(prod=1))

        first = classify(
            definition=make_definition(name="process", qualname="A.process", kind="method"),
            index=shared_index,
            config=config(),
        )
        second = classify(
            definition=make_definition(name="process", qualname="B.process", kind="method"),
            index=shared_index,
            config=config(),
        )

        assert first.verdict == "used"
        assert second.verdict == "used"
