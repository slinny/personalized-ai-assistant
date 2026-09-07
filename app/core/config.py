import re
from typing import Self
from uuid import UUID

from pydantic import PostgresDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
