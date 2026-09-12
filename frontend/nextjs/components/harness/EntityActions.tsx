"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Icon from "./Icon";
import s from "./management.module.css";

export default function EntityActions({kind, title, onOpen, onDelete, onRename, onMove, projects = [], projectId = null, disabled = false}: {
  kind: "项目" | "任务"; title: string; onOpen: () => void;
  onDelete: () => Promise<void>; disabled?: boolean;
  onRename?: (title: string) => Promise<void>;
  onMove?: (projectId: string | null) => Promise<void>;
  projects?: {id: string; name: string}[]; projectId?: string | null;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const [position, setPosition] = useState<{top: number; left: number} | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editor, setEditor] = useState<"" | "rename" | "move">("");
  const [draft, setDraft] = useState("");
  const editInput = useRef<HTMLInputElement>(null);
  const closeMenu = () => { if (busy) return; setPosition(null); setEditor(""); setError(""); trigger.current?.focus(); };
  useEffect(() => { if (editor === "rename") { editInput.current?.focus(); editInput.current?.select(); } }, [editor]);
  useEffect(() => { if (position) menu.current?.querySelector<HTMLButtonElement>("button")?.focus(); }, [position]);
  useEffect(() => {
    if (!position) return;
    const outside = (event: PointerEvent) => {
      if (!busy && !menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) { setPosition(null); setEditor(""); }
    };
    const close = (event: Event) => {
      if (event.type === "scroll" && event.target instanceof Node && menu.current?.contains(event.target)) return;
      if (!busy) { setPosition(null); setEditor(""); }
    };
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => { document.removeEventListener("pointerdown", outside); window.removeEventListener("resize", close); window.removeEventListener("scroll", close, true); };
  }, [position, busy]);
  useEffect(() => {
    if (confirming) { dialog.current?.showModal(); cancel.current?.focus(); }
    else if (dialog.current?.open) { dialog.current.close(); trigger.current?.focus(); }
  }, [confirming]);
  const dismiss = () => { if (!busy) setConfirming(false); };
  return <>
    <button ref={trigger} className={s.trigger} aria-label={`${kind}操作：${title}`} aria-haspopup="menu" aria-expanded={!!position}
      onClick={() => {
        if (position) { closeMenu(); return; }
        const rect = trigger.current!.getBoundingClientRect();
        setEditor(""); setError("");
        setPosition({left: Math.max(8, Math.min(rect.right - 240, window.innerWidth - 248)), top: Math.max(8, Math.min(rect.bottom + 4, window.innerHeight - 220))});
      }}><Icon name="more" size={16}/></button>
    {position && createPortal(<div ref={menu} className={s.menu} role={editor ? "dialog" : "menu"} aria-label={editor === "rename" ? `重命名${kind}` : editor === "move" ? "移动任务" : `${kind}操作`} style={position}
      onKeyDown={e => {
        if (editor) { if (e.key === "Escape") {e.preventDefault(); closeMenu();} return; }
        if (e.key === "Escape" || e.key === "Tab") { if(e.key === "Escape") e.preventDefault(); closeMenu(); }
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
          e.preventDefault(); const items = Array.from(menu.current!.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
          const current = items.indexOf(document.activeElement as HTMLButtonElement);
          const next = e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : (current + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
          items[next]?.focus();
        }
      }}>
      {editor ? <form className={s.editor} onSubmit={async e => {
        e.preventDefault(); if (busy || (editor === "rename" && !draft.trim())) return;
        setBusy(true); setError("");
        try {
          if (editor === "rename") await onRename?.(draft.trim()); else await onMove?.(draft || null);
          setPosition(null); setEditor(""); trigger.current?.focus();
        } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败"); }
        finally { setBusy(false); }
      }}>
        <label>{editor === "rename" ? `${kind}名称` : "移动到"}
          {editor === "rename" ? <input ref={editInput} value={draft} onChange={e => setDraft(e.target.value)} maxLength={kind === "项目" ? 120 : 255} disabled={busy}/>
            : <select value={draft} onChange={e => setDraft(e.target.value)} disabled={busy} autoFocus>
              <option value="">独立任务（不属于项目）</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>}
        </label>
        {error && <p role="alert" className={s.danger}>{error}</p>}
        <div className={s.buttons}><button type="button" disabled={busy} onClick={closeMenu}>取消</button>
          <button type="submit" disabled={busy || (editor === "rename" ? !draft.trim() || draft.trim() === title : draft === (projectId || ""))}>{busy ? "保存中…" : "保存"}</button></div>
      </form> : <>
      <button role="menuitem" onClick={() => { closeMenu(); onOpen(); }}><Icon name={kind === "项目" ? "folder" : "file"} size={16}/>{kind === "项目" ? "项目详情" : "打开任务"}</button>
      {onRename && <button role="menuitem" onClick={() => {setDraft(title); setError(""); setEditor("rename");}}><Icon name="compose" size={16}/>重命名</button>}
      {onMove && <button role="menuitem" disabled={disabled} onClick={() => {setDraft(projectId || ""); setError(""); setEditor("move");}}><Icon name="folder" size={16}/>移动到项目</button>}
      <button role="menuitem" className={s.danger} disabled={disabled} onClick={() => { setPosition(null); setError(""); setConfirming(true); }}><Icon name="trash" size={16}/>删除{kind}</button>
      </>}
    </div>, document.body)}
    <dialog ref={dialog} className={s.confirm} aria-label={`删除${kind}`} onCancel={e => { e.preventDefault(); dismiss(); }}>
      <h2>删除{kind}？</h2>
      <p className={s.title}>{title}</p>
      <p>{kind === "项目" ? "仅删除项目分组，子任务会保留在任务列表中。工作目录与文件不会删除。" : "将删除此任务的对话、报告记录和执行历史，无法在界面中恢复。已生成的本地文件不会删除。"}</p>
      {error && <p role="alert" className={s.danger}>{error}</p>}
      <div className={s.buttons}>
        <button ref={cancel} disabled={busy} onClick={dismiss}>取消</button>
        <button className={s.deleteButton} disabled={busy || disabled} onClick={async () => {
          setBusy(true); setError("");
          try { await onDelete(); setConfirming(false); }
          catch (cause) { setError(cause instanceof Error ? cause.message : "删除失败，请重试"); }
          finally { setBusy(false); }
        }}>{busy ? "正在删除…" : `删除${kind}`}</button>
      </div>
    </dialog>
  </>;
}
