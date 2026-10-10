"""Evidence-bound problem gate and opportunity assessment.

Unknown business claims remain unknown; a project can retain its historic feed
eligibility without being promoted to an A/B opportunity.
"""

import hashlib
import re
from sqlalchemy import select
from .db import Problem, ProblemEvidence, ProjectProblemLink, now_utc
from .detection import normalize
from .detection import is_uzbek, material_type

MINOR = re.compile(
    r"(?:button colou?r|tugma rangi|rangini o[‘']zgartir|new theme|yangi mavzu|"
    r"export button|eksport tugmasi|minor ui|kichik interfeys)", re.I
)
PAIN = re.compile(
    r"(?:muammo|qiyinchilik|yetishm|yo[‘']qot|vaqt sarf|xatolik|xavf|"
    r"javobsiz|qo[‘']lda|miss(?:ed)? calls?|lose customers|struggl|waste time|"
    r"manual(?:ly)?|risk|costly|inefficien|проблем|теря|очеред|вручную)", re.I
)
SUBJECT = re.compile(
    r"(?:klinika|dorixona|mijoz|tadbirkor|talaba|yo[‘']lovchi|do[‘']kon|jurnalist|"
    r"bemor|biznes|oila|shifokor|clinic|patient|student|shop|business|"
    r"customer|family|клиник|пациент|студент|магазин)", re.I
)
LOCAL = re.compile(
    r"(?:uzcard|humo|lex\.uz|soliq|markirovka|belgilash talabi|"
    r"o[‘']zbekiston qonun|uzbekistan regulation|ўзбекистон қонун)", re.I
)
SOLUTION = re.compile(
    r"(?:avtomatlashtir|hal qil|yordam ber|imkon(?:ini)? beradi|ta[’']minla|"
    r"matnga o[‘']gir|matnga o[‘']tkaz|qisqartir|reduces?|prevents?|automates?|solves?|allows?|enables?|"
    r"решает|позволяет|автоматиз)", re.I
)
REGULATION = re.compile(r"(?:majburiy|talab(?:lar)? joriy|mandatory|regulation|обязательн)", re.I)
DEMAND = re.compile(r"(?:shikoyat|complain|struggl|yetishm|javobsiz|missed|теря)", re.I)
TEMPLATES = (
    (re.compile(r"(?:HUMO.{0,80}(?:uzilish|ishlamay|muammo)|(?:uzilish|ishlamay|muammo).{0,80}HUMO)", re.I),
     "HUMO kartalari bilan ayrim bank ilovalarida uzilishlar yuz bermoqda", "HUMO kartasi foydalanuvchilari"),
    (re.compile(r"(?:clinic|klinika|клиник).{0,100}(?:miss(?:ed)? calls?|unanswered calls?|javobsiz qo[‘']ng[‘']iroq|пропущенн.{0,15}звон)", re.I),
     "Klinikalar qo‘ng‘iroqlarga javob bera olmay, mijozlarni yo‘qotadi", "klinikalar"),
    (re.compile(r"(?:shop|store|do[‘']kon|магазин).{0,100}(?:manual inventory|inventory manually|qo[‘']lda.{0,20}(?:hisob|ombor)|вручную.{0,20}(?:склад|товар))", re.I),
     "Do‘konlar ombor hisobini qo‘lda yuritadi", "do‘konlar"),
    (re.compile(r"(?:business|biznes|компан).{0,100}(?:lose.{0,30}(?:telegram|instagram).{0,20}messages?|telegram.{0,30}xabarlarn.{0,20}yo[‘']qot)", re.I),
     "Bizneslar mijoz xabarlarini yo‘qotadi", "bizneslar"),
    (re.compile(r"retseptni shakllantirishda xatolarni bartaraf etish", re.I),
     "Retseptni shakllantirishdagi xatolar xavfi", "shifokorlar va bemorlar", "UZBEKISTAN_LOCAL"),
)


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def problem_scope(text, country="Uzbekistan"):
    if LOCAL.search(text):
        return "UZBEKISTAN_LOCAL"
    if country != "Uzbekistan" and re.search(r"global|worldwide|international|международ", text, re.I):
        return "GLOBAL"
    return "EVERYDAY"


