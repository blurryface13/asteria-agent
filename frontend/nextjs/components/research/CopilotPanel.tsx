import React, { Dispatch, SetStateAction, useEffect, useRef } from 'react';
import ChatInput from '@/components/ResearchBlocks/elements/ChatInput';
import LoadingDots from '@/components/LoadingDots';
import { Data } from '@/types/data';
import Question from '@/components/ResearchBlocks/Question';
import ChatResponse from '@/components/ResearchBlocks/ChatResponse';
import Image from 'next/image';

interface CopilotPanelProps {
  question: string;
  chatPromptValue: string;
  setChatPromptValue: Dispatch<SetStateAction<string>>;
  handleChat: (message: string) => void;
  orderedData: Data[];
  loading: boolean;
  isProcessingChat: boolean;
  isStopped: boolean;
  bottomRef: React.RefObject<HTMLDivElement>;
  isCopilotVisible?: boolean;
  setIsCopilotVisible?: Dispatch<SetStateAction<boolean>>;
}

const CopilotPanel: React.FC<CopilotPanelProps> = ({
  question,
  chatPromptValue,
  setChatPromptValue,
  handleChat,
  orderedData,
  loading,
  isProcessingChat,
  isStopped,
  bottomRef,
  isCopilotVisible,
  setIsCopilotVisible
}) => {
  // Filter to only get chat messages (questions and responses) after the initial question
  const chatMessages = orderedData.filter((data, index) => {
    // Include all questions except the first one
    if (data.type === 'question') {
      return index > 0;
    }
    // Include all chat responses
    return data.type === 'chat';
  });

  // Reference to the chat container
  const chatContainerRef = useRef<HTMLDivElement>(null);
  
  // Function to scroll to bottom
  const scrollToBottom = () => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  };

  // Scroll when messages change or loading/processing state changes
  useEffect(() => {
    scrollToBottom();
  }, [chatMessages.length, loading, isProcessingChat]);

  // Also handle mutations in the DOM that might affect scroll height
  useEffect(() => {
    if (!chatContainerRef.current) return;
    
    const observer = new MutationObserver(scrollToBottom);
    
    observer.observe(chatContainerRef.current, {
      childList: true,
      subtree: true,
      characterData: true
    });
    
    return () => observer.disconnect();
  }, []);

  return (
    <>
      {/* Panel Header */}
      <div className="flex items-center justify-between border-b border-white/[0.08] bg-white/[0.035] px-4 py-3 backdrop-blur-xl">
        {/* Left side */}
        <div className="flex items-center">
          <a href="/" className="mr-3">
            <img
              src="/img/asteria-logo.png?v=bunny1"
              alt="logo"
              width={32}
              height={32}
              className="rounded-md"
            />
          </a>
          <h2 className="text-base font-semibold tracking-[-0.02em] text-white/80">
            Report chat
          </h2>
        </div>
        
        {/* Right side */}
        <div className="flex items-center gap-3">
          {/* Connection status indicator */}
          <div className="flex items-center">
            <div className={`w-1.5 h-1.5 rounded-full ${loading || isProcessingChat ? 'bg-amber-500 animate-pulse' : 'bg-teal-500'} mr-2`}></div>
            <span className="text-xs text-white/35">{loading ? 'researching' : isProcessingChat ? 'thinking' : 'active'}</span>
          </div>
          
          {/* Toggle button */}
          {setIsCopilotVisible && (
            <button 
              onClick={(e) => {
                e.preventDefault();
                setIsCopilotVisible(false);
              }}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-transparent text-slate-500 transition-colors hover:border-slate-200 hover:bg-white hover:text-slate-700"
              aria-label="Hide copilot panel"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Chat Messages - Scrollable */}
      <div 
        ref={chatContainerRef} 
        className="flex-1 overflow-y-auto bg-transparent px-3 py-3 custom-scrollbar"
      >
        {/* Status message - conditional on research state */}
        <div className="mb-4">
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.04] p-3">
            <div className="flex items-start gap-3">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-white/[0.08] bg-white/[0.06] text-white/55">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                </svg>
              </div>
              <div className="text-sm text-white/55">
                {loading ? (
                  <p>Working on the report. Questions become available after the report is complete.</p>
                ) : (
                  <p>I can answer questions about this report and its cited findings.</p>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Chat messages */}
        <div className="space-y-4">
          {chatMessages.map((data, index) => {
            if (data.type === 'question') {
              return (
                <div key={`chat-question-${index}`}>
                  <Question question={data.content} />
                </div>
              );
            } else if (data.type === 'chat') {
              return (
                <div key={`chat-answer-${index}`}>
                  <ChatResponse answer={data.content} metadata={data.metadata} />
                </div>
              );
            }
            return null;
          })}
        </div>

        {/* Loading indicator - always show during research or processing */}
        {(loading || isProcessingChat) && (
          <div className="flex justify-center">
            <div className="flex flex-col items-center">
              <LoadingDots />
            </div>
          </div>
        )}

        {/* Invisible element for scrolling */}
        <div ref={bottomRef} />
      </div>

      {/* Chat Input */}
      <div className="border-t border-white/[0.08] bg-white/[0.035] px-3 py-3 backdrop-blur-xl">
        {!isStopped && (
          <ChatInput
            promptValue={chatPromptValue}
            setPromptValue={setChatPromptValue}
            handleSubmit={handleChat}
            disabled={loading || isProcessingChat}
            placeholder="Ask about this report..."
          />
        )}
        {isStopped && (
          <div className="text-center p-2 text-gray-500 bg-gray-50/40 rounded-md border border-gray-200/40 text-sm">
            Research has been stopped. Start a new research to continue chatting.
          </div>
        )}
      </div>

      {/* Custom scrollbar styles */}
      <style jsx global>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        
        .animate-pulse {
          animation: pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }
        
        .custom-scrollbar::-webkit-scrollbar {
          width: 4px;
        }
        
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(17, 24, 39, 0.1);
        }
        
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(75, 85, 99, 0.5);
          border-radius: 20px;
        }
        
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(75, 85, 99, 0.7);
        }
      `}</style>
    </>
  );
};

export default CopilotPanel;
