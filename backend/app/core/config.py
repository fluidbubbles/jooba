from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str

    # Redis
    redis_url: str

    # Nylas
    nylas_client_id: str
    nylas_api_key: str
    nylas_callback_url: str
    nylas_webhook_secret: str = ""  # auto-stored on webhook registration
    nylas_webhook_url: str = ""  # optional — polling fallback if unset

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-5-mini"

    # App
    secret_key: str

    # Provider selection
    email_provider: str  # nylas | mock
    llm_provider: str  # openai | mock

    # Unsubscribe
    unsubscribe_base_url: str

    # Frontend URL (for OAuth redirect)
    frontend_url: str

    # Unreplied threshold
    unreplied_threshold_minutes: int = 5

    # Referral auto-enrollment
    referral_sequence_name: str = "Referral Outreach"
    referral_clarification_sequence_name: str = "Referral Clarification"
    referral_thank_you_sequence_name: str = "Referral Thank You"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
