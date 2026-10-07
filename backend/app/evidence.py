import re
from sqlalchemy import select
from .dates import valid_date
from .db import Project, ProjectEvidence, RegistrySource, RejectedCandidate, now_utc
from .detection import CONCRETE, IDEA_LIST, SPAM, normalize, editorial_series, financial_program
from .fallback import ACTION
from .network import canonical_url
from .ranking import publisher_group
from .registry import ensure_publisher
from .schemas import Analysis, Article

EVIDENCE_LABELS = {
    "project_exists": "Loyiha mavjudligi",
    "official_launch": "Ommaviy ishga tushirish",
    "prototype_demo": "Prototip namoyishi",
    "hackathon_participation": "Hakatonda ishtirok",
    "competition_result": "Tanlov natijasi",
    "creator_identity": "Muallif yoki jamoa aniqlangan",
    "organization_confirmation": "Tashkilot tasdig‘i",
    "funding": "Moliyalashtirish",
    "award": "Mukofot",
    "official_website": "Rasmiy sayt",
    "github_repository": "GitHub repozitoriysi",
    "media_report": "OAV xabari",
    "active_users": "Amaldagi foydalanuvchilar",
    "university_confirmation": "Universitet tasdig‘i",
    "event_confirmation": "Rasmiy tadbir tasdig‘i",
}
STOP_LABELS = {
    "low_evidence": "Tasdiqlanganlik yetarli emas",
    "missing_source": "Haqiqiy manba yo‘q",
    "creator_unknown": "Muallif yoki jamoa tasdiqlanmagan",
    "existence_unconfirmed": "Mahsulot yoki prototip tasdiqlanmagan",
    "idea_list": "G‘oyalar ro‘yxati",
    "spam": "Spam yoki SEO matni",
    "invalid_date": "Nashr sanasi yaroqsiz",
    "speculation": "Faqat kelajak rejasi yoki taxmin",
    "date_out_of_range": "Nashr sanasi belgilangan oraliqdan tashqarida",
    "not_a_project": "Haqiqiy loyiha aniqlanmadi",
    "not_project": "Haqiqiy loyiha aniqlanmadi",
    "awaiting_analysis": "Tahlil yoki qo‘shimcha dalil kerak",
}
PATTERNS = {
    "official_launch": r"ishga tush|launched|запущ|запуст",
    "prototype_demo": r"prototip.{0,60}(?:namoyish|taqdim)|(?:namoyish|taqdim).{0,60}prototip|prototype|прототип",
    "hackathon_participation": r"(?:hackathon|hakaton|хакатон).{0,100}(?:ishtirok|qatnash|participat|участ)|(?:ishtirok|participat|участ).{0,100}(?:hackathon|хакатон|hakaton)",
    "competition_result": r"g[‘’\']olib|winner|победител",
    "award": r"mukofot|award|наград",
    "funding": r"(?:grant|investitsiya|investment|funding|инвестиц).{0,60}(?:oldi|jalb|received|raised|получ|привлек)",
    "active_users": r"foydalanilmoqda|active users|customers use|используют",
}
EXISTENCE = {
    "official_launch",
    "prototype_demo",
    "hackathon_participation",
    "competition_result",
    "funding",
    "award",
    "active_users",
    "project_exists",
}
GENERIC_IDENTITIES = {
    "universitet",
    "university",
    "team",
    "jamoa",
    "company",
    "kompaniya",
    "unknown",
    "noma lum",
}


def identified(analysis):
    return any(
        v and normalize(v) not in GENERIC_IDENTITIES for v in (analysis.creator, analysis.organization)
    )


def evidence_types(analysis, quote, kind):
    types = set()
    named = normalize(analysis.name) in normalize(quote)
    # A future plan for an unrelated project at the end of a news article must
    # neither prove nor veto existence of the named product.
    existence_quote = " ".join(
        sentence
        for sentence in re.split(r"(?<=[.!?])\s+", quote)
        if normalize(analysis.name) in normalize(sentence)
        or re.match(r"(?:Uning|Ushbu|Loyiha|Tizim|Platforma|Ilova)\b", sentence)
    )
    speculative = re.search(
        r"will be|will launch|not yet|rejalashtiril|yaratilishi mumkin|планируется|будет создан|будет запущен",
        existence_quote,
        re.I,
    )
    if named and not speculative:
        types.update(k for k, pattern in PATTERNS.items() if re.search(pattern, existence_quote, re.I))
        if (
            CONCRETE.search(existence_quote)
            or ACTION.search(existence_quote)
            or re.search(r"created|developed|demonstrated|разработан|создан", existence_quote, re.I)
        ):
            types.add("project_exists")
    if identified(analysis) and any(
        v and normalize(v) in normalize(quote) for v in (analysis.creator, analysis.organization)
    ):
        if re.search(
            r"tomonidan|yarat|ishlab chiq|ishga tush|created|develop|built|launched|presented|team|jamoa|автор|разработ|созда|запуст|представил|asoschi|hammuassis|founder|основател|hamkorlikda",
            quote,
            re.I,
        ):
            types.add("creator_identity")
    if types & EXISTENCE:
        if kind == "university":
            types.add("university_confirmation")
        if kind == "event":
            types.add("event_confirmation")
        if kind == "official":
            types.add("organization_confirmation")
    if kind == "news":
        types.add("media_report")
    for label, url in analysis.links.items():
        if url in quote and label in ("official", "github"):
            types.add("official_website" if label == "official" else "github_repository")
    return types


