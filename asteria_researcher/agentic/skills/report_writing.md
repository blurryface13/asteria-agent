# Academic report writing

Version 3. This skill defines how to turn an evidence ledger into a readable
academic deliverable. It does not decide whether more research is needed and it
does not authorize new sources or tools.

## Deliverable contract

Write the report content in the user's requested language.
Organize claims by research question and comparison axis rather than by the
order in which papers were found. Every factual claim about a paper must be
supported by a source actually read in the current task. Keep separate:

- evidence directly reported by a source;
- a synthesis or inference made by the writer;
- an unresolved limitation or missing comparison.

Do not claim exhaustive coverage, reproduce unpublished experiments, or infer a
method's superiority from citation count alone. When experimental numbers are
compared, state the dataset, metric, protocol and source conditions when
available; otherwise describe the comparison qualitatively.

## Review structure

For a normal literature review, prefer this compact structure:

1. A direct answer / executive conclusion, with a short scope boundary.
2. Field taxonomy or evolution, only where supported by the collected papers.
3. Thematic method comparison: problem, core idea, data/setting and evidence.
4. Limitations, contradictions and research gaps.
5. Conclusion and references.

Do not write one isolated mini-summary for every paper. Use tables only when a
small number of comparable fields are available. A table cell must not imply a
value was reported when the source did not provide it; use “未报告”.

## Synthesis and handoff

Use the Lead's synthesis as editorial direction, not a replacement for original
child findings. Preserve each conclusion with its applicable conditions, source
and limitations. Avoid repeating a lossy condensed metric from Lead memory when
the child report or original evidence preserves the experiment setting.

Select details that answer the user's questions. Do not fill a short architecture
review with unrelated benchmark scores. Explain why differences matter for the
user's scenario; recommendations should specify when to choose an approach and
what tradeoff follows. Missing optional details are limitations, not a demand for
another research round. Use short paragraphs, separate list items for actions,
Chinese paraphrases, and explicit Markdown math delimiters for formulas.

## Citation and evidence discipline

- Place a Markdown source link near the claim it supports.
- Use only supplied `read_sources` and evidence passages; discovered or
  mentioned references are not valid citations until independently read.
- Keep URLs unchanged so the citation audit can match them to the evidence
  ledger.
- Do not invent DOI, author, year, page number, metric, dataset or result.
- If a claim is an across-paper synthesis, cite the supporting papers together
  and mark the wording as a synthesis rather than attributing it to one paper.
- End with a deduplicated reference list containing only cited and read sources.

## Before delivery

Check citation provenance, unsupported claims, thematic coverage and requested
length. Follow the separately injected output contract; fonts, layout and
compiler instructions are not part of this content-writing skill.
