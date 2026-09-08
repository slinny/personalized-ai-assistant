"""Public SSE contract. Sequence numbers are local to one connection, not replay IDs."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.conversation import MessageResponse

FailureCode = Literal["generation_failed", "generation_timeout", "output_limit", "lease_expired"]


class Started(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_message: MessageResponse
    assistant_message: MessageResponse


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

    def encode(self) -> bytes:
        return f"event: {self.event}\ndata: {self.model_dump_json()}\n\n".encode()
