import re
from datetime import timedelta
from sqlalchemy import select
from .db import Event, aware
from .dates import parse_date
from .detection import UZBEKISTAN
from .network import canonical_url

EVENT_TYPES = {
    "accelerator_demo": r"accelerator.{0,30}demo|akselerator.{0,30}namoyish|акселератор.{0,30}демо",
    "grant_competition": r"grant.{0,30}(?:tanlov|competition)|грант.{0,30}конкурс",
    "hackathon": r"hackathon|hakaton|хакатон",
    "demo_day": r"demo\s*day|демо.?день",
    "competition": r"tanlov|konkurs|конкурс|competition",
    "exhibition": r"ko‘rgazma|выставк|exhibition",
    "startup_pitch": r"pitch|питч",
    "innovation_forum": r"forum|форум",
    "university_event": r"university.{0,20}(?:event|demo)|universitet.{0,20}tadbir",
}
REGIONS = [
    "Samarqand",
    "Buxoro",
    "Farg‘ona",
    "Andijon",
    "Namangan",
    "Qoraqalpog‘iston",
    "Xorazm",
    "Navoiy",
    "Qarshi",
    "Qashqadaryo",
    "Jizzax",
    "Sirdaryo",
    "Surxondaryo",
    "Toshkent",
]


def detect_event(article):
    text = article.title + " " + article.text
    if not UZBEKISTAN.search(text) and not any(r.lower() in text.lower() for r in REGIONS):
        return None
    event_type = next(
        (key for key, pattern in EVENT_TYPES.items() if re.search(pattern, article.title, re.I)), None
    )
    if (not event_type
            and re.search(r"\bloyihalar\b.{0,80}\bnamoyish etildi\b", article.title, re.I)
            and re.search(r"\b(?:forum|tadbir|ko‘rgazma|hackathon)\w*", article.text[:2500], re.I)):
        event_type = "exhibition"
    if not event_type:
        return None
    quoted = re.search(r'[“«"]([^”»"\n]{3,150})[”»"]', article.title)
    name = quoted[1] if quoted else article.title[:300]
    if not any(re.search(pattern, article.title, re.I) for pattern in EVENT_TYPES.values()):
        # A report headed "which projects were shown?" can name the actual
        # forum only in its lead. Keep that name for useful follow-up queries.
        lead = article.text[:900]
        named_forum = re.search(
            r"((?:Markaziy|Central|International)\s+[^.!?\n]{4,75}?\b(?:venchur\s+forumi|innovation\s+forum|startup\s+forum))\s*\(([A-Z]{2,9})\)",
            lead,
        )
        if named_forum:
            name = named_forum[1].strip() + " (" + named_forum[2] + ")"
    dates = re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", article.text)
    start = parse_date(dates[0]) if dates else None
    end = parse_date(dates[1]) if len(dates) > 1 else None
    if end and start and end < start:
        end = None
    return dict(
        name=name,
        event_type=event_type,
        organizer="",
        country="Uzbekistan",
        city=next((r for r in REGIONS if r.lower() in text.lower()), ""),
        start_date=start,
        end_date=end,
        official_url=article.url if article.kind in ("official", "event", "university") else None,
        source_url=canonical_url(article.url),
        source_id=article.source_id,
        evidence_quote=article.title,
        status="discovered",
    )


def save_event(factory, article, now):
    data = detect_event(article)
    if not data:
        return None, False
    with factory.begin() as session:
        item = session.scalar(select(Event).where(Event.source_url == data["source_url"]))
        if item:
            if item.name == article.title[:300] and data["name"] != item.name:
                item.name = data["name"]
            return item.id, False
        item = Event(**data, discovered_at=now)
        session.add(item)
        session.flush()
        return item.id, True


def event_queries(event, window=None):
    from .queries import EVENT_TERMS

    name = event.name.replace('"', "")
    year = f" {window[0].year}" if window else ""
    return [f'"{name}" Uzbekistan {term}{year}' for term in EVENT_TERMS]


def followup_due(event, now):
    return (
        event.status != "closed"
        and aware(event.discovered_at) >= now - timedelta(days=90)
        and (event.last_checked_at is None or aware(event.last_checked_at) + timedelta(hours=6) <= now)
    )
