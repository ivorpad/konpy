from konpy.config.deprecation_warnings import collect_deprecation_warnings
from konpy.config.schema import ConfigV1


class TestCollectDeprecationWarnings:
    def test_returns_empty_list_when_deprecated_field_is_absent(self) -> None:
        config = ConfigV1.model_validate(
            {
                "version": "v1",
                "conventions": [
                    {
                        "paths": "src/*.py",
                        "must": {
                            "declareFunctions": [
                                {"name": "create", "receiveParamsOfTypes": ["Config"]}
                            ]
                        },
                    }
                ],
            }
        )

        assert collect_deprecation_warnings(config=config) == []

    def test_warns_for_top_level_must_declare_functions(self) -> None:
        config = ConfigV1.model_validate(
            {
                "version": "v1",
                "conventions": [
                    {
                        "paths": "src/*.py",
                        "must": {
                            "declareFunctions": [
                                {"name": "create", "receiveParamOfType": "Config"}
                            ]
                        },
                    }
                ],
            }
        )

        assert collect_deprecation_warnings(config=config) == [
            'Warning: "receiveParamOfType" is deprecated in '
            'conventions[0].must.declareFunctions[0].receiveParamOfType. '
            'Use "receiveParamsOfTypes" instead.'
        ]

    def test_warns_for_top_level_must_not_export_functions(self) -> None:
        config = ConfigV1.model_validate(
            {
                "version": "v1",
                "conventions": [
                    {
                        "paths": "src/*.py",
                        "mustNot": {
                            "exportFunctions": [
                                {"name": "debug", "receiveParamOfType": "Config"}
                            ]
                        },
                    }
                ],
            }
        )

        assert collect_deprecation_warnings(config=config) == [
            'Warning: "receiveParamOfType" is deprecated in '
            'conventions[0].mustNot.exportFunctions[0].receiveParamOfType. '
            'Use "receiveParamsOfTypes" instead.'
        ]

    def test_warns_inside_must_blocks(self) -> None:
        config = ConfigV1.model_validate(
            {
                "version": "v1",
                "conventions": [
                    {
                        "paths": "src/*.py",
                        "must": [
                            {
                                "must": {
                                    "declareFunctions": [
                                        {"name": "create", "receiveParamOfType": "Config"}
                                    ]
                                },
                                "mustNot": {
                                    "exportFunctions": [
                                        {"name": "debug", "receiveParamOfType": "Config"}
                                    ]
                                },
                            }
                        ],
                    }
                ],
            }
        )

        assert collect_deprecation_warnings(config=config) == [
            'Warning: "receiveParamOfType" is deprecated in '
            'conventions[0].must[0].must.declareFunctions[0].receiveParamOfType. '
            'Use "receiveParamsOfTypes" instead.',
            'Warning: "receiveParamOfType" is deprecated in '
            'conventions[0].must[0].mustNot.exportFunctions[0].receiveParamOfType. '
            'Use "receiveParamsOfTypes" instead.',
        ]

    def test_does_not_warn_for_string_function_entries(self) -> None:
        config = ConfigV1.model_validate(
            {
                "version": "v1",
                "conventions": [
                    {
                        "paths": "src/*.py",
                        "must": {"declareFunctions": ["create"]},
                    }
                ],
            }
        )

        assert collect_deprecation_warnings(config=config) == []
