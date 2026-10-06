from urllib.parse import urlsplit

RUBRIC = {
    "practical": ("Praktik foyda", {"unknown": 0, "described": 0.5, "prototype": 1.5, "in_use": 2.5}),
    "problem": ("Muammoni hal qilish", {"unknown": 0, "stated": 1, "demonstrated": 2}),
    "audience": ("Potensial auditoriya", {"unknown": 0, "specific": 0.75, "multiple": 1.5}),
    "innovation": ("Innovatsionlik", {"unknown": 0, "adaptation": 0.5, "novel": 1.5}),
    "usability": ("Foydalanish imkoniyati", {"unknown": 0, "demo": 0.5, "available": 1, "adopted": 1.5}),
}
LEVELS = {
    "unknown": "Dalil yetarli emas",
    "described": "Vazifasi bayon qilingan",
    "prototype": "Prototip namoyish etilgan",
    "in_use": "Amalda qo‘llanmoqda",
    "stated": "Muammo bayon qilingan",
    "demonstrated": "Yechim natijasi ko‘rsatilgan",
    "specific": "Aniq auditoriya",
    "multiple": "Bir nechta auditoriya",
    "adaptation": "Mavjud yechimga moslashtirish",
    "novel": "Yangiligi dalillangan",
    "demo": "Namoyish mavjud",
    "available": "Foydalanish mumkin",
    "adopted": "Foydalanuvchilar mavjud",
}


def publisher_group(url):
    # Shared subdomains count as one publisher; configured syndication is not independent proof.
    host = (urlsplit(url).hostname or "").removeprefix("www.")
    return ".".join(host.split(".")[-3:] if host.endswith((".co.uk", ".com.uz")) else host.split(".")[-2:])


def score(analysis, sources):
    components = {}
    for key, (label, values) in RUBRIC.items():
        value = getattr(analysis.evidence, key)
        index = getattr(analysis.evidence, key + "_fact")
        supported = index is not None and 0 <= index < len(analysis.facts)
        value = value if supported else "unknown"
        components[key] = {
            "label": label,
            "score": values[value],
            "max": max(values.values()),
            "reason": LEVELS[value],
            "fact_index": index if supported else None,
        }
    kinds = {s.kind for s in sources}
    quality = 1 if kinds & {"official", "university", "event"} else 0.6 if "news" in kinds else 0.2
    components["source"] = {
        "label": "Manba ishonchliligi",
        "score": quality,
        "max": 1,
        "reason": "Rasmiy manba" if quality == 1 else "OAV manbasi" if quality == 0.6 else "Noma’lum manba",
    }
    return round(sum(c["score"] for c in components.values()), 2), components


def confidence(analysis, sources):
    kinds = {s.kind for s in sources}
    publishers = {publisher_group(s.url) for s in sources}
    # Different domains are corroboration candidates, not a guarantee of independent reporting.
    components = {
        "source": {
            "label": "Manba turi",
            "score": 4 if kinds & {"official", "university", "event"} else 2 if "news" in kinds else 0.5,
            "max": 4,
        },
        "corroboration": {
            "label": "Turli nashrlardagi dalillar",
            "score": min(2, max(0, len(publishers) - 1)),
            "max": 2,
        },
        "identity": {
            "label": "Muallif yoki tashkilot",
            "score": 1 if analysis.creator or analysis.organization else 0,
            "max": 1,
        },
        "link": {"label": "Loyiha havolasi", "score": 1 if analysis.main_url else 0, "max": 1},
        "evidence": {"label": "Iqtibosli dalillar", "score": min(2, len(analysis.facts) * 0.5), "max": 2},
    }
    return round(sum(c["score"] for c in components.values()), 2), components
