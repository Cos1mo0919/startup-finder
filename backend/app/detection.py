import re
import unicodedata
from .schemas import Analysis, Fact, Evidence


def normalize(text):
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^\w\s]", "", text).strip()


UZBEKISTAN = re.compile(
    r"o[‘’ʻʼ'`]?zbekiston|uzbekistan|узбекистан|ўзбекистон|toshkent|ташкент|tashkent|samarqand|самарканд|samarkand|namangan|navoiy|qarshi|qashqadaryo|jizzax|sirdaryo|surxondaryo|xorazm|qoraqalpog|farg[‘’']?ona|andijon|buxoro|nukus",
    re.I,
)
PROJECT = re.compile(
    r"start[ -]?up|startap|стартап|loyiha|проект|prototype|prototip|прототип|ishlab chiq|разработ|launch|ishga tush|taqdim et|namoyish|hackathon|хакатон|hakaton",
    re.I,
)
EXISTENCE = re.compile(
    r"ishga tush(?:ir)?(?:di|ilgan|irildi|gan)|taqdim et(?:di|ildi|ilgan)|namoyish et(?:di|ildi|ilgan)|ishlab chiq(?:di|ildi|ilgan)|yarat(?:di|ildi|ilgan)|prototip|mablag[‘’\']|investitsiya|grant|g[‘’\']olib|foydalan(?:il|moqda)|launched|demonstrated|prototype|funding|developed|представ|запуст|разработал|прототип|получил.{0,40}(?:грант|инвест)",
    re.I,
)


CONCRETE = re.compile(
    r"ishga tush(?:ir)?(?:di|ilgan|irildi|gan)|taqdim et(?:di|ildi|ilgan)|"
    r"namoyish et(?:di|ildi|ilgan)|ishlab chiq(?:di|ildi|ilgan)|yarat(?:di|ildi|ilgan)|"
    r"foydalanilmoqda|(?:grant|investitsiya|mablag‘).{0,25}(?:oldi|olgan|ajratildi|jalb qildi)",
    re.I,
)


def is_candidate(article):
    text = article.title + " " + article.text
    return bool(UZBEKISTAN.search(text) and PROJECT.search(text) and EXISTENCE.search(text))


def is_uzbek(text, declared=""):
    # Reject Cyrillic/foreign-language material in keyless mode, even if html lang is wrong.
    letters = [c for c in text if c.isalpha()]
    if letters and sum("\u0400" <= c <= "\u04ff" for c in letters) / len(letters) > 0.1:
        return False
    markers = re.findall(
        r"\b(?:uchun|bilan|loyiha|loyihasi|ishlab|yangi|tomonidan|hamda|ushbu|foydalanish|etildi|yaratildi|ishga|bo[‘’']lgan|o[‘’']zbekiston)\b",
        text.lower(),
    )
    return len(markers) >= 3


def extractive_analysis(article):
    if not is_candidate(article) or not is_uzbek(article.text, article.language):
        return None
    # Only explicit quoted names adjacent to project/startup are accepted without AI.
    text = article.title + " " + article.text
    match = re.search(
        r'[“«"]([^”»"\n]{2,100})[”»"]\s*(?:nomli\s+)?(?:startap|loyiha|platforma|ilova|dastur|qurilma)',
        text,
        re.I,
    )
    if not match:
        match = re.search(
            r"(@[A-Za-z][A-Za-z0-9_]{4,63})\s+(?:Telegram[- ]?bot|chat[- ]?bot|bot)", text, re.I
        )
    if not match:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", article.text)
    evidence = [s for s in sentences if match[1].lower() in s.lower() and CONCRETE.search(s) and len(s) >= 20]
    if not evidence:
        return None
    quote = evidence[0][:1400]
    identity = re.search(
        r"([A-Z][\w‘’'-]+(?:\s+[A-Z][\w‘’'-]+){0,3}(?:\s+(?:University|universiteti|instituti|jamoasi|kompaniyasi)))\s+tomonidan",
        quote,
    )
    creator = identity[1] if identity else ""
    return Analysis(
        is_project=True,
        uzbekistan_related=True,
        name=match[1],
        creator=creator,
        summary_uz=quote,
        what_uz=quote,
        facts=[Fact(text_uz=quote, quote=quote, source_url=article.url)],
        evidence=Evidence(practical="described", practical_fact=0),
        analysis_mode="extractive",
    )


IDEA_LIST = re.compile(
    r"(?:\d+|best|top|eng yaxshi|лучшие).{0,30}(?:startup ideas|startap g[‘’']oyalari|идей для|бизнес.идеи)|startup ideas|startap g[‘’']oyalari",
    re.I,
)
ECOSYSTEM = re.compile(
    r"(?:yangi|new|новый).{0,30}(?:fund|fond|фонд|акселератор|accelerator|grant dasturi)|IT Park.{0,40}(?:kengay|expan|расшир)|davlat dasturi|государственн.{0,15}программ|kompaniya.{0,50}sotib ol|acquires?\b|acquisition of|приобрел.{0,40}компан|(?:investitsiya|investment|funding).{0,40}(?:jalb qildi|raised)|grant.{0,30}(?:dasturi|program|программ)",
    re.I,
)
SPAM = re.compile(r"buy (?:backlinks|followers)|casino bonus|казино.{0,20}бонус|100% guaranteed profit", re.I)


def material_type(article):
    if IDEA_LIST.search(article.title) or SPAM.search(article.title + " " + article.text[:1000]):
        return "REJECT"
    if ECOSYSTEM.search(article.title):
        return "ECOSYSTEM_SIGNAL"
    from .events import detect_event

    if detect_event(article) and not CONCRETE.search(article.text):
        return "EVENT"
    return "PROJECT" if is_candidate(article) else "OTHER"
