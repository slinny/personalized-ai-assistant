from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.behavior import BehaviorProfile


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Check(Record):
    kind: Literal["contains", "not_contains", "max_words"]
    value: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_limit(self) -> Self:
        if self.kind == "max_words" and (not self.value.isdecimal() or int(self.value) < 1):
            raise ValueError("max_words requires a positive integer")
        return self


class Turn(Record):
    content: str = Field(min_length=1, max_length=20000)
    checks: list[Check] = Field(default_factory=list)
    rubric: str = Field(min_length=1)


class HistoryPair(Record):
    user: str = Field(min_length=1, max_length=20000)
    assistant: str = Field(min_length=1, max_length=20000)


class Case(Record):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    version: int = Field(ge=1)
    category: str = Field(min_length=1)
    profile: BehaviorProfile
    history: list[HistoryPair] = Field(default_factory=list, max_length=20)
    turns: list[Turn] = Field(min_length=1, max_length=10)


class Suite(Record):
    version: int = Field(ge=1)
    cases: list[Case] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case IDs must be unique")
        return self


def load_suite(path: Path) -> Suite:
    return Suite.model_validate_json(path.read_text(encoding="utf-8"))
