---
name: izlanish-scoring-and-evidence
description: >
  Scoring, evidence and validation rules for the izlanish / startup-finder project.
  Use this skill whenever modifying opportunity scoring, problem scoring, market scoring,
  evidence levels, stop-filters, rating grades, score explanations, publication confidence,
  or any logic that determines how strongly a project/problem/opportunity is rated.
---

# izlanish Scoring and Evidence

## Current catalog scoring — v3.1

`docs/PROJECT_CATALOG_PIPELINE_V3_1.md` defines the public catalog score.
It is the code-computed one-decimal average of four independently explained
1–10 scores: clarity, real_product, novelty and potential. A low score does
not block publication. No LLM means `catalog_score=null`, `score_pending=true`,
`evidence_count=0` for a trusted deterministic publication; the public UI
shows “Baholanmagan”, never a neutral ranking constant as a score. Funding
alone never proves usage or warrants `real_product >= 8`. The detailed
problem, market, solution, opportunity and evidence ratings below are a
separate optional intelligence layer after catalog publication. Their stop
filters affect opportunity recommendations, not catalog existence.

## Purpose

This skill defines how izlanish evaluates:

- problems;
- projects;
- solution ideas;
- market opportunities;
- evidence strength;
- stop-filter outcomes;
- final grades.

The system must never assign attractive scores just because an item sounds innovative.

Every score must be traceable to:

- a defined criterion;
- a reason;
- supporting evidence;
- a confidence level.

The central rule is:

**No score without reasoning. No strong grade without evidence.**

---

# 1. Scoring Philosophy

The rating system is inspired by the original Excel prototype.

The Excel philosophy must be preserved:

- measure real pain;
- measure frequency;
- measure current cost;
- estimate market;
- estimate monetization potential;
- estimate execution difficulty;
- apply evidence adjustment;
- apply stop-filter before trusting the final score.

Do not optimize scores for visual appeal.

Do not inflate scores because the feed is empty.

Do not force every project into A/B/C/D if evidence is too weak.

Use PENDING when necessary.

---

# 2. Public Score vs Internal Score

The system should use two layers.

## Internal detailed scoring

Used for analysis and storage.

## Public simplified scoring

Used in cards and normal UI.

The public catalog card shows the four-factor catalog score or “Baholanmagan”.
Deep intelligence scores are optional detail content.

Detailed sub-scores should be shown only on detail pages.

---

# 3. Core Internal Criteria

Use a 1–5 internal scale for detailed criteria unless a future migration explicitly changes the model.

The recommended criteria are:

## PROBLEM

1. pain_strength
2. frequency
3. mandatory_pressure
4. current_cost

## MARKET

5. potential_customer_count
6. willingness_to_pay
7. expansion_potential

## BUSINESS MODEL

8. recurring_revenue_potential
9. customer_accessibility
10. low_capital_requirement
11. low_legal_risk

## EXECUTION

12. mvp_speed
13. competition_attractiveness
14. implementation_feasibility
15. uzbekistan_applicability

Each criterion must store:

- score
- reason
- evidence references
- confidence

---

# 4. Problem Score

The public “Muammo” score should reflect how meaningful the problem is.

Consider:

- pain intensity;
- frequency;
- cost;
- urgency;
- regulatory pressure;
- wasted time;
- missed revenue;
- safety consequences;
- operational disruption.

Suggested reasoning:

High score:
- recurring;
- expensive;
- urgent;
- widespread or severe;
- costly workaround.

Medium score:
- real but occasional;
- moderate inconvenience;
- limited financial impact.

Low score:
- cosmetic;
- rare;
- optional;
- weak inconvenience;
- no evidence of meaningful consequence.

Do not treat “annoying” as automatically severe.

---

# 5. Market Score

The public “Bozor” score should reflect opportunity size and monetization potential.

Consider:

- number of potential users/customers;
- willingness to pay;
- current spend;
- accessible segment size;
- expansion potential;
- geographic portability;
- purchasing power;
- business urgency.

A large theoretical population does not automatically mean a strong market.

Example:

Millions of people may have a minor inconvenience,
but if nobody will pay to solve it,
market score should remain limited.

