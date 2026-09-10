import { ReactNode, useRef, useCallback, useEffect, Dispatch, SetStateAction } from "react";
import { Toaster } from "react-hot-toast";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import { ChatBoxSettings } from "@/types/data";

interface ResearchPageLayoutProps {
  children: ReactNode;
  loading: boolean;
  isStopped: boolean;
  showResult: boolean;
  onStop?: () => void;
  onNewResearch: () => void;
  chatBoxSettings: ChatBoxSettings;
  setChatBoxSettings: Dispatch<SetStateAction<ChatBoxSettings>>;
  mainContentRef?: React.RefObject<HTMLDivElement>;
  showScrollButton?: boolean;
  onScrollToBottom?: () => void;
  toastOptions?: object;
  sidebarOpen?: boolean;
  workspaceRail?: ReactNode;
}

export default function ResearchPageLayout({
  children,
  loading,
  isStopped,
  showResult,
  onStop,
  onNewResearch,
  chatBoxSettings,
  setChatBoxSettings,
  mainContentRef,
  showScrollButton = false,
  onScrollToBottom,
  toastOptions = {},
  sidebarOpen = true,
  workspaceRail
}: ResearchPageLayoutProps) {
  const defaultRef = useRef<HTMLDivElement>(null);
  const contentRef = mainContentRef || defaultRef;

  return (
    <main className="flex min-h-screen flex-col bg-[oklch(12%_0.012_255)] text-white">
      <Toaster 
        position="bottom-center" 
        toastOptions={toastOptions}
      />
      
      <Header 
        loading={loading}
        isStopped={isStopped}
        showResult={showResult}
        sidebarOpen={sidebarOpen}
        railOpen={Boolean(workspaceRail)}
        onStop={onStop || (() => {})}
        onNewResearch={onNewResearch}
        chatBoxSettings={chatBoxSettings}
        setChatBoxSettings={setChatBoxSettings}
      />
      
      <div 
        ref={contentRef}
        className={`min-h-[100vh] pt-[72px] ${workspaceRail ? (sidebarOpen ? 'lg:pl-[268px]' : 'lg:pl-[64px]') : ''}`}
      >
        {children}
      </div>

      {workspaceRail}
      
      {showScrollButton && showResult && (
        <button
          onClick={onScrollToBottom}
          className="fixed bottom-8 right-8 z-50 flex h-12 w-12 items-center justify-center rounded-full border border-white/90 bg-white/80 text-slate-600 shadow-[0_10px_30px_rgba(15,23,42,0.12)] backdrop-blur-xl transition hover:scale-105 hover:text-sky-700"
        >
          <svg 
            xmlns="http://www.w3.org/2000/svg" 
            className="h-6 w-6" 
            fill="none" 
            viewBox="0 0 24 24" 
            stroke="currentColor"
          >
            <path 
              strokeLinecap="round" 
              strokeLinejoin="round" 
              strokeWidth={2} 
              d="M19 14l-7 7m0 0l-7-7m7 7V3" 
            />
          </svg>
        </button>
      )}
      
      <Footer setChatBoxSettings={setChatBoxSettings} chatBoxSettings={chatBoxSettings} />
    </main>
  );
} 
