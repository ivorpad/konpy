from __future__ import annotations

import json
from pathlib import Path

from konpy.config.errors import Ok
from konpy.config.loader import load_config_runtime
from konpy.config.plugin_loader import load_plugin_registry
from konpy.config.schema import ConfigV1
from konpy.core.convention_name import generate_convention_name
from konpy.core.explain import build_explained_config
from konpy.core.filesystem import FakeFileSystem
from konpy.core.policy import resolve_effective_policy
from konpy.core.runner import run
from konpy.predicates.registry import builtin_predicate_registry
from tests.fake_distribution import install_fake_distribution


def config(conventions: list[dict], **extra: object) -> ConfigV1:
    return ConfigV1.model_validate({"version": "v1", "conventions": conventions, **extra})


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


class TestObjectFormMust:
    def test_produces_a_single_block_with_no_must_not(self) -> None:
        policy = resolve_effective_policy(
            config([{"paths": "src/*.py", "must": {"haveType": "file"}}]),
            predicate_registry=builtin_predicate_registry(),
        )

        blocks = policy.conventions[0].blocks
        assert len(blocks) == 1
        assert blocks[0].must is not None
        assert blocks[0].mustNot is None


class TestBlockArrayMust:
    def test_each_hand_written_block_passes_through_unchanged(self) -> None:
        policy = resolve_effective_policy(
            config(
                [
                    {
                        "paths": "src/*.py",
                        "must": [
                            {"name": "first", "must": {"haveType": "file"}},
                            {"name": "second", "mustNot": {"haveType": "directory"}},
                        ],
                    }
                ]
            ),
            predicate_registry=builtin_predicate_registry(),
        )

        blocks = policy.conventions[0].blocks
        assert len(blocks) == 2
        assert blocks[0].name == "first"
        assert blocks[0].must is not None
        assert blocks[1].name == "second"
        assert blocks[1].mustNot is not None


class TestConventionLevelMustNotAlone:
    def test_produces_a_single_must_not_only_block(self) -> None:
        policy = resolve_effective_policy(
            config([{"paths": "src/*.py", "mustNot": {"import": ["requests"]}}]),
            predicate_registry=builtin_predicate_registry(),
        )

        blocks = policy.conventions[0].blocks
        assert len(blocks) == 1
        assert blocks[0].must is None
        assert blocks[0].mustNot is not None


class TestMustListPlusMustNot:
    def test_appends_a_synthetic_must_not_only_block(self) -> None:
        policy = resolve_effective_policy(
            config(
                [
                    {
                        "paths": "src/*.py",
                        "must": [{"must": {"haveType": "file"}}],
                        "mustNot": {"areBarrelFiles": True},
                    }
                ]
            ),
            predicate_registry=builtin_predicate_registry(),
        )

        blocks = policy.conventions[0].blocks
        assert len(blocks) == 2
        assert blocks[0].must is not None
        assert blocks[0].mustNot is None
        assert blocks[1].must is None
        assert blocks[1].mustNot is not None
        assert blocks[1].name is None


class TestObjectFormMustPlusMustNot:
    def test_merges_into_a_single_combined_block(self) -> None:
        policy = resolve_effective_policy(
            config(
                [
                    {
                        "paths": "src/*.py",
                        "must": {"haveType": "file"},
                        "mustNot": {"areBarrelFiles": True},
                    }
                ]
            ),
            predicate_registry=builtin_predicate_registry(),
        )

        blocks = policy.conventions[0].blocks
        assert len(blocks) == 1
        assert blocks[0].must is not None
        assert blocks[0].mustNot is not None


class TestNestedForIfBlocksPassThrough:
    def test_if_and_for_survive_untouched(self) -> None:
        policy = resolve_effective_policy(
            config(
                [
                    {
                        "paths": "src/*.py",
                        "must": [
                            {
                                "if": {"hasFile": "pyproject.toml"},
                                "for": {"files": ["*.py", "*.pyi"]},
                                "must": {"haveType": "file"},
                            }
                        ],
                    }
                ]
            ),
            predicate_registry=builtin_predicate_registry(),
        )

        block = policy.conventions[0].blocks[0]
        assert block.if_ is not None
        assert block.if_.hasFile == "pyproject.toml"
        assert block.for_ is not None
        assert block.for_.files == ["*.py", "*.pyi"]


class TestAnonymousConventionNaming:
    def test_matches_generate_convention_name_called_with_the_same_registry(self) -> None:
        registry = builtin_predicate_registry()
        c = config([{"paths": "src/*.py", "must": {"exportFunctions": ["create"]}}])

        policy = resolve_effective_policy(c, predicate_registry=registry)

        expected = generate_convention_name(
            must=c.conventions[0].must,
            must_not=c.conventions[0].mustNot,
            predicate_registry=registry,
        )
        assert policy.conventions[0].name == expected