---

# 6. Solution Score

The public “Yechim” score should reflect how directly and effectively the project solves the identified problem.

Consider:

- problem-solution fit;
- directness;
- usability;
- speed;
- reliability;
- differentiation;
- technical plausibility;
- improvement over current workaround.

A project may solve a strong problem poorly.

Do not transfer a high problem score into a high solution score automatically.

---

# 7. Evidence Score

The public “Dalil” score must reflect the strength and quality of evidence.

Evidence quality should consider:

- source authority;
- number of independent sources;
- official confirmation;
- existence of working product;
- pilot;
- users;
- customers;
- payments;
- contracts;
- funding;
- event participation;
- demo/prototype;
- GitHub/official site;
- local demand evidence.

Strong evidence is not the same as many weak articles.

One official source may be stronger than ten copied articles.

---

# 8. Evidence Levels

Use a separate Evidence Level from 1 to 5.

## Level 1 — Hypothesis

Examples:
- one weak article;
- vague claim;
- concept only;
- no independent confirmation.

Use when:
evidence is minimal.

## Level 2 — External Analogue / Thesis

Examples:
- known foreign analogue;
- investor thesis;
- research indication;
- international example.

Useful, but not strong local validation.

## Level 3 — Market / Local Signal

Examples:
- multiple reliable sources;
- real competitor;
- local regulation;
- launch evidence;
- recurring demand signal;
- verified project existence.

This is the normal threshold for many legitimate published items.

## Level 4 — Strong Validation

Examples:
- confirmed usage;
- pilot;
- institutional adoption;
- customer interviews;
- repeated real-world implementation.

Do not assign automatically from generic media coverage.

## Level 5 — Payment / Adoption

Examples:
- confirmed customers;
- contracts;
- paid usage;
- recurring revenue;
- large adoption;
- verified strong traction.

Require explicit evidence.

Do not fabricate Level 4 or Level 5.

---

# 9. Evidence Adjustment

The final opportunity rating should be adjusted by evidence.

A theoretically attractive opportunity with weak evidence must not receive the same final confidence as a validated one.

Conceptually:

raw_opportunity_score
×
evidence_adjustment
=
confidence_adjusted_score

Do not hard-code an arbitrary multiplier without documenting it.

If the current code already has a valid formula,
preserve it unless intentionally migrated.

Any formula change must be:

- documented;
- tested;
- migration-safe;
- compared against existing examples.

---

# 10. Stop Filter

Stop-filter must be evaluated BEFORE final grading.

A strong average score must never hide a fatal flaw.

Allowed outcomes:

- PASS
- LIMITED
- PENDING
- REJECTED

---

# 11. REJECTED Conditions

Use REJECTED when one or more fatal conditions apply.

Examples:

- no meaningful problem;
- no identifiable affected user;
- only a minor feature;
- no credible evidence project exists;
- solution does not address claimed problem;
- obviously impossible legal constraint;
- no plausible demand;
- item is not actually a project/problem/opportunity.

A REJECTED item must not receive A/B/C.

---

# 12. PENDING Conditions

Use PENDING when:

- project may be real;
- problem may be meaningful;
- but evidence is incomplete;
- creator identity uncertain;
- date unclear;
- solution description ambiguous;
- source insufficient;
- translation/normalization still required.

PENDING should be recoverable.

The system should try to collect more evidence later.

Do not leave permanent pending states without reason.

---

# 13. LIMITED Conditions

Use LIMITED when the item is valid but has a major structural weakness.

Examples:

- strong problem but tiny market;
- strong demand but severe regulation;
- useful solution but extreme capital requirement;
- good concept but difficult customer acquisition;
- strong local opportunity with poor scaling.

LIMITED may still receive a grade, but not the highest grade.

---

# 14. Grade System

Use these final grades:

- A
- B
- C
- D
- REJECTED

PENDING is a status, not a grade.

## A — Very Strong

Characteristics:
- strong problem;
- attractive market;
- good solution fit;
- meaningful evidence;
- no fatal stop-filter;
- implementation reasonably plausible.

