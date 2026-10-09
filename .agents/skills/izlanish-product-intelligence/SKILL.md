---
name: izlanish-product-intelligence
description: >
  Product intelligence rules for the izlanish / startup-finder project.
  Use this skill whenever modifying project classification, problem discovery,
  opportunity analysis, entity relationships, evidence rules, stop-filters,
  publication eligibility, project/problem linking, solution-idea logic,
  market-signal interpretation, or any product logic that determines what
  should or should not appear in the intelligence system.
---

# izlanish Product Intelligence

## Current catalog rule — v3.1

`docs/PROJECT_CATALOG_PIPELINE_V3_1.md` governs project catalog publication.
A concrete, identifiable project with a meaningful source-backed description
may be published without a problem statement, creator, market score, or
opportunity grade. Problem, market and opportunity analysis below is optional
post-publication enrichment. A missing problem must never, by itself, reject
or hide a catalog project. Generic news without a project remains in review or
is rejected according to classifier confidence. The public catalog is about
projects; deeper intelligence stays internal. Global discovery is authorized
alongside Uzbekistan coverage. When an older instruction below says a problem
is mandatory for publication, read it as mandatory only for a *strong
opportunity recommendation*.

## Purpose

This skill defines the core product logic of the izlanish / startup-finder system.

The product is not primarily a startup-news aggregator.

Its main purpose is to discover, validate, structure and analyze:

- real problems;
- real projects and solutions;
- solution opportunities;
- market and ecosystem signals;
- evidence-backed business opportunities.

The system must prioritize quality and meaningfulness over raw item count.

The core question for any project or solution is:

**“Qanday muammoni hal qiladi?”**

If the system cannot answer this clearly and with reasonable evidence, the item must not be promoted as a strong project or opportunity.

---

# 1. Core Product Philosophy

The system must follow this intelligence chain:

SOURCE
→ CANDIDATE
→ ENTITY TYPE
→ PROBLEM
→ SOLUTION
→ EVIDENCE
→ MARKET
→ SCORE
→ OPPORTUNITY
→ PUBLICATION

Do not start from:
“Is this an interesting startup?”

Start from:
“What problem exists, who has it, and how is it being solved?”

The product should help answer:

- What problem exists?
- Who experiences it?
- How serious is it?
- How frequent is it?
- What does it currently cost?
- What solutions already exist?
- Is the problem already being solved poorly?
- Is the found project a real solution or only a minor feature?
- Is there sufficient evidence?
- Is there meaningful opportunity potential?
- Is this relevant locally, globally, or as an everyday problem?

---

# 2. Core Entity Types

Every candidate must be classified into exactly one primary entity type:

- PROJECT
- PROBLEM
- SOLUTION_IDEA
- SIGNAL
- IGNORE

Do not force every discovered article into PROJECT.

## PROJECT

A real existing solution.

Examples:
- startup;
- company product;
- university project;
- hackathon project;
- prototype;
- SaaS;
- service;
- marketplace;
- hardware;
- AI tool;
- public-service solution;
- research project with a working prototype.

A PROJECT must have evidence that it actually exists.

A PROJECT may have a meaningful problem relationship; it is optional for catalog publication.

## PROBLEM

A real issue experienced by:

- people;
- businesses;
- institutions;
- professionals;
- government;
- communities;
- society.

Problems may be:

- everyday;
- local;
- business;
- medical;
- educational;
- logistical;
- financial;
- legal;
- ecological;
- technological;
- social;
- infrastructure-related;
- global.

A problem does not need to be large.

It must be real, understandable and sufficiently meaningful.

## SOLUTION_IDEA

A possible new solution to a confirmed problem.

A SOLUTION_IDEA is not an existing company or startup.

It may be created only when:

- the problem is sufficiently evidenced;
- the affected user is known;
- the current workaround or current solution is understood;
- there is a plausible reason existing solutions are insufficient;
- there is a plausible solution mechanism.

Always clearly label SOLUTION_IDEA as a hypothesis or generated idea.

Never present it as an existing project.

## SIGNAL

Important information that is not itself a project.

Examples:

- investment;
- funding;
- accelerator;
- grant;
- subsidy;
- law;
- regulation;
- government program;
- fund launch;
- acquisition;
- market growth;
- technology adoption;
- demand trend;
- hiring trend;
- sector activity;
- startup shutdown;
- pricing shift;
- policy shift.

Signals can strengthen evidence for:
- sectors;
- problems;
- projects;
- opportunities.

But SIGNAL must not automatically become PROJECT.

