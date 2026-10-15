from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True)
    database_url: str = ""
    sources_file: Path = ROOT / "config/sources.json"
    trusted_catalog_file: Path = ROOT / "config/trusted_catalog_pages.json"
    telegram_channels_file: Path = ROOT / "config/telegram_channels.json"
    telegram_api_id: int = 0
    telegram_api_hash: SecretStr = SecretStr("")
    telegram_session: SecretStr = SecretStr("")
    telegram_bot_token: SecretStr = SecretStr("")
    admin_telegram_chat_id: str = ""
    ai_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4.1-mini"
    llm_enabled: bool = True
    llm_provider_order: str = "gemini,openrouter,groq,openai"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.1-flash-lite"
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = "openai/gpt-4.1-mini"
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "openai/gpt-oss-20b"
    openai_model: str = ""
    llm_timeout_seconds: float = Field(default=30, ge=1, le=120)
    llm_max_retries_per_provider: int = Field(default=1, ge=0, le=3)
    llm_circuit_breaker_failures: int = Field(default=3, ge=1, le=20)
    search_api_key: SecretStr = SecretStr("")
    admin_api_key: SecretStr = SecretStr("")
    trusted_egress_proxy: bool = False
    scheduler_enabled: bool = True
    database_auto_migrate: bool = True
    startup_data_updates_enabled: bool = True
    cors_origins: list[str] = Field(default_factory=list)
    daily_project_target: int = Field(default=20, ge=1, le=100)
    daily_max_run_seconds: int = Field(default=2700, ge=1, le=2700)
    daily_pages_per_run: int = Field(default=60, ge=0, le=1000)
    daily_pages_per_day: int = Field(default=80, ge=0, le=1000)
    trial_pages_per_run: int = Field(default=40, ge=1, le=200)
    trial_pages_per_day: int = Field(default=40, ge=1, le=200)
    daily_gemini_requests_per_run: int = Field(default=10, ge=0, le=100)
    daily_gemini_requests_per_day: int = Field(default=250, ge=0, le=500)
    daily_groq_requests_per_run: int = Field(default=10, ge=0, le=100)
    daily_groq_requests_per_day: int = Field(default=500, ge=0, le=1000)
    daily_groq_tokens_per_day: int = Field(default=100000, ge=0, le=200000)
    daily_gemini_tokens_per_day: int = Field(default=1000000, ge=0)
    groq_requests_per_minute: int = Field(default=30, ge=1, le=30)
    groq_tokens_per_minute: int = Field(default=8000, ge=1, le=8000)
    groq_tokens_per_request: int = Field(default=5500, ge=512, le=5500)
    gemini_requests_per_minute: int = Field(default=10, ge=1, le=10)
    gemini_tokens_per_minute: int = Field(default=200000, ge=1, le=250000)
    llm_rate_limit_retries: int = Field(default=2, ge=0, le=3)
    llm_rate_limit_backoff_seconds: int = Field(default=15, ge=1, le=60)
    daily_search_requests_per_run: int = Field(default=0, ge=0, le=100)
    daily_search_requests_per_day: int = Field(default=0, ge=0, le=100)
    daily_github_requests_per_run: int = Field(default=2, ge=0, le=10)
    daily_github_requests_per_day: int = Field(default=2, ge=0, le=10)
    daily_candidates_per_run: int = Field(default=80, ge=1, le=500)
    daily_candidates_per_day: int = Field(default=120, ge=1, le=500)
    daily_max_sources: int = Field(default=12, ge=1, le=30)
    daily_llm_min_interval_seconds: int = Field(default=6, ge=1, le=120)
    daily_llm_max_output_tokens: int = Field(default=2048, ge=256, le=4096)
    daily_max_database_bytes: int = Field(default=250_000_000, ge=1, le=500_000_000)
    daily_max_rss_mb: int = Field(default=384, ge=64, le=512)
    free_provider_quotas_confirmed: bool = False
    free_search_quota_confirmed: bool = False
    daily_publish_limit: int = Field(default=100, ge=1, le=100)
    daily_uz_limit: int = Field(default=30, ge=0, le=100)
    scheduler_hour: int = Field(default=9, ge=0, le=23)
    scheduler_timezone: Literal["Asia/Tashkent"] = "Asia/Tashkent"
    github_token: SecretStr = SecretStr("")
    evidence_min_score: float = Field(default=5.0, ge=0, le=10)
    archive_pages: int = Field(default=20, ge=1, le=600)
    search_queries_per_source: int = Field(default=3, ge=1, le=30)
    max_event_followups: int = Field(default=3, ge=0, le=20)
    max_candidates: int = Field(default=30, ge=1, le=200)
    catalog_neutral_rank: float = Field(default=4.5, ge=0, le=10)
    reanalysis_batch_size: int = Field(default=5, ge=1, le=50)
    reanalysis_delay_seconds: float = Field(default=0.2, ge=0, le=10)
    llm_batch_delay_seconds: float = Field(default=1.0, ge=0, le=30)
    reanalysis_failure_limit: int = Field(default=3, ge=1, le=20)
    fetch_timeout: float = Field(default=15, ge=1, le=60)
    max_page_bytes: int = Field(default=2_000_000, ge=1000, le=5_000_000)
    user_agent: str = "StartupFinder/0.1 (+public research aggregator; respects robots.txt)"
    frontend_dist: Path = ROOT / "frontend/dist"

    @model_validator(mode="after")
    def require_database_url(self):
        if not self.database_url.strip():
            raise ValueError("DATABASE_URL is required. Configure PostgreSQL for the application; tests pass an isolated SQLite URL explicitly.")
        return self

    @property
    def ai_key(self) -> str:
        return self.ai_api_key.get_secret_value() or self.openai_api_key.get_secret_value()
