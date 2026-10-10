from collections import Counter
import hashlib


def candidate_id(url):
    return "sha256:" + hashlib.sha256(url.encode()).hexdigest()


def inspect_raw(session, reference):
    """Read-only, secret-free processing trace by raw ID or source URL."""
    from sqlalchemy import select
    from .db import RawDiscovery
    from .network import canonical_url

    if str(reference).isdigit():
        row = session.get(RawDiscovery, int(reference))
    else:
        url = canonical_url(reference)
        row = session.scalar(select(RawDiscovery).where(RawDiscovery.source_url == url)
                             .order_by(RawDiscovery.id.desc()))
    if row is None:
        return {"status": "not_found", "reference": reference}
    return {"id": row.id, "source_adapter": row.source_adapter, "source_name": row.source_name,
            "source_url": row.source_url, "external_id": row.external_id, "title": row.title,
            "status": row.status, "reason": row.failure_reason,
            "discovered_at": row.discovered_at.isoformat(),
            "publication_date": row.publication_date.isoformat() if row.publication_date else None,
            "processed_at": row.processed_at.isoformat() if row.processed_at else None,
            "candidate_url": row.candidate_url, "canonical_project_id": row.canonical_project_id,
            "llm_provider": row.llm_provider, "llm_model": row.llm_model,
            "llm_attempt_count": row.llm_attempt_count,
            "classifier_prompt_version": row.classifier_prompt_version,
            "processing_history": row.processing_history or []}


def inspect_candidate(session, url):
    """Distinguish never discovered, queued, pending, rejected and stored visibility."""
    from sqlalchemy import select
    from .db import Candidate, Project, Source, RejectedCandidate
    from .network import canonical_url

    reference = url
    if url.startswith("sha256:"):
        url = next(
            (value for value in session.scalars(select(Candidate.url)) if candidate_id(value) == reference),
            None,
        )
        if url is None:
            return {
                "id": reference,
                "url": None,
                "status": "not_found",
                "reason": "No candidate matches this ID",
                "pending_reason": None,
            }
    url = canonical_url(url)
    candidate = session.get(Candidate, url)
    project = session.scalar(select(Project).join(Source).where(Source.url == url))
    rejection = session.get(RejectedCandidate, url)
    return {
        "id": candidate_id(url),
        "url": url,
        "title": candidate.article.get("title", "") if candidate else "",
        "pending_reason": candidate.reason if candidate and candidate.status in ("pending", "review_required") else None,
        "status": candidate.status if candidate else "not_discovered",
        "reason": candidate.reason
        if candidate
        else "URL is absent from the candidate queue; no candidate status is available",
        "source_id": candidate.source_id if candidate else None,
        "archive_scope": candidate.archive_scope if candidate else [],
        "attempts": candidate.attempts if candidate else 0,
        "processing_version": candidate.processing_version if candidate else None,
        "analysis_mode": candidate.analysis_mode if candidate else None,
        "entity_type": candidate.entity_type if candidate else None,
        "project_ids": candidate.project_ids if candidate else [],
        "last_run_id": candidate.last_run_id if candidate else None,
        "language": candidate.article.get("language") if candidate else None,
        "published_at": candidate.article.get("published_at") if candidate else None,
        "stored_rejection_reasons": rejection.reasons if rejection else [],
        "project": {
            "id": project.id,
            "name": project.name,
            "visible": project.visible,
            "stop_reasons": project.stop_reasons,
            "problem_gate_status": project.problem_gate_status,
            "problem_gate_reason": project.problem_gate_reason,
            "opportunity_grade": project.opportunity_grade,
        }
        if project
        else None,
    }


