"""Exception-only Telegram admin notifications with durable cooldowns."""

from __future__ import annotations

from datetime import timedelta

import httpx
from sqlalchemy import func, select

from .db import (Candidate, Project, ProjectDeepAnalysis, ProviderHealth,
                 RegistrySource, SchedulerCheckpoint, now_utc, aware)


def exceptional_conditions(session):
    conditions = []
    backlog = session.scalar(select(func.count()).select_from(Candidate).where(
        Candidate.status == "review_required")) or 0
    if backlog >= 100:
        conditions.append(("review_backlog", f"Review queue: {backlog}"))
    broken = session.scalars(select(RegistrySource).where(
        RegistrySource.enabled.is_(True), RegistrySource.consecutive_errors >= 3)).all()
    for source in broken:
        conditions.append((f"source:{source.id}", f"Source {source.id}: {source.consecutive_errors} failures ({source.last_error})"))
    providers = session.scalars(select(ProviderHealth)).all()
    if providers and all(row.consecutive_failures >= 3 for row in providers):
        conditions.append(("llm_all_unhealthy", "All configured LLM providers are failing"))
    strong = session.scalars(select(ProjectDeepAnalysis).join(Project, Project.id == ProjectDeepAnalysis.project_id)
                             .where(Project.publication_status == "PUBLISHED",
                                    ProjectDeepAnalysis.weighted_score >= 80)).all()
    for row in strong:
        conditions.append((f"deep_a:{row.project_id}",
                           f"Deep analysis A candidate: project {row.project_id}, {row.weighted_score}/100"))
    return conditions


def send_alerts(settings, factory, client=None):
    token = settings.telegram_bot_token.get_secret_value()
    chat_id = settings.admin_telegram_chat_id
    if not token or not chat_id:
        return {"status": "not_configured", "sent": 0}
    sender = client or httpx
    sent, failed = 0, 0
    with factory() as session:
        events = exceptional_conditions(session)
    for key, message in events:
        checkpoint_name = f"admin_alert:{key}"
        now = now_utc()
        with factory() as session:
            prior = session.get(SchedulerCheckpoint, checkpoint_name)
            if prior and prior.last_success_at and aware(prior.last_success_at) > now - timedelta(hours=6):
                continue
        try:
            response = sender.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                   json={"chat_id": chat_id, "text": f"izlanish: {message}"}, timeout=15)
            response.raise_for_status()
            if response.json().get("ok") is not True:
                failed += 1
                continue
            with factory.begin() as session:
                checkpoint = session.get(SchedulerCheckpoint, checkpoint_name)
                if checkpoint is None:
                    checkpoint = SchedulerCheckpoint(name=checkpoint_name, cursor={})
                    session.add(checkpoint)
                checkpoint.last_success_at = now
                checkpoint.cursor = {"event": key}
            sent += 1
        except (httpx.HTTPError, ValueError, AttributeError):
            failed += 1
    return {"status": "partial" if failed else "completed", "sent": sent, "failed": failed}
