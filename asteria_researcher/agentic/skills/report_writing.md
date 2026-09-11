# Academic report writing

Version 1. This skill defines how to turn an evidence ledger into a readable
academic deliverable. It does not decide whether more research is needed and it
does not authorize new sources or tools.

## Deliverable contract

Write a Chinese Markdown report suitable for deterministic conversion to LaTeX.
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

1. Scope and inclusion boundary.
2. Field taxonomy or evolution, only where supported by the collected papers.
3. Thematic method comparison: problem, core idea, data/setting and evidence.
4. Limitations, contradictions and research gaps.
5. Conclusion and references.

Do not write one isolated mini-summary for every paper. Use tables only when a
small number of comparable fields are available. A table cell must not imply a
value was reported when the source did not provide it; use “未报告”.

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

## LaTeX-compatible writing

Use plain Markdown headings (`#`, `##`, `###`), paragraphs, simple bullet lists,
and conservative tables. Keep equations and complex layout out of the first
draft unless explicitly required. Avoid raw LaTeX commands, HTML, embedded
scripts, local absolute paths and custom macros. Put figure intent in prose or
a simple Markdown image reference; the publisher is responsible for escaping
text and compiling the fixed template.

Before delivery, check in this order: citation provenance, unsupported claims,
section coverage, requested language and length, then Markdown/LaTeX compilation.
If compilation fails, fix the smallest source-level incompatibility and rerun
the compiler; never execute model-supplied macros or shell commands.
