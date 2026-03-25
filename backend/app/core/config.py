from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = Field(default="postgresql+asyncpg://jooba:jooba@db:5432/jooba")

    # Redis
    redis_url: str = Field(default="redis://redis:6379/0")

    # Nylas
    nylas_client_id: str = Field(default="")
    nylas_api_key: str = Field(default="")
    nylas_callback_url: str = Field(default="http://localhost:8000/api/nylas/callback")

    # OpenAI
    openai_api_key: str = Field(default="")

    # App
    secret_key: str = Field(default="change-me-in-production")

    # Provider selection
    email_provider: str = Field(default="nylas")  # nylas | mock
    llm_provider: str = Field(default="openai")  # openai | mock

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
