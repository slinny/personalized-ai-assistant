from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Language = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=35)]
ModelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Personality = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
Instructions = Annotated[str, StringConstraints(max_length=10000)]
Greeting = Annotated[str, StringConstraints(max_length=1000)]
Holidays = Annotated[dict[Name, Greeting], Field(max_length=100)]


class AssistantPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    preferred_user_name: Name | None = None
    warmth: Personality | None = None
    verbosity: Personality | None = None
    humor: Personality | None = None
    formality: Personality | None = None
    primary_language: Language | None = None
    language_switching_mode: Literal["follow_user", "fixed"] | None = None
    custom_instructions: Instructions | None = None
    morning_greeting_enabled: StrictBool | None = None
    evening_greeting_enabled: StrictBool | None = None
    good_night_greeting_enabled: StrictBool | None = None
    holiday_preferences: Holidays | None = None
    preferred_model: ModelName | None = None

    @model_validator(mode="after")
    def reject_nonnullable_nulls(self) -> Self:
        for field in self.model_fields_set - {"preferred_user_name", "preferred_model"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class AssistantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    name: str
    preferred_user_name: str | None
    warmth: float
    verbosity: float
    humor: float
    formality: float
    primary_language: str
    language_switching_mode: Literal["follow_user", "fixed"]
    custom_instructions: str
    morning_greeting_enabled: bool
    evening_greeting_enabled: bool
    good_night_greeting_enabled: bool
    holiday_preferences: dict[str, str]
    preferred_model: str | None
