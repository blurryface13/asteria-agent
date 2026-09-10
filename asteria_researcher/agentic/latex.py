"""Safe text-to-LaTeX publishing: no model-supplied TeX is executed."""
from __future__ import annotations

import asyncio
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


def render_tex(markdown: str) -> str:
    lines = []
    for line in markdown.splitlines():
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            command = ["section", "subsection", "subsubsection"][len(heading[1])-1]
            lines.append("\\" + command + "*{" + escape(heading[2]) + "}")
        elif line.startswith("```"):
            lines.append(r"\smallskip")
        else:
            # Preserve all source URLs visibly, without allowing arbitrary TeX.
            line = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", line)
            line = line.replace("**", "").replace("`", "")
            lines.append(escape(line) + "\n")
    return (r"\documentclass[UTF8,fontset=fandol,11pt]{ctexart}" + "\n"
            r"\usepackage[a4paper,margin=25mm]{geometry}" + "\n"
            r"\usepackage{hyperref}" + "\n"
            r"\hypersetup{hidelinks}" + "\n"
            r"\setlength{\parindent}{0pt}\setlength{\parskip}{6pt}" + "\n"
            r"\emergencystretch=3em\sloppy" + "\n"
            r"\begin{document}" + "\n" + "\n".join(lines) + "\n" + r"\end{document}" + "\n")


async def publish(markdown: str, root: Path) -> dict[str, str]:
    compiler = shutil.which("xelatex")
    if not compiler:
        raise RuntimeError("XeLaTeX is required for scientific report publication")
    folder = root.resolve() / ("scientific_" + uuid4().hex)
    folder.mkdir(parents=True)
    (folder / "report.md").write_text(markdown, encoding="utf-8")
    (folder / "report.tex").write_text(render_tex(markdown), encoding="utf-8")
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
