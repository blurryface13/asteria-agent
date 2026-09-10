import React from "react";
import dynamic from "next/dynamic";
import { ChatBoxSettings } from "@/types/data";

// The preferences dialog uses a browser portal and Framer Motion. Loading it
// only after hydration keeps the server-rendered workbench response reliable.
const PreferencesModal = dynamic(() => import("./Settings/Modal"), { ssr: false });

interface HeaderProps {
  loading?: boolean;
  isStopped?: boolean;
  showResult?: boolean;
  sidebarOpen?: boolean;
  onStop?: () => void;
  onNewResearch?: () => void;
  isCopilotMode?: boolean;
  chatBoxSettings?: ChatBoxSettings;
  setChatBoxSettings?: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
}

const Header = ({
  loading,
  isStopped,
  showResult = false,
  sidebarOpen = true,
  onStop,
  onNewResearch,
  isCopilotMode,
  chatBoxSettings,
  setChatBoxSettings,
}: HeaderProps) => {
  const jagentUrl = process.env.NEXT_PUBLIC_JAGENT_URL?.trim();
  const iconButton = "flex h-10 w-10 items-center justify-center rounded-full border border-slate-200/70 bg-white/75 text-slate-500 shadow-[0_4px_14px_rgba(15,23,42,0.04)] backdrop-blur-xl transition hover:border-sky-200 hover:bg-white hover:text-sky-700";

  return (
    <header className={`fixed inset-x-0 top-0 z-30 transition-[left] duration-200 ${showResult ? (sidebarOpen ? "lg:left-[276px]" : "lg:left-[56px]") : ""}`}>
      <div className={`flex h-[72px] items-center justify-between border-b px-5 backdrop-blur-xl sm:px-8 lg:px-10 ${showResult ? "border-slate-200/70 bg-white/75" : "border-slate-200/80 bg-white/90"}`}>
        {showResult ? (
          <div className="flex items-center gap-2 text-sm font-medium text-slate-600">
            <span className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_0_4px_rgba(16,185,129,0.12)]" />
            <span>研究任务</span>
          </div>
        ) : (
          <a href="/" className="flex items-center gap-3" aria-label="返回 Bunny Research 首页">
            <img src="/img/asteria-logo.png" alt="" width={38} height={38} className="h-9 w-9 object-contain" />
            <span className="text-[1.1rem] font-semibold tracking-[-0.025em] text-slate-700">Bunny Research</span>
          </a>
        )}

        <div className="flex items-center gap-2">
          <a href="/knowledge" className={`${iconButton} hidden sm:flex`} aria-label="打开知识库" title="知识库">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4.5 5.5A2.5 2.5 0 0 1 7 3h11.5v16H7a2.5 2.5 0 0 0-2.5 2.5V5.5Z" /><path d="M4.5 21.5A2.5 2.5 0 0 1 7 19h11.5" /></svg>
          </a>
          <a href="/rag-workspace" className={`${iconButton} hidden md:flex`} aria-label="打开 RAG 工作区" title="RAG 工作区">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M5 4.5h14v15H5z" /><path d="M8 8h8M8 12h8M8 16h5" /></svg>
          </a>
          {jagentUrl ? <a href={jagentUrl} target="_blank" rel="noreferrer" className="hidden rounded-full px-3 py-2 text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 xl:block">个人主页</a> : null}
          {chatBoxSettings && setChatBoxSettings && (
            <PreferencesModal
              chatBoxSettings={chatBoxSettings}
              setChatBoxSettings={setChatBoxSettings}
              variant="compact"
              iconOnly={!showResult}
            />
          )}
          {loading && !isStopped && <button type="button" onClick={onStop} className="rounded-full bg-rose-50 px-4 py-2 text-sm font-medium text-rose-600 transition hover:bg-rose-100">停止</button>}
          {showResult && !loading && !isCopilotMode && <button type="button" onClick={onNewResearch} className="rounded-full bg-slate-800 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700">新建研究</button>}
        </div>
      </div>
    </header>
  );
};

export default Header;
