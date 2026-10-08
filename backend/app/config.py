from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str
    openrouter_model: str = "anthropic/claude-sonnet-4.5"
    # "effort" (low|medium|high), not "max_tokens" -- verified live against a
    # real OpenRouter call: anthropic/claude-sonnet-4.5 via OpenRouter returns
    # reasoning_details with {"effort": "high"} but NOT with {"max_tokens": N},
    # contradicting earlier research that claimed Anthropic models need the
    # budget-token style. Confirmed deepseek/deepseek-r1 DOES work with
    # max_tokens, so this is model/provider-specific, not a universal rule.
    reasoning_effort: str = "high"

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
