"""Conservative entity/attribution extraction; no invented translation or identity."""

import re
from .schemas import Analysis, Fact, Evidence

PRODUCT = r"startap|startup|стартап|loyiha|проект|project|platforma|платформ|platform|ilova|приложени|app|dastur|software|qurilma|устройств|device|tizim|систем|system|prototip|prototype|прототип|servis|сервис|service|bot|ekotizim|onlayn maydon"
ACTION = re.compile(
    r"yarat(?:di|ildi|ilgan|gan)|ishlab chiq(?:di|ildi|ilgan|qan)|ishga tush(?:ir)?(?:di|irildi|irilgan|gan)|taqdim et(?:di|ildi|ilgan)|namoyish et|faoliyat (?:yurit|ko‘rsat)|ish boshlagan|foydalan(?:moqda|ilmoqda)|taklif etadi|developed|created|built|launched|presented|demonstrated|won (?:a |the )?hackathon|разработа[лн]|созда[лн]|представи[лв]|запусти[лв]|победил.{0,30}хакатон|g[‘’ʻ']olib bo[‘’ʻ']ldi",
    re.I,
)
FUTURE = re.compile(
    r"will (?:be|launch|build)|not yet|rejalashtiril|yaratilishi mumkin|планируется|будет (?:создан|запущен)",
    re.I,
)
TOKEN = r"[A-ZА-ЯЁЎҚҒҲ][\w‘’ʻʼ'`-]+"
PERSON = rf"{TOKEN}(?:\s+{TOKEN}){{1,3}}"


def project_name(article):
    candidates = []
    for text in (article.title, article.text[:7000]):
        for m in re.finditer(
            rf'[“«"]\s*([^”»"\n]{{2,90}}?)\s*[”»"]\s*(?:deb nomlangan\s+|nomli\s+)?(?:{PRODUCT})', text, re.I
        ):
            candidates.append(m[1].strip())
        for m in re.finditer(rf'(?:{PRODUCT})\w*\s+[“«"]\s*([^”»"\n]{{2,90}}?)\s*[”»"]', text, re.I):
            candidates.append(m[1].strip())
    # Branded interview headings, e.g. "Brand: ..."; require a definition in the body.
    heading = re.match(r"([A-Z][A-Za-z0-9.-]{2,45})\s*[:—–]", article.title)
    if heading and re.search(re.escape(heading[1]) + rf"\s*[—–-].{{0,200}}(?:{PRODUCT})", article.text, re.I):
        candidates.insert(0, heading[1])
    bot = re.search(
        r"(@[A-Za-z][A-Za-z0-9_]{4,63})\s+(?:Telegram[- ]?bot|chat[- ]?bot|bot)", article.text, re.I
    )
    if bot:
        candidates.append(bot[1])
    # Unquoted named products next to explicit launch verbs.
    for m in re.finditer(
        rf"(?:launched|presented|developed|создал|представил|разработал)\s+(?:a |the )?(?:{PRODUCT})\w*\s+({TOKEN}(?:[.-]{TOKEN})?)",
        article.text,
    ):
        candidates.append(m[1])
    return list(dict.fromkeys(n for n in candidates if len(n.split()) <= 8))


def creator_in(text):
    patterns = [
        rf"(?:asoschilari|asoschisi|hammuassisi|muallifi|founders?|основатель|основатели|автор)\s*(?:[—–:-]\s*)?({PERSON})",
        rf"({PERSON})\s*(?:tomonidan|developed|created|built|launched|presented|разработал|создал|представил)",
        rf"({TOKEN}(?:\s+{TOKEN}){{0,3}}\s+(?:University|universiteti|instituti|jamoasi|kompaniyasi))\s+tomonidan",
        rf"(?:created|developed|built|launched)\s+by\s+({PERSON})",
        rf"({PERSON})(?:ning)?\s+.{{0,80}}(?:yaratdi|ishlab chiqdi|taqdim etdi)",
        # A quoted organization explicitly credited in the same sentence, not merely mentioned.
        r'[“«"]\s*([A-Z][A-Za-z0-9 .-]{2,50})\s*[”»"](?:ning)?\s+[^.!?]{0,160}(?:tomonidan|hamkorlikda ishlab chiqilgan)',
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return re.sub(r"^(?:In )?(?:Uzbekistan|Узбекистане|O‘zbekiston)\s+", "", m[1].strip())
    return ""


def extract(article):
    from .detection import is_candidate, is_uzbek

    if not is_candidate(article):
        return None
    text = article.text.split("\nHavolalar:")[0]
    for name in project_name(article):
        position = text.lower().find(name.lower())
        if position < 0:
            continue
        # A contiguous original passage; no stitched or translated quotation.
        begin = max(0, text.rfind(". ", 0, position) + 2) if ". " in text[:position] else 0
        quote = text[begin : begin + 1800]
        if not ACTION.search(quote) or FUTURE.search(quote[:500]):
            continue
        creator = creator_in(quote)
        if not creator:
            # Explicit attribution elsewhere in the article is kept as a separate fact.
            identity_quote = next(
                (s for s in re.split(r"(?<=[.!?])\s+", text) if name.lower() in s.lower() and creator_in(s)),
                "",
            )
            creator = creator_in(identity_quote)
        else:
            identity_quote = ""
        native = is_uzbek(quote)
        if not native and not creator:
            continue
        description = (
            quote[:1400]
            if native
            else f"Ushbu loyiha O‘zbekiston bilan bog‘liq. Manbada {name} loyihasi va uning yaratuvchisi — {creator} haqida ma’lumot berilgan. Asl dalil quyida keltirilgan; to‘liq tarjima uchun AI tahlili kerak."
        )
        facts = [
            Fact(
                text_uz=quote[:1400]
                if native
                else f"Ushbu loyiha uchun {name} nomi va {creator} haqidagi ma’lumot manbada ko‘rsatilgan.",
                quote=quote,
                source_url=article.url,
            )
        ]
        if identity_quote:
            facts.append(
                Fact(
                    text_uz=f"Ushbu loyiha uchun {creator} nomi manbada muallif sifatida ko‘rsatilgan.",
                    quote=identity_quote[:1800],
                    source_url=article.url,
                )
            )
        prototype = bool(re.search(r"prototip|prototype|прототип", quote, re.I))
        launched = bool(re.search(r"ishga tush|launched|запуст", quote, re.I))
        return Analysis(
            is_project=True,
            uzbekistan_related=True,
            name=name,
            creator=creator,
            summary_uz=description,
            what_uz=description,
            facts=facts,
            evidence=Evidence(
                practical="prototype" if prototype else "described",
                practical_fact=0,
                usability="available" if launched else "demo" if prototype else "unknown",
                usability_fact=0 if launched or prototype else None,
            ),
            limitations_uz=[
                "Qoidalar asosida ajratilgan ma’lumot. To‘liq tahlil va noma’lum tafsilotlar uchun qo‘shimcha dalil kerak."
            ],
            analysis_mode="extractive",
        )
    return None
