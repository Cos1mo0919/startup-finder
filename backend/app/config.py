from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str = f"sqlite:///{ROOT / 'data/finder.sqlite3'}"
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

    @property
    def ai_key(self) -> str:
        return self.ai_api_key.get_secret_value() or self.openai_api_key.get_secret_value()
