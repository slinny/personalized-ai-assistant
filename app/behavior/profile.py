from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.assistant import Instructions, Language, Name, Personality


class BehaviorProfile(BaseModel):
    """Validated behavior snapshot; accepts loaded ORM profiles via model_validate."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    name: Name
    preferred_user_name: Name | None = None
    warmth: Personality = 0.5
    verbosity: Personality = 0.5
    humor: Personality = 0.5
    formality: Personality = 0.5
    primary_language: Language = "en"
    language_switching_mode: Literal["follow_user", "fixed"] = "follow_user"
    custom_instructions: Instructions = ""