## IGNORE

Noise or content that should not become a meaningful entity.

Examples:

- political appointments;
- celebrity news;
- unrelated company PR;
- generic corporate announcements;
- small UI changes;
- minor product features;
- stock-price stories;
- irrelevant tariffs;
- vague “innovation” claims;
- articles with no useful evidence or meaningful problem.

Always preserve a reason for IGNORE when useful for diagnostics.

---

# 3. Mandatory Problem Gate

Every PROJECT candidate may undergo a problem gate for optional intelligence enrichment.

The required primary question is:

**“Qanday muammoni hal qiladi?”**

The answer must be concrete.

Good:
“Private clinics lose potential customers because incoming calls are not answered quickly enough.”

Bad:
“Improves user experience.”

Bad:
“Uses AI to improve efficiency.”

Bad:
“Adds another function to an existing platform.”

After defining the problem, evaluate:

1. Who has this problem?
2. Is the problem independently meaningful?
3. Is it recurring or consequential?
4. Does it cost time, money, convenience, safety or opportunity?
5. Is there evidence that the problem is real?
6. Does the project directly solve that problem?
7. Is the solution meaningful enough to stand on its own?
8. Is it only a small addition to an existing system?

Allowed statuses:

- PASS
- PENDING
- REJECT

## PASS

Use when:
- problem is clear;
- affected user is clear;
- project existence is evidenced;
- project meaningfully addresses the problem.

## PENDING

Use when:
- candidate may be valuable;
- project may exist;
- problem may be real;
- but evidence is not yet sufficient.

PENDING is not a permanent dead end.

The system should try to gather more evidence later.

## REJECT

Use when:
- no meaningful problem exists;
- no identifiable affected user;
- only a cosmetic or minor feature;
- no credible evidence of existence;
- article does not actually describe a project;
- project does not solve the claimed problem.

Store exact rejection reason.

---

# 4. Minor-Feature Filter

A core product rule:

A small feature is not automatically a valuable project.

Reject or strongly down-rank if the candidate is only:

- a new button;
- a theme;
- an export option;
- a minor dashboard change;
- a small integration;
- a cosmetic improvement;
- a convenience feature with no meaningful independent problem.

Potentially valid:

“Automatically checks contracts for legal risks for small businesses that cannot afford lawyers.”

Potentially valid:

“Turns Telegram customer messages into structured CRM leads because businesses currently lose customer requests.”

Do not use the word “innovation” as evidence.

Do not classify something as PROJECT only because the article calls it innovative.

---

# 5. Problem Scope

Every PROBLEM should have a scope.

Allowed scopes:

- EVERYDAY
- UZBEKISTAN_LOCAL
- GLOBAL

## EVERYDAY

A recurring human or business problem that may exist in many countries.

Country is secondary.

Examples:

- people forget recurring payments;
- students miss deadlines;
- small businesses lose Telegram messages;
- clinics miss calls;
- stores manually track inventory;
- couriers struggle with bad addresses;
- repetitive document work wastes time.

These may come from any country.

## UZBEKISTAN_LOCAL

A problem strongly shaped by Uzbekistan-specific context.

Examples:

- local regulation;
- payment infrastructure;
- accounting;
- tax;
- marking/compliance;
- local language;
- Telegram-heavy workflows;
- local public services;
- regional infrastructure;
- Uzbekistan-specific bureaucracy.

## GLOBAL

A broad international problem or trend.

Examples:

- climate risk;
- AI labor displacement;
- global healthcare access;
- cybersecurity trends;
- major energy transitions;
- large-scale global market changes.

Do not classify something GLOBAL just because it was found abroad.

An ordinary everyday problem found in another country can still be EVERYDAY.

---

# 6. Evidence Rules

Facts and analysis must always be separated.

## Confirmed Facts

Examples:

- project exists;
- creator identity;
- official website;
- event participation;
- funding;
- launch date;
- award;
- user count;
- pilot;
- partnership;
- GitHub repository.

## System Analysis

Examples:

- market may be large;
- problem appears severe;
- business model looks promising;
- opportunity score;
- possible risks;
- Uzbekistan applicability.

Never present analysis as a confirmed fact.

Every important claim should have evidence where possible.

Useful evidence types include:

- PROJECT_EXISTS
- CREATOR_IDENTITY
- EVENT_PARTICIPATION
- AWARD
- FUNDING
- LAUNCH
- USERS
- CUSTOMERS
- PILOT
- OFFICIAL_SITE
- GITHUB
- UNIVERSITY
- PROBLEM_EXISTS
- REGULATION
- DEMAND
- MARKET_SIZE
- PAYMENT_SIGNAL

