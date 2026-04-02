from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    app_name: str = "leer-api"
    app_env: str = "development"

    # --- Database ---
    database_url: str

    # --- Blob storage (shared) ---
    blob_backend: str = "local"
    blob_inline_threshold_bytes: int = 256 * 1024  # 256 KB

    # --- Blob storage: local ---
    blob_local_root: str = ".leer/blobs"

    # --- Blob storage: S3 ---
    blob_s3_bucket: str | None = None
    blob_s3_region: str | None = None
    blob_s3_prefix: str = ""

    # --- Blob storage: Azure ---
    blob_azure_container: str | None = None
    blob_azure_account_url: str | None = None
    blob_azure_connection_string: str | None = None
    blob_azure_prefix: str = ""

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
