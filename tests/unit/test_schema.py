from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from konsistent.config.schema import RawConfigV1, ReusableConventionsPackageV1
from konsistent.predicates.registry import PredicateRegistry, builtin_predicate_registry


def parses(payload: dict[str, Any]) -> bool:
    try:
        RawConfigV1.model_validate(payload)
    except ValidationError:
        return False
    return True


def config(conventions: list[Any], **extra: Any) -> dict[str, Any]:
    return {"version": "v1", "conventions": conventions, **extra}


class TestConfigV1Accepts:
    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"version": "v1", "conventions": []}, id="minimal"),
            pytest.param(
                {"$schema": "https://example.com/schema.json", "version": "v1", "conventions": []},
                id="dollar-schema",
            ),
            pytest.param(
                config([], extends=["./base/konsistent.json"]),
                id="extends-array",
            ),
            pytest.param(
                config([], disable=["legacy-rule"]),
                id="disable-array",
            ),
            pytest.param(
                config(
                    [],
                    extends=["./base/konsistent.json", "/abs/base/konsistent.json"],
                    disable=["legacy-rule", "old-rule"],
                ),
                id="extends-and-disable",
            ),
            pytest.param(
                config(
                    [
                        {
                            "name": "components-are-files",
                            "paths": "src/components/*.py",
                            "must": {"haveType": "file"},
                        }
                    ]
                ),
                id="have-type",
            ),
            pytest.param(
                config(
                    [{"paths": "src/*.py", "mustNot": {"exportConstants": ["debug"]}}]
                ),
                id="must-not-only",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "must": {"haveType": "file"},
                            "mustNot": {"exportConstants": ["debug"]},
                        }
                    ]
                ),
                id="must-and-must-not",
            ),
            pytest.param(
                config([{"paths": ["src/*.py", "lib/*.py"], "must": {}}]), id="paths-array"
            ),
            pytest.param(
                config(
                    [
                        {
                            "name": "my-rule",
                            "description": "A test rule",
                            "paths": "src/*.py",
                            "must": {"haveType": "directory"},
                        }
                    ]
                ),
                id="all-optional-fields",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "must": {
                                "matchContent": ["SPDX-License-Identifier"],
                                "havePairedFile": "tests/test_${name}.py",
                                "haveDocstrings": True,
                                "annotateFunctions": True,
                            },
                        }
                    ]
                ),
                id="m11-predicates-true-shapes",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "must": {
                                "haveDocstrings": {
                                    "modules": False,
                                    "classes": True,
                                    "functions": True,
                                    "publicOnly": False,
                                },
                                "annotateFunctions": {
                                    "returns": False,
                                    "params": True,
                                    "publicOnly": False,
                                },
                            },
                        }
                    ]
                ),
                id="m11-predicates-object-shapes",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "must": {
                                "declareTypes": [{"name": "LocalType"}],
                                "declareConstants": ["localConstant"],
                                "declareFunctions": [
                                    {
                                        "name": "createLocal",
                                        "receiveParamOfType": "LocalConfig",
                                        "receiveParamsOfTypes": ["LocalConfig"],
                                        "returnValueOfType": "Local",
                                    }
                                ],
                                "declareInterfaces": [{"name": "Local", "extend": "BaseLocal"}],
                                "declareClasses": [
                                    {
                                        "name": "LocalClass",
                                        "extend": "BaseClass",
                                        "implement": ["Serializable"],
                                    }
                                ],
                            },
                        }
                    ]
                ),
                id="declaration-predicates",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "must": {
                                "useDeclarationOrder": ["alpha", "beta"],
                                "importFrom": "collections",
                                "importFromCurrentDir": True,
                                "importFromParents": False,
                                "importFromExternals": True,
                                "importTypesFromCurrentDir": True,
                                "importTypesFromParents": False,
                                "importTypesFromExternals": True,
                            },
                        }
                    ]
                ),
                id="order-and-import-source-predicates",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "must": [
                                {"must": {"haveType": "file"}},
                                {"if": {"hasFile": "index.py"}, "must": {"haveType": "file"}},
                            ],
                        }
                    ]
                ),
                id="must-as-block-array",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "components/{name}",
                            "must": [
                                {
                                    "for": {"files": "{storyFile}_stories.py"},
                                    "must": {"exportConstants": ["meta"]},
                                }
                            ],
                        }
                    ]
                ),
                id="block-with-for",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "components/{name}",
                            "must": [
                                {
                                    "if": {"hasFile": "${name}_test.py"},
                                    "for": {"files": "${name}_test.py"},
                                    "must": {"export": ["describe"]},
                                }
                            ],
                        }
                    ]
                ),
                id="block-with-if-and-for",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "packages/{providerId}",
                            "must": [
                                {
                                    "if": {
                                        "placeholderSatisfies": "providerId:matches(^[a-z]+ai$)"
                                    },
                                    "must": {"haveType": "directory"},
                                }
                            ],
                        }
                    ]
                ),
                id="block-with-placeholder-satisfies",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "must": [
                                {"if": {"hasFile": "index.py"}, "mustNot": {"export": ["debug"]}}
                            ],
                        }
                    ]
                ),
                id="block-with-only-must-not",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "severity": "error", "must": {"haveType": "file"}}]),
                id="severity-error",
            ),
            pytest.param(
                config(
                    [{"paths": "src/*.py", "severity": "warning", "must": {"haveType": "file"}}]
                ),
                id="severity-warning",
            ),
            pytest.param(
                config(
                    [],
                    conventionSources={
                        "common": "./local-conventions.json",
                        "org": "@org/conventions",
                    },
                ),
                id="convention-sources",
            ),
            pytest.param(
                config(
                    ["common/some-convention"], conventionSources={"common": "./x.json"}
                ),
                id="bare-string-ref",
            ),
            pytest.param(
                config(
                    ["common/foo", {"paths": "src/*.py", "must": {"haveType": "file"}}],
                    conventionSources={"common": "./x.json"},
                ),
                id="mixed-refs-and-hand-written",
            ),
            pytest.param(
                config(
                    [
                        {
                            "use": "common/some-convention",
                            "paths": ["src/components/{componentName}.py"],
                        }
                    ],
                    conventionSources={"common": "./x.json"},
                ),
                id="use-ref-paths-override",
            ),
            pytest.param(
                config(
                    [{"use": "common/some-convention"}],
                    conventionSources={"common": "./x.json"},
                ),
                id="use-ref-no-overrides",
            ),
            pytest.param(
                config(
                    [
                        {
                            "use": "common/some-convention",
                            "severity": "warning",
                            "excludeFiles": ["src/skip.py"],
                            "must": {"haveType": "file"},
                        }
                    ],
                    conventionSources={"common": "./x.json"},
                ),
                id="use-ref-with-overrides",
            ),
            pytest.param(
                config(
                    [
                        {
                            "use": "common/some-convention",
                            "mustNot": {"exportConstants": ["debug"]},
                        }
                    ],
                    conventionSources={"common": "./x.json"},
                ),
                id="use-ref-must-not-override",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/{name}",
                            "must": [
                                {"must": {"haveType": "directory"}},
                                "common/some-must-block",
                            ],
                        }
                    ],
                    conventionSources={"common": "./x.json"},
                ),
                id="string-ref-inside-must",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/{name}",
                            "must": [
                                {"must": {"haveType": "directory"}},
                                {"use": "common/some-must-block"},
                            ],
                        }
                    ],
                    conventionSources={"common": "./x.json"},
                ),
                id="use-ref-inside-must",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/{name}",
                            "must": [
                                {
                                    "use": "common/some-must-block",
                                    "if": {"hasFile": "${name}.py"},
                                    "for": {"files": "${name}.py"},
                                    "excludeFiles": ["${name}_skip.py"],
                                    "must": {"haveType": "file"},
                                }
                            ],
                        }
                    ],
                    conventionSources={"common": "./x.json"},
                ),
                id="use-ref-inside-must-with-overrides",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/{name}",
                            "must": [
                                {
                                    "use": "common/foo",
                                    "name": "renamed",
                                    "description": "Overridden description.",
                                }
                            ],
                        }
                    ],
                    conventionSources={"common": "./x.json"},
                ),
                id="use-ref-inside-must-name-description",
            ),
            pytest.param(
                config(
                    [
                        {
                            "name": "convention-with-hint",
                            "description": "Every module needs a docstring.",
                            "hint": "Add a one-line summary at the top of the file.",
                            "paths": "src/**/*.py",
                            "must": {"haveDocstrings": True},
                        }
                    ]
                ),
                id="convention-with-hint",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/{name}",
                            "must": [
                                {
                                    "name": "block-with-hint",
                                    "hint": "Give this block a fix hint.",
                                    "must": {"haveType": "file"},
                                }
                            ],
                        }
                    ],
                ),
                id="must-block-with-hint",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "packages/openai/src/__init__.py",
                            "placeholders": {"providerId": "openai"},
                            "must": {},
                        }
                    ]
                ),
                id="placeholders-map",
            ),
            pytest.param(
                config(
                    [
                        {
                            "use": "common/foo",
                            "paths": "packages/openai/src/__init__.py",
                            "placeholders": {"providerId": "openai"},
                        }
                    ],
                    conventionSources={"common": "./x.json"},
                ),
                id="placeholders-on-use-ref",
            ),
        ],
    )
    def test_accepts(self, payload: dict[str, Any]) -> None:
        assert parses(payload) is True


