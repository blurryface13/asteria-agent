import React, { useRef } from "react";
import { Toaster } from "react-hot-toast";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import { ChatBoxSettings } from "@/types/data";

interface CopilotLayoutProps {
  children: React.ReactNode;
  loading: boolean;
  isStopped: boolean;
  showResult: boolean;
  onStop?: () => void;
  onNewResearch?: () => void;
  chatBoxSettings: ChatBoxSettings;
  setChatBoxSettings: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
  mainContentRef?: React.RefObject<HTMLDivElement>;
  toastOptions?: Record<string, any>;
  toggleSidebar?: () => void;
  sidebarOpen?: boolean;
  workspaceRail?: React.ReactNode;
}

export default function CopilotLayout({
  children,
  loading,
  isStopped,
  showResult,
  onStop,
  onNewResearch,
  chatBoxSettings,
  setChatBoxSettings,
  mainContentRef,
  toastOptions = {},
  toggleSidebar,
  sidebarOpen = true,
  workspaceRail
}: CopilotLayoutProps) {
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
        isCopilotMode={true}
        chatBoxSettings={chatBoxSettings}
        setChatBoxSettings={setChatBoxSettings}
      />
      
      <div 
        ref={contentRef}
        className={`flex-1 flex flex-col pt-[72px] ${workspaceRail ? (sidebarOpen ? 'lg:pl-[296px]' : 'lg:pl-[68px]') : ''}`}
      >
        {children}
      </div>

      {workspaceRail}
      
      <div className="relative z-10">
        <Footer setChatBoxSettings={setChatBoxSettings} chatBoxSettings={chatBoxSettings} />
      </div>
    </main>
  );
} 
