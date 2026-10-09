"""Isolated test server. Fixtures NEVER enter the live database."""

import tempfile
from pathlib import Path
import uvicorn
from backend.app.config import Settings
from backend.app.db import now_utc, make_db
from backend.app.main import create_app
from backend.app.pipeline import Pipeline
from tests.conftest import FakeDiscovery, sample_analysis, sample_article


def main():
    with tempfile.TemporaryDirectory(prefix="finder-browser-") as folder:
        source_file = Path(folder) / "sources.json"
        source_file.write_text("[]")
        settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{folder}/browser.sqlite3",
            sources_file=source_file,
            scheduler_enabled=False,
            ai_api_key="",
            openai_api_key="",
            search_api_key="",
            admin_api_key="test-admin-key",
        )
        engine, factory = make_db(settings.database_url)
        article = sample_article()
        Pipeline(settings, factory, FakeDiscovery([])).persist(sample_analysis(article), [article], now_utc())
        engine.dispose()
        uvicorn.run(create_app(settings), host="127.0.0.1", port=8011, log_level="warning")


if __name__ == "__main__":
    main()
