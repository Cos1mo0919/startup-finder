"""Targeted query plans. No credentials or publisher URLs live here."""

from datetime import date, datetime, time, timedelta
from .dates import TASHKENT

QUERIES = {
    "uz": [
        "talaba loyiha taqdim etdi",
        "innovatsion loyiha ishlab chiqdi",
        "hackathon g‘olibi loyiha",
        "yangi startap ishga tushirdi",
        "universitet loyihasi prototip",
        "yangi dastur yaratildi",
        "tanlov g‘olibi loyiha",
    ],
    "ru": [
        "студент представил проект",
        "стартап презентация",
        "хакатон победитель проект",
        "университет разработал систему",
        "представили прототип",
    ],
    "en": [
        "student project developed",
        "hackathon winner project",
        "startup demo launch",
        "university prototype",
        "innovation competition",
        "accelerator startup demo day",
    ],
}
EVENT_TERMS = [
    "winner",
    "project",
    "loyiha",
    "team",
    "startup",
    "demo",
    "student",
    "g‘olib prototip",
    "победители проекты команды",
]


def targeted_queries(region="Uzbekistan", year=None):
    suffix = f" {year}" if year else ""
    # Interleave languages so a bounded run never spends its entire budget on one language.
    result = []
    for i in range(max(map(len, QUERIES.values()))):
        for phrases in QUERIES.values():
            if i < len(phrases):
                result.append(f"{region} {phrases[i]}{suffix}")
    return result


def archive_windows(start=date(2022, 1, 1), end=date(2026, 9, 30)):
    if start < date(2022, 1, 1) or end < start or end > datetime.now(TASHKENT).date():
        raise ValueError("Archive dates must be 2022 onward, ordered and not in the future")
    return [(max(start, date(y, 1, 1)), min(end, date(y, 12, 31))) for y in range(start.year, end.year + 1)]


def window_bounds(window):
    start, end = window
    return datetime.combine(start, time.min, TASHKENT), datetime.combine(
        end + timedelta(days=1), time.min, TASHKENT
    )


def in_window(value, window):
    if value is None:
        return False
    from .db import aware

    start, end = window_bounds(window)
    return start <= aware(value) < end


def freshness(window):
    return f"{window[0].isoformat()}to{window[1].isoformat()}"