def problems_from_article(article, analysis=None):
    """Return distinct, attributable problem quotes; never synthesize claims."""
    body = article.text[:12000]
    findings = []
    for sentence in sentences(body):
        if len(sentence) < 25 or len(sentence) > 800:
            continue
        template = next((item[1:] for item in TEMPLATES if item[0].search(sentence)), None)
        native = is_uzbek(sentence) or len(re.findall(r"\b(?:sabab|mijozlar|vaqt|qo[‘']ng[‘']iroq|muammo|qiyinchilik|uchun|bilan)\b", sentence, re.I)) >= 2
        if (native and PAIN.search(sentence) and SUBJECT.search(sentence)) or template:
            # A project story must connect the named solution to the problem.
            title_and_intro = article.title + " " + body[:1200]
            linked = (
                normalize(analysis.name) in normalize(sentence)
                or any(SOLUTION.search(s) for s in sentences(body) if analysis.name.lower() in s.lower())
                or ("matnga" in sentence.lower() and "matnga" in title_and_intro.lower()
                    and normalize(analysis.name) in normalize(title_and_intro))
            ) if analysis else True
            if not linked:
                continue
            statement = sentence if native else template[0]
            if native and re.search(r"jurnalistlar.{0,180}matnga.{0,140}vaqt sarf", sentence, re.I):
                match = re.search(r"jurnalistlar.{0,180}matnga.{0,140}vaqt sarf[^.!?]*", sentence, re.I)
                if match:
                    statement = match.group(0)[0].upper() + match.group(0)[1:] + "."
            finding = {
                "statement": statement,
                "subject": SUBJECT.search(sentence).group(0) if native else template[1],
                "scope": template[2] if template and len(template) > 2 else problem_scope(sentence),
                "quote": sentence,
                "source_url": article.url,
                "source_id": article.source_id,
                "published_at": article.published_at,
            }
            if normalize(statement) not in {normalize(p["statement"]) for p in findings}:
                findings.append(finding)
    return findings


def problem_from_article(article, analysis=None):
    return next(iter(problems_from_article(article, analysis)), None)


def entity_type(article):
    """Five public types; EVENT is stored separately under IGNORE for this enum."""
    if MINOR.search(article.title + " " + article.text[:2000]) and not PAIN.search(article.text[:2000]):
        return "IGNORE"
    if article.url.startswith("https://news.ycombinator.com/item?") and article.title.startswith("Show HN:"):
        return "SIGNAL"
    old = material_type(article)
    if old == "PROJECT":
        return "PROJECT"
    if old == "ECOSYSTEM_SIGNAL":
        return "SIGNAL"
    if old == "EVENT":
        return "IGNORE"
    if problem_from_article(article):
        return "PROBLEM"
    if REGULATION.search(article.title + " " + article.text[:1200]) and LOCAL.search(article.title + " " + article.text[:1200]):
        return "SIGNAL"
    return "IGNORE"


def meaningful_problem(article, analysis=None):
    """A single adverse incident is not enough for product intelligence."""
    text = article.title + " " + article.text[:3000]
    if re.search(r"(?:bir|bitta|one|single).{0,35}(?:shifoxona|hospital).{0,80}(?:dori|medicine|drug)", text, re.I):
        return False
    if analysis is not None:
        return bool(problems_from_article(article, analysis))
    structural = re.search(r"(?:muntazam|tez-tez|har kuni|ko[‘']plab|tizimli|takror|doimiy|regular|repeated|systemic|many|multiple|across|keng tarqal)", text, re.I)
    return bool(structural and problem_from_article(article))


def problem_gate(analysis, articles):
    full_text = " ".join(a.title + " " + a.text[:5000] for a in articles)
    if MINOR.search(full_text) and not any(PAIN.search(a.text[:5000]) and SOLUTION.search(a.text[:5000]) for a in articles):
        return "REJECT", "minor_feature", None
    if not analysis.creator or not analysis.facts:
        return "PENDING", "insufficient_evidence", None
    for article in articles:
        found = problem_from_article(article, analysis)
        if found:
            return "PASS", "source_backed_problem", found
    return "PENDING", "pending_problem_analysis", None


