from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

NoteText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class MemoryEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: NoteText


class MemoryCreate(MemoryEdit):
    source_message_id: UUID | None = None


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    content: str
    source_message_id: UUID | None
    created_at: datetime
    updated_at: datetime