REASON_LABELS = {
    "needs_translation": "Tarjima kerak",
    "ambiguous_project": "Loyiha nomi yoki mazmuni noaniq",
    "missing_creator": "Muallif yoki jamoa kerak",
    "insufficient_evidence": "Qo‘shimcha dalil kerak",
    "needs_ai_analysis": "AI tahlili kerak",
    "not_project": "Aniq loyiha emas",
    "not_a_project": "Aniq loyiha emas",
    "missing_existence_evidence": "Mavjudlik dalili yo‘q",
    "existence_unconfirmed": "Mavjudlik dalili yo‘q",
    "duplicates": "Dublikat birlashtirildi",
    "old_date": "Oddiy qidiruv uchun eski nashr",
    "invalid_date": "2022-yildan oldin yoki kelajak sanasi",
    "outside_archive_window": "Tanlangan arxiv davridan tashqarida",
    "unknown_publication_date": "Nashr sanasi noma’lum",
    "date_out_of_range": "Nashr sanasi oraliqdan tashqarida",
    "spam": "Spam yoki SEO",
    "idea_list": "G‘oyalar ro‘yxati",
    "noise_topic": "Mavzuga aloqasiz xabar",
    "ecosystem_signal": "Ekotizim xabari",
    "creator_unknown": "Muallif tasdiqlanmagan",
    "low_evidence": "Tasdiqlanganlik yetarli emas",
    "blocked_source": "Manbaga kirish cheklangan",
    "parser_failure": "Sahifani o‘qish xatosi",
    "needs_ai_or_more_evidence": "AI yoki qo‘shimcha dalil kutilmoqda",
    "minor_feature": "Mustaqil muammoni hal qilmaydigan kichik funksiya",
    "pending_problem_analysis": "Muammo dalili qo‘shimcha tekshirilmoqda",
    "missing_target_user": "Muammo kimga taalluqli ekani noma’lum",
    "missing_solution": "Yechim mexanizmi aniq emas",
    "no_meaningful_problem": "Mazmunli mustaqil muammo topilmadi",
    "source_backed_problem_and_solution": "Manbali muammo va yechim tasdiqlandi",
}
ORIGIN_LABELS = {
    "web_search": "Internet qidiruvi",
    "rss": "RSS",
    "uzhunt": "UzHunt",
    "it_park": "IT Park",
    "university": "Universitet",
    "event_discovery": "Tadbir orqali qidiruv",
    "hackathon": "Hakaton",
    "accelerator": "Akselerator",
    "event_source": "Tadbir manbasi",
    "other": "Boshqa",
}


def summarize_run(counts, errors, ai_enabled):
    stages = Counter(e.get("stage", "source") for e in errors)
    return {
        "source_errors": stages["source"],
        "parser_errors": stages["parser"],
        "event_errors": stages["event"],
        "ai_unavailable": not ai_enabled,
        "pending": counts.get("pending", 0),
        "configuration_errors": sum(
            e["code"]
            in (
                "requires_api_key",
                "event_requires_search_key",
                "source_requires_configuration",
                "archive_configuration_missing",
            )
            for e in errors
        ),
        "error_counts": dict(Counter(e["code"] for e in errors)),
    }


def candidate_diagnostics(session):
    from sqlalchemy import select
    from .db import Candidate, Project, RejectedCandidate, Run

    candidates = list(session.scalars(select(Candidate)))
    published = list(session.scalars(select(Project).where(Project.publication_status == "PUBLISHED")))
    reasons = Counter()
    candidate_states = {c.url: c.status for c in candidates}
    for row in session.scalars(select(RejectedCandidate)):
        if candidate_states.get(row.url, "rejected") == "rejected":
            reasons.update(row.reasons)
    origins = {}
    for c in candidates:
        b = origins.setdefault(c.origin or "other", Counter())
        b["candidates"] += 1
        b[c.status] += 1
        if c.analysis_mode:
            b["processed_" + c.analysis_mode] += 1
        if c.status == "error":
            reasons[
                "blocked_source"
                if c.reason.startswith("http_") or "robots" in c.reason
                else "parser_failure"
                if not c.article.get("text")
                else c.reason
            ] += 1
    reasons["ecosystem_signal"] = sum(c.status == "ecosystem" for c in candidates)
    reasons["duplicates"] = sum(r.counts.get("duplicates", 0) for r in session.scalars(select(Run)))
    return {
        "processing_summary": {
            "published_without_ai": sum(p.content.get("analysis_mode") == "extractive" for p in published),
            "deterministic_rated": sum(p.content.get("analysis_mode") == "extractive" for p in published),
            "ai_rated": sum(p.content.get("analysis_mode") == "ai" for p in published),
            "rejected": sum(c.status == "rejected" for c in candidates),
            "pending_ai": sum(
                c.status == "pending"
                or (
                    c.status == "error"
                    and ("translation" in c.reason or c.reason.startswith(("ai_", "unsupported_")))
                )
                for c in candidates
            ),
            "queued": sum(c.status == "queued" for c in candidates),
            "review_required": sum(c.status == "review_required" for c in candidates),
            "processed_ai": sum(c.analysis_mode == "ai" for c in candidates),
            "processed_fallback": sum(c.analysis_mode == "extractive" for c in candidates),
            "ai_errors": sum(
                c.status == "error" and (c.reason.startswith("ai_") or c.reason.startswith("unsupported_"))
                for c in candidates
            ),
            "translation_errors": sum(c.status == "error" and "translation" in c.reason for c in candidates),
        },
        "reject_reason_stats": [
            {"reason": k, "label": REASON_LABELS.get(k, k), "count": v}
            for k, v in sorted(reasons.items())
            if v
        ],
        "pending_reason_stats": dict(Counter(c.reason for c in candidates if c.status in ("pending", "review_required"))),
        "language_stats": dict(Counter(c.article.get("language") or "unknown" for c in candidates)),
        "origin_stats": [
            {"origin": k, "label": ORIGIN_LABELS.get(k, k), **dict(v)} for k, v in sorted(origins.items())
        ],
        "historical_counts": dict(
            Counter(
                str(p.published_at.year)
                for p in session.scalars(select(Project).where(Project.publication_status == "PUBLISHED"))
            )
        ),
    }


def list_candidates(session, status="pending"):
    from sqlalchemy import select
    from .db import Candidate

    query = select(Candidate.url).order_by(Candidate.url)
    if status != "all":
        query = query.where(Candidate.status == status)
    items = [inspect_candidate(session, url) for url in session.scalars(query)]
    return {"status_filter": status, "count": len(items), "items": items}


def debug_report(session, settings):
    """Local diagnostic export: no API keys, proxy URLs, DB credentials or article bodies."""
    import subprocess
    from sqlalchemy import select
    from sqlalchemy.engine import make_url
    from .config import ROOT
    from .db import Candidate, RegistrySource, Run
    from .registry import load_sources

    def git_value(*args):
        try:
            result = subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=5, check=True
            )
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    seeds = {s.id: s for s in load_sources(settings.sources_file)}
    sources = []
    for source in session.scalars(select(RegistrySource).order_by(RegistrySource.id)):
        archive = source.options.get("archive", {})
        seed_archive = seeds[source.id].options.get("archive", {}) if source.id in seeds else None
        sources.append(
            {
                "id": source.id,
                "name": source.name,
                "enabled": source.enabled,
                "method": source.collection_method,
                "archive_configured": bool(archive),
                "seed_archive_configured": bool(seed_archive),
                "archive_matches_seed": archive == seed_archive if seed_archive is not None else None,
                "archive_adapter": "sitemap"
                if archive.get("sitemap_index")
                else "pagination"
                if archive.get("page_url")
                else "current_listings",
                "last_error": source.last_error,
                "consecutive_errors": source.consecutive_errors,
                "last_success_at": source.last_success_at.isoformat() if source.last_success_at else None,
            }
        )
    runs = list(session.scalars(select(Run).order_by(Run.id.desc())))
    selected = runs[:5]
    windows = set()
    for run in runs:
        window = tuple(run.details.get("window", []))
        if window and window not in windows:
            windows.add(window)
            if run not in selected:
                selected.append(run)
    database = make_url(settings.database_url)
    dirty = git_value("status", "--porcelain", "--untracked-files=no")
    return {
        "schema": 1,
        "git_commit": git_value("rev-parse", "HEAD"),
        "tracked_changes": bool(dirty) if dirty is not None else None,
        "database": {
            "driver": database.drivername,
            "file": database.database if database.get_backend_name() == "sqlite" else None,
        },
        "settings": {
            "max_candidates": settings.max_candidates,
            "archive_pages": settings.archive_pages,
            "trusted_egress_proxy": settings.trusted_egress_proxy,
            "ai_enabled": bool(settings.ai_key),
            "search_enabled": bool(settings.search_api_key.get_secret_value()),
            "sources_sha256": hashlib.sha256(settings.sources_file.read_bytes()).hexdigest(),
        },
        "candidate_counts": dict(Counter(session.scalars(select(Candidate.status)))),
        "pending": list_candidates(session),
        "sources": sources,
        "runs": [
            {"id": r.id, "status": r.status, "counts": r.counts, "details": r.details, "errors": r.errors}
            for r in selected
        ],
    }
