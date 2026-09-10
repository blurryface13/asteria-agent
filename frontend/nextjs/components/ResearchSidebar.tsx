import React, { useEffect, useRef } from "react";
import Link from "next/link";
import { ResearchHistoryItem } from "../types/data";
import { formatDistanceToNow } from "date-fns";
import { motion, AnimatePresence } from "framer-motion";

interface ResearchSidebarProps {
  history: ResearchHistoryItem[];
  onSelectResearch: (id: string) => void;
  onNewResearch: () => void;
  onDeleteResearch: (id: string) => void;
  isOpen: boolean;
  toggleSidebar: () => void;
}

const navItems = [
  { href: "/", label: "新建研究", icon: "+" },
  { href: "/knowledge", label: "知识库", icon: "⌕" },
  { href: "/rag-workspace", label: "RAG 工作区", icon: "◇" },
];

const ResearchSidebar: React.FC<ResearchSidebarProps> = ({ history, onSelectResearch, onNewResearch, onDeleteResearch, isOpen, toggleSidebar }) => {
  const sidebarRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // The rail is persistent on desktop. The previous global listener closed it
    // whenever the user clicked the main work area, which made the sidebar look
    // as if it had randomly disappeared.
    if (window.matchMedia("(min-width: 1024px)").matches) return;

    const handleClickOutside = (event: MouseEvent) => { if (isOpen && sidebarRef.current && !sidebarRef.current.contains(event.target as Node)) toggleSidebar(); };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen, toggleSidebar]);

  const formatTimestamp = (timestamp: number | string | Date | undefined) => {
    if (!timestamp) return "未记录时间";
    try { const date = new Date(timestamp); return isNaN(date.getTime()) ? "未记录时间" : formatDistanceToNow(date, { addSuffix: true }); } catch { return "未记录时间"; }
  };

  return <>
    <AnimatePresence>{isOpen && <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-40 bg-slate-950/10 md:hidden" onClick={toggleSidebar} aria-hidden="true" />}</AnimatePresence>
    <motion.aside ref={sidebarRef} initial={false} animate={{ width: isOpen ? 276 : 16 }} transition={{ duration: 0.2, ease: "easeOut" }} className="fixed inset-y-0 left-0 z-50 overflow-hidden border-r border-slate-200 bg-[oklch(97.8%_0.006_250)] text-slate-800" aria-label="研究工作区导航">
      {isOpen ? <div className="flex h-full w-[276px] flex-col px-3 py-4">
        <div className="flex items-center justify-between px-2 pb-6">
          <Link href="/" className="flex items-center gap-2.5" onClick={onNewResearch}><img src="/img/asteria-logo.png" alt="" width={32} height={32} className="h-8 w-8 object-contain" /><span className="text-sm font-semibold tracking-tight text-slate-900">Bunny Research</span></Link>
          <button type="button" onClick={toggleSidebar} className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-white hover:text-slate-700" aria-label="收起导航栏"><span className="text-lg leading-none">‹</span></button>
        </div>
        <nav className="space-y-1" aria-label="主导航">
          {navItems.map((item, index) => <React.Fragment key={item.href}>{index === 1 && <div className="my-4 border-t border-slate-200" />}{item.href === "/" ? <button type="button" onClick={onNewResearch} className="flex w-full items-center gap-3 rounded-lg bg-white px-3 py-2.5 text-left text-sm font-medium text-slate-800 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-colors hover:bg-teal-50 hover:text-teal-800"><span className="flex h-5 w-5 items-center justify-center rounded-md bg-teal-600 text-sm font-medium text-white">{item.icon}</span>{item.label}</button> : <Link href={item.href} className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-slate-500 transition-colors hover:bg-white hover:text-slate-800"><span className="flex h-5 w-5 items-center justify-center font-mono text-base text-slate-400">{item.icon}</span>{item.label}</Link>}</React.Fragment>)}
        </nav>
        <div className="mt-7 flex min-h-0 flex-1 flex-col">
          <div className="flex items-center justify-between px-2"><span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">最近研究</span><span className="text-xs text-slate-400">{history.length}</span></div>
          <div className="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">{history.length === 0 ? <div className="rounded-lg border border-dashed border-slate-300 px-3 py-5 text-center text-xs leading-5 text-slate-400">完成一次研究后，记录会显示在这里。</div> : history.map((item) => <div key={item.id} className="group relative rounded-lg transition-colors hover:bg-white"><Link href={`/research/${item.id}`} onClick={() => onSelectResearch(item.id)} className="block px-3 py-2.5 pr-8"><p className="truncate text-xs font-medium text-slate-700">{item.question}</p><p className="mt-1 text-[11px] text-slate-400">{formatTimestamp(item.timestamp || (item as any).updated_at || (item as any).created_at)}</p></Link><button type="button" onClick={(event) => { event.stopPropagation(); onDeleteResearch(item.id); }} className="absolute right-2 top-2.5 hidden rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-red-600 group-hover:block" aria-label="删除研究记录">×</button></div>)}</div>
        </div>
        <div className="mt-4 flex items-center justify-between rounded-lg border border-slate-200 bg-white/70 px-3 py-2.5 text-xs text-slate-500"><span>个人工作区</span><span className="h-2 w-2 rounded-full bg-emerald-500" title="本地服务已连接" /></div>
      </div> : <button type="button" onClick={toggleSidebar} className="flex h-12 w-12 items-center justify-center text-slate-500 hover:text-slate-900" aria-label="展开导航栏"><span className="text-lg">›</span></button>}
    </motion.aside>
  </>;
};

export default ResearchSidebar;