_PLUGIN_SOURCE = """
from konpy.plugin import PredicatePlugin, create_diagnostic


def handler(*, expected, context, structure, convention_name=None, severity=None):
    return [
        create_diagnostic(
            file_path=context.path,
            predicate_name="acmeRule",
            message=f'acmeRule violated: "{expected}"',
            convention_name=convention_name,
            severity=severity,
        )
    ]


plugin = PredicatePlugin(
    key="acmeRule",
    value_model=str,
    handler=handler,
    forbidden_message_template='Forbidden acmeRule "{resolved_value}"',
)
"""


class TestAnonymousConventionNamingWithPluginPredicate:
    def test_same_name_in_policy_explain_and_a_real_run(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-effective-policy-plugin",
            import_package="konpy_test_effective_policy_plugin",
            modules={"rules": _PLUGIN_SOURCE},
            entry_points={
                "konpy.predicates": {
                    "acmeRule": "konpy_test_effective_policy_plugin.rules:plugin",
                }
            },
        )
        loaded_registry = load_plugin_registry(plugins=["konpy-test-effective-policy-plugin"])
        assert isinstance(loaded_registry, Ok)
        registry = loaded_registry.value

        c = ConfigV1.model_validate(
            {
                "version": "v1",
                "plugins": ["konpy-test-effective-policy-plugin"],
                "conventions": [{"paths": "src/module.py", "must": {"acmeRule": "expected"}}],
            },
            context=registry.validation_context(),
        )

        policy = resolve_effective_policy(c, predicate_registry=registry)
        policy_name = policy.conventions[0].name
        assert policy_name == "must-acme-rule"

        explained = build_explained_config(c, predicate_registry=registry)
        assert explained.conventions[0].name == policy_name

        result = run(
            config=c,
            file_system=FakeFileSystem(contents={"src/module.py": "VALUE = 1\n"}),
            predicate_registry=registry,
        )
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].convention_name == policy_name


class TestSeverityDefaulting:
    def test_defaults_to_error_when_unset(self) -> None:
        policy = resolve_effective_policy(
            config([{"paths": "src/*.py", "must": {"haveType": "file"}}]),
            predicate_registry=builtin_predicate_registry(),
        )
        assert policy.conventions[0].severity == "error"

    def test_preserves_explicit_warning(self) -> None:
        policy = resolve_effective_policy(
            config(
                [
                    {
                        "paths": "src/*.py",
                        "severity": "warning",
                        "must": {"haveType": "file"},
                    }
                ]
            ),
            predicate_registry=builtin_predicate_registry(),
        )
        assert policy.conventions[0].severity == "warning"


class TestExtendsAndConventionSourcesResolveThroughPolicy:
    def test_local_convention_sources_resolve_without_error(self, tmp_path: Path) -> None:
        write_json(
            tmp_path / "local-conventions.json",
            {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "package-must-have-readme",
                        "description": "Every package must contain README.",
                        "paths": ["packages/{packageName}"],
                        "must": {"haveFiles": ["README.md"]},
                    }
                ],
            },
        )
        base_config_path = tmp_path / "base.json"
        write_json(
            base_config_path,
            {
                "version": "v1",
                "conventionSources": {"common": "./local-conventions.json"},
                "conventions": ["common/package-must-have-readme"],
            },
        )
        config_path = tmp_path / "konpy.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./base.json"],
                "conventions": [],
            },
        )

        loaded = load_config_runtime(config_path=config_path)
        assert isinstance(loaded, Ok)

        policy = resolve_effective_policy(
            loaded.value.config,
            predicate_registry=loaded.value.predicate_registry,
        )

        assert [c.name for c in policy.conventions] == ["package-must-have-readme"]
        assert policy.conventions[0].paths == ("packages/{packageName}",)


class TestRunnerExplainParityOnStrictConfig:
    def test_convention_name_sets_match_and_are_non_empty(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        loaded = load_config_runtime(config_path=repo_root / "konpy.strict.json")
        assert isinstance(loaded, Ok)

        policy = resolve_effective_policy(
            loaded.value.config,
            predicate_registry=loaded.value.predicate_registry,
        )
        explained = build_explained_config(
            loaded.value.config,
            predicate_registry=loaded.value.predicate_registry,
        )

        policy_names = {c.name for c in policy.conventions}
        explained_names = {c.name for c in explained.conventions}

        assert policy_names == explained_names
        assert policy_names != set()
