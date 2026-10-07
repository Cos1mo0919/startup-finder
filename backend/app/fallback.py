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
    # Unquoted brands must be directly described as a product, never just a company mention.
    for m in re.finditer(
        rf"\b({TOKEN}(?:[.-]{TOKEN})?)\s+(?:nomli\s+)?(?:startapi|startap|platformasi|platforma|ilovasi|ilova|tizimi|servisi|loyihasi|prototipi)\b",
        article.title + " " + article.text[:7000],
    ):
        if m[1] not in {"Yangi", "Ushbu", "Mazkur", "Bu", "Startup", "Base"}:
            candidates.append(m[1])
    for text in (article.title, article.text[:7000]):
        for m in re.finditer(r'[“«"]([^”»"\n]{2,70})[”»"]\s+[^.!?]{0,90}mobil ilovani ishga tushirdi', text):
            candidates.append(m[1].strip())
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
        rf"(?:launched|presented|developed|built|created|demonstrated|создал|представил|разработал|запустил)\s+(?:a |the )?(?:{PRODUCT})\w*\s+({TOKEN}(?:[.-]{TOKEN})?)",
        article.text,
    ):
        candidates.append(m[1])
    return list(dict.fromkeys(n for n in candidates if len(n.split()) <= 8 and "?" not in n))


def creator_in(text):
    patterns = [
        r'[“«"]([^”»"\n]{2,70})[”»"]\s+(?:kompaniyasi\s+)?[^.!?]{0,100}(?:ilovani|platformani|tizimni)\s+ishga tushirdi',
        rf"({TOKEN}(?:\s+{TOKEN}){{0,3}}\s+(?:jamoasi|kompaniyasi|universiteti))[^.!?]{{0,120}}(?:ishlab chiq|yarat|ishga tush)",
        rf"(?:asoschilari|asoschisi|hammuassisi|muallifi|founders?|основатель|основатели|автор)\s*(?:[—–:-]\s*)?({PERSON})",
        rf"({PERSON})\s*(?:tomonidan|developed|created|built|launched|presented|demonstrated|won|разработал|создал|представил|запустил|победил)",
        rf"({TOKEN}(?:\s+{TOKEN}){{0,3}}\s+(?:University|universiteti|instituti|jamoasi|kompaniyasi))\s+tomonidan",
        rf"(?:created|developed|built|launched)\s+by\s+({PERSON})",
        rf"({PERSON})(?:ning)?\s+.{{0,80}}(?:yaratdi|ishlab chiqdi|taqdim etdi)",
        # A quoted organization explicitly credited in the same sentence, not merely mentioned.
        r'[“«"]\s*([A-Z][A-Za-z0-9 .-]{2,50})\s*[”»"](?:ning)?\s+[^.!?]{0,160}(?:tomonidan|hamkorlikda ishlab chiqilgan)',
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return re.sub(r"^(?:In Uzbekistan|В Узбекистане|O‘zbekistonda)\s+", "", m[1].strip())
    return ""


def pending_reason(article):
    names = project_name(article)
    if not names:
        return "ambiguous_project"
    if not creator_in(article.text):
        return "missing_creator"
    if not ACTION.search(article.text):
        return "insufficient_evidence"
    from .detection import is_uzbek

    return "needs_translation" if not is_uzbek(article.text) else "insufficient_evidence"


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
        named_sentence = next(
            (s for s in re.split(r"(?<=[.!?])\s+", quote) if name.lower() in s.lower()), quote
        )
        if not ACTION.search(quote) or FUTURE.search(named_sentence):
            continue
        # Attribution must refer to this product, not another organization later
        # in a long news article. Explicit anaphora is allowed within this passage.
        creator = next(
            (
                creator_in(s)
                for s in re.split(r"(?<=[.!?])\s+", quote)
                if creator_in(s)
                and (name.lower() in s.lower() or re.match(r"(?:Uning|Ushbu loyiha|Loyiha muallifi)\b", s))
            ),
            "",
        )
        if not creator:
            # Explicit attribution elsewhere in the article is kept as a separate fact.
            identity_quote = next(
                (s for s in re.split(r"(?<=[.!?])\s+", text) if name.lower() in s.lower() and creator_in(s)),
                "",
            )
            creator = creator_in(identity_quote)
        else:
            identity_quote = ""
        if not creator:
            continue
        native = is_uzbek(quote)
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
        in_use = bool(re.search(r"foydalanmoqda|foydalanilmoqda|customers use|используют", quote, re.I))
        # Only copy explicitly stated Uzbek functions and audiences, never infer a benefit.
        sentences = re.split(r"(?<=[.!?])\s+", quote)
        problem = next(
            (
                s
                for s in sentences
                if native
                and re.search(r"muammo|yordam beradi|imkon(?:ini|iyat)|osonlashtir|avtomatlashtir", s, re.I)
            ),
            "",
        )
        normalized_quote = re.sub(r"[ʻʼ’'`]", "‘", quote.lower())
        groups = [
            word
            for word in (
                "talabalar",
                "shifokorlar",
                "yo‘lovchilar",
                "tadbirkorlar",
                "kompaniyalar",
                "fermerlar",
            )
            if native and word in normalized_quote
        ]
        business = "kompaniyalar" in groups or "tadbirkorlar" in groups
        individuals = any(g not in ("kompaniyalar", "tadbirkorlar") for g in groups)
        organization = (
            creator if re.search(r"universitet|institut|kompaniya|jamoasi|University", creator, re.I) else ""
        )
        return Analysis(
            is_project=True,
            uzbekistan_related=True,
            name=name,
            creator=creator,
            organization=organization,
            university=organization if re.search(r"universitet|University", organization, re.I) else "",
            summary_uz=description,
            what_uz=description,
            problem_uz=problem[:1500],
            audience_groups=groups,
            audience="both"
            if business and individuals
            else "business"
            if business
            else "individual"
            if individuals
            else "unknown",
            facts=facts,
            evidence=Evidence(
                practical="in_use" if in_use else "prototype" if prototype else "described",
                practical_fact=0,
                usability="available" if launched else "demo" if prototype else "unknown",
                usability_fact=0 if launched or prototype else None,
                problem="stated" if problem else "unknown",
                problem_fact=0 if problem else None,
                audience="specific" if groups else "unknown",
                audience_fact=0 if groups else None,
            ),
            limitations_uz=[
                "Qoidalar asosida ajratilgan ma’lumot. To‘liq tahlil va noma’lum tafsilotlar uchun qo‘shimcha dalil kerak."
            ],
            analysis_mode="extractive",
            extraction_version=5,
        )
    return None
