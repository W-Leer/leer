from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    app_name: str = "leer-api"
    app_env: str = "development"

    # --- Database ---
    database_url: str

    # --- Blob storage ---
    blob_backend: str = "local"
    blob_local_root: str = ".leer/blobs"
    blob_inline_threshold_bytes: int = 256 * 1024  # 256 KB

    # --- Optional ---
    log_level: str = "info"

    # Tell Pydantic to read from .env file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance.
    Ensures we only load env once.
    """
    return Settings()
