"use client";

import React, { useRef, useEffect } from "react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { ResearchHistoryItem } from "@/types/data";

interface WorkspaceRailProps {
  history: ResearchHistoryItem[];
  isOpen: boolean;
  onToggle: () => void;
  onNewResearch: () => void;
  onSelectResearch: (id: string) => void;
  onDeleteResearch: (id: string) => void;
}

type IconKind = "new" | "host" | "agent" | "knowledge" | "evaluation" | "search" | "collapse";

function RailIcon({ kind }: { kind: IconKind }) {
  const common = "h-[18px] w-[18px]";
  if (kind === "new") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M12 5v14M5 12h14" /></svg>;
  if (kind === "host") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="4" y="5" width="16" height="14" rx="2" /><path d="M8 9h.01M11 9h5M8 13h8M8 16h5" /></svg>;
  if (kind === "agent") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="5" y="7" width="14" height="12" rx="3" /><path d="M9 7V5h6v2M9 12h.01M15 12h.01M9 16h6M12 3v2" /></svg>;
  if (kind === "knowledge") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v17H7.5A2.5 2.5 0 0 0 5 22V5.5Z" /><path d="M5 19a2.5 2.5 0 0 1 2.5-2H19M9 7h6M9 11h6" /></svg>;
  if (kind === "evaluation") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M5 19V9M12 19V5M19 19v-7" /><path d="M3 19h18" /></svg>;
  if (kind === "search") return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="10.8" cy="10.8" r="6.3" /><path d="m16 16 4.5 4.5" /></svg>;
  return <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="4" y="5" width="16" height="14" rx="2" /><path d="M9 5v14" /></svg>;
}

const navItems: Array<{ href: string; label: string; icon: IconKind }> = [
  { href: "/rag-workspace", label: "主机与工作区", icon: "host" },
  { href: "/doc-agent", label: "Agent 能力", icon: "agent" },
  { href: "/knowledge", label: "知识库", icon: "knowledge" },
  { href: "/evaluation", label: "评测中心", icon: "evaluation" },
];

export default function WorkspaceRail({ history, isOpen, onToggle, onNewResearch, onSelectResearch, onDeleteResearch }: WorkspaceRailProps) {
  const railRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (typeof window === "undefined" || window.matchMedia("(min-width: 1024px)").matches) return;
    const handleOutsideClick = (event: MouseEvent) => {
      if (isOpen && railRef.current && !railRef.current.contains(event.target as Node)) onToggle();
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [isOpen, onToggle]);

  const timestamp = (value: ResearchHistoryItem["timestamp"]) => {
    if (!value) return "未记录时间";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "未记录时间" : formatDistanceToNow(date, { addSuffix: true });
  };

  return (
    <>
      {isOpen && <button type="button" aria-label="关闭导航遮罩" onClick={onToggle} className="fixed inset-0 z-40 bg-black/30 lg:hidden" />}
      <aside ref={railRef} aria-label="Asteria 工作区导航" className={`fixed inset-y-0 left-0 z-50 flex flex-col border-r border-white/[0.08] bg-[oklch(16%_0.012_255_/_0.94)] text-white shadow-[18px_0_60px_rgba(3,7,18,0.24)] backdrop-blur-2xl transition-[width,transform] duration-200 lg:translate-x-0 ${isOpen ? "w-[268px]" : "w-[64px] -translate-x-full lg:translate-x-0"}`}>
        <div className={`flex h-[72px] items-center border-b border-white/[0.08] ${isOpen ? "justify-between px-4" : "justify-center"}`}>
          {isOpen ? (
            <Link href="/" onClick={onNewResearch} className="flex items-center gap-2.5" aria-label="返回 Asteria Research 首页">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[oklch(25%_0.025_255)] ring-1 ring-white/10"><img src="/img/asteria-logo.png" alt="" width={28} height={28} className="h-7 w-7 object-contain" /></span>
              <span className="text-[15px] font-semibold tracking-[-0.02em] text-white/90">Asteria Research</span>
            </Link>
          ) : <img src="/img/asteria-logo.png" alt="Asteria Research" width={34} height={34} className="h-8 w-8 object-contain" />}
          <button type="button" onClick={onToggle} className={`flex h-8 w-8 items-center justify-center rounded-lg text-white/45 transition hover:bg-white/[0.08] hover:text-white ${isOpen ? "" : "mt-3"}`} aria-label={isOpen ? "收起导航栏" : "展开导航栏"} title={isOpen ? "收起导航栏" : "展开导航栏"}>
            <RailIcon kind="collapse" />
          </button>
        </div>

        <div className={`px-3 pt-4 ${isOpen ? "" : "px-2"}`}>
          <button type="button" onClick={onNewResearch} className={`flex w-full items-center rounded-xl bg-white/[0.10] text-left text-[13px] font-medium text-white/90 transition hover:bg-white/[0.16] ${isOpen ? "gap-3 px-3 py-2.5" : "justify-center px-2 py-3"}`}>
            <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-[oklch(72%_0.15_55)] text-[oklch(18%_0.02_55)]"><RailIcon kind="new" /></span>
            {isOpen && <span>新建任务</span>}
          </button>
        </div>

        <nav className={`mt-5 space-y-1 px-3 ${isOpen ? "" : "px-2"}`} aria-label="功能入口">
          {navItems.map((item) => <Link key={item.href} href={item.href} className={`flex items-center rounded-xl text-[13px] text-white/58 transition hover:bg-white/[0.08] hover:text-white/90 ${isOpen ? "gap-3 px-3 py-2.5" : "justify-center px-2 py-3"}`} title={isOpen ? undefined : item.label}>
            <span className="flex h-6 w-6 items-center justify-center text-white/55"><RailIcon kind={item.icon} /></span>
            {isOpen && <span>{item.label}</span>}
          </Link>)}
        </nav>

        {isOpen && <div className="mt-7 flex min-h-0 flex-1 flex-col px-3">
          <div className="flex items-center justify-between px-2 text-[11px] font-medium tracking-[0.13em] text-white/35"><span>最近任务</span><span>{history.length}</span></div>
          <div className="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto pr-1 [scrollbar-width:thin]">
            {history.length === 0 ? <div className="rounded-xl border border-dashed border-white/[0.12] px-3 py-5 text-center text-xs leading-5 text-white/32">完成一次研究后，任务会显示在这里。</div> : history.map((item) => <div key={item.id} className="group relative rounded-xl transition hover:bg-white/[0.07]">
              <Link href={`/research/${item.id}`} onClick={() => onSelectResearch(item.id)} className="block px-3 py-2.5 pr-8"><p className="truncate text-xs font-medium text-white/72">{item.question}</p><p className="mt-1 text-[11px] text-white/32">{timestamp(item.timestamp || (item as any).updated_at || (item as any).created_at)}</p></Link>
              <button type="button" onClick={(event) => { event.stopPropagation(); onDeleteResearch(item.id); }} className="absolute right-2 top-2.5 hidden rounded p-1 text-white/30 hover:bg-white/[0.10] hover:text-red-300 group-hover:block" aria-label="删除研究记录">×</button>
            </div>)}
          </div>
        </div>}

        <div className={`border-t border-white/[0.08] ${isOpen ? "mx-3 px-2" : "mx-2 px-0"} py-4`}>
          {isOpen ? <div className="flex items-center justify-between text-xs text-white/40"><span>本地工作区</span><span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />已连接</span></div> : <span className="mx-auto block h-1.5 w-1.5 rounded-full bg-emerald-400" title="本地工作区已连接" />}
        </div>
      </aside>
    </>
  );
}