Interpretation:
worth immediate deeper validation.

## B — Promising

Characteristics:
- good problem;
- credible opportunity;
- some uncertainty;
- evidence acceptable but not exceptional.

Interpretation:
worth deeper research.

## C — Watch

Characteristics:
- some potential;
- important uncertainty;
- weak evidence or limited market;
- not ready for strong recommendation.

Interpretation:
keep under observation.

## D — Weak

Characteristics:
- weak problem;
- low willingness to pay;
- unattractive execution;
- poor fit;
- weak differentiation.

Interpretation:
low current priority.

## REJECTED

Fatal filter failure.

---

# 15. Suggested Grade Boundaries

Exact numeric thresholds may evolve.

Do not change them casually.

If the system currently uses a 0–100 opportunity score,
a reasonable starting structure may be:

A:
80–100

B:
65–79

C:
50–64

D:
below 50

But:

stop-filter overrides numeric grade.

Evidence weakness may cap grade.

Example:
raw score 86
but Evidence Level 1
→ should not display as confident A.

Use confidence caps where appropriate.

---

# 16. Grade Caps by Evidence

A useful general principle:

Evidence Level 1:
maximum public confidence should remain low.

Evidence Level 2:
do not confidently present A.

Evidence Level 3:
A/B possible if other criteria are strong.

Evidence Level 4–5:
strong grades may be trusted more.

Do not implement exact caps without tests and documentation,
but preserve this principle.

---

# 17. Confidence

Each important score should have a confidence value.

Suggested:

LOW
MEDIUM
HIGH

or numeric confidence.

Confidence should depend on:

- evidence count;
- evidence quality;
- source independence;
- consistency;
- recency;
- clarity.

A score of 8.5/10 with LOW confidence should be presented differently from 8.5/10 with HIGH confidence.

---

# 18. Facts vs Analysis

This is mandatory.

## Fact

“Project participated in Demo Day.”

## Analysis

“Demo Day participation increases evidence confidence.”

## Fact

“Company reports 500 customers.”

## Analysis

“This suggests early market validation.”

Never store system interpretation as a confirmed fact.

---

# 19. Source Weighting

Source reliability may influence evidence strength.

Possible source classes:

OFFICIAL
PRIMARY
RELIABLE_MEDIA
SECONDARY
WEAK
UNKNOWN

Examples:

Official government / university / company page:
strong.

Independent reliable media:
good.

Copied aggregator:
weaker.

Anonymous post:
weak.

Do not assign credibility solely based on domain popularity.

---

# 20. Evidence Independence

Multiple articles are not independent if they copy the same press release.

Do not count:

10 syndicated copies

as:

10 independent confirmations.

Where possible, detect shared origin.

Evidence diversity matters.

---

# 21. Recency

Some evidence loses relevance over time.

Examples:

- old funding round;
- outdated regulation;
- old user count;
- old competitor pricing.

Store evidence date.

Do not blindly use stale evidence for current claims.

Historical facts remain valid as history,
but current-market conclusions should use recent data.

---

# 22. Problem Frequency

Frequency must be evaluated carefully.

Possible levels:

RARE
OCCASIONAL
MONTHLY
WEEKLY
DAILY
CONTINUOUS

Do not confuse one severe event with a frequently recurring problem.

Both can matter differently.

---

# 23. Current Cost

Current cost may include:

- direct money;
- employee time;
- lost sales;
- penalties;
- delays;
- safety risk;
- wasted inventory;
- missed opportunities;
- customer churn.

Current cost does not need to be exact.

But if estimated,
label it as estimate.

---

# 24. Willingness to Pay

Do not infer strong willingness to pay only because the problem is painful.

Look for:

- existing spend;
- paid alternatives;
- salaries for manual workaround;
- outsourcing spend;
- software subscriptions;
- contracts;
- customer payment evidence;
- regulatory necessity.

If no payment evidence exists,
keep confidence lower.

---

# 25. Competition

Competition is not automatically negative.

No competitors may mean:

- unexplored opportunity;
or
- no demand.

Many competitors may mean:

- validated market;
or
- saturated market.

Use context.

