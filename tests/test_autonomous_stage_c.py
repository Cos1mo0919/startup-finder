"""Offline tests for Telegram ingestion, exceptional alerts and post-publication analysis."""

import json
from types import SimpleNamespace

from pydantic import SecretStr
from sqlalchemy import select

from backend.app.admin_alerts import send_alerts
from backend.app.catalog import CatalogEntry, CatalogResult
from backend.app.catalog_pipeline import CatalogPipeline
from backend.app.catalog_store import save_catalog_result
from backend.app.db import Candidate, Project, ProjectDeepAnalysis, RawDiscovery, RegistrySource, now_utc
from backend.app.deep_analysis import deep_analysis_once, validate_criteria, weighted_score
from backend.app.scheduler import make_scheduler
from backend.app.telegram_ingest import configured_channels, ingest_post, poll_channels
from tests.conftest import FakeDiscovery, sample_article


def test_telegram_message_idempotent_and_enters_shared_raw_queue(settings, factory):
    message = SimpleNamespace(id=42, raw_text="AgroKo‘mak yangi loyiha talabalar arizalarini bir joyda yig‘adi. https://example.org",
                              date=now_utc(), media=None)
    assert ingest_post(factory, "uzhunt_uz", message)
    assert not ingest_post(factory, "uzhunt_uz", message)
    pipeline = CatalogPipeline(settings, factory, FakeDiscovery([]))
    result = pipeline.run(discover=False, reanalyze=False)
    assert result["counts"]["review_required"] == 1
    with factory() as session:
        raw = session.scalar(select(RawDiscovery))
        assert raw.source_type == "telegram" and raw.external_id == "42"
        assert raw.raw_payload["linked_urls"] == ["https://example.org"]
        assert session.get(Candidate, raw.source_url).reason == "llm_unavailable"
    pipeline.close()


def test_channel_config_and_poll_checkpoint(settings, factory, tmp_path):
    path = tmp_path / "channels.json"
    path.write_text(json.dumps({"channels": [{"username": "@uzhunt_uz", "enabled": True},
                                            {"username": "bad/path", "enabled": True}]}))
    assert configured_channels(path) == ["uzhunt_uz"]
    settings = settings.model_copy(update={"telegram_channels_file": path})
    assert __import__("asyncio").run(poll_channels(settings, factory))["status"] == "credentials_missing"


def test_deep_analysis_after_publication_does_not_change_publication(settings, factory):
    article = sample_article()
    with factory.begin() as session:
        save_catalog_result(session, article, CatalogResult("PROJECT", 0.9, (
            CatalogEntry(name="AgroKo‘mak", confidence=0.9,
                         description_uz="AgroKo‘mak talabalar arizalarini bir joyda to‘playdi va ishni tezlashtiradi."),),
            analysis_method="deterministic"))
    class Service:
        available = True
        def analyze_json(self, system, user, validate):
            return SimpleNamespace(result=validate({"criteria": {"pain_strength": {
                "score": 3, "reason": "Manual processing costs time", "evidence_refs": [article.url]}}}),
                provider="groq", model="offline")
    result = deep_analysis_once(settings, factory, Service())
    assert result["analyzed"] == 1
    with factory() as session:
        project = session.scalar(select(Project))
        deep = session.get(ProjectDeepAnalysis, project.id)
        assert project.publication_status == "PUBLISHED"
        assert deep.criteria["pain_strength"]["score"] == 3
        assert deep.weighted_score is None


def test_deep_weights_need_validation_and_evidence_refs(settings, factory, tmp_path):
    path = tmp_path / "weights.json"
    path.write_text(json.dumps({"version": "unverified", "validated": False, "weights": {}}))
    assert weighted_score({}, path) == (None, "unverified")
    try:
        validate_criteria({"criteria": {"pain_strength": {"score": 5, "reason": "Unverified",
            "evidence_refs": ["https://invented.example"]}}}, {"https://source.example"})
        assert False, "invalid evidence accepted"
    except ValueError:
        pass


def test_admin_alerts_only_exceptional_with_cooldown(settings, factory):
    with factory.begin() as session:
        session.add(RegistrySource(id="failing", name="Failing", url="https://source.example",
                                   enabled=True, consecutive_errors=3, last_error="http_503"))
    class Sender:
        def __init__(self):
            self.calls = []
        def post(self, url, json, timeout):
            self.calls.append(json)
            return SimpleNamespace(raise_for_status=lambda: None)
    sender = Sender()
    config = settings.model_copy(update={"telegram_bot_token": SecretStr("test-token"),
                                         "admin_telegram_chat_id": "123"})
    first = send_alerts(config, factory, sender)
    assert first["sent"] == 1 and len(sender.calls) == 1
    assert send_alerts(config, factory, sender)["sent"] == 0
    assert len(sender.calls) == 1
    assert "test-token" not in str(sender.calls)


def test_scheduler_registers_optional_workers(settings, factory):
    scheduler = make_scheduler(settings, factory)
    assert {job.id for job in scheduler.get_jobs()} >= {"telegram_ingestion", "admin_alerts", "deep_analysis"}
