from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20000)]

    @field_validator("content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    assistant_profile_id: UUID
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    conversation_id: UUID
    position: int
    role: Literal["user", "assistant"]
    content: str
    status: Literal["in_progress", "completed", "cancelled", "failed"]
    created_at: datetime
    updated_at: datetime


class TurnResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
    omitted_memory_ids: list[str] = Field(default_factory=list)
