import React from "react";
import dynamic from "next/dynamic";
import { ChatBoxSettings } from "@/types/data";

// The preferences dialog uses a browser portal and Framer Motion. Loading it
// only after hydration keeps the server-rendered workbench response reliable
// while preserving the full settings experience in the browser.
const PreferencesModal = dynamic(() => import("./Settings/Modal"), { ssr: false });

interface HeaderProps {
  loading?: boolean;
  isStopped?: boolean;
  showResult?: boolean;
  onStop?: () => void;
  onNewResearch?: () => void;
  isCopilotMode?: boolean;
  chatBoxSettings?: ChatBoxSettings;
  setChatBoxSettings?: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
}

const Header = ({ loading, isStopped, showResult, onStop, onNewResearch, isCopilotMode, chatBoxSettings, setChatBoxSettings }: HeaderProps) => {
  const jagentUrl = process.env.NEXT_PUBLIC_JAGENT_URL?.trim();
  return <header className="fixed inset-x-0 top-0 z-30 md:left-[276px]">
    <div className="flex h-[72px] items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur-md sm:px-8 lg:px-10">
      <a href="/" className="flex items-center gap-2 md:hidden"><span className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-900 text-xs font-semibold text-white">A</span><span className="text-sm font-semibold text-slate-800">Asteria Research</span></a>
      <div className="hidden items-center gap-2 text-xs text-slate-400 md:flex"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />本地工作区</div>
      <div className="ml-auto flex items-center gap-2">
        <a href="/knowledge" className="hidden rounded-md px-3 py-2 text-sm text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 sm:block">知识库</a>
        <a href="/rag-workspace" className="hidden rounded-md px-3 py-2 text-sm text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 lg:block">RAG 工作区</a>
        {jagentUrl ? <a href={jagentUrl} target="_blank" rel="noreferrer" className="hidden rounded-md px-3 py-2 text-sm text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 xl:block">个人主页</a> : null}
        {chatBoxSettings && setChatBoxSettings && <PreferencesModal chatBoxSettings={chatBoxSettings} setChatBoxSettings={setChatBoxSettings} variant="compact" />}
        {loading && !isStopped && <button type="button" onClick={onStop} className="rounded-md bg-red-50 px-3 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-100">停止</button>}
        {showResult && !loading && !isCopilotMode && <button type="button" onClick={onNewResearch} className="rounded-md bg-teal-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-700">新建研究</button>}
      </div>
    </div>
  </header>;
};

export default Header;
