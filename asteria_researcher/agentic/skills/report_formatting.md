# General report formatting

This is a domain-neutral publishing skill. It can be selected for academic
reviews, company research, data analysis or other research reports when no
domain-specific writing skill exists.

## Separate content from presentation

First produce a structured report object containing the title, abstract or
executive summary, sections, claims, tables, figures and source links. Keep
research reasoning and factual evidence in the content object. Do not make the
model hand-write page layout, font declarations, bibliography formatting or
compiler commands.

Then select a named format profile. A format profile owns the page size,
typography, heading hierarchy, spacing, table and figure treatment, citation
style, bibliography layout and output targets such as Markdown, LaTeX, PDF or
HTML. A template is a format profile implementation, not a research skill.

## Default writing contract

- Use clear section hierarchy and short paragraphs.
- Distinguish source-reported facts, cross-source synthesis and open questions.
- Keep tables only when the compared fields are genuinely comparable.
- Preserve source URLs and evidence locations for later audits.
- Use “未报告” or an equivalent explicit marker instead of filling missing
  values with assumptions.
- Keep format-specific markup out of the content model whenever a renderer can
  add it deterministically.

## Renderer boundary

The renderer may escape text, resolve references, apply the selected template,
compile the document and return diagnostics. It must not silently add claims,
citations or experimental results. If a format profile is unavailable, report
that fact and keep the structured content usable for another renderer.
