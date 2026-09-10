"use client";

import React, { FC } from "react";
import { format } from "date-fns";
import InputArea from "./ResearchBlocks/elements/InputArea";
import { ChatBoxSettings, ResearchHistoryItem } from "@/types/data";

type HeroProps = {
  promptValue: string;
  setPromptValue: React.Dispatch<React.SetStateAction<string>>;
  handleDisplayResult: (query: string) => void;
  history?: ResearchHistoryItem[];
  chatBoxSettings?: ChatBoxSettings;
  setChatBoxSettings?: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
};

const Hero: FC<HeroProps> = ({
  promptValue,
  setPromptValue,
  handleDisplayResult,
  history = [],
}) => {
  const recentHistory = history.slice(0, 4);

  const formatTimestamp = (timestamp: number | string | Date | undefined) => {
    if (!timestamp) return "未记录时间";
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime()) ? "未记录时间" : format(date, "yyyy/M/d HH:mm");
  };

  return (
    <section className="min-h-[calc(100vh-72px)] w-full bg-[oklch(99.2%_0.003_250)] px-5 pb-16 pt-16 sm:px-8 sm:pt-20">
      <div className="mx-auto flex w-full max-w-[1120px] flex-col items-center">
        <img
          src="/img/asteria-logo.png"
          alt="Bunny Research"
          width={72}
          height={72}
          className="h-[72px] w-[72px] object-contain"
        />

        <p className="mt-7 text-center text-[clamp(1.05rem,2vw,1.35rem)] font-medium tracking-[-0.02em] text-slate-500">
          Say Hello to Bunny Research, your AI partner for instant insights and comprehensive research
        </p>

        <div className="mt-10 w-full max-w-[960px]">
          <InputArea
            promptValue={promptValue}
            setPromptValue={setPromptValue}
            handleSubmit={handleDisplayResult}
          />
          <p className="mt-4 text-center text-sm text-slate-500">
            Enter any research topic or specific question
          </p>
        </div>

        {recentHistory.length > 0 && (
          <section className="mt-20 w-full" aria-labelledby="recent-research-heading">
            <h2 id="recent-research-heading" className="mb-5 text-2xl font-semibold tracking-[-0.03em] text-slate-700">
              Recent Research
            </h2>
            <div className="divide-y divide-slate-200/80 rounded-2xl border border-slate-200/70 bg-white/65 shadow-[0_10px_35px_rgba(15,23,42,0.035)] backdrop-blur-xl">
              {recentHistory.map((item) => (
                <a
                  key={item.id}
                  href={`/research/${item.id}`}
                  className="block px-6 py-5 transition-colors first:rounded-t-2xl last:rounded-b-2xl hover:bg-white/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/60"
                >
                  <p className="truncate text-lg font-medium text-slate-700">{item.question}</p>
                  <p className="mt-1 text-sm text-slate-500">{formatTimestamp(item.timestamp)}</p>
                </a>
              ))}
            </div>
          </section>
        )}
      </div>
    </section>
  );
};

export default Hero;
