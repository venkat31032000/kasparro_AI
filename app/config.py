from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---------------------------------------------------------
    # Application
    # ---------------------------------------------------------
    app_name: str = "Kasparro AI Visibility Analysis"


    analyst_token: str = "local-analyst-token"
    reviewer_token: str = "local-reviewer-token"
    # ---------------------------------------------------------
    # Database
    # ---------------------------------------------------------
    database_url: str = "sqlite:///./kasparro.db"

    # ---------------------------------------------------------
    # LLM
    # ---------------------------------------------------------
    # Keep the real API key in .env, never in source code.
    llm_api_key: str | None = None

    # OpenAI-compatible API endpoint.
    llm_base_url: str = "https://api.openai.com/v1"

    # Model used by the live semantic classifier.
    llm_model: str = "gpt-4.1-mini"

    # ---------------------------------------------------------
    # LLM execution limits
    # ---------------------------------------------------------
    llm_timeout_seconds: float = 30.0

    # Bound model output size so malformed/unexpected responses
    # cannot generate arbitrarily large outputs.
    llm_max_output_tokens: int = 800

    # ---------------------------------------------------------
    # Environment configuration
    # ---------------------------------------------------------
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()