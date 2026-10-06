from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str = f"sqlite:///{ROOT / 'data/finder.sqlite3'}"
    sources_file: Path = ROOT / "config/sources.json"
    ai_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4.1-mini"
    search_api_key: SecretStr = SecretStr("")
    trusted_egress_proxy: bool = False
    scheduler_enabled: bool = True
    evidence_min_score: float = Field(default=5.0, ge=0, le=10)
    max_event_followups: int = Field(default=3, ge=0, le=20)
    max_candidates: int = Field(default=30, ge=1, le=200)
    fetch_timeout: float = Field(default=15, ge=1, le=60)
    max_page_bytes: int = Field(default=2_000_000, ge=1000, le=5_000_000)
    user_agent: str = "StartupFinder/0.1 (+public research aggregator; respects robots.txt)"
    frontend_dist: Path = ROOT / "frontend/dist"

    @property
    def ai_key(self) -> str:
        return self.ai_api_key.get_secret_value() or self.openai_api_key.get_secret_value()
