"""Public SSE contract. Sequence numbers are local to one connection, not replay IDs."""

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.conversation import MessageResponse

FailureCode = Literal["generation_failed", "generation_timeout", "output_limit", "lease_expired"]


class Started(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_message: MessageResponse
    assistant_message: MessageResponse
    omitted_memory_ids: list[str] = Field(default_factory=list)


class Delta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class Terminal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: MessageResponse
    error_code: FailureCode | None = None


class StreamError(BaseModel):
    code: Literal["outcome_unknown"] = "outcome_unknown"


class StreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal[
        "turn.started",
        "message.delta",
        "message.completed",
        "message.cancelled",
        "message.failed",
        "stream.error",
    ]
    message_id: UUID
    sequence: int = Field(ge=1)
    payload: Started | Delta | Terminal | StreamError

    @model_validator(mode="after")
    def consistent_payload(self) -> Self:
        expected = {
            "turn.started": Started,
            "message.delta": Delta,
            "message.completed": Terminal,
            "message.cancelled": Terminal,
            "message.failed": Terminal,
            "stream.error": StreamError,
        }[self.event]
        if not isinstance(self.payload, expected):
            raise ValueError("Event and payload must match")
        if isinstance(self.payload, Terminal):
            if self.event != "message." + self.payload.message.status:
                raise ValueError("Terminal event and saved status must match")
            if self.payload.message.id != self.message_id:
                raise ValueError("Event must identify the saved message")
        if (
            isinstance(self.payload, Started)
            and self.payload.assistant_message.id != self.message_id
        ):
            raise ValueError("Event must identify the reserved message")
        return self

    def encode(self) -> bytes:
        return f"event: {self.event}\ndata: {self.model_dump_json()}\n\n".encode()