Do not score competition with simplistic:
“less competition = always better”.

The criterion should reflect attractiveness,
not just competitor count.

---

# 26. Capital Requirement

Low capital requirement may improve execution attractiveness.

High capital requirement may reduce score.

But some high-capital opportunities can still be strong.

Do not reject only because hardware/infrastructure is expensive.

Consider:
market size
funding environment
time to MVP
required assets
regulatory burden

---

# 27. Legal Risk

Legal risk must be treated separately from normal execution complexity.

Examples:

LOW:
ordinary SaaS.

MEDIUM:
payments, healthcare data, regulated workflow.

HIGH:
licensing, medical claims, financial regulation, personal data risk.

Do not invent legal conclusions.

If unclear:
mark uncertainty.

---

# 28. Uzbekistan Applicability

When relevant, score:

uzbekistan_applicability

Consider:

- language;
- purchasing power;
- regulation;
- local workflows;
- infrastructure;
- internet/mobile usage;
- payment systems;
- distribution;
- cultural behavior;
- existing competition.

Do not assume:
“worked abroad = works in Uzbekistan.”

Also do not assume:
“foreign project = low local applicability.”

---

# 29. Solution-Idea Scoring

SOLUTION_IDEA should be scored more cautiously than existing PROJECT.

Because it may not exist yet.

For solution ideas:

- evidence belongs mainly to the problem;
- execution score is hypothetical;
- business model is hypothetical;
- evidence of product existence is not applicable.

Clearly separate:
problem evidence
from
idea feasibility.

Do not give solution ideas the same confidence as real validated projects.

---

# 30. Problem-Only Scoring

A PROBLEM may exist without a PROJECT.

In that case score:

- pain;
- frequency;
- current cost;
- affected users;
- evidence;
- urgency;
- market relevance.

Do not invent a solution score if no solution exists.

---

# 31. Signal Influence

SIGNAL may strengthen or weaken opportunity analysis.

Examples:

Positive:
- new investment;
- rising demand;
- supportive regulation;
- hiring growth;
- repeated launches.

Negative:
- restrictive regulation;
- startup shutdowns;
- falling demand;
- major competitor dominance.

Do not let one signal dominate the entire score.

Use signal clusters where possible.

---

# 32. Score Explanations

Every public score should have a short human-readable explanation.

Example:

Muammo 8.5/10

Reason:
“Private clinics repeatedly lose calls and potential revenue; multiple sources confirm the issue.”

Not:

“AI calculated 8.5.”

Avoid opaque scoring.

---

# 33. Missing Data

Do not replace missing data with confident assumptions.

If a criterion is unknown:

store:
unknown

or
low confidence

Do not force every field to 3/5.

Missing data should lower confidence,
not create fake precision.

---

# 34. Precision

Avoid false precision.

Bad:

7.43891 / 10

Better:

7.4 / 10

or:

7 / 10

depending on UI.

Internally more precision may be stored if necessary.

Public UI should remain understandable.

---

# 35. Re-Scoring

New evidence may change a score.

The system should support re-scoring.

When re-scoring:

- preserve prior evidence;
- preserve score history if practical;
- update current score;
- record reason for significant changes.

Example:

Evidence Level 2 → 4
after confirmed pilot.

The opportunity grade may improve.

---

# 36. Score History

Where practical, preserve:

previous_score
new_score
changed_at
change_reason

This helps explain why a project moved from C to B.

Do not require full history if current architecture cannot support it yet,
but do not overwrite critical evidence silently.

---

# 37. Deterministic vs AI Scoring

The system may use:

deterministic
AI
hybrid

AI may help produce reasoning,
but must not be the only authority.

Where strong deterministic evidence exists,
basic scoring should still work without paid AI.

Store:

rating_method

Examples:

deterministic_fallback
ai
hybrid

---

# 38. Keyless Mode

Without AI keys:

- do not publish random grades;
- do not leave all strong items pending;
- use deterministic evidence rules;
- use conservative scoring;
- mark confidence correctly.

Strong source evidence can still produce legitimate scores.

---

# 39. Calibration

The scoring model should be calibrated using real examples.

Use known cases:

strong project
weak project
minor feature
strong problem/no solution
signal only
duplicate
poor evidence

Tests should cover edge cases.

Do not calibrate only against ideal examples.

---

# 40. Example: Strong Project

Problem:
Private clinics lose incoming customer calls.

Evidence:
- real product;
- official site;
- event participation;
- pilot;
- local market context.

Possible result:

Muammo:
9/10

Bozor:
8/10

Dalil:
8/10

Yechim:
8/10

Imkoniyat:
82/100

Grade:
A or B depending on execution/evidence details.

Reasoning must be stored.

---

# 41. Example: Minor Feature

Candidate:
“CRM adds dark mode.”

Problem:
weak/non-independent.

Stop-filter:
REJECTED.

Do not calculate attractive opportunity grade.

---

# 42. Example: Strong Problem, No Project

Problem:
Small businesses lose incoming Telegram leads.

Evidence:
multiple recurring complaints,
manual workflow,
lost revenue.

Project:
none.

Result:
PROBLEM may score highly.

Do not invent project evidence.

A SOLUTION_IDEA may later be generated cautiously.

---

# 43. Example: Strong Idea, Weak Evidence

Idea:
AI assistant for compliance.

Problem:
plausible.

Evidence:
only one weak source.

Result:
PENDING / low confidence.

Do not show A.

---

# 44. Example: Strong Evidence, Weak Market

Project:
real product.

Evidence:
official + customers.

Problem:
very narrow.

Market:
small.

Result:
good evidence,
but opportunity grade may remain C/B depending on economics.

Do not let evidence score replace market score.

---

# 45. UI Rules for Scores

The compact catalog card shows its catalog score when scored, or “Baholanmagan”.
Deep analysis appears only when populated on the detail page.

Detailed page may show all criteria.

Use clear labels.

Do not make users interpret raw internal factor names.

---

# 46. Status/Admin Diagnostics

Admin/status should expose scoring diagnostics such as:

- items scored;
- items pending score;
- rejected by stop-filter;
- evidence-level distribution;
- average opportunity score;
- rating method distribution;
- missing evidence reasons;
- score recalculations.

This helps validate model behavior.

---

# 47. Tests Required

Whenever modifying scoring/evidence logic,
add or update tests for:

- problem score;
- market score;
- solution score;
- evidence score;
- evidence levels;
- stop-filter override;
- grade boundaries;
- evidence caps;
- missing data;
- deterministic fallback;
- re-scoring;
- duplicate evidence;
- independent-source handling;
- stale evidence;
- solution idea scoring;
- problem-only scoring.

---

# 48. What This Skill Must Be Used For

Use this skill whenever modifying:

- opportunity score;
- Muammo score;
- Bozor score;
- Dalil score;
- Yechim score;
- evidence level;
- evidence confidence;
- score formulas;
- stop-filter;
- grade rules;
- A/B/C/D;
- publication confidence;
- score explanations;
- deterministic fallback ratings;
- re-scoring behavior;
- score-related migrations.

Do not use this skill as the primary authority for:

- source polling;
- scheduler;
- crawler implementation;
- CSS/layout;
- generic deployment;
- repository operations.

Use specialized skills for those.

---

# 49. Non-Negotiable Rules

Never:

- fabricate evidence;
- fabricate customers;
- fabricate revenue;
- fabricate payments;
- fabricate market size;
- assign strong grades without reasoning;
- let numeric average override fatal stop-filter;
- treat many copied articles as many independent sources;
- replace missing data with fake certainty;
- give generated ideas the same confidence as real products.

Always:

- explain scores;
- link scores to evidence;
- record uncertainty;
- separate facts from analysis;
- use stop-filter;
- calibrate conservatively;
- prefer honesty over attractive ratings.

---

# 50. Core Principle

The defining principle is:

**A high score is useful only when the evidence behind it is understandable and defensible.**

Every strong rating must answer:

- Why is the problem important?
- Why does the market matter?
- Why is the solution credible?
- What evidence supports the conclusion?
- What uncertainty remains?

If those questions cannot be answered,
the system should lower confidence or keep the item pending.
