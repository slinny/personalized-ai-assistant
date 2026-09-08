import re
from typing import Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PostgresDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelBudgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    context_window_tokens: int = Field(gt=0)
    max_output_tokens: int | None = Field(default=None, ge=1, le=16000)
    safety_margin_tokens: int = Field(default=1024, gt=0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    auth_token: SecretStr | None = None
    auth_user_id: UUID | None = None

    @model_validator(mode="after")
    def validate_auth(self) -> Self:
        if (self.auth_token is None) != (self.auth_user_id is None):
            raise ValueError("AUTH_TOKEN and AUTH_USER_ID must be configured together")
        if self.auth_token is not None and not re.fullmatch(
            r"[A-Za-z0-9._~+/-]{32,}=*", self.auth_token.get_secret_value()
        ):
            raise ValueError("AUTH_TOKEN must contain at least 32 ASCII bearer-token characters")
        return self

    openai_api_key: SecretStr | None = None
    openai_model: str | None = Field(default=None, min_length=1, max_length=200)
    openai_timeout_seconds: float = Field(default=30, gt=0, le=120, allow_inf_nan=False)
    openai_max_output_tokens: int = Field(default=2048, ge=1, le=16000)
    context_model_budgets: dict[str, ModelBudgetConfig] = Field(default_factory=dict)
    context_history_scan_limit: int = Field(default=10000, ge=2, le=100000)
    generation_lease_seconds: int = Field(default=180, ge=1, le=3600)

    @model_validator(mode="after")
    def validate_context_budgets(self) -> Self:
        for model, budget in self.context_model_budgets.items():
            if not model or model != model.strip() or len(model) > 200:
                raise ValueError("Context budget keys must be nonblank, trimmed model names")
            output = budget.max_output_tokens or self.openai_max_output_tokens
            if output + budget.safety_margin_tokens >= budget.context_window_tokens:
                raise ValueError("Each model budget must leave room for input")
        return self

    @field_validator("openai_model")
    @classmethod
    def validate_model(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("OPENAI_MODEL must not be blank")
        return value.strip() if value is not None else None

    @field_validator("openai_api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("OPENAI_API_KEY must not be blank")
        return value

    @model_validator(mode="after")
    def validate_generation_lease(self) -> Self:
        if self.generation_lease_seconds <= self.openai_timeout_seconds:
            raise ValueError("Generation lease must exceed provider timeout")
        return self

    app_name: str = "Personalized AI Assistant"
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+psycopg://assistant:assistant@localhost:5432/assistant"
    )

    @field_validator("database_url")
    @classmethod
    def require_psycopg(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use postgresql+psycopg://")
        return value
