# Report output contract · v2

Return Markdown, not JSON or a TeX document. The content skill chooses narrative;
the independent format profile owns page layout, fonts and spacing. Any content
type may use either profile.

Use a single # title, ## sections and ### subsections when needed, paragraphs,
simple lists and pipe tables with a header separator. Do not invent empty sections.
Preserve source URLs beside claims. No remote images, local paths, HTML, executable
TeX macros or shell commands. Complex equations and embedded figures are not yet
supported; do not promise they were typeset.

The publisher parses Markdown, escapes text and applies a trusted template. It
cannot add facts or fix citations. Writer and revision use this same contract.
A compiler error is a publishing error, never permission to fabricate a PDF.
