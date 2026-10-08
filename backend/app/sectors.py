SECTORS = {
    "ai": "Sun’iy intellekt",
    "fintech": "Moliyaviy texnologiyalar",
    "healthtech": "Tibbiy texnologiyalar",
    "edtech": "Ta’lim texnologiyalari",
    "agritech": "Agrotexnologiyalar",
    "govtech": "Davlat texnologiyalari",
    "smart_city": "Aqlli shahar",
    "cybersecurity": "Kiberxavfsizlik",
    "ecommerce": "Elektron savdo",
    "logistics": "Logistika",
    "mobility": "Harakatlanish va transport",
    "legaltech": "Huquqiy texnologiyalar",
    "climatetech": "Iqlim texnologiyalari",
    "energy": "Energetika",
    "construction": "Qurilish",
    "robotics": "Robototexnika",
    "saas": "Bulutli xizmatlar",
    "developer_tools": "Dasturchi vositalari",
    "design": "Dizayn",
    "manufacturing": "Ishlab chiqarish",
    "foodtech": "Oziq-ovqat texnologiyalari",
    "traveltech": "Sayohat texnologiyalari",
    "other": "Boshqa",
}
LEGACY = {
    "finance": "fintech",
    "healthcare": "healthtech",
    "education": "edtech",
    "agriculture": "agritech",
    "government": "govtech",
    "transportation": "mobility",
    "environment": "climatetech",
    "security": "cybersecurity",
    "development": "developer_tools",
    "industry": "manufacturing",
}
PATTERNS = {
    "ai": ["sun’iy intellekt", "sun‘iy intellekt", "artificial intelligence", "машинное обучение"],
    "healthtech": ["tibbiyot", "klinik", "healthcare"],
    "edtech": ["ta’lim", "ta‘lim", "education"],
    "agritech": ["fermer", "agro", "qishloq xo‘jaligi"],
    "energy": ["energetik", "gaz ta‘minoti", "energy"],
    "fintech": ["fintech", "bank", "to‘lov"],
    "robotics": ["robot"],
    "climatetech": ["iqlim", "climate"],
    "foodtech": ["foodtech"],
    "traveltech": ["traveltech"],
    "legaltech": ["legaltech"],
    "saas": ["saas"],
    "developer_tools": ["developer tool", "dasturchi vosita"],
}


def classify_sectors(analysis):
    supplied = [v for v in [analysis.primary_sector, *analysis.sectors] if v in SECTORS and v != "other"]
    mapped = LEGACY.get(analysis.category, analysis.category)
    if mapped in SECTORS and mapped != "other":
        supplied.append(mapped)
    text = (analysis.name + " " + analysis.summary_uz + " " + " ".join(analysis.keywords)).lower()
    # A plant clinic is an agricultural service, not evidence of human healthcare.
    plant_clinics = ("o‘simlik klinik", "o'simlik klinik", "ўсимлик клиник")
    if any(plant_clinic in text for plant_clinic in plant_clinics) and not any(
        term in text for term in ("tibbiyot", "shifokor", "hospital", "patient", "medical")
    ):
        supplied = [sector for sector in supplied if sector != "healthtech"]
    for plant_clinic in plant_clinics:
        text = text.replace(plant_clinic, "")
    supplied.extend(k for k, terms in PATTERNS.items() if any(t in text for t in terms))
    values = list(dict.fromkeys(supplied))[:8] or ["other"]
    return values[0], values
