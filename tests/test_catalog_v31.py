import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from backend.app.catalog import (
    CatalogClassifier, CatalogEntry, CatalogResult, ClassifierFailure, catalog_score,
    decision, deterministic_entry, duplicate_decision, parse_classifier_response,
)
from backend.app.catalog_store import save_catalog_result
from backend.app.db import Candidate, Project, Source
from backend.app.schemas import Article

FIXTURES = json.loads((Path(__file__).parent / "fixtures/catalog_eval.json").read_text())


def article(index=0):
    item = FIXTURES[index]
    return Article(url=item["url"], publisher="Saved source", title=item["title"], text=item["text"],
                   published_at=datetime(2026, 3, 10, tzinfo=timezone.utc), kind="news")


def project_payload(**changes):
    data = {
        "classification": "PROJECT", "name": "KotibAI", "aliases": ["Kotib AI"],
        "creator": None, "official_url": None, "country": "Uzbekistan", "sector": "AI",
        "project_type": "startup", "stage": "launched",
        "what_it_does": "Converts Uzbek voice messages to text.",
        "description_uz": "KotibAI o‘zbek tilidagi ovozli xabarlarni matnga aylantirib biznes jarayonlarini avtomatlashtiradi",
        "scores": {"clarity": 7, "real_product": 7, "novelty": 4, "potential": 4},
        "score_reasons": {"clarity": "Function described", "real_product": "Service operation described",
                          "novelty": "insufficient evidence; neutral fallback",
                          "potential": "insufficient evidence; neutral fallback"},
        "score_evidence": {"novelty": False, "potential": False}, "confidence": 0.91,
    }
    data.update(changes)
    return data


def test_real_saved_fixture_labels_are_hand_written():
    assert [row["expected_label"] for row in FIXTURES] == ["PROJECT", "NOT_PROJECT", "MULTI"]
    assert all(row["label_origin"] == "hand_reviewed_from_saved_page" for row in FIXTURES)


def test_offline_classifier_runs_real_saved_pages_through_mock_llm(settings, monkeypatch):
    from backend.app import catalog

    monkeypatch.setattr(catalog, "public_dns", lambda *_: None)
    responses = [
        project_payload(),
        {"classification": "NOT_PROJECT", "confidence": 0.93, "reason": "scholarship announcement"},
        {"classification": "MULTI", "confidence": 0.9, "entries": [
            project_payload(name="Tezbor", aliases=[], description_uz="Tezbor hududlar orasida yetkazib berish xizmatini raqamli platforma orqali tashkil qiladi"),
            project_payload(name="Tezride", aliases=[], description_uz="Tezride talabalar uchun viloyatlararo taksi safarlarini onlayn kelishish imkonini beradi"),
        ]},
    ]
    class Response:
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"message": {"content": json.dumps(self.payload)}}]}
    class Client:
        def post(self, url, **kwargs):
            assert kwargs["json"]["response_format"] == {"type": "json_object"}
            return Response(responses.pop(0))
    config = settings.model_copy(update={"ai_api_key": SecretStr("offline-test-key")})
    classifier = CatalogClassifier(config, Client())
    assert [classifier.classify(article(index)).classification for index in range(3)] == [
        row["expected_label"] for row in FIXTURES
    ]


def test_llm_schema_scoring_and_status():
    result = parse_classifier_response(project_payload(), article().text)
    assert decision(result, result.entries[0]) == ("AUTO_PUBLISHED", "llm_verified_project")
    assert catalog_score(result.entries[0]) == 5.5
    assert result.entries[0].creator is None


@pytest.mark.parametrize("change,reason", [
    ({"scores": {"clarity": 7, "real_product": 7, "novelty": 6, "potential": 4}}, "invalid_score_evidence"),
    ({"score_reasons": {"clarity": "Clear", "real_product": "Launched", "novelty": "No evidence", "potential": "insufficient evidence; neutral fallback"}}, "invalid_score_evidence"),
    ({"description_uz": "KotibAI matn yozadi"}, "invalid_description"),
    ({"sector": "Magic"}, "invalid_enum"),
    ({"scores": {"clarity": 7, "real_product": 9, "novelty": 4, "potential": 4}}, "invalid_score_evidence"),
])
def test_llm_validation_rejects_invalid_response(change, reason):
    with pytest.raises(ClassifierFailure, match=reason):
        parse_classifier_response(project_payload(**change), article().text)


def test_low_confidence_not_project_goes_to_review():
    weak = parse_classifier_response({"classification": "NOT_PROJECT", "confidence": 0.6,
                                      "reason": "mixed article"}, article(2).text)
    assert decision(weak) == ("REVIEW_REQUIRED", "uncertain_not_project")
    strong = parse_classifier_response({"classification": "NOT_PROJECT", "confidence": 0.9,
                                        "reason": "scholarship announcement"}, article(1).text)
    assert decision(strong) == ("REJECTED", "scholarship announcement")