Prefer stronger evidence in this order:

1. official source;
2. primary project/company source;
3. official event/university/government source;
4. multiple reliable independent media;
5. reliable secondary source;
6. weak single source.

Do not pretend evidence is stronger than it is.

---

# 7. Problem Deduplication

Multiple articles may describe the same underlying problem.

Examples:

“Clinics miss calls.”

“Medical centers lose clients because calls go unanswered.”

“Private clinics need call automation.”

These may represent one PROBLEM.

Deduplicate using:

- normalized problem meaning;
- affected user;
- sector;
- geography;
- recurring context;
- semantic similarity;
- current workaround;
- consequences.

Keep:
- aliases;
- source links;
- evidence history.

Do not delete earlier evidence.

---

# 8. Project Deduplication

Do not create multiple cards for the same project.

Example:

Spot
IT Park
Gazeta

all describe Project X.

Result:
one PROJECT
with multiple source/evidence records.

Use:

- canonical name;
- creator;
- official domain;
- source URLs;
- GitHub;
- event context;
- semantic similarity;
- date context.

Same creator with different products:
keep separate projects.

Always preserve:
first_seen_at

Update:
last_seen_at
source_count
evidence
analysis

---

# 9. Project ↔ Problem Relationship

A project may solve one or multiple problems.

A problem may have multiple competing projects.

The system should support:

Problem:
“Clinics lose incoming calls.”

Solutions:
- Project A
- Project B
- Project C

A project must have one primary problem when possible.

Store relationship quality.

Suggested concepts:

- primary_problem
- solution_strength
- relationship_confidence
- evidence_summary

Do not automatically assume the article’s marketing claim is the real problem.

Infer carefully and record confidence.

---

# 10. Solution-Idea Rules

Do not generate random startup ideas from every problem.

A SOLUTION_IDEA should be created only if:

1. problem is clear;
2. affected user is clear;
3. problem has sufficient evidence;
4. current workaround is known or inferable;
5. current workaround has a real weakness;
6. a plausible new solution mechanism exists.

Useful stored fields:

- idea_title;
- problem;
- target_user;
- proposed_solution;
- current_alternatives;
- why_current_alternatives_fail;
- business_model_hypothesis;
- MVP_hypothesis;
- main_risks;
- evidence_basis.

Always label generated ideas clearly.

Never mix them with confirmed existing PROJECT entities.

---

# 11. Market Signal Logic

Signals should enrich intelligence.

Examples:

- multiple HealthTech investments;
- government digitization program;
- several new health startups;
- hiring growth in a category.

These together may indicate stronger sector activity.

Do not conclude:
“Sector is booming”
from one weak signal.

Signal confidence should consider:

- source quality;
- number of independent signals;
- time recency;
- size/importance;
- consistency across sources.

Signals may be linked to:
- project;
- problem;
- sector;
- opportunity.

---

# 12. Stop Filter

A high average score must never hide a fatal flaw.

Allowed stop-filter statuses:

- PASS
- LIMITED
- PENDING
- REJECTED

Fatal or strong stop conditions include:

- no meaningful problem;
- no affected user;
- nobody plausibly willing to pay where commercial logic matters;
- only a minor feature;
- project does not actually address the problem;
- no sufficient evidence of project existence;
- extreme capital requirement relative to opportunity;
- unacceptable legal restriction;
- obviously saturated or impossible implementation without differentiator.

A REJECTED item must not receive a high opportunity grade.

A PENDING item must not be presented as confirmed.

Store exact reasons.

---

# 13. Scoring Philosophy

Do not invent arbitrary AI scores.

Every score should have:

- numeric score;
- textual reason;
- supporting evidence;
- confidence.

Use a detailed internal scoring model.

Recommended factors:

## Problem

- pain_strength
- frequency
- mandatory_pressure
- current_cost

## Market

- potential_customer_count
- willingness_to_pay
- expansion_potential

## Business Model

- recurring_revenue_potential
- customer_accessibility
- low_capital_requirement
- low_legal_risk

## Execution

- mvp_speed
- competition_attractiveness
- implementation_feasibility
- uzbekistan_applicability

The compact public catalog shows the v3.1 catalog score when available.
The detailed intelligence scores below belong in the optional detail section.

Do not overload the main card with every internal criterion.

---

# 14. Evidence Level

Use a 1–5 evidence level.

