from .Button import Button

describe = "Button"


def test_renders_label() -> None:
    result = Button(label="Click me")
    assert result["label"] == "Click me"

