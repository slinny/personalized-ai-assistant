"""A deliberately small, non-executable appearance contract."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Color = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]


def luminance(color: str) -> float:
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
    return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


def contrast(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class Theme(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1] = 1
    background: Color = "#f4f6fa"
    surface: Color = "#ffffff"
    text: Color = "#202b40"
    accent: Color = "#294fc4"
    font: Literal["system", "serif"] = "system"
    font_size: int = Field(default=16, ge=16, le=22)
    spacing: Literal["comfortable", "compact"] = "comfortable"
    radius: int = Field(default=16, ge=0, le=24)

    @model_validator(mode="after")
    def readable(self) -> Self:
        for foreground in (self.text, self.accent):
            for background in (self.background, self.surface):
                if contrast(foreground, background) < 4.5:
                    raise ValueError("Text and accent must have 4.5:1 contrast on both surfaces")
        return self


class ThemeGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    current: Theme | None = None