def attach_evidence(session, project, analysis, articles, now):
    existing = {(e.url, e.evidence_type, e.quote) for e in project.evidence_records}
    for article in articles:
        registry = ensure_publisher(session, article)
        for source in project.sources:
            if source.url == canonical_url(article.url):
                source.source_id = registry.id
        for fact in analysis.facts:
            if canonical_url(fact.source_url) != canonical_url(article.url):
                continue
            for kind in evidence_types(analysis, fact.quote, registry.trust_kind):
                key = (canonical_url(article.url), kind, fact.quote)
                if key in existing:
                    continue
                project.evidence_records.append(
                    ProjectEvidence(
                        url=key[0],
                        evidence_type=kind,
                        quote=fact.quote,
                        source_id=registry.id,
                        confidence=registry.reliability_score / 10,
                        discovered_at=now,
                        notes=EVIDENCE_LABELS[kind],
                    )
                )
                existing.add(key)


def evidence_score(records, registry):
    types = {e.evidence_type for e in records}
    supporting = [e for e in records if e.evidence_type in EXISTENCE]
    quality = max(
        (registry[e.source_id].reliability_score for e in supporting if e.source_id in registry), default=0
    )
    # Identical syndicated quotations do not count as independent corroboration.
    groups, quotes = set(), set()
    for e in supporting:
        quote = normalize(e.quote)
        if quote not in quotes:
            groups.add(publisher_group(e.url))
            quotes.add(quote)
    components = {
        "source": {"label": "Manba ishonchliligi", "score": round(quality * 0.35, 2), "max": 3.5},
        "existence": {"label": "Mavjudlik dalili", "score": 2 if supporting else 0, "max": 2},
        "identity": {
            "label": "Muallif yoki jamoa dalili",
            "score": 1.5 if "creator_identity" in types else 0,
            "max": 1.5,
        },
        "independence": {
            "label": "Turli nashrlardagi mustaqil iqtiboslar",
            "score": min(1.5, max(0, len(groups) - 1) * 0.75),
            "max": 1.5,
        },
        "roles": {
            "label": "Dalil turlari",
            "score": min(
                1.5,
                len(
                    types
                    & (
                        EXISTENCE
                        | {
                            "creator_identity",
                            "university_confirmation",
                            "organization_confirmation",
                            "event_confirmation",
                        }
                    )
                )
                * 0.3,
            ),
            "max": 1.5,
        },
    }
    return round(sum(c["score"] for c in components.values()), 2), components


def evaluate_project(session, project, threshold=5):
    registry = {s.id: s for s in session.scalars(select(RegistrySource))}
    project.confidence, project.confidence_components = evidence_score(project.evidence_records, registry)
    for item in project.evidence_records:
        if item.source_id in registry:
            item.confidence = registry[item.source_id].reliability_score / 10
    types = {e.evidence_type for e in project.evidence_records}
    project.detection_signals = [
        {
            "type": t,
            "label": EVIDENCE_LABELS.get(t, t),
            "urls": list(dict.fromkeys(e.url for e in project.evidence_records if e.evidence_type == t)),
        }
        for t in sorted(types)
    ]
    project.real_project_confidence = round(project.confidence * 10, 1)
    reasons = []
    if project.confidence < threshold:
        reasons.append("low_evidence")
    if not project.sources:
        reasons.append("missing_source")
    if "creator_identity" not in types:
        reasons.append("creator_unknown")
    if not types & EXISTENCE:
        reasons.append("existence_unconfirmed")
    text = project.name + " " + project.content.get("summary_uz", "")
    if editorial_series(text):
        reasons.append("not_project")
    if financial_program(text):
        reasons.append("ecosystem_signal")
    if IDEA_LIST.search(text):
        reasons.append("idea_list")
    if SPAM.search(text):
        reasons.append("spam")
    if not valid_date(project.published_at, now_utc(), archive=True):
        reasons.append("invalid_date")
    project.stop_reasons = reasons
    project.visible = not reasons
    return reasons


def record_rejection(session, url, title, reasons, score=0, signals=None):
    url = canonical_url(url)
    row = session.get(RejectedCandidate, url)
    if row is None:
        row = RejectedCandidate(url=url)
        session.add(row)
    row.title = title[:500]
    row.reasons = list(dict.fromkeys(reasons))
    row.evidence_score = score
    row.signals = signals or []
    row.rejected_at = now_utc()


def audit_existing(factory, threshold):
    """Idempotent backfill and gate for legacy cards; never changes first_seen."""
    from .sectors import classify_sectors

    with factory.begin() as session:
        for project in session.scalars(select(Project)):
            analysis = Analysis.model_validate(project.content)
            articles = [
                Article(
                    url=s.url,
                    publisher=s.publisher,
                    title=project.name,
                    text=" ".join(s.quotes),
                    published_at=s.published_at,
                    kind=s.kind,
                )
                for s in project.sources
            ]
            attach_evidence(session, project, analysis, articles, now_utc())
            project.primary_sector, project.sectors = classify_sectors(analysis)
            reasons = evaluate_project(session, project, threshold)
            if not reasons:
                for source in project.sources:
                    rejected = session.get(RejectedCandidate, source.url)
                    if rejected:
                        session.delete(rejected)
            if reasons and project.sources:
                record_rejection(
                    session,
                    project.sources[0].url,
                    project.name,
                    reasons,
                    project.confidence,
                    project.detection_signals,
                )
