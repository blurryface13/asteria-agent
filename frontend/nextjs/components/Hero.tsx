"use client";

import React, { FC } from "react";
import InputArea from "./ResearchBlocks/elements/InputArea";
import { ChatBoxSettings, SearchStrategy } from "@/types/data";

type HeroProps = {
  promptValue: string;
  setPromptValue: React.Dispatch<React.SetStateAction<string>>;
  handleDisplayResult: (query: string) => void;
  chatBoxSettings?: ChatBoxSettings;
  setChatBoxSettings?: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
};

const suggestions = [
  { id: "literature", name: "梳理文献综述", description: "从研究主题、关键论文到方法脉络，形成带引用的综述。", prompt: "请帮我梳理一份关于：的文献综述", icon: "⌕" },
  { id: "compare", name: "对比最新研究", description: "比较不同方法的核心思路、实验设置与局限。", prompt: "请对比最近关于：的代表性研究", icon: "↔" },
  { id: "roadmap", name: "制定研究路线", description: "把一个问题拆成可执行的学习、复现与实验计划。", prompt: "请为：制定一份研究与实验路线", icon: "↗" },
];

const strategies: { value: SearchStrategy; label: string }[] = [
  { value: "general", label: "全网检索" },
  { value: "academic", label: "学术优先" },
  { value: "hybrid", label: "混合检索" },
];

const Hero: FC<HeroProps> = ({ promptValue, setPromptValue, handleDisplayResult, chatBoxSettings, setChatBoxSettings }) => {
  const handleSelectStrategy = (strategy: SearchStrategy) => {
    if (!chatBoxSettings || !setChatBoxSettings) return;
    const nextSettings = { ...chatBoxSettings, search_strategy: strategy };
    setChatBoxSettings(nextSettings);
    if (typeof window !== "undefined") localStorage.setItem("chatBoxSettings", JSON.stringify(nextSettings));
  };

  return (
    <section className="research-home relative mx-auto flex min-h-[calc(100vh-120px)] w-full max-w-[1120px] flex-col px-5 pb-16 pt-10 sm:px-8 lg:px-12 lg:pt-16">
      <div className="mx-auto w-full max-w-[820px]">
        <div className="mb-8 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">
          <span className="h-2 w-2 rounded-full bg-teal-500" />
          Research workspace
        </div>
        <h1 className="max-w-[680px] text-4xl font-semibold tracking-[-0.04em] text-slate-950 sm:text-5xl">你想研究什么？</h1>
        <p className="mt-4 max-w-[660px] text-base leading-7 text-slate-500 sm:text-lg">直接描述目标、问题或想验证的假设。系统会根据任务意图组织检索、工具调用与报告生成。</p>

        <div className="mt-9">
          <InputArea promptValue={promptValue} setPromptValue={setPromptValue} handleSubmit={handleDisplayResult} />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 px-1 text-xs text-slate-400">
            <span>Enter 开始研究，Shift + Enter 换行</span>
            <div className="flex items-center gap-1.5" aria-label="检索范围">
              {strategies.map((strategy) => {
                const active = (chatBoxSettings?.search_strategy || "general") === strategy.value;
                return <button key={strategy.value} type="button" onClick={() => handleSelectStrategy(strategy.value)} className={`rounded-md px-2.5 py-1 transition-colors ${active ? "bg-teal-50 font-medium text-teal-700" : "text-slate-400 hover:bg-slate-100 hover:text-slate-600"}`}>{strategy.label}</button>;
              })}
            </div>
          </div>
        </div>

        <div className="mt-16">
          <div className="mb-4 flex items-center justify-between"><h2 className="text-sm font-semibold text-slate-800">从一个方向开始</h2><span className="text-xs text-slate-400">示例会填入输入框</span></div>
          <div className="grid gap-3 md:grid-cols-3">
            {suggestions.map((item) => <button key={item.id} type="button" onClick={() => setPromptValue(item.prompt)} className="group min-h-[154px] rounded-xl border border-slate-200 bg-white p-5 text-left shadow-[0_1px_2px_rgba(15,23,42,0.03)] transition-all duration-200 hover:-translate-y-0.5 hover:border-teal-300 hover:shadow-[0_12px_28px_rgba(15,23,42,0.08)]"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 font-mono text-lg text-slate-500 transition-colors group-hover:bg-teal-50 group-hover:text-teal-700">{item.icon}</span><span className="mt-5 block text-sm font-semibold text-slate-900">{item.name}</span><span className="mt-2 block text-xs leading-5 text-slate-500">{item.description}</span></button>)}
          </div>
        </div>
      </div>
    </section>
  );
};

export default Hero;