class TestConfigV1Rejects:
    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(
                config([{"paths": "src/*.py", "must": {"importFrom": ["collections"]}}]),
                id="import-from-not-string",
            ),
            pytest.param(
                config(
                    [
                        {
                            "name": "bad-hint",
                            "hint": 123,
                            "paths": "src/*.py",
                            "must": {"haveType": "file"},
                        }
                    ]
                ),
                id="hint-not-string",
            ),
            pytest.param({"conventions": []}, id="missing-version"),
            pytest.param({"version": "v2", "conventions": []}, id="wrong-version"),
            pytest.param(
                config([{"paths": "src/*.py", "must": {"haveType": "symlink"}}]),
                id="wrong-have-type",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "must": {"matchContent": "TODO"}}]),
                id="match-content-not-array",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "must": {"matchContent": []}}]),
                id="match-content-empty-array",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "must": {"matchContent": ["["]}}]),
                id="match-content-invalid-regex",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "must": {"havePairedFile": ["tests/test_x.py"]}}]),
                id="have-paired-file-not-string",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "must": {"havePairedFile": ""}}]),
                id="have-paired-file-empty-string",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "must": {"haveDocstrings": False}}]),
                id="have-docstrings-false",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "must": {
                                "haveDocstrings": {
                                    "modules": False,
                                    "classes": False,
                                    "functions": False,
                                }
                            },
                        }
                    ]
                ),
                id="have-docstrings-all-targets-disabled",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "must": {"haveDocstrings": {"unknown": True}},
                        }
                    ]
                ),
                id="have-docstrings-unknown-field",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "must": {"annotateFunctions": False}}]),
                id="annotate-functions-false",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "must": {
                                "annotateFunctions": {
                                    "returns": False,
                                    "params": False,
                                }
                            },
                        }
                    ]
                ),
                id="annotate-functions-all-checks-disabled",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "must": {"annotateFunctions": {"unknown": True}},
                        }
                    ]
                ),
                id="annotate-functions-unknown-field",
            ),
            pytest.param(
                config([{"name": "Invalid Name!", "paths": "src/*.py", "must": {}}]),
                id="invalid-convention-name",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "must": {"unknownPredicate": ["foo"]}}]),
                id="unknown-predicate-in-must",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "mustNot": {"unknownPredicate": ["foo"]}}]),
                id="unknown-predicate-in-must-not",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "mustNot": [{"must": {"exportConstants": ["debug"]}}],
                        }
                    ]
                ),
                id="must-not-as-block-array",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "mustNot": ["common/no-debug"]}]),
                id="must-not-as-string-ref",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "mustNot": [{"use": "common/no-debug"}]}]),
                id="must-not-as-use-ref",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "packages/{name}",
                            "must": [
                                {
                                    "if": {
                                        "hasFile": "index.py",
                                        "placeholderSatisfies": "name:segments(1)",
                                    },
                                    "must": {"haveType": "file"},
                                }
                            ],
                        }
                    ]
                ),
                id="if-with-both-conditions",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "must": [{"if": {}, "must": {"haveType": "file"}}]}]),
                id="empty-if",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/*.py",
                            "must": [
                                {"if": {"unknownCondition": "x"}, "must": {"haveType": "file"}}
                            ],
                        }
                    ]
                ),
                id="unknown-if-field",
            ),
            pytest.param(
                config([{"paths": "src/*.py", "must": [{"if": {"hasFile": "index.py"}}]}]),
                id="block-with-neither-must-nor-must-not",
            ),
            pytest.param(
                config(
                    [{"paths": "src/*.py", "severity": "info", "must": {"haveType": "file"}}]
                ),
                id="invalid-severity",
            ),
            pytest.param(
                config([], conventionSources={"Bad Prefix": "./x.json"}),
                id="bad-source-prefix",
            ),
            pytest.param(
                config([], conventionSources={"common": 123}),
                id="non-string-source-value",
            ),
            pytest.param(config(["not-a-reference"]), id="bare-string-not-a-ref"),
            pytest.param(config(["Common/Foo"]), id="bare-string-uppercase"),
            pytest.param(
                config([{"use": "common/some-convention", "name": "renamed"}]),
                id="use-ref-with-name",
            ),
            pytest.param(
                config([{"use": "common/some-convention", "description": "rewritten"}]),
                id="use-ref-with-description",
            ),
            pytest.param(config([{"use": "common"}]), id="use-single-segment"),
            pytest.param(config([{"use": "Common/Foo"}]), id="use-uppercase"),
            pytest.param(config([{"use": "common/Foo"}]), id="use-uppercase-name-segment"),
            pytest.param(
                config([{"use": "common/some-convention", "unknownField": "x"}]),
                id="use-ref-unknown-field",
            ),
            pytest.param(
                config([{"paths": "src/{name}", "must": ["not-a-reference"]}]),
                id="bad-string-ref-inside-must",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/{name}",
                            "must": [{"use": "common/foo", "unknownField": "x"}],
                        }
                    ]
                ),
                id="use-ref-inside-must-unknown-field",
            ),
            pytest.param(
                config(
                    [{"paths": "src/{name}", "must": [{"use": "common/foo", "paths": "src/*.py"}]}]
                ),
                id="use-ref-inside-must-with-paths",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/{name}",
                            "must": [{"use": "common/foo", "severity": "warning"}],
                        }
                    ]
                ),
                id="use-ref-inside-must-with-severity",
            ),
            pytest.param(
                config([{"paths": "src/{name}", "must": [{"use": "not-a-reference"}]}]),
                id="use-ref-inside-must-malformed",
            ),
            pytest.param(
                config(
                    [{"paths": "src/index.py", "placeholders": {"1bad": "value"}, "must": {}}]
                ),
                id="invalid-placeholder-name",
            ),
            pytest.param(
                config(
                    [{"paths": "src/index.py", "placeholders": {"name": "bad value"}, "must": {}}]
                ),
                id="invalid-placeholder-value",
            ),
            pytest.param(
                config(
                    [
                        {
                            "paths": "src/{name}",
                            "must": [{"placeholders": {"name": "foo"}, "must": {}}],
                        }
                    ]
                ),
                id="placeholders-in-inner-block",
            ),
            pytest.param(
                config([], extends="./base/konsistent.json"),
                id="extends-not-array",
            ),
            pytest.param(
                config([], extends=[123]),
                id="extends-item-not-string",
            ),
            pytest.param(
                config([], disable="legacy-rule"),
                id="disable-not-array",
            ),
            pytest.param(
                config([], disable=["Bad Name!"]),
                id="disable-invalid-name",
            ),
            pytest.param(
                config([], unexpectedTopLevel=True),
                id="unknown-top-level-field",
            ),
        ],
    )
    def test_rejects(self, payload: dict[str, Any]) -> None:
        assert parses(payload) is False


class TestReusableConventionsPackage:
    def test_accepts_minimal_package(self) -> None:
        ReusableConventionsPackageV1.model_validate(
            {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "some-convention",
                        "description": "A reusable convention.",
                        "must": {"haveType": "file"},
                    }
                ],
            }
        )

    def test_accepts_optional_hint(self) -> None:
        package = ReusableConventionsPackageV1.model_validate(
            {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "some-convention",
                        "description": "A reusable convention.",
                        "hint": "Consider running the generator first.",
                        "must": {"haveType": "file"},
                    }
                ],
            }
        )

        assert package.conventions[0].hint == "Consider running the generator first."

    def test_requires_name_and_description(self) -> None:
        with pytest.raises(ValidationError):
            ReusableConventionsPackageV1.model_validate(
                {
                    "conventionSpecVersion": "v1",
                    "conventions": [{"must": {"haveType": "file"}}],
                }
            )

    def test_requires_must_or_must_not(self) -> None:
        with pytest.raises(ValidationError):
            ReusableConventionsPackageV1.model_validate(
                {
                    "conventionSpecVersion": "v1",
                    "conventions": [{"name": "x", "description": "y"}],
                }
            )


def plugin_registry_for(*, key: str, value_model: Any = str) -> PredicateRegistry:
    base = builtin_predicate_registry()
    return PredicateRegistry(
        handlers=base.handlers,
        ast_predicates=base.ast_predicates,
        item_level_must_not_predicates=base.item_level_must_not_predicates,
        plugin_value_adapters={key: TypeAdapter(value_model)},
        plugin_forbidden_messages={},
        plugin_validate_placeholders={key: True},
        plugin_origins={},
    )


class TestPluginPredicateValidation:
    def test_accepts_plugins_top_level_key(self) -> None:
        assert parses(config([], plugins=["konsistent-acme-plugin"])) is True

    def test_rejects_plugins_when_not_array(self) -> None:
        assert parses(config([], plugins="konsistent-acme-plugin")) is False

    def test_rejects_plugins_when_item_is_not_string(self) -> None:
        assert parses(config([], plugins=[123])) is False

    def test_accepts_plugin_predicate_only_with_registry_context(self) -> None:
        payload = config(
            [
                {
                    "paths": "src/*.py",
                    "must": {"customRule": "expected"},
                }
            ],
            plugins=["konsistent-custom-plugin"],
        )
        registry = plugin_registry_for(key="customRule", value_model=str)

        parsed = RawConfigV1.model_validate(payload, context=registry.validation_context())

        assert parsed.conventions[0].must is not None
        assert parsed.conventions[0].must.model_extra == {"customRule": "expected"}

    def test_accepts_plugin_predicate_in_must_not_with_registry_context(self) -> None:
        payload = config(
            [
                {
                    "paths": "src/*.py",
                    "mustNot": {"customRule": "expected"},
                }
            ],
            plugins=["konsistent-custom-plugin"],
        )
        registry = plugin_registry_for(key="customRule", value_model=str)

        parsed = RawConfigV1.model_validate(payload, context=registry.validation_context())

        assert parsed.conventions[0].mustNot is not None
        assert parsed.conventions[0].mustNot.model_extra == {"customRule": "expected"}

    def test_validates_plugin_predicate_values_with_adapter(self) -> None:
        payload = config(
            [
                {
                    "paths": "src/*.py",
                    "must": {"customRule": 123},
                }
            ],
            plugins=["konsistent-custom-plugin"],
        )
        registry = plugin_registry_for(key="customRule", value_model=str)

        with pytest.raises(ValidationError) as error:
            RawConfigV1.model_validate(payload, context=registry.validation_context())

        assert 'plugin predicate "customRule" value is invalid' in str(error.value)

    def test_rejects_unregistered_extra_predicate_even_when_registry_exists(self) -> None:
        payload = config(
            [
                {
                    "paths": "src/*.py",
                    "must": {"otherRule": "expected"},
                }
            ],
            plugins=["konsistent-custom-plugin"],
        )
        registry = plugin_registry_for(key="customRule", value_model=str)

        with pytest.raises(ValidationError) as error:
            RawConfigV1.model_validate(payload, context=registry.validation_context())

        assert 'unknown predicate key "otherRule"' in str(error.value)

    def test_unknown_predicate_rejection_is_unchanged_without_registry(self) -> None:
        payload = config(
            [
                {
                    "paths": "src/*.py",
                    "must": {"customRule": "expected"},
                }
            ],
            plugins=["konsistent-custom-plugin"],
        )

        assert parses(payload) is False


class TestReusableConventionsPluginPredicates:
    def test_accepts_plugin_predicate_with_registry_context(self) -> None:
        registry = plugin_registry_for(key="customRule", value_model=str)

        package = ReusableConventionsPackageV1.model_validate(
            {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "some-convention",
                        "description": "A reusable convention.",
                        "must": {"customRule": "expected"},
                    }
                ],
            },
            context=registry.validation_context(),
        )

        assert package.conventions[0].must is not None
        assert package.conventions[0].must.model_extra == {"customRule": "expected"}
