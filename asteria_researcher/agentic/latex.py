"""Safe text-to-LaTeX publishing: no model-supplied TeX is executed."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import shutil
from uuid import uuid4


def escape(value: str) -> str:
    replacements = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
                    "$": r"\$", "&": r"\&", "#": r"\#", "%": r"\%",
                    "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(char, char) for char in value)


# Math is preserved as a structured fragment, but arbitrary TeX commands are
# still escaped. This keeps useful formulas editable without turning the
# publishing path into a model-controlled TeX execution surface.
SAFE_MATH_COMMANDS = {
    "alpha", "beta", "gamma", "delta", "epsilon", "theta", "lambda", "mu", "pi", "sigma", "phi", "psi", "omega",
    "mathrm", "mathbf", "mathit", "mathsf", "operatorname", "text", "frac", "dfrac", "tfrac", "sqrt", "left", "right",
    "sum", "prod", "int", "lim", "log", "exp", "sin", "cos", "tan", "cdot", "times", "pm", "leq", "geq", "neq",
    "approx", "infty", "to", "rightarrow", "mapsto", "top", "mid", "perp", "forall", "exists", "in", "notin",
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

def render_tex(markdown: str, profile: str = "academic") -> str:
    profiles = format_profiles()
    if profile not in profiles:
        raise ValueError(f"Unknown report format profile: {profile}")
    template_path = (TEMPLATES / profiles[profile]["template"]).resolve()
    if not template_path.is_relative_to(TEMPLATES.resolve()):
        raise ValueError("Template must be a trusted local asset")
    def inline(text):
        text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", text)
        text = text.replace("**", "").replace("`", "")
        parts, cursor = [], 0
        pattern = re.compile(r"(?<!\\)(\$\$([^$\n]+?)\$\$|\$([^$\n]+?)\$|\\\((.+?)\\\))")
        for match in pattern.finditer(text):
            parts.append(escape(text[cursor:match.start()]))
            parts.append(r"\(" + sanitize_math(match[2] or match[3] or match[4]) + r"\)")
            cursor = match.end()
        parts.append(escape(text[cursor:]))
        return "".join(parts)
    lines, index, list_kind = [], 0, None
    source = markdown.splitlines()
    while index < len(source):
        line = source[index]
        index += 1
        item = re.match(r"^\s*(?:([-*+])|\d+[.)])\s+(.+)$", line)
        kind = ("itemize" if item[1] else "enumerate") if item else None
        if list_kind and kind != list_kind:
            lines.append("\\end{" + list_kind + "}")
            list_kind = None
        if item:
            if not list_kind:
                lines.append("\\begin{" + kind + "}")
                list_kind = kind
            lines.append(r"\item " + inline(item[2]))
            continue
        display = re.fullmatch(r"\s*(?:\$\$(.+?)\$\$|\\\[(.+?)\\\])\s*", line)
        if display:
            lines.append(r"\[" + sanitize_math(display[1] or display[2]) + r"\]")
            continue
        if "|" in line and index < len(source) and re.fullmatch(r"[\s|:\-]+", source[index]) and "-" in source[index]:
            cells = lambda row: [inline(c.strip()) for c in row.strip().strip("|").split("|")]
            header = cells(line)
            index += 1
            lines.extend([r"\par\smallskip\noindent", r"\begin{tabularx}{\linewidth}{" + "X" * len(header) + "}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"])
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
                lines.append(r"{\LARGE\bfseries " + inline(heading[2]) + r"\par}\vspace{12pt}")
            else:
                command = ["section", "subsection"][len(heading[1])-2]
                lines.append("\\" + command + "{" + inline(heading[2]) + "}")
        elif line.startswith("```"):
            lines.append(r"\smallskip")
        else:
            lines.append(inline(line) + "\n")
    if list_kind:
        lines.append("\\end{" + list_kind + "}")
    template = template_path.read_text(encoding="utf-8")
    if template.count("% ASTERIA_BODY") != 1:
        raise ValueError("Template must have exactly one body slot")
    return template.replace("% ASTERIA_BODY", "\n".join(lines))


async def publish(markdown: str, root: Path, *, profile: str = "academic") -> dict[str, str]:
    compiler = shutil.which("xelatex")
    if not compiler:
        raise RuntimeError("XeLaTeX is required for scientific report publication")
    folder = root.resolve() / ("scientific_" + uuid4().hex)
    folder.mkdir(parents=True)
    (folder / "report.md").write_text(markdown, encoding="utf-8")
    (folder / "report.tex").write_text(render_tex(markdown, profile), encoding="utf-8")
    (folder / "publication.json").write_text(json.dumps({"format_profile": profile, "renderer": "safe-markdown-v2"}))
    process = await asyncio.create_subprocess_exec(
        compiler, "-no-shell-escape", "-halt-on-error", "-interaction=nonstopmode", "report.tex",
        cwd=folder, env={**os.environ, "openin_any": "p", "openout_any": "p"},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), 90)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    (folder / "compile.txt").write_bytes(output)
    if process.returncode or not (folder / "report.pdf").is_file():
        raise RuntimeError(f"LaTeX compilation failed; inspect {folder / 'compile.txt'}")
    return {key: f"outputs/{folder.name}/{name}" for key, name in {
        "tex": "report.tex", "latex_pdf": "report.pdf", "compile_log": "compile.txt", "md": "report.md"}.items()}
