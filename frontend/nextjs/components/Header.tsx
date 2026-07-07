import React from 'react';
import Image from "next/image";

interface HeaderProps {
  loading?: boolean;      // Indicates if research is currently in progress
  isStopped?: boolean;    // Indicates if research was manually stopped
  showResult?: boolean;   // Controls if research results are being displayed
  onStop?: () => void;    // Handler for stopping ongoing research
  onNewResearch?: () => void;  // Handler for starting fresh research
  isCopilotMode?: boolean; // Indicates if we are in copilot mode
}

const Header = ({ loading, isStopped, showResult, onStop, onNewResearch, isCopilotMode }: HeaderProps) => {
  return (
    <div className="fixed top-0 left-0 right-0 z-50">
      {/* Pure transparent blur background */}
      <div className="absolute inset-0 backdrop-blur-sm bg-transparent"></div>
      
      {/* Header container */}
      <div className="container relative h-[60px] px-4 lg:h-[80px] lg:px-0 pt-4 pb-4">
        {/* Knowledge Hub entry - top right */}
        <a
          href="/knowledge"
          className="absolute right-4 top-4 flex items-center gap-1.5 rounded-full border border-gray-200 bg-white/80 px-3 py-1.5 text-sm text-gray-600 shadow-sm hover:bg-gray-50 hover:text-teal-700 transition-colors"
          title="文献知识库问答"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
          </svg>
          <span className="hidden sm:inline">知识库</span>
        </a>

        <div className="flex flex-col items-center">
          {/* Logo/Home link */}
          <a href="/">
            <img
              src="/img/asteria-logo.png?v=bunny1"
              alt="logo"
              width={60}
              height={60}
              className="lg:h-16 lg:w-16"
            />
          </a>
          
          {/* Action buttons container */}
          <div className="flex gap-2 mt-2 transition-all duration-300 ease-in-out">
            {/* Stop button - shown only during active research */}
            {loading && !isStopped && (
              <button
                onClick={onStop}
                className="flex items-center justify-center px-4 sm:px-6 h-9 sm:h-10 text-sm text-gray-900 bg-red-500 rounded-full hover:bg-red-600 transform hover:scale-105 transition-all duration-200 shadow-lg whitespace-nowrap min-w-[80px]"
              >
                Stop
              </button>
            )}
            {/* New Research button - shown after stopping or completing research - but not in copilot mode */}
            {(isStopped || !loading) && showResult && !isCopilotMode && (
              <button
                onClick={onNewResearch}
                className="flex items-center justify-center px-4 sm:px-6 h-9 sm:h-10 text-sm text-white bg-teal-500 rounded-full hover:bg-teal-600 transform hover:scale-105 transition-all duration-200 shadow-lg whitespace-nowrap min-w-[120px]"
              >
                New Research
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Header;
