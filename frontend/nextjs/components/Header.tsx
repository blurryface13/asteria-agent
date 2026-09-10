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
  railOpen?: boolean;
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
  railOpen = false,
  onStop,
  onNewResearch,
  isCopilotMode,
  chatBoxSettings,
  setChatBoxSettings,
}: HeaderProps) => {
  const jagentUrl = process.env.NEXT_PUBLIC_JAGENT_URL?.trim();
  const iconButton = "flex h-10 w-10 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.06] text-white/55 backdrop-blur-xl transition hover:border-white/[0.16] hover:bg-white/[0.10] hover:text-white";
  const headerOffset = railOpen ? (sidebarOpen ? "lg:left-[268px]" : "lg:left-[64px]") : "";

  return (
    <header className={`fixed inset-x-0 top-0 z-30 transition-[left] duration-200 ${headerOffset}`}>
      <div className="flex h-[72px] items-center justify-between border-b border-white/[0.08] bg-[oklch(12%_0.012_255_/_0.82)] px-5 backdrop-blur-2xl sm:px-8 lg:px-10">
        {showResult ? (
          <div className="flex items-center gap-2 text-sm font-medium text-white/60">
            <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_0_4px_rgba(52,211,153,0.12)]" />
            <span>Research task</span>
          </div>
        ) : (
          <a href="/" className={`flex items-center gap-3 ${railOpen ? "lg:hidden" : ""}`} aria-label="返回 Asteria Research 首页">
            <img src="/img/asteria-logo.png" alt="" width={38} height={38} className="h-9 w-9 object-contain" />
            <span className="text-[1.1rem] font-semibold tracking-[-0.025em] text-white/85">Asteria Research</span>
          </a>
        )}

        <div className="flex items-center gap-2">
          <a href="/knowledge" className={`${iconButton} hidden sm:flex ${railOpen ? "lg:hidden" : ""}`} aria-label="打开知识库" title="知识库">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4.5 5.5A2.5 2.5 0 0 1 7 3h11.5v16H7a2.5 2.5 0 0 0-2.5 2.5V5.5Z" /><path d="M4.5 21.5A2.5 2.5 0 0 1 7 19h11.5" /></svg>
          </a>
          <a href="/rag-workspace" className={`${iconButton} hidden md:flex ${railOpen ? "lg:hidden" : ""}`} aria-label="打开 RAG 工作区" title="RAG 工作区">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M5 4.5h14v15H5z" /><path d="M8 8h8M8 12h8M8 16h5" /></svg>
          </a>
          {jagentUrl ? <a href={jagentUrl} target="_blank" rel="noreferrer" className="hidden rounded-xl px-3 py-2 text-sm text-white/50 transition hover:bg-white/[0.08] hover:text-white xl:block">个人主页</a> : null}
          {chatBoxSettings && setChatBoxSettings && (
            <PreferencesModal
              chatBoxSettings={chatBoxSettings}
              setChatBoxSettings={setChatBoxSettings}
              variant="compact"
              iconOnly={!showResult}
            />
          )}
          {loading && !isStopped && <button type="button" onClick={onStop} className="rounded-full bg-rose-50 px-4 py-2 text-sm font-medium text-rose-600 transition hover:bg-rose-100">停止</button>}
          {showResult && !loading && !isCopilotMode && <button type="button" onClick={onNewResearch} className="rounded-xl bg-white/[0.10] px-4 py-2 text-sm font-medium text-white/85 transition hover:bg-white/[0.16]">新建研究</button>}
        </div>
      </div>
    </header>
  );
};

export default Header;