def problem_fingerprint(statement, subject, scope):
    # Exact normalized aliases are merged; loose semantic similarity cannot safely
    # merge different pains without an optional reviewed semantic model.
    semantic = ""
    if re.search(r"klinika|clinic|клиник", statement, re.I) and re.search(r"qo[‘']ng[‘']iroq|calls?|звон", statement, re.I) and re.search(r"javob|miss|unanswer|пропущ", statement, re.I):
        semantic = "clinic_missed_calls"
    else:
        semantic = next((item[1] for item in TEMPLATES if item[0].search(statement)), "")
    key = "|".join([semantic, scope]) if semantic else "|".join([normalize(statement), normalize(subject), scope])
    return hashlib.sha256(key.encode()).hexdigest()


def cited_problem_scores(finding):
    """Narrow editorial rubric: only explicit pain/frequency/cost statements score."""
    quote = finding["quote"]
    refs = [finding["source_url"]]
    result = {}
    if re.search(r"(?:mijoz.{0,25}yo[‘']qot|lose customers|xavfsizligiga xavf)", quote, re.I):
        result["pain_strength"] = {"score": 4, "reason": "Manbada mijoz yoki xavfsizlik yo‘qotishi aniq aytilgan", "evidence_refs": refs}
    elif re.search(r"(?:vaqt sarf|uzilish|qo[‘']lda|missed calls|manual(?:ly)?|xatolarni bartaraf)", quote, re.I):
        result["pain_strength"] = {"score": 3, "reason": "Manbada vaqt sarfi, xizmat uzilishi yoki xato xavfi aytilgan", "evidence_refs": refs}
    if re.search(r"(?:har kuni|every day|daily)", quote, re.I):
        result["frequency"] = {"score": 4, "reason": "Manbada har kunlik takrorlanish aytilgan", "evidence_refs": refs}
    elif re.search(r"(?:tez-tez|muntazam|often|regularly)", quote, re.I):
        result["frequency"] = {"score": 3, "reason": "Manbada muntazam takrorlanish aytilgan", "evidence_refs": refs}
    if re.search(r"(?:majburiy|mandatory|обязательн)", quote, re.I):
        result["mandatory_pressure"] = {"score": 5, "reason": "Manbada majburiy talab ko‘rsatilgan", "evidence_refs": refs}
    if re.search(r"(?:\d+|uch|ikki)\s*soat.{0,35}vaqt sarf|vaqt sarf.{0,35}(?:\d+|uch|ikki)\s*soat", quote, re.I):
        result["current_cost"] = {"score": 3, "reason": "Manbada aniq vaqt xarajati keltirilgan", "evidence_refs": refs}
    for criterion in result.values():
        criterion["confidence"] = "LOW"  # One quoted source, not independent market validation.
    return result


def upsert_problem(session, finding, sector="other", country="Uzbekistan", project=None):
    fp = problem_fingerprint(finding["statement"], finding["subject"], finding["scope"])
    problem = session.scalar(select(Problem).where(Problem.fingerprint == fp))
    if problem is None:
        problem = Problem(
            fingerprint=fp,
            title_uz=finding["statement"][:300],
            description_uz=finding["statement"],
            problem_type=finding["scope"],
            scope=finding["scope"],
            country=country if finding["scope"] == "UZBEKISTAN_LOCAL" else "",
            sector=sector,
            affected_users=finding["subject"],
            status="EVIDENCED",
            confidence=0.5,
            evidence_level=2,
            first_evidence_published_at=finding["published_at"],
            scores=cited_problem_scores(finding),
        )
        session.add(problem)
        session.flush()
    problem.last_seen_at = now_utc()
    if not problem.scores:
        problem.scores = cited_problem_scores(finding)
    if finding["published_at"] and (problem.first_evidence_published_at is None or finding["published_at"].replace(tzinfo=None) < problem.first_evidence_published_at.replace(tzinfo=None)):
        problem.first_evidence_published_at = finding["published_at"]
    if finding["statement"] != problem.description_uz and finding["statement"] not in (problem.aliases or []):
        problem.aliases = [*(problem.aliases or []), finding["statement"]][:20]
    if not session.scalar(select(ProblemEvidence).where(
        ProblemEvidence.problem_id == problem.id,
        ProblemEvidence.source_url == finding["source_url"],
        ProblemEvidence.quote == finding["quote"],
    )):
        session.add(ProblemEvidence(
            problem_id=problem.id,
            source_id=finding["source_id"],
            source_url=finding["source_url"],
            quote=finding["quote"],
            publication_date=finding["published_at"],
            confidence=0.5,
            evidence_type="REGULATION" if REGULATION.search(finding["quote"]) else "DEMAND" if DEMAND.search(finding["quote"]) else "PROBLEM_EXISTS",
        ))
    if project and not session.scalar(select(ProjectProblemLink).where(
        ProjectProblemLink.project_id == project.id, ProjectProblemLink.problem_id == problem.id
    )):
        session.add(ProjectProblemLink(project_id=project.id, problem_id=problem.id,
                                       evidence_summary=finding["quote"][:800]))
    return problem


