from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str
    openrouter_model: str = "anthropic/claude-sonnet-4.5"
    reasoning_max_tokens: int = 2000

    postgres_user: str = "appuser"
    postgres_password: str = "changeme"
    postgres_db: str = "chatdb"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    streaming_api_version: str = "v3"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
