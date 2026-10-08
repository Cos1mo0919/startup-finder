import hashlib
import math
import re
from collections import Counter
from difflib import SequenceMatcher
from urllib.parse import urlsplit
from sqlalchemy import select
from .db import Project, Source
from .detection import normalize
from .network import canonical_url


def fingerprint(analysis):
    identity = "|".join(
        normalize(str(v or ""))
        for v in [analysis.name, analysis.creator, analysis.organization, analysis.country]
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def semantic_similarity(a, b):
    # Explainable local vector-space similarity (term-frequency cosine), no external model/key.
    stop = {"uchun", "bilan", "loyiha", "yangi", "this", "that", "the", "and", "для", "это", "проект"}
    x, y = [
        Counter(t for t in re.findall(r"\w+", normalize(s)) if len(t) > 2 and t not in stop) for s in (a, b)
    ]
    denominator = math.sqrt(sum(v * v for v in x.values()) * sum(v * v for v in y.values()))
    return sum(v * y.get(k, 0) for k, v in x.items()) / denominator if denominator else 0


def find_duplicate(session, analysis, urls, allow_shared_source=False):
    canonical = [canonical_url(u) for u in urls]
    source = session.scalar(select(Source).where(Source.url.in_(canonical)))
    if source and not allow_shared_source:
        return source.project
    if allow_shared_source:
        for existing in session.scalars(select(Source).where(Source.url.in_(canonical))):
            if normalize(analysis.name) in {
                existing.project.normalized_project_name,
                *(normalize(alias) for alias in existing.project.aliases),
            }:
                return existing.project
    if analysis.main_url:
        project = session.scalar(select(Project).where(Project.main_url == canonical_url(analysis.main_url)))
        if project:
            # Company homepages can represent multiple products; only a product path is unique.
            path = urlsplit(analysis.main_url).path.strip("/")
            if path or project.normalized_project_name == normalize(analysis.name):
                return project
    incoming_names = {normalize(analysis.name), *(normalize(a) for a in analysis.aliases)}
    for project in session.scalars(select(Project).where(Project.country == analysis.country)):
        existing_names = {project.normalized_project_name, *(normalize(a) for a in project.aliases)}
        similarity = max(SequenceMatcher(None, a, b).ratio() for a in incoming_names for b in existing_names)
        same_creator = bool(
            analysis.creator and project.creator and normalize(analysis.creator) == normalize(project.creator)
        )
        same_org = bool(
            analysis.organization
            and project.organization
            and normalize(analysis.organization) == normalize(project.organization)
        )
        # Conflicting identities and distinct numbered products must remain separate.
        conflict = (analysis.creator and project.creator and not same_creator) or (
            analysis.organization and project.organization and not same_org
        )
        numbers_differ = re.findall(r"\d+", analysis.name) != re.findall(r"\d+", project.name)
        if conflict or numbers_differ:
            continue
        description_similarity = semantic_similarity(analysis.summary_uz, project.content["summary_uz"])
        if similarity == 1 and len(normalize(analysis.name)) >= 5 and description_similarity >= 0.82:
            return project
        # Shared authors alone never merge different project names.
        if similarity >= 0.92 and (same_creator or same_org):
            if (
                similarity == 1
                or semantic_similarity(analysis.summary_uz, project.content["summary_uz"]) >= 0.65
            ):
                return project
    return None
