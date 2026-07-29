from pydantic_settings import BaseSettings, SettingsConfigDict

# The single development user. Phase 2 deletes this along with app/seed.py, when
# real registration replaces it.
SEED_USER_EMAIL = "sonu@example.com"


class Settings(BaseSettings):
    """Application settings, read from the environment.

    There is no default for database_url on purpose. If it is missing the process
    fails at import time rather than quietly falling back to something local.
    """

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str


settings = Settings()
