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
    nylas_webhook_secret: str = Field(default="")
    nylas_webhook_url: str = Field(default="")

    # OpenAI
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")

    # App
    secret_key: str = Field(default="change-me-in-production")

    # Provider selection
    email_provider: str = Field(default="nylas")  # nylas | mock
    llm_provider: str = Field(default="openai")  # openai | mock

    # Unsubscribe
    unsubscribe_base_url: str = Field(default="http://localhost:8000/api/unsubscribe")

    # Frontend URL (for OAuth redirect)
    frontend_url: str = Field(default="http://localhost:3000")

    # Unreplied threshold
    unreplied_threshold_minutes: int = Field(default=5)

    # Referral auto-enrollment
    referral_sequence_name: str = Field(default="Referral Outreach")
    referral_clarification_sequence_name: str = Field(default="Referral Clarification")
    referral_thank_you_sequence_name: str = Field(default="Referral Thank You")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
