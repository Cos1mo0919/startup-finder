"""One bounded, keyless-first daily job. No startup audits or deep enrichment."""

import argparse
import json
import resource
import sys
from collections import Counter
from datetime import timedelta
from time import monotonic

from pydantic import SecretStr
from sqlalchemy import case, func, or_, select

from .catalog_pipeline import CatalogPipeline
from .config import Settings
from .daily import today_stats
from .db import Candidate, DailyStats, RegistrySource, Run, SchedulerCheckpoint, make_db, now_utc
from .free_budget import ACTIVE, BudgetStop, DailyBudget, state_name
from .llm_budget import policies
from .network import canonical_url
from .raw_discovery import ingest_raw
from .registry import due, record_check
from .writer import WriterBusy, writer_scope
from .safe_errors import safe_error


def profile(settings, trial=False):
    target = min(settings.daily_project_target, 5) if trial else settings.daily_project_target
    allowed = settings.free_provider_quotas_confirmed
    search = settings.free_search_quota_confirmed and settings.daily_search_requests_per_day > 0
    limits = {
        "pages": (settings.daily_pages_per_run, settings.daily_pages_per_day),
        "llm:gemini": (settings.daily_gemini_requests_per_run, settings.daily_gemini_requests_per_day),
        "llm:groq": (settings.daily_groq_requests_per_run, settings.daily_groq_requests_per_day),
        "llm:openai": (0, 0), "llm:openrouter": (0, 0),
        "search:brave": (settings.daily_search_requests_per_run, settings.daily_search_requests_per_day),
        "search:github": (settings.daily_github_requests_per_run, settings.daily_github_requests_per_day),
        "candidates": (settings.daily_candidates_per_run, settings.daily_candidates_per_day),
    }
    if trial:
        caps = {"pages": 20, "llm:gemini": 5, "llm:groq": 5, "llm:openai": 0, "llm:openrouter": 0, "search:brave": 0,
                "search:github": 1, "candidates": 20}
        limits = {key: tuple(min(value, caps[key]) for value in values) for key, values in limits.items()}
        limits["pages"] = (settings.trial_pages_per_run, settings.trial_pages_per_day)
    updates = {"scheduler_enabled": False, "database_auto_migrate": False,
               "gemini_model": "gemini-3.1-flash-lite",
               "startup_data_updates_enabled": False, "daily_publish_limit": target, "daily_uz_limit": 0,
               "llm_provider_order": "gemini,groq", "ai_api_key": SecretStr(""),
               "openai_api_key": SecretStr(""), "openrouter_api_key": SecretStr(""),
               "llm_max_retries_per_provider": 0, "max_candidates": 1, "max_event_followups": 0,
               "search_queries_per_source": 1,
               "fetch_timeout": min(settings.fetch_timeout, 10),
               "max_page_bytes": min(settings.max_page_bytes, 500_000)}
    for provider in ("gemini", "groq"):
        if not allowed or not all(limits["llm:" + provider]):
            updates[provider + "_api_key"] = SecretStr("")
    if not search or trial:
        updates["search_api_key"] = SecretStr("")
    return settings.model_copy(update=updates), limits, min(settings.daily_max_run_seconds, 300) if trial else settings.daily_max_run_seconds


def llm_provider_ready(settings):
    """Trials require a confirmed free quota and at least one configured free provider."""
    return bool(settings.free_provider_quotas_confirmed and (
        settings.gemini_api_key.get_secret_value() or settings.groq_api_key.get_secret_value()
    ))


def candidate_budget_key(day, mode):
    if mode not in {"trial", "daily"}:
        raise ValueError("Invalid candidate budget mode")
    return f"free_candidates:{mode}:{day}"


class ModeDailyBudget(DailyBudget):
    """DailyBudget with independent trial/daily candidate ledgers, mirroring pages."""
    def __init__(self, *args, candidate_mode, **kwargs):
        self.candidate_mode = candidate_mode
        super().__init__(*args, **kwargs)
        with self.factory.begin() as session:
            key = candidate_budget_key(self.day, candidate_mode)
            row = session.get(SchedulerCheckpoint, key)
            if row is None:
                session.add(SchedulerCheckpoint(name=key, cursor={"usage": {}, "events": []}))

    def resource_key(self, resource):
        if resource == "candidates":
            return candidate_budget_key(self.day, self.candidate_mode)
        return super().resource_key(resource)

    def check(self, enforce_caps=True):
        super().check(enforce_caps=False)
        if not enforce_caps:
            return
        with self.factory() as session:
            for key, (run_cap, day_cap) in self.limits.items():
                if self.quotas and key.startswith("llm:"):
                    continue
                provider = key.removeprefix("llm:")
                shared = session.get(SchedulerCheckpoint, state_name(self.day)).cursor
                if shared.get("blocked", {}).get(provider):
                    continue
                row = session.get(SchedulerCheckpoint, self.resource_key(key))
                spent = (row.cursor if row else {}).get("usage", {}).get(key, 0)
                if run_cap > 0 and self.used[key] >= run_cap:
                    self.stop("run_limit:" + key)
                if day_cap > 0 and spent >= day_cap:
                    self.stop("daily_limit:" + key)


