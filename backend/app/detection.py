import re
import unicodedata


def normalize(text):
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^\w\s]", "", text).strip()


UZBEKISTAN = re.compile(
    r"o[‘’ʻʼ'`]?zbekiston|uzbekistan|узбекистан|ўзбекистон|toshkent|ташкент|tashkent|samarqand|самарканд|samarkand|namangan|navoiy|qarshi|qashqadaryo|jizzax|sirdaryo|surxondaryo|xorazm|qoraqalpog|farg[‘’']?ona|andijon|buxoro|nukus",
    re.I,
)
PROJECT = re.compile(
    r"tizim|систем|system|service|servis|qurilma|device|start[ -]?up|startap|стартап|loyiha|проект|prototype|prototip|прототип|ishlab chiq|разработ|launch|ishga tush|taqdim et|namoyish|hackathon|хакатон|hakaton",
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
    from .fallback import ACTION

    return bool(
        UZBEKISTAN.search(text) and PROJECT.search(text) and (EXISTENCE.search(text) or ACTION.search(text))
    )


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
    from .fallback import extract

    return extract(article)


IDEA_LIST = re.compile(
    r"(?:\d+|best|top|eng yaxshi|лучшие).{0,30}(?:startup ideas|startap g[‘’']oyalari|идей для|бизнес.идеи)|startup ideas|startap g[‘’']oyalari",
    re.I,
)
ECOSYSTEM = re.compile(
    r"(?:yangi|new|новый).{0,30}(?:fund|fond|фонд|акселератор|accelerator|grant dasturi)|IT Park.{0,40}(?:kengay|expan|расшир)|davlat dasturi|государственн.{0,15}программ|kompaniya.{0,50}sotib ol|acquires?\b|acquisition of|приобрел.{0,40}компан|(?:investitsiya|investment|funding).{0,40}(?:jalb qildi|raised)|grant.{0,30}(?:dasturi|program|программ)",
    re.I,
)
SPAM = re.compile(r"buy (?:backlinks|followers)|casino bonus|казино.{0,20}бонус|100% guaranteed profit", re.I)


NOISE = re.compile(
    r"(?:mehmonxona|bino|ko‘chmas mulk|hotel|building|недвижимост|здани|гостиниц).{0,60}(?:sotil|sotuv|sale|прода)|lavozim.{0,40}tayin|direktor.{0,40}tayin|назначен|appointed|celebrity|знаменитост|aksiya.{0,30}(?:narxi|qimmat)|stock market|биржев|hamkorlik.{0,40}muhokama|деловая встреча|corporate meeting",
    re.I,
)


def early_reason(article):
    if IDEA_LIST.search(article.title):
        return "idea_list"
    if SPAM.search(article.title + " " + article.text[:1000]):
        return "spam"
    from .fallback import project_name, ACTION

    concrete = bool(project_name(article) and ACTION.search(article.text))
    if not concrete and NOISE.search(article.title):
        return "noise_topic"
    return ""


def material_type(article):
    reason = early_reason(article)
    if reason:
        return "REJECT"
    from .fallback import project_name, ACTION

    concrete = bool(project_name(article) and ACTION.search(article.text))
    if ECOSYSTEM.search(article.title) and not any(
        n.lower() in article.title.lower() for n in project_name(article)
    ):
        return "ECOSYSTEM_SIGNAL"
    from .events import detect_event

    if detect_event(article) and not concrete:
        return "EVENT"
    return "PROJECT" if is_candidate(article) else "OTHER"
