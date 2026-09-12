"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Icon from "./Icon";
import s from "./management.module.css";

export default function EntityActions({kind, title, onOpen, onDelete, disabled = false}: {
  kind: "项目" | "任务"; title: string; onOpen: () => void;
  onDelete: () => Promise<void>; disabled?: boolean;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const [position, setPosition] = useState<{top: number; left: number} | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const closeMenu = () => { setPosition(null); trigger.current?.focus(); };
  useEffect(() => {
    if (!position) return;
    menu.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) setPosition(null);
    };
    const close = () => setPosition(null);
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => { document.removeEventListener("pointerdown", outside); window.removeEventListener("resize", close); window.removeEventListener("scroll", close, true); };
  }, [position]);
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
        setPosition({left: Math.max(8, Math.min(rect.right - 176, window.innerWidth - 184)), top: Math.max(8, Math.min(rect.bottom + 4, window.innerHeight - 110))});
      }}><Icon name="more" size={16}/></button>
    {position && createPortal(<div ref={menu} className={s.menu} role="menu" aria-label={`${kind}操作`} style={position}
      onKeyDown={e => {
        if (e.key === "Escape" || e.key === "Tab") { if(e.key === "Escape") e.preventDefault(); closeMenu(); }
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
          e.preventDefault(); const items = Array.from(menu.current!.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
          const current = items.indexOf(document.activeElement as HTMLButtonElement);
          const next = e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : (current + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
          items[next]?.focus();
        }
      }}>
      <button role="menuitem" onClick={() => { closeMenu(); onOpen(); }}><Icon name={kind === "项目" ? "folder" : "file"} size={16}/>{kind === "项目" ? "项目详情" : "打开任务"}</button>
      <button role="menuitem" className={s.danger} disabled={disabled} onClick={() => { setPosition(null); setError(""); setConfirming(true); }}><Icon name="trash" size={16}/>删除{kind}</button>
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
