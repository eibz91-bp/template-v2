from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:pass@localhost:5432/loans"
    database_min_pool: int = 5
    database_max_pool: int = 20

    score_provider_url: str = "https://api.scoring-provider.com/v1/score"
    score_min_threshold: int = 600

    stp_url: str = "https://api.stp.com/v1/disburse"
    nvio_url: str = "https://api.nvio.com/v1/disburse"

    http_timeout: float = 30.0

    model_config = {"env_prefix": "LOAN_"}


settings = Settings()
