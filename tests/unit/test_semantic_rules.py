from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from konpy.cli._semantic_rules import (
    SemanticRulesPackageV1,
    SemanticRuleV1,
    read_semantic_rules,
)
from konpy.config.errors import Err, Ok


def valid_package() -> dict[str, object]:
    return {
        "semanticRulesSpecVersion": "v1",
        "rules": [
            {
                "name": "check-error-messages",
                "prompt": "Verify that raised errors contain useful context.",
                "match": ["src/**/*.py"],
                "source": "Errors must contain useful context.",
            }
        ],
    }


def test_valid_package_round_trips() -> None:
    package = SemanticRulesPackageV1.model_validate(valid_package())

    assert package.semanticRulesSpecVersion == "v1"
    assert package.rules[0].name == "check-error-messages"
    assert package.rules[0].match == ["src/**/*.py"]
    assert package.model_dump(mode="json") == valid_package()


def test_package_allows_empty_rules() -> None:
    package = SemanticRulesPackageV1.model_validate(
        {
            "semanticRulesSpecVersion": "v1",
            "rules": [],
        }
    )

    assert package.rules == []


@pytest.mark.parametrize(
    "name",
    [
        "Uppercase",
        "contains_underscore",
        "contains space",
        "",
    ],
)
def test_rule_name_uses_convention_name_pattern(name: str) -> None:
    with pytest.raises(ValidationError):
        SemanticRuleV1.model_validate(
            {
                "name": name,
                "prompt": "Verify the rule.",
                "match": ["**/*.py"],
            }
        )


def test_empty_prompt_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SemanticRuleV1.model_validate(
            {
                "name": "valid-name",
                "prompt": "",
                "match": ["**/*.py"],
            }
        )


def test_empty_match_list_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SemanticRuleV1.model_validate(
            {
                "name": "valid-name",
                "prompt": "Verify the rule.",
                "match": [],
            }
        )


def test_empty_match_item_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SemanticRuleV1.model_validate(
            {
                "name": "valid-name",
                "prompt": "Verify the rule.",
                "match": [""],
            }
        )


def test_source_is_optional_and_may_be_empty() -> None:
    without_source = SemanticRuleV1.model_validate(
        {
            "name": "valid-name",
            "prompt": "Verify the rule.",
            "match": ["**/*.py"],
        }
    )
    with_empty_source = SemanticRuleV1.model_validate(
        {
            "name": "another-name",
            "prompt": "Verify another rule.",
            "match": ["**/*.py"],
            "source": "",
        }
    )

    assert without_source.source is None
    assert with_empty_source.source == ""


@pytest.mark.parametrize(
    ("target", "extra"),
    [
        ("rule", {"unknown": True}),
        ("package", {"unknown": True}),
    ],
)
def test_models_reject_extra_fields(
    target: str,
    extra: dict[str, object],
) -> None:
    payload = valid_package()
    if target == "rule":
        rule = payload["rules"][0]
        assert isinstance(rule, dict)
        rule.update(extra)
    else:
        payload.update(extra)

    with pytest.raises(ValidationError):
        SemanticRulesPackageV1.model_validate(payload)


def test_loader_reads_valid_package(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps(valid_package()), encoding="utf-8")

    result = read_semantic_rules(rules_path)

    assert isinstance(result, Ok)
    assert result.value.rules[0].name == "check-error-messages"


def test_loader_accepts_string_path(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps(valid_package()), encoding="utf-8")

    result = read_semantic_rules(str(rules_path))

    assert isinstance(result, Ok)


def test_loader_missing_file_returns_err(tmp_path: Path) -> None:
    result = read_semantic_rules(tmp_path / "missing.json")

    assert isinstance(result, Err)
    assert "Could not read semantic rules file:" in result.error
    assert "missing.json" in result.error


def test_loader_unreadable_path_returns_err(tmp_path: Path) -> None:
    directory = tmp_path / "rules.json"
    directory.mkdir()

    result = read_semantic_rules(directory)

    assert isinstance(result, Err)
    assert "Could not read semantic rules file:" in result.error


def test_loader_malformed_json_returns_err(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text('{"rules":', encoding="utf-8")

    result = read_semantic_rules(rules_path)

    assert isinstance(result, Err)
    assert "Invalid semantic rules file:" in result.error
    assert "Malformed JSON at line" in result.error


def test_loader_rejects_non_object_json(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text("[]", encoding="utf-8")

    result = read_semantic_rules(rules_path)

    assert isinstance(result, Err)
    assert "Expected a JSON object" in result.error


def test_loader_reports_schema_validation_errors(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "semanticRulesSpecVersion": "v1",
                "rules": [
                    {
                        "name": "missing-prompt",
                        "match": ["**/*.py"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = read_semantic_rules(rules_path)

    assert isinstance(result, Err)
    assert "Invalid semantic rules file:" in result.error
    assert "rules.0.prompt" in result.error
