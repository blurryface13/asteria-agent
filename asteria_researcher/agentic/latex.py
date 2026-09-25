"""Safe text-to-LaTeX publishing: no model-supplied TeX is executed."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import zipfile
from uuid import uuid4
from .pdf_fonts import embed_unicode_maps
from .report_tools import REFERENCE_HEADING_RE, is_reference_heading


def escape(value: str, *, break_words=False) -> str:
    if break_words:
        # Break long protocol identifiers inside narrow table cells, without
        # changing link targets or executing model-supplied TeX.
        value = re.sub(r'([A-Za-z0-9]{8})(?=[A-Za-z0-9])', '\\1\u200b', value)
        value = value.replace('/', '/\u200b').replace('-', '-\u200b')
    replacements = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
                    "$": r"\$", "&": r"\&", "#": r"\#", "%": r"\%",
                    "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
                    "∪": r"\ensuremath{\cup}", "∩": r"\ensuremath{\cap}",
                    "∈": r"\ensuremath{\in}", "≤": r"\ensuremath{\leq}", "≥": r"\ensuremath{\geq}"}
    replacements.update({'\u200b': r'\allowbreak{}', '≈': r'\ensuremath{\approx}',
                         '≠': r'\ensuremath{\neq}',
                         '≤': r'\ensuremath{\leq}', '≥': r'\ensuremath{\geq}',
                         '→': r'\ensuremath{\rightarrow}', '←': r'\ensuremath{\leftarrow}'})
    return "".join(replacements.get(char, char) for char in value)


# Math is preserved as a structured fragment, but arbitrary TeX commands are
# still escaped. This keeps useful formulas editable without turning the
# publishing path into a model-controlled TeX execution surface.
SAFE_MATH_COMMANDS = {
    "alpha", "beta", "gamma", "delta", "epsilon", "eta", "theta", "lambda", "mu", "pi", "sigma", "phi", "psi", "omega",
    "mathrm", "mathbf", "mathit", "mathsf", "operatorname", "text", "frac", "dfrac", "tfrac", "sqrt", "left", "right",
    "sum", "prod", "int", "lim", "log", "exp", "sin", "cos", "tan", "cdot", "times", "pm", "leq", "geq", "neq",
    "approx", "ell", "infty", "to", "rightarrow", "leftarrow", "mapsto", "top", "mid", "perp", "forall", "exists", "in", "notin", "cup", "cap", "hat", "bar", "overline",
}


def sanitize_math(value: str) -> str:
    """Keep a small, presentation-oriented TeX math vocabulary only."""
    result, index = [], 0
    while index < len(value):
        if value[index] == "\\":
            match = re.match(r"\\([A-Za-z]+|[^A-Za-z])", value[index:])
            if not match:
                result.append(r"\textbackslash{}")
                index += 1
                continue
            command = match[1]
            if command.isalpha() and command in SAFE_MATH_COMMANDS:
                result.append("\\" + command)
            elif command in {'%', '&', '#', '$', '_', '{', '}'}:
                # These are literal math glyphs. Turning \% into a bare %
                # comments out the rest of the TeX line, including math close.
                result.append('\\' + command)
            elif not command.isalpha() and command in {"!", ",", ";", ":", "'", "[", "]", "(", ")"}:
                result.append("\\" + command)
            else:
                result.append(r"\textbackslash{}" + command)
            index += len(match[0])
            continue
        char = value[index]
        result.append({"&": r"\&", "%": r"\%", "#": r"\#", "~": r"\textasciitilde{}"}.get(char, char))
        index += 1
    return "".join(result)


TEMPLATES = Path(__file__).with_name("templates")

def format_profiles():
    return json.loads((TEMPLATES / "profiles.json").read_text())

def render_tex(markdown: str, profile: str = "academic", *, assets=()) -> str:
    profiles = format_profiles()
    if profile not in profiles:
        raise ValueError(f"Unknown report format profile: {profile}")
    template_path = (TEMPLATES / profiles[profile]["template"]).resolve()
    if not template_path.is_relative_to(TEMPLATES.resolve()):
        raise ValueError("Template must be a trusted local asset")
    reference_numbers = {}
    reference_labels = {}
    # Honor bibliography order even when the body cites sources out of order.
    bibliography = REFERENCE_HEADING_RE.split(markdown, maxsplit=1)
    if len(bibliography) == 2:
        # Writers may use either Markdown links or 'Title — bare URL'. Seed
        # numbers from both before visiting body citations in a different order.
        for url in re.findall(r"https?://[^\s<>\[\]()]+", bibliography[1]):
            url = url.rstrip(".,;，。；")
            reference_numbers.setdefault(url, len(reference_numbers) + 1)
        for label, url in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", bibliography[1]):
            reference_labels.setdefault(url, label)
    in_references = False
    def inline(text, table_cell=False):
        # Writer may wrap a Markdown source link in Chinese citation brackets.
        # The numbered PDF link already supplies its own brackets.
        text = re.sub(r'〔(\[[^\]]+\]\(https?://[^)]+\))〕', r'\1', text)
        parts, cursor = [], 0
        pattern = re.compile(r"(?<!\\)(\$\$([^$\n]+?)\$\$|\$([^$\n]+?)\$|\\\((.+?)\\\))|\[([^\]]+)\]\((https?://[^)]+)\)|\*\*(.+?)\*\*|`([^`]+)`")
        for match in pattern.finditer(text):
            parts.append(escape(text[cursor:match.start()], break_words=table_cell))
            if match[5] is not None:
                url, label = match[6], match[5]
                number = reference_numbers.setdefault(url, len(reference_numbers) + 1)
                reference_labels.setdefault(url, label)
                display = f"[{number}] " + label if in_references else f"[{number}]"
                parts.append(r"\href{" + escape(url) + "}{" + escape(display) + "}")
            elif match[7] is not None:
                parts.append(r"\textbf{" + inline(match[7], table_cell) + "}")
            elif match[8] is not None:
                parts.append(r"\texttt{" + escape(match[8]) + "}")
            else:
                parts.append(r"\(" + sanitize_math(match[2] or match[3] or match[4]) + r"\)")
            cursor = match.end()
        parts.append(escape(text[cursor:], break_words=table_cell))
        return "".join(parts)
    lines, index, list_kind = [], 0, None
    source = markdown.splitlines()
    while index < len(source):
        line = source[index]
        index += 1
        illustration = re.fullmatch(r'!\[([^\]]*)\]\(([^)]+)\)', line.strip())
        if illustration:
            name = illustration[2]
            if name not in assets or not re.fullmatch(r'figures/[a-z][a-z0-9-]{0,40}\.png', name):
                raise ValueError('Only registered local PNG figures may be published')
            if list_kind:
                lines.append('\\end{' + list_kind + '}')
                list_kind = None
            lines.extend([r'\begin{center}', r'\includegraphics[width=\linewidth,height=.65\textheight,keepaspectratio]{' + name + '}',
                          r'\par\small ' + inline(illustration[1]), r'\end{center}'])
            continue
        item = re.match(r"^\s*(?:([-*+])|\d+[.)])\s+(.+)$", line)
        kind = ("itemize" if item[1] else "enumerate") if item else None
        if list_kind and kind != list_kind:
            lines.append("\\end{" + list_kind + "}")
            list_kind = None
        if item:
            if not list_kind:
                lines.append("\\begin{" + kind + "}")
                if in_references:
                    lines.append(r"\small\raggedright\setlength{\itemsep}{2pt}\setlength{\parsep}{0pt}")
                list_kind = kind
            linked_reference = in_references and re.search(r'\[[^\]]+\]\(https?://', item[2])
            lines.append((r"\item[] " if linked_reference else r"\item ") + inline(item[2]))
            continue
        display = re.fullmatch(r"\s*(?:\$\$(.+?)\$\$|\\\[(.+?)\\\])\s*", line)
        if display:
            lines.append(r"\[" + sanitize_math(display[1] or display[2]) + r"\]")
            continue
        if "|" in line and index < len(source) and re.fullmatch(r"[\s|:\-]+", source[index]) and "-" in source[index]:
            cells = lambda row: [inline(c.strip(), table_cell=True) for c in row.strip().strip("|").split("|")]
            header = cells(line)
            index += 1
            lines.extend([r"\par\smallskip\noindent", r"\begin{tabularx}{\linewidth}{" + r">{\raggedright\arraybackslash}X" * len(header) + "}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"])
            while index < len(source) and "|" in source[index] and source[index].strip():
                row = cells(source[index])
                if len(row) != len(header):
                    raise ValueError("Markdown table row has a different number of columns")
                lines.append(" & ".join(row) + r" \\")
                index += 1
            lines.extend([r"\bottomrule", r"\end{tabularx}\par\smallskip"])
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            if len(heading[1]) == 1:
                lines.append(r"{\raggedright\LARGE\bfseries\hyphenpenalty=10000 " + inline(heading[2]) + r"\par}\vspace{8pt}")
            else:
                in_references = is_reference_heading(heading[2])
                command = ["section", "subsection"][len(heading[1])-2]
                title = heading[2]
                if profile == "academic":
                    # ctex already supplies section numbers in this template.
                    title = re.sub(r"^(?:[一二三四五六七八九十百]+[、．.]|\d+[、．.]|\d+(?:\.\d+)+\.?)\s+", "", title)
                    title = re.sub(r"^[一二三四五六七八九十百]+、", "", title)
                lines.append("\\" + command + "{" + inline(title) + "}")
        elif line.startswith("```"):
            lines.append(r"\smallskip")
        else:
            lines.append(inline(line) + "\n")
    if list_kind:
        lines.append("\\end{" + list_kind + "}")
    if reference_numbers and not REFERENCE_HEADING_RE.search(markdown):
        lines.append(r"\section*{参考资料}")
        for url, number in reference_numbers.items():
            lines.append(r"\noindent\href{" + escape(url) + "}{" + escape(f"[{number}] {reference_labels[url]}") + r"}\par")
    template = template_path.read_text(encoding="utf-8")
    if assets:
        template = template.replace(r'\begin{document}', r'\usepackage{graphicx}' + '\n' + r'\begin{document}')
    if template.count("% ASTERIA_BODY") != 1:
        raise ValueError("Template must have exactly one body slot")
    return template.replace("% ASTERIA_BODY", "\n".join(lines))


async def publish(markdown: str, root: Path, *, profile: str = "academic", assets=None) -> dict[str, str]:
    compiler = shutil.which("xelatex")
    if not compiler:
        raise RuntimeError("XeLaTeX is required for scientific report publication")
    folder = root.resolve() / ("scientific_" + uuid4().hex)
    folder.mkdir(parents=True)
    assets = assets or {}
    for name, source_path in assets.items():
        if not re.fullmatch(r'figures/[a-z][a-z0-9-]{0,40}\.png', name):
            raise ValueError('Invalid registered figure name')
        source_path = Path(source_path)
        if source_path.is_symlink() or source_path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError('Figure must be a bounded regular PNG')
        from PIL import Image
        with Image.open(source_path) as im:
            if im.format != 'PNG' or im.width * im.height > 24_000_000:
                raise ValueError('Invalid PNG figure')
            im.verify()
        target = folder / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source_path, target)
    (folder / "report.md").write_text(markdown, encoding="utf-8")
    (folder / "report.tex").write_text(render_tex(markdown, profile, assets=assets), encoding="utf-8")
    (folder / "publication.json").write_text(json.dumps({"format_profile": profile, "renderer": "safe-markdown-v3", "status": "compiling"}))
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            compiler, "-no-shell-escape", "-halt-on-error", "-interaction=nonstopmode", "report.tex",
            cwd=folder, env={**os.environ, "openin_any": "p", "openout_any": "p"},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        output, _ = await asyncio.wait_for(process.communicate(), 90)
        (folder / "compile.txt").write_bytes(output)
        if process.returncode or not (folder / "report.pdf").is_file():
            raise RuntimeError(f"LaTeX compilation failed; inspect {folder / 'compile.txt'}")
        mapped_fonts = await asyncio.to_thread(embed_unicode_maps, folder / "report.pdf")
    except BaseException as error:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        (folder / "publication.json").write_text(json.dumps({
            "format_profile": profile, "renderer": "safe-markdown-v3",
            "status": "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
            "error_type": type(error).__name__}))
        raise
    (folder / "publication.json").write_text(json.dumps({
        "format_profile": profile, "renderer": "safe-markdown-v3",
        "embedded_unicode_maps": mapped_fonts, "status": "completed"}))
    # Preserve the caller's output root (including nested or absolute QA roots).
    output_folder = folder.relative_to(Path.cwd()) if folder.is_relative_to(Path.cwd()) else folder
    result = {key: str(output_folder / name) for key, name in {
        "tex": "report.tex", "latex_pdf": "report.pdf", "compile_log": "compile.txt", "md": "report.md"}.items()}
    if assets:
        with zipfile.ZipFile(folder / 'report-bundle.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in ['report.md', 'report.tex', 'report.pdf', *assets]:
                archive.write(folder / name, name)
        result['report_bundle'] = str(output_folder / 'report-bundle.zip')
    return result