def test_multi_splits_independent_entries():
    page = article(2)
    one = project_payload(name="Tezbor", aliases=[], description_uz="Tezbor hududlar orasida yetkazib berish xizmatini raqamli platforma orqali tashkil qiladi")
    two = project_payload(name="Tezride", aliases=[], description_uz="Tezride talabalar uchun viloyatlararo taksi safarlarini onlayn kelishish imkonini beradi")
    result = parse_classifier_response({"classification": "MULTI", "entries": [one, two], "confidence": 0.9}, page.text)
    assert [entry.name for entry in result.entries] == ["Tezbor", "Tezride"]


def test_keyless_generic_news_stays_review(settings):
    assert CatalogClassifier(settings).classify(article()).reason == "llm_unavailable"
    assert decision(CatalogClassifier(settings).classify(article())) == ("REVIEW_REQUIRED", "llm_unavailable")


def test_trusted_adapter_requires_explicit_pair_and_meaningful_description(tmp_path):
    path = tmp_path / "trusted.json"
    path.write_text(json.dumps({"entries": [{"adapter": "university", "page_type": "university_project",
                                            "trusted_for_deterministic_publish": True}]}))
    item = article()
    item.adapter, item.page_type = "university", "university_project"
    item.project_name = "KotibAI"
    item.project_description = "KotibAI o‘zbek tilidagi ovozli xabarlarni matnga o‘giradi va murakkab biznes jarayonlarini avtomatlashtirish imkonini beradi."
    entry = deterministic_entry(item, path)
    assert entry and entry.scores is None and entry.project_type == "university_project"
    item.page_type = "news_article"
    assert deterministic_entry(item, path) is None
    item.page_type = "university_project"
    item.project_description = "one of the finalists"
    with pytest.raises(ClassifierFailure, match="insufficient_description"):
        deterministic_entry(item, path)


def test_catalog_persistence_preserves_source_and_deduplicates(settings, factory):
    item = article()
    result = parse_classifier_response(project_payload(), item.text)
    with factory.begin() as session:
        assert save_catalog_result(session, item, result)["auto_published"] == 1
    with factory.begin() as session:
        again = save_catalog_result(session, item, result)
        assert again["duplicates"] >= 1
    with factory() as session:
        projects = session.scalars(select(Project)).all()
        assert len(projects) == 1
        project = projects[0]
        assert project.publication_status == "PUBLISHED"
        assert project.catalog_score == 5.5 and project.score_pending is False
        assert project.first_seen and project.published_at == item.published_at.replace(tzinfo=None)
        assert project.publication_excerpt in item.text
        assert len(project.sources) == 1
        assert len(project.status_history) == 1
        assert session.get(Candidate, item.url).status == "published"


def test_catalog_publication_survives_legacy_audit_and_restart(settings, factory):
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    from backend.app.evidence import audit_existing

    item = article()
    result = parse_classifier_response(project_payload(), item.text)
    with factory.begin() as session:
        save_catalog_result(session, item, result)
    audit_existing(factory, settings.evidence_min_score)
    with TestClient(create_app(settings)) as client:
        listed = client.get("/api/projects?period=all").json()
        assert listed["total"] == 1
        assert listed["items"][0]["name"] == "KotibAI"
    with factory() as session:
        assert session.scalar(select(Project)).publication_status == "PUBLISHED"


def test_llm_disagreement_is_reviewed_without_deletion(settings, factory):
    item = article()
    entry = CatalogEntry(name="KotibAI", confidence=0.9, description_uz="KotibAI o‘zbek tilidagi ovozli xabarlarni matnga o‘giradi va murakkab biznes jarayonlarini avtomatlashtirish imkonini beradi")
    result = CatalogResult("PROJECT", 0.9, (entry,), analysis_method="deterministic")
    with factory.begin() as session:
        save_catalog_result(session, item, result)
    with factory.begin() as session:
        save_catalog_result(session, item, CatalogResult("NOT_PROJECT", 0.8, reason="not product"))
    with factory() as session:
        project = session.scalar(select(Project))
        assert project.publication_status == "REVIEW_REQUIRED"
        assert project.review_reason == "llm_reclassified_not_project"
        assert len(project.status_history) == 2
        assert len(session.scalars(select(Source)).all()) == 1


def test_similar_names_with_conflicting_creators_not_merged(settings, factory):
    item = article()
    first = parse_classifier_response(project_payload(creator="Hikmatilla Ubaydullaev"), item.text)
    with factory.begin() as session:
        save_catalog_result(session, item, first)
    with factory() as session:
        match, possible = duplicate_decision(session, CatalogEntry(name="KotibAI", creator="Another Creator", confidence=0.9), "https://example.org/other")
        assert match is None and possible is None
