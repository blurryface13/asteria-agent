# Archived adaptation — not injected at runtime

This historical local adaptation summarizes Gallant Lab's
`literature-review-toolkit` PLAYBOOK; it is not a verbatim copy. It was based on
upstream commit `4c95c5be9fd4e28a95458a4055af0f8affb64020` under the included
MIT license. Runtime now uses source_priority.md (verbatim excerpt) plus a separate local adapter.

### Phase 7 — Write the review article (OPTIONAL)

Turn the finished corpus into a narrative **review article** as a `.docx`. Run
only when the user asks for a written review (not for the bibliography itself).
Prerequisites: canonical references and citation verification are done; a
thematic family figure is useful when available.

**Authorship and honesty (non-negotiable when an LLM writes it).** If the
article is AI-authored, say so plainly. Put the model's name in `authors`, add
an `author_note` that identifies it as an AI, and include a `disclosure`
paragraph stating that the bibliography was machine-assembled and
machine-verified and that the author has read only abstracts/metadata, not full
texts. Language models fabricate citations; verification is what makes an
AI-written review trustworthy, and the disclosure must make that provenance
explicit.

**Prose.** Author the prose with a scientific-writing skill: one idea per
sentence and forward flow. Organize sections by the strongest thematic or
theoretical families. The title should convey the question, the answer, and why
it matters. Every in-text citation MUST name a paper that exists in the verified
source table, so the reference list backs it.

**Respect the temporal order of ideas.** When a sentence makes an origin claim
— signalled by *emerges, first, established, identified, introduced, was mapped,
showed that, early work, foundational, began, demonstrated,* or *discovery* — it
MUST cite the earliest paper that deserves priority, and order multiple
citations oldest-first. Do not credit a later review for a finding made by an
earlier primary paper.

**Priority audit.** After drafting the content object, dispatch an audit pass
with the draft and the source table. For each origin-claim sentence, check
whether an earlier paper deserves priority and report:
`claim → currently cites (year) → earlier source (year) → fix`.
Apply only evidence-supported corrections.

**Mechanics.** The renderer owns only the mechanical render: title/author block,
abstract, section headings and body paragraphs, figures, and a reference list
built from canonical metadata. It does NOT write prose. Keep the prose in a
small structured content object and render from that object. A citation gate
must run before rendering so the document cannot contain a citation missing from
the source table.

## Asteria compatibility adapter

- The current deliverable is Chinese Markdown first, then a safe LaTeX/PDF
  rendering; do not force the upstream DOCX output path.
- Source links and page-level evidence in the current task replace the
  upstream author–date-only citation gate.
- The upstream temporal-priority audit is guidance for the evidence auditor;
  it does not authorize new papers or bypass the current read-source rule.
- Model output never supplies executable LaTeX macros or shell commands.
