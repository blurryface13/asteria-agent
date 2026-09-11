# Literature search subagent prompt — TEMPLATE

Fill in the `{PLACEHOLDERS}` and pass the result as the `prompt` field of an
Agent call (subagent_type: `general-purpose`). The agent has WebSearch + WebFetch
and will return a curated list. Do NOT trust its citations — verify them all in
Phase 3.

**Antecedents variant (Phase 2b).** This same template is reused for the required
antecedents pass. For that pass, FLIP the tier emphasis: the target is
foundational / classic / highly-cited work that PRE-DATES the modern literature
(methodology origins, foundational empirical results, or theory). Run one agent
per axis, set `{TIER_BOUNDARY_YEAR}` so "classic" dominates, and expect some
no-DOI books/chapters (handle per Phase 2b).

---

You are doing a literature search for an academic neuroscience review on the
**{REVIEW_TITLE}** by {LAB_NAME}. I need you to identify papers relevant to
ONE specific topic: **{TOPIC_NAME}**.

## What "{TOPIC_NAME}" means in this review

{TOPIC_DEFINITION}
<!-- 3-5 sentences. Include: brain regions, methods, theoretical positions,
     contested claims, what's IN scope and what's OUT of scope (adjacent
     topics covered separately). -->

## What I already have (DO NOT re-include these)

{ALREADY_HAVE_LIST}
<!-- Bullet list of existing papers, each one line: First Author Year — title -->

## Selection criteria — TWO TIERS

- **Pre-{TIER_BOUNDARY_YEAR}**: ONLY include if highly impactful / well-cited
  / foundational. Think classic, canonical work.
- **{TIER_BOUNDARY_YEAR}–present**: Be promiscuous. Include even if not yet
  highly cited — they haven't had time. Anything methodologically interesting,
  addressing an open question, or extending a major framework is worth
  including.

The current date is {TODAY}. Search for papers up through today.

## Aim for ~{TARGET_COUNT} papers, balanced across

1. Classic / foundational (pre-{TIER_BOUNDARY_YEAR}, high impact)
2. Recent reviews and updates ({TIER_BOUNDARY_YEAR}-present)
3. Recent empirical work using {RELEVANT_METHODS}
4. Recent theoretical / computational advances
5. Recent {DOMAIN_SPECIFIC_CATEGORY} (e.g. clinical, lesion, intracranial)

## How to search

Use WebSearch and WebFetch. Try multiple query variants for each angle:

{SEARCH_QUERIES}
<!-- One bulleted line per query. Mix broad and narrow. Include some with
     explicit recent years (2024, 2025, etc.) -->

Search both Google Scholar (via `scholar.google.com` URLs) and PubMed
(`pubmed.ncbi.nlm.nih.gov`). Verify each paper actually exists by fetching
its abstract page before including it.

## What to return for EACH paper

1. **APA citation** (full, with all authors if ≤6, else et al.)
2. **DOI link** in the form `https://doi.org/<doi>` — verify it resolves.
   Every paper MUST have a DOI link. Do NOT return PubMed or PMC URLs as the
   primary link; if you only have a PMID/PMCID, look up the DOI via PubMed
   or EuropePMC and return that. If a paper has truly no DOI (rare for
   published work), exclude it.
3. **PMCID if available** (for cross-checking only; not the primary link)
4. **3–5 sentence summary**: what the study did and why it's relevant to
   {TOPIC_NAME}. Read the actual abstract — do NOT make up findings.
5. **Tag**: one of: `classic` | `recent-review` | `recent-empirical` |
   `recent-method` | `recent-LLM` | `recent-theory` | `recent-clinical`
6. **Year**

Format as a numbered list grouped by tag. No process notes — just the
curated list.

Cap output at ~{TARGET_COUNT} papers. Quality over quantity for
pre-{TIER_BOUNDARY_YEAR}, err toward inclusion for recent work.

**Important:** Many published papers have similar titles. Always confirm
the first author and year by visiting the actual landing page (PubMed,
journal, or arxiv). Do not invent author names or invert findings — the
review needs accurate citations.