def next_candidate(factory, seen, llm_ready, source_counts=None, per_source_cap=None):
    # Cheap project/title hints improve yield before source priority/age; only
    # ordering changes. Evidence and classification gates are unchanged.
    with factory() as session:
        text = func.lower(func.coalesce(Candidate.article["title"].as_string(),
                                        Candidate.article["_discovery_title"].as_string(), ""))
        hint = case((or_(*(text.contains(term) for term in ("startup", "startap", "loyiha", "project", "ilova", "prototype"))), 1), else_=0)
        query = select(Candidate.url).outerjoin(RegistrySource, RegistrySource.id == Candidate.source_id).where(
            Candidate.status == "queued" if not llm_ready else or_(
                Candidate.status == "queued",
                (Candidate.status.in_(["pending", "review_required", "error"]) &
                 or_(Candidate.updated_at <= now_utc() - timedelta(hours=6),
                     (Candidate.reason == "llm_unavailable") & (Candidate.analysis_mode == "deterministic")))),
            Candidate.review_decision.not_in(["REJECT", "KEEP_FOR_REVIEW"]))
        if seen:
            query = query.where(Candidate.url.not_in(seen))
        if source_counts is not None and per_source_cap:
            saturated = [source for source, count in source_counts.items()
                         if source is not None and count >= per_source_cap]
            if saturated:
                query = query.where(or_(Candidate.source_id.is_(None), Candidate.source_id.not_in(saturated)))
        return session.scalar(query.order_by(
            case((RegistrySource.source_type.in_(["startup_platform", "university", "hackathon", "accelerator"]), 2),
                 (RegistrySource.id == "show-hn-rss", 2), else_=0).desc(),
            hint.desc(), RegistrySource.priority.desc(), Candidate.updated_at, Candidate.url).limit(1))


def ingest_links(factory, source, links):
    created = 0
    with factory.begin() as session:
        for item in links[:80]:
            url = canonical_url(item["url"])
            _, new = ingest_raw(session, source_adapter=source.id, source_url=url, source_name=source.name,
                                source_type=source.source_type, page_type=source.options.get("page_type", ""),
                                title=item.get("title", ""), publication_date=item.get("published_at"),
                                raw_payload={"free_daily_run_id": ACTIVE.get().run_id} if ACTIVE.get() else {})
            created += int(new)
            if session.get(Candidate, url) is None:
                session.add(Candidate(url=url, source_id=source.id, status="queued", origin=source.source_type,
                                      article={"_queued": True, "_fetch_url": item["url"],
                                               "_feed_date": item["published_at"].isoformat() if item.get("published_at") else None,
                                               "_discovery_title": item.get("title", "")}))
    return created


