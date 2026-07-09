import React, { FC, useEffect, useState, useRef } from "react";
import InputArea from "./ResearchBlocks/elements/InputArea";
import { motion, AnimatePresence } from "framer-motion";
import { ChatBoxSettings, SearchStrategy } from "@/types/data";

type THeroProps = {
  promptValue: string;
  setPromptValue: React.Dispatch<React.SetStateAction<string>>;
  handleDisplayResult: (query : string) => void;
  chatBoxSettings?: ChatBoxSettings;
  setChatBoxSettings?: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
};

const Hero: FC<THeroProps> = ({
  promptValue,
  setPromptValue,
  handleDisplayResult,
  chatBoxSettings,
  setChatBoxSettings,
}) => {
  const [isVisible, setIsVisible] = useState(false);
  const [showGradient, setShowGradient] = useState(true);
  const particlesContainerRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    setIsVisible(true);
    
    // Create particles for the background effect
    if (particlesContainerRef.current) {
      const container = particlesContainerRef.current;
      const particleCount = window.innerWidth < 768 ? 15 : 30; // Reduce particles on mobile
      
      // Clear any existing particles
      container.innerHTML = '';
      
      for (let i = 0; i < particleCount; i++) {
        const particle = document.createElement('div');
        
        // Random particle attributes
        const size = Math.random() * 4 + 1;
        const posX = Math.random() * 100;
        const posY = Math.random() * 100;
        const duration = Math.random() * 50 + 20;
        const delay = Math.random() * 5;
        const opacity = Math.random() * 0.3 + 0.1;
        
        // Apply styles
        particle.className = 'absolute rounded-full bg-white';
        Object.assign(particle.style, {
          width: `${size}px`,
          height: `${size}px`,
          left: `${posX}%`,
          top: `${posY}%`,
          opacity: opacity.toString(),
          animation: `float ${duration}s ease-in-out ${delay}s infinite`,
        });
        
        container.appendChild(particle);
      }
    }
    
    // Add scroll event listener to show/hide gradient
    let lastScrollY = window.scrollY;
    const threshold = 50; // Amount of scroll before hiding gradient (reduced for quicker response)
    
    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      
      if (currentScrollY <= threshold) {
        // At or near the top, show gradient
        setShowGradient(true);
      } else if (currentScrollY > lastScrollY) {
        // Scrolling down, hide gradient
        setShowGradient(false);
      } else if (currentScrollY < lastScrollY) {
        // Scrolling up, show gradient
        setShowGradient(true);
      }
      
      lastScrollY = currentScrollY;
    };
    
    window.addEventListener('scroll', handleScroll);
    
    const container = particlesContainerRef.current;
    // Clean up function
    return () => {
      if (container) {
        container.innerHTML = '';
      }
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  const handleClickSuggestion = (value: string) => {
    setPromptValue(value);
  };

  const handleSelectStrategy = (strategy: SearchStrategy) => {
    if (!chatBoxSettings || !setChatBoxSettings) return;

    const nextSettings = {
      ...chatBoxSettings,
      search_strategy: strategy
    };

    setChatBoxSettings(nextSettings);
    if (typeof window !== 'undefined') {
      localStorage.setItem('chatBoxSettings', JSON.stringify(nextSettings));
    }
  };

  // Animation variants for consistent animations
  const fadeInUp = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 }
  };

  return (
    <div className="relative overflow-visible min-h-[100vh] flex items-center pt-[60px] sm:pt-[80px] mt-[-60px] sm:mt-[-130px]">
      {/* Particle background */}
      <div ref={particlesContainerRef} className="absolute inset-0 -z-20"></div>
      
      <motion.div 
        initial="hidden"
        animate={isVisible ? "visible" : "hidden"}
        variants={fadeInUp}
        transition={{ duration: 0.8 }}
        className="flex flex-col items-center justify-center w-full py-6 sm:py-8 md:py-16 lg:pt-10 lg:pb-20"
      >
        {/* Header text */}
        <motion.h1 
          variants={fadeInUp}
          transition={{ duration: 0.8, delay: 0.1 }}
          className="text-2xl sm:text-3xl md:text-4xl font-semibold tracking-normal text-center text-gray-900 mb-8 sm:mb-10 md:mb-12 px-4"
        >
          What would you like to research next?
        </motion.h1>

        {/* Input section with enhanced styling */}
        <motion.div 
          variants={fadeInUp}
          transition={{ duration: 0.8, delay: 0.2 }}
          className="w-full max-w-[800px] pb-6 sm:pb-8 md:pb-10 px-4"
        >
          <div className="relative group">
            <div className="absolute -inset-1 bg-gradient-to-r from-teal-600/70 via-cyan-500/60 to-blue-600/70 rounded-xl blur-md opacity-60 group-hover:opacity-85 transition duration-1000 group-hover:duration-200 animate-gradient-x"></div>
            <div className="relative bg-white bg-opacity-20 backdrop-blur-sm rounded-xl ring-1 ring-gray-200/60">
              <InputArea
                promptValue={promptValue}
                setPromptValue={setPromptValue}
                handleSubmit={handleDisplayResult}
              />
            </div>
          </div>
          
          {/* Disclaimer text */}
          <motion.div
            variants={fadeInUp}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="mt-6 text-center px-4"
          >
            <p className="text-gray-500 text-sm font-light">
              Bunny Research may make mistakes. Verify important information and check sources.
            </p>
          </motion.div>
        </motion.div>

        <motion.div
          variants={fadeInUp}
          transition={{ duration: 0.7, delay: 0.35 }}
          className="mb-5 flex flex-wrap items-center justify-center gap-2 px-4"
          aria-label="Search strategy"
        >
          {strategies.map((strategy) => {
            const active = (chatBoxSettings?.search_strategy || 'general') === strategy.value;
            return (
              <button
                key={strategy.value}
                type="button"
                onClick={() => handleSelectStrategy(strategy.value)}
                className={`h-9 rounded-full border px-3 text-sm font-medium transition-all duration-200 ${
                  active
                    ? 'border-teal-200 bg-teal-50 text-teal-800 shadow-sm'
                    : 'border-gray-200 bg-white/75 text-gray-600 hover:border-gray-300 hover:bg-white'
                }`}
              >
                {strategy.label}
              </button>
            );
          })}
        </motion.div>

        {/* Suggestions section with enhanced styling */}
        <motion.div 
          variants={fadeInUp}
          transition={{ duration: 0.8, delay: 0.4 }}
          className="grid w-full max-w-3xl grid-cols-1 gap-3 px-4 pb-6 sm:grid-cols-3 sm:pb-8 md:pb-10"
        >
          <AnimatePresence>
            {suggestions.map((item, index) => (
              <motion.button
                key={item.id}
                type="button"
                variants={fadeInUp}
                initial="hidden"
                animate="visible"
                transition={{ duration: 0.4, delay: 0.6 + (index * 0.1) }}
                className="group flex min-h-[76px] cursor-pointer items-start gap-3 rounded-lg border border-gray-200 bg-white/78 p-4 text-left shadow-sm backdrop-blur-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-teal-200 hover:bg-white hover:shadow-md"
                onClick={() => handleClickSuggestion(item.prompt)}
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
              >
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-gray-200 bg-gray-50 text-gray-600 transition-colors group-hover:border-teal-100 group-hover:bg-teal-50 group-hover:text-teal-700">
                  {item.icon}
                </span>
                <span>
                  <span className="block text-sm font-semibold leading-5 text-gray-900">
                    {item.name}
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-gray-500">
                    {item.description}
                  </span>
                </span>
              </motion.button>
            ))}
          </AnimatePresence>
        </motion.div>
      </motion.div>

      {/* Magical premium gradient glow at the bottom */}
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: showGradient ? 1 : 0 }}
        transition={{ duration: 1.2 }}
        className="fixed bottom-0 left-0 right-0 h-[12px] z-50 overflow-hidden pointer-events-none"
      >
        <div className="relative w-full h-full">
          {/* Main perfect center glow with smooth fade at edges */}
          <div 
            className="absolute inset-0"
            style={{
              opacity: 0.85,
              background: 'radial-gradient(ellipse at center, rgba(12, 219, 182, 1) 0%, rgba(6, 219, 238, 0.7) 25%, rgba(6, 219, 238, 0.2) 50%, rgba(0, 0, 0, 0) 75%)',
              boxShadow: '0 0 30px 6px rgba(12, 219, 182, 0.5), 0 0 60px 10px rgba(6, 219, 238, 0.25)'
            }}
          />
          
          {/* Subtle shimmer overlay with perfect center focus */}
          <div 
            className="absolute inset-0"
            style={{
              animation: 'shimmer 8s ease-in-out infinite alternate',
              opacity: 0.5,
              background: 'radial-gradient(ellipse at center, rgba(255, 255, 255, 0.8) 0%, rgba(255, 255, 255, 0.2) 30%, rgba(255, 255, 255, 0) 60%)'
            }}
          />
          
          {/* Gentle breathing effect */}
          <div 
            className="absolute inset-0"
            style={{
              opacity: 0.4,
              animation: 'breathe 7s cubic-bezier(0.4, 0.0, 0.2, 1) infinite',
              background: 'radial-gradient(circle at center, rgba(255, 255, 255, 0.6) 0%, rgba(255, 255, 255, 0) 50%)'
            }}
          />
        </div>
      </motion.div>
      
      {/* Custom keyframes for magical animations */}
      <style jsx global>{`
        @keyframes shimmer {
          0% {
            opacity: 0.4;
            transform: scale(0.98);
          }
          50% {
            opacity: 0.6;
          }
          100% {
            opacity: 0.4;
            transform: scale(1.02);
          }
        }
        
        @keyframes breathe {
          0%, 100% {
            opacity: 0.3;
            transform: scale(0.96);
          }
          50% {
            opacity: 0.5;
            transform: scale(1.04);
          }
        }
      `}</style>
    </div>
  );
};

type suggestionType = {
  id: number;
  name: string;
  description: string;
  prompt: string;
  icon: React.ReactNode;
};

const suggestions: suggestionType[] = [
  {
    id: 1,
    name: "Map a literature review",
    description: "梳理主题、流派与关键论文",
    prompt: "帮我规划一个文献综述：",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
      </svg>
    ),
  },
  {
    id: 2,
    name: "Compare recent papers",
    description: "对比方法、实验与局限",
    prompt: "帮我对比最近几篇论文：",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18"></path>
        <path d="m19 9-5 5-4-4-3 3"></path>
      </svg>
    ),
  },
  {
    id: 3,
    name: "Build a research roadmap",
    description: "拆解学习路线与实践步骤",
    prompt: "帮我制定一个研究学习路线：",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 20h9"></path>
        <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"></path>
      </svg>
    ),
  },
];

const strategies: { value: SearchStrategy; label: string }[] = [
  { value: 'general', label: 'General Web' },
  { value: 'academic', label: 'Academic' },
  { value: 'hybrid', label: 'Hybrid' },
];

export default Hero;
