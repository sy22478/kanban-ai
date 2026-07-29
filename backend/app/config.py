from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from the environment.

    There is no default for database_url on purpose. If it is missing the process
    fails at import time rather than quietly falling back to something local.
    """

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str


settings = Settings()