def run_daily(settings, factory, *, trial=False, pipeline_factory=CatalogPipeline):
    settings, limits, seconds = profile(settings, trial)
    # Classification is mandatory for this bounded worker. Do not touch the queue
    # or candidate counters when the free providers cannot actually be called.
    if not llm_provider_ready(settings):
        return {"status": "completed", "run_id": None, "stop_reason": "no_llm_provider",
                "counts": {"attempted": 0, "processed": 0, "review_required": 0, "llm_requests": 0},
                "usage": {}, "candidate_runs": []}
    try:
        scope = writer_scope(factory, seconds=seconds + 300, mark_interrupted=True)
        with scope:
            now, began = now_utc(), monotonic()
            with factory.begin() as session:
                row = Run(started_at=now, status="running", counts={}, details={"mode": "free_daily", "trial": trial})
                session.add(row)
                session.flush()
                run_id = row.id
                initial = today_stats(session, settings)["published"]
            mode = "trial" if trial else "daily"
            budget = ModeDailyBudget(factory, limits, settings.daily_publish_limit, seconds, run_id,
                                 min_interval=settings.daily_llm_min_interval_seconds,
                                 output_tokens=settings.daily_llm_max_output_tokens,
                                 max_database_bytes=settings.daily_max_database_bytes,
                                 max_rss_mb=settings.daily_max_rss_mb,
                                 page_mode=mode, candidate_mode=mode,
                                 provider_policies=policies(settings))
            with factory.begin() as session:
                row = session.get(SchedulerCheckpoint, state_name(budget.day))
                row.cursor = {**row.cursor, "page_mode": mode, "candidate_mode": mode, "providers_enabled": {
                    "gemini": bool(settings.gemini_api_key.get_secret_value()),
                    "groq": bool(settings.groq_api_key.get_secret_value()),
                    "openai": False, "openrouter": False,
                    "search:brave": bool(settings.search_api_key.get_secret_value())}}
            token = ACTIVE.set(budget)
            pipeline, counts, seen, stop, errors = None, Counter(), set(), "", []
            counts.update({key: 0 for key in ("attempted", "processed", "pipeline_calls_returned", "rejected",
                          "review_required", "duplicates", "published", "fetch_failed", "budget_stopped", "no_decision", "worker_failed")})
            candidate_runs = []
            active_url = None
            trial_sources = Counter()
            try:
                budget.check()
                pipeline = pipeline_factory(settings, factory)
                def drain():
                    nonlocal active_url
                    while True:
                        budget.check()
                        url = next_candidate(factory, seen, bool(pipeline.llm_service and pipeline.llm_service.available),
                                             trial_sources if trial else None, 3 if trial else None)
                        if not url:
                            return
                        active_url = url
                        with factory() as session:
                            source_id = session.get(Candidate, url).source_id
                        budget.reserve("candidates")
                        seen.add(url)
                        if trial:
                            trial_sources[source_id] += 1
                        counts["attempted"] += 1
                        result = pipeline.run(discover=False, only_urls=[url], reanalyze=False)
                        from .run_report import candidate_outcome
                        outcome = candidate_outcome(factory, url, result)
                        candidate_runs.append(outcome)
                        counts["pipeline_calls_returned"] += 1
                        if outcome["stage"] in {"published", "duplicate", "rejected", "review_required", "pending"}:
                            counts["processed"] += 1
                        else:
                            counts[outcome["stage"]] += 1
                        counts["rejected"] += result.get("counts", {}).get("rejected", 0) + result.get("counts", {}).get("pre_filtered", 0)
                        counts["review_required"] += result.get("counts", {}).get("review_required", 0)
                        counts["duplicates"] += result.get("counts", {}).get("duplicates", 0)
                        with factory.begin() as session:
                            row = session.get(Run, run_id)
                            row.details = {**row.details, "candidate_runs": candidate_runs,
                                           "trial_source_counts": dict(trial_sources) if trial else {}}
                        budget.check()
                        active_url = None
                drain()
                with factory() as session:
                    sources = list(session.scalars(select(RegistrySource).where(RegistrySource.enabled.is_(True))
                                                  .order_by(RegistrySource.priority.desc(), RegistrySource.id)))
                checked = 0
                for source in sources:
                    budget.check()
                    if checked >= min(settings.daily_max_sources, 6 if trial else settings.daily_max_sources):
                        stop = "source_batch_complete"
                        break
                    if not due(source, now_utc()):
                        continue
                    if source.collection_method == "search" and (not settings.search_api_key.get_secret_value()
                                                                 or budget.blocked("search:brave")):
                        continue
                    if source.collection_method == "github_search" and (not all(limits["search:github"])
                                                                        or budget.blocked("search:github")):
                        continue
                    checked += 1
                    try:
                        links = pipeline.discovery.collect(source, now_utc(), False)
                        counts["raw_discoveries"] += ingest_links(factory, source, links)
                        search_key = ("search:github" if source.collection_method == "github_search"
                                      else "search:brave" if source.collection_method == "search" else "")
                        blocked = budget.blocked(search_key) if search_key else None
                        record_check(factory, source.id, now_utc(), len(links), error=blocked or "")
                        counts["sources_checked"] += 1
                    except BudgetStop:
                        raise
                    except Exception as exc:
                        record_check(factory, source.id, now_utc(), error="daily_source_failed")
                        errors.append({**safe_error(exc, function="free_daily.collect"), "source_id": source.id})
                    drain()
                stop = stop or "queue_empty_or_sources_complete"
            except BudgetStop as exc:
                stop = str(exc)
            except Exception as exc:
                stop = "worker_error"
                errors.append(safe_error(exc, function="free_daily.run_daily", candidate_url=active_url))
                if active_url:
                    counts["worker_failed"] += 1
                    from .diagnostics import candidate_id
                    candidate_runs.append({"candidate_id": candidate_id(active_url), "stage": "worker_failed",
                                           "exception_class": type(exc).__name__})
            finally:
                try:
                    if pipeline:
                        pipeline.close()
                except Exception as exc:
                    stop = "worker_error"
                    errors.append(safe_error(exc, function="free_daily.close", candidate_url=active_url))
                finally:
                    ACTIVE.reset(token)
                with factory.begin() as session:
                    row = session.get(Run, run_id)
                    daily = session.get(DailyStats, budget.day)
                    counts["published"] = max(0, (daily.published_count if daily else 0) - initial)
                    counts["llm_requests"] = sum(value for key, value in budget.used.items() if key.startswith("llm:"))
                    row.counts = dict(counts)
                    row.status = "failed" if stop == "worker_error" else "completed"
                    refunded = budget.pages.refund(session) if row.status == "failed" else 0
                    page_state = session.get(SchedulerCheckpoint, budget.pages.key).cursor
                    page_report = {"mode": budget.pages.mode, "refunded": refunded,
                                   "attempted_this_run": budget.used["pages"],
                                   "charged_today": page_state.get("usage", {}).get("pages", 0),
                                   "daily_limit": limits["pages"][1]}
                    candidate_state = session.get(SchedulerCheckpoint, candidate_budget_key(budget.day, mode)).cursor
                    candidate_report = {"mode": mode, "attempted_this_run": budget.used["candidates"],
                                        "charged_today": candidate_state.get("usage", {}).get("candidates", 0),
                                        "daily_limit": limits["candidates"][1]}
                    row.finished_at, row.duration_seconds = now_utc(), round(monotonic() - began, 2)
                    row.errors = errors
                    row.details = {**row.details, "stop_reason": stop, "usage": dict(budget.used),
                                   "last_error": errors[-1] if errors else None,
                                   "page_budget": page_report, "candidate_budget": candidate_report,
                                   "candidate_runs": candidate_runs,
                                   "limits": limits, "target": budget.target, "day": budget.day,
                                   "budget_events": budget.events, "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
                    row.details = {**row.details, "remaining_queue": session.scalar(select(func.count()).select_from(Candidate)
                                   .where(Candidate.status.in_(["queued", "pending", "review_required"])))}
            return {"status": "failed" if stop == "worker_error" else "completed", "run_id": run_id,
                    "stop_reason": stop, "counts": dict(counts), "usage": dict(budget.used),
                    "page_budget": page_report, "candidate_budget": candidate_report,
                    "candidate_runs": candidate_runs,
                    "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    except WriterBusy:
        return {"status": "busy", "stop_reason": "another_writer_active"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", action="store_true", help="At most five publications, separate 40-page budget, five calls per free LLM, five minutes")
    parser.add_argument("--reset-trial-pages", action="store_true", help="Read-only preview of today's trial page reset")
    parser.add_argument("--apply", action="store_true", help="Apply trial page reset under writer lease")
    parser.add_argument("--expect-state", help="Fingerprint from the reset preview; rejects changed counters/day")
    parser.add_argument("--inspect-run", type=int, help="Read-only candidate-stage diagnostics for a prior run")
    args = parser.parse_args()
    if sum((args.trial, args.reset_trial_pages, args.inspect_run is not None)) > 1:
        parser.error("Choose only one of --trial, --reset-trial-pages, --inspect-run")
    if (args.apply or args.expect_state) and not args.reset_trial_pages:
        parser.error("--apply/--expect-state require --reset-trial-pages")
    if args.apply and not args.expect_state:
        parser.error("--apply requires --expect-state from the read-only preview")
    try:
        settings = Settings()
        # Never migrate or seed the production schema before taking the lease.
        engine, factory = make_db(settings.database_url, auto_migrate=False, statement_timeout_ms=30000)
        try:
            if args.reset_trial_pages:
                from .page_budget import reset_trial_pages
                result = reset_trial_pages(factory, apply=args.apply, expected=args.expect_state,
                                           limits=(settings.trial_pages_per_run, settings.trial_pages_per_day))
            elif args.inspect_run is not None:
                from .run_report import inspect_run
                result = inspect_run(factory, args.inspect_run)
            else:
                result = run_daily(settings, factory, trial=args.trial)
            print(json.dumps(result, ensure_ascii=False))
        finally:
            engine.dispose()
        return 0 if args.reset_trial_pages or args.inspect_run is not None else int(result.get("status") == "failed")
    except Exception as exc:
        message = {"status": "failed", "error": safe_error(exc, function="free_daily.main")}
        if args.reset_trial_pages:
            message["hint"] = "Reset not applied. Repeat the read-only preview and use its current --expect-state."
        print(json.dumps(message), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())