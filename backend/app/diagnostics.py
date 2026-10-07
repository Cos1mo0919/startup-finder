from collections import Counter


def inspect_candidate(session, url):
    """Distinguish never discovered, queued, pending, rejected and stored visibility."""
    from sqlalchemy import select
    from .db import Candidate, Project, Source, RejectedCandidate
    from .network import canonical_url

    url = canonical_url(url)
    candidate = session.get(Candidate, url)
    project = session.scalar(select(Project).join(Source).where(Source.url == url))
    rejection = session.get(RejectedCandidate, url)
    return {
        "url": url,
        "status": candidate.status if candidate else "not_discovered",
        "reason": candidate.reason
        if candidate
        else "URL is absent from the candidate queue; no candidate status is available",
        "source_id": candidate.source_id if candidate else None,
        "archive_scope": candidate.archive_scope if candidate else [],
        "attempts": candidate.attempts if candidate else 0,
        "processing_version": candidate.processing_version if candidate else None,
        "published_at": candidate.article.get("published_at") if candidate else None,
        "stored_rejection_reasons": rejection.reasons if rejection else [],
        "project": {
            "id": project.id,
            "name": project.name,
            "visible": project.visible,
            "stop_reasons": project.stop_reasons,
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
            e["code"] in ("requires_api_key", "event_requires_search_key", "source_requires_configuration")
            for e in errors
        ),
        "error_counts": dict(Counter(e["code"] for e in errors)),
    }


def candidate_diagnostics(session):
    from sqlalchemy import select
    from .db import Candidate, Project, RejectedCandidate, Run

    candidates = list(session.scalars(select(Candidate)))
    published = list(session.scalars(select(Project).where(Project.visible.is_(True))))
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
        "pending_reason_stats": dict(Counter(c.reason for c in candidates if c.status == "pending")),
        "language_stats": dict(Counter(c.article.get("language") or "unknown" for c in candidates)),
        "origin_stats": [
            {"origin": k, "label": ORIGIN_LABELS.get(k, k), **dict(v)} for k, v in sorted(origins.items())
        ],
        "historical_counts": dict(
            Counter(
                str(p.published_at.year)
                for p in session.scalars(select(Project).where(Project.visible.is_(True)))
            )
        ),
    }
