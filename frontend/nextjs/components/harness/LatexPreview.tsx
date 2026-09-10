"use client";
import { useEffect, useState } from "react";
import { getHost } from "@/helpers/getHost";
import s from "./harness.module.css";

export default function LatexPreview({
  paths,
}: {
  paths: Record<string, string>;
}) {
  const [source, setSource] = useState(""),
    [error, setError] = useState("");
  const safe = (path?: string) =>
    path &&
    /^outputs\/scientific_[a-f0-9]{32}\/(report\.(tex|pdf)|compile\.txt)$/.test(
      path,
    )
      ? `${getHost()}/${path}`
      : "";
  const tex = safe(paths.tex),
    pdf = safe(paths.latex_pdf),
    log = safe(paths.compile_log);
  useEffect(() => {
    const controller = new AbortController();
    setSource("");
    setError("");
    if (tex)
      fetch(tex, { signal: controller.signal })
        .then((r) => {
          if (!r.ok) throw Error(`读取源码失败 (${r.status})`);
          return r.text();
        })
        .then(setSource)
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        });
    return () => controller.abort();
  }, [tex]);
  if (!tex || !pdf) return <p>此报告暂无 LaTeX 产物。</p>;
  return (
    <div>
      <div className={s.reportTools}>
        <a href={tex} target="_blank" rel="noreferrer" className={s.outline}>
          下载 .tex
        </a>
        <a href={pdf} target="_blank" rel="noreferrer" className={s.outline}>
          打开 PDF
        </a>
        <a href={log} target="_blank" rel="noreferrer" className={s.outline}>
          编译日志
        </a>
      </div>
      {error && <p role="alert">{error}</p>}
      <div className={s.latexSplit}>
        <pre aria-label="LaTeX 源码" className={s.source}>
          {source || (error ? "源码读取失败，请检查上方错误信息。" : "正在读取源码…")}
        </pre>
        <iframe title="LaTeX PDF 预览" src={pdf} />
      </div>
    </div>
  );
}
