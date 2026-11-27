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

    class Config:
        # All secrets live in Emma/.env (repo root). Run uvicorn from api/.
        # A local api/.env, if present, overrides it.
        env_file = ("../.env", ".env")
        extra = "ignore"  # Emma/.env also holds other apps' secrets


settings = Settings()
