from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Point this at property_platform, connecting as app_platform —
    # never as postgres. See db/README.md.
    #
    # If FastAPI runs inside Docker on the same Windows box as EMMA,
    # use host.docker.internal. If you run uvicorn directly on
    # Windows (no Docker), use localhost instead.
    database_url: str = "postgresql://app_platform:CHANGE_ME@host.docker.internal:5432/property_platform"

    jwt_secret_key: str = "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Comma-separated browser origins allowed to call the API (CORS), e.g.
    # "https://my-site.vercel.app". Empty = no cross-origin browser access.
    cors_origins: str = ""

    # EMMA's chat (app/chat). Change the model or provider here / in .env.
    chat_provider: str = "openai"
    chat_model: str = "gpt-6-luna"
    chat_timezone: str = "America/Los_Angeles"  # what "today" means to EMMA
    chat_reasoning_effort: str = "low"     # "" to leave it to the model
    chat_max_steps: int = 8                # tool rounds per message
    chat_max_output_tokens: int = 4000
    chat_timeout_seconds: int = 60
    chat_limit_per_10min: int = 20         # messages per person
    chat_limit_per_day: int = 200
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # Which copy of the API this is ("real" or "demo"), and which one runs
    # the Telegram bot. Only one process may poll a bot token at a time.
    app_instance: str = "real"
    telegram_bot_token: str = ""
    telegram_bot_for: str = "demo"

    class Config:
        # All secrets live in Emma/.env (repo root). Run uvicorn from api/.
        # A local api/.env, if present, overrides it.
        env_file = ("../.env", ".env")
        extra = "ignore"  # Emma/.env also holds other apps' secrets


settings = Settings()
