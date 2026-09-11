import json
import subprocess
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.theme import Theme, ThemeGenerate, contrast


@pytest.mark.parametrize(
    "changes",
    [
        {"text": "#f4f6fa"},
        {"accent": "#ffffff"},
        {"background": "url(https://example.com)"},
        {"font": "https://example.com/font"},
        {"font_size": 12},
        {"font_size": "18"},
        {"radius": 100},
        {"version": 2},
        {"css": "body { display: none }"},
    ],
)
def test_reject_unreadable_or_executable_theme(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Theme.model_validate({**Theme().model_dump(), **changes})


def test_actual_ui_presets_pass_server_validation() -> None:
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import {curatedThemes} from './app/ui/personalization.mjs';"
            "process.stdout.write(JSON.stringify(curatedThemes));",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    for theme in json.loads(result.stdout).values():
        assert Theme.model_validate(theme)
    assert contrast("#000000", "#ffffff") == 21


def test_generation_input_is_bounded() -> None:
    for prompt in (" ", "x" * 1001):
        with pytest.raises(ValidationError):
            ThemeGenerate(prompt=prompt)