CRITERIA = {
    "problem": ("pain_strength", "frequency", "mandatory_pressure", "current_cost"),
    "market": ("potential_customer_count", "willingness_to_pay", "expansion_potential"),
    "business_model": ("recurring_revenue_potential", "customer_accessibility", "low_capital_requirement", "low_legal_risk"),
    "execution": ("mvp_speed", "competition_attractiveness", "implementation_feasibility", "uzbekistan_applicability"),
}


def opportunity(criteria, evidence_level, gate="PASS", fatal_reasons=()):
    """Fifteen 1–5 cited inputs. Missing inputs are not treated as a neutral 3."""
    if gate == "REJECT" or fatal_reasons:
        return {"score": None, "grade": "REJECTED", "stop_status": "REJECTED", "reasons": list(fatal_reasons)}
    if gate != "PASS":
        return {"score": None, "grade": "PENDING", "stop_status": "PENDING", "reasons": ["problem_gate_pending"]}
    valid = {}
    for group in CRITERIA.values():
        for key in group:
            item = criteria.get(key) or {}
            if (isinstance(item.get("score"), (int, float)) and 1 <= item["score"] <= 5
                    and item.get("reason") and item.get("evidence_refs")
                    and item.get("confidence") in ("LOW", "MEDIUM", "HIGH")):
                valid[key] = item
    if len(valid) < 15:
        return {"score": None, "grade": "PENDING", "stop_status": "PENDING", "reasons": ["insufficient_scoring_evidence"], "criteria": valid}
    groups = {name: round(sum(valid[k]["score"] for k in keys if k in valid) / (5 * sum(k in valid for k in keys)) * 10, 1) for name, keys in CRITERIA.items()}
    base = sum(groups.values()) / 4 * 10
    multiplier = {1: 0.45, 2: 0.6, 3: 0.75, 4: 0.9, 5: 1}.get(evidence_level, 0.45)
    score = round(base * multiplier, 1)
    grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"
    return {"score": score, "grade": grade, "stop_status": "PASS", "groups": groups,
            "evidence_level": evidence_level, "evidence_multiplier": multiplier, "criteria": valid, "reasons": []}


def migrate_existing_problems(factory):
    """Idempotently infer only from cached source text that survives article parsing."""
    from .db import Candidate, Project
    from .schemas import Analysis, Article
    from .publication import refresh_publication

    with factory.begin() as session:
        for project in session.scalars(select(Project)):
            if project.analysis_method in {"llm", "deterministic", "hybrid", "manual"}:
                # Catalog publication is independent of optional problem analysis.
                # A mixed legacy content shape must not reapply the old gate.
                continue
            if project.problem_gate_status == "PASS" and (project.opportunity_details or {}).get("criteria"):
                refresh_publication(project)
                continue
            try:
                analysis = Analysis.model_validate(project.content)
            except Exception:
                continue
            articles = []
            for source in project.sources:
                row = session.get(Candidate, source.url)
                if row and not row.article.get("_queued"):
                    try:
                        articles.append(Article.model_validate(row.article))
                    except Exception:
                        pass
            gate, reason, finding = problem_gate(analysis, articles)
            project.problem_gate_status, project.problem_gate_reason = gate, reason
            if finding:
                project.problem_statement = finding["statement"]
                project.problem_subject = finding["subject"]
                project.problem_scope = finding["scope"]
                project.problem_evidence_summary = finding["quote"]
                upsert_problem(session, finding, project.primary_sector, project.country, project)
            project.opportunity_details = opportunity(cited_problem_scores(finding) if finding else {}, 2, gate)
            project.opportunity_score = project.opportunity_details["score"]
            project.opportunity_grade = project.opportunity_details["grade"]
            refresh_publication(project)
