from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    sandbox_image: str = "python:3.12-slim"
    max_timeout_seconds: int = 20
    max_code_chars: int = 20_000
    max_output_chars: int = 4_000
    sandbox_mem_limit: str = "128m"
    sandbox_nano_cpus: int = 500_000_000  # 0.5 CPU
    sandbox_pids_limit: int = 64
    sandbox_tmpfs_size: str = "16m"
    # Caps concurrent sandbox containers -- each one is a real container on
    # the host, not a cheap in-process call.
    max_concurrent: int = 4


settings = Settings()
