"use client";

import React, { FC } from "react";
import { format } from "date-fns";
import InputArea from "./ResearchBlocks/elements/InputArea";
import { ChatBoxSettings, ResearchHistoryItem } from "@/types/data";

type HeroProps = {
  promptValue: string;
  setPromptValue: React.Dispatch<React.SetStateAction<string>>;
  handleDisplayResult: (query: string) => void;
  onEnterWorkspace?: () => void;
  history?: ResearchHistoryItem[];
  chatBoxSettings?: ChatBoxSettings;
  setChatBoxSettings?: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
};

const Hero: FC<HeroProps> = ({
  promptValue,
  setPromptValue,
  handleDisplayResult,
  onEnterWorkspace,
  history = [],
}) => {
  const recentHistory = history.slice(0, 4);

  const formatTimestamp = (timestamp: number | string | Date | undefined) => {
    if (!timestamp) return "未记录时间";
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime()) ? "未记录时间" : format(date, "yyyy/M/d HH:mm");
  };

  return (
    <section className="relative min-h-[calc(100vh-72px)] w-full overflow-hidden bg-[oklch(12%_0.012_255)] px-5 pb-16 pt-16 text-white sm:px-8 sm:pt-20">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_18%,oklch(28%_0.045_255_/_0.34),transparent_34%),radial-gradient(circle_at_85%_85%,oklch(32%_0.055_70_/_0.10),transparent_28%)]" />
      <div className="relative mx-auto flex w-full max-w-[1080px] flex-col items-center">
        <div className="mt-20 w-full max-w-[900px]">
          <InputArea
            promptValue={promptValue}
            setPromptValue={setPromptValue}
            handleSubmit={onEnterWorkspace ? (query) => query ? handleDisplayResult(query) : onEnterWorkspace() : handleDisplayResult}
            allowEmptySubmit={Boolean(onEnterWorkspace)}
          />
        </div>

        {recentHistory.length > 0 && (
          <section className="mt-16 w-full" aria-labelledby="recent-research-heading">
            <div className="mb-4 flex items-center justify-between"><h2 id="recent-research-heading" className="text-sm font-medium text-white/55">最近任务</h2><span className="text-xs text-white/30">{history.length} 条</span></div>
            <div className="divide-y divide-white/[0.07] overflow-hidden rounded-2xl border border-white/[0.08] bg-white/[0.035] backdrop-blur-xl">
              {recentHistory.map((item) => (
                <a
                  key={item.id}
                  href={`/research/${item.id}`}
                  className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-white/[0.06] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/60"
                >
                  <p className="truncate text-sm font-medium text-white/75">{item.question}</p>
                  <p className="shrink-0 text-xs text-white/30">{formatTimestamp(item.timestamp)}</p>
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