## Level 1
Weak hypothesis or single weak signal.

## Level 2
International analogue or investor thesis.

## Level 3
Multiple sources, competitor, local demand, regulation, launch evidence.

## Level 4
Strong validation, confirmed usage, interviews, pilot, institutional evidence.

## Level 5
Actual payment, contracts, strong adoption or repeated real-world usage.

Automated scraping must not falsely claim Level 4 or 5.

Require explicit evidence.

---

# 15. Opportunity Grades

Use:

- A
- B
- C
- D
- REJECTED

## A
Very strong opportunity.

Problem strong.
Evidence meaningful.
Market attractive.
Worth immediate deeper validation.

## B
Promising.

Good candidate with some uncertainty.

## C
Watch / reserve.

Potential exists, but meaningful gaps remain.

## D
Weak.

Problem, market or execution is currently unattractive.

## REJECTED
Fails mandatory problem/evidence gate.

Do not assign A/B to fatal stop-filter failures.

---

# 16. Publication Rules

An item may be published as PROJECT when its identity, concrete function,
source URL and description meet the v3.1 LLM or trusted deterministic rules;
deduplication is complete. Problem intelligence and opportunity grade are not
publication gates. Deterministic publication requires the explicit adapter +
page_type allowlist; generic keyless RSS/news goes to review.

If uncertain:

PENDING

Do not lower standards only because the feed is empty.

Quality > quantity.

A healthy run may publish few items.

That is acceptable.

---

# 17. Uzbekistan Relevance

Uzbekistan is the primary operational market.

But the system may contain:

- Uzbekistan projects;
- everyday problems from anywhere;
- international projects;
- global trends;
- solution ideas.

When applicable, evaluate:

“O‘zbekistonga mosligi”

Consider:

- local regulation;
- purchasing power;
- language;
- digital adoption;
- infrastructure;
- payment systems;
- cultural behavior;
- local competitors;
- implementation cost.

Do not force a high score just because a project is local.

Do not force a low score just because it originated abroad.

---

# 18. Historical Integrity

Never delete valuable historical project/problem/signal data simply because new data arrives.

Preserve:

- first_seen;
- old evidence;
- source history;
- prior status where useful;
- project aliases;
- problem aliases.

New evidence may improve analysis.

It should not erase provenance.

---

# 19. Keyless Mode

The system must remain useful without paid AI/search APIs.

AI can improve:

- summaries;
- classification;
- semantic deduplication;
- problem extraction;
- score reasoning;
- idea generation.

But deterministic evidence must still support meaningful publication where possible.

Strong evidence should not remain pending forever only because AI is unavailable.

Store analysis method when relevant:

- deterministic
- ai
- hybrid

---

# 20. User-Facing Language

All normal user-facing UI should be Uzbek.

Do not translate:

- company names;
- project names;
- people names;
- official product names;
- URLs.

Summaries and analysis should be Uzbek.

Facts and system analysis should be visually separated.

---

# 21. What This Skill Must Be Used For

Use this skill whenever modifying:

- candidate classification;
- PROJECT / PROBLEM / SIGNAL / SOLUTION_IDEA logic;
- problem extraction;
- problem gate;
- stop-filter;
- evidence model;
- score model;
- project/problem linking;
- problem deduplication;
- project deduplication;
- publication eligibility;
- opportunity grades;
- solution-idea generation;
- market-signal interpretation;
- migration of product intelligence data;
- business logic affecting what appears in the product.

Do not use this skill as the primary source for:

- CSS-only visual changes;
- deployment setup;
- generic infrastructure;
- scheduler implementation details;
- source parser implementation details.

Those should use more specialized skills.

---

# 22. Non-Negotiable Rules

Never:

- publish a meaningless feature as a strong project;
- confuse SIGNAL with PROJECT;
- present generated ideas as existing startups;
- present analysis as fact;
- delete historical evidence without reason;
- create duplicate projects unnecessarily;
- fabricate sources;
- fabricate customers;
- fabricate funding;
- fabricate scores without reasoning;
- weaken filters to increase counts.

Always:

- ask what problem is solved;
- identify who has the problem;
- preserve evidence;
- preserve provenance;
- separate facts from analysis;
- record uncertainty;
- prefer quality over quantity.

---

# 23. Core Principle

The defining principle of izlanish is:

**A project matters because of the problem it solves, not merely because it exists.**

When evaluating a new item, always ask:

**“Qanday muammoni hal qiladi?”**

If there is no clear, meaningful and evidence-backed answer, do not promote the item as a strong opportunity.
