import React, { FC, useEffect, useRef, useState } from "react";
import TypeAnimation from "../../TypeAnimation";

type InputAreaProps = {
  promptValue: string;
  setPromptValue: React.Dispatch<React.SetStateAction<string>>;
  handleSubmit: (query: string) => void;
  handleSecondary?: (query: string) => void;
  disabled?: boolean;
  reset?: () => void;
  isStopped?: boolean;
};

const InputArea: FC<InputAreaProps> = ({ promptValue, setPromptValue, handleSubmit, disabled, reset, isStopped }) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isFocused, setIsFocused] = useState(false);

  useEffect(() => { textareaRef.current?.focus(); }, []);

  const resetHeight = () => { if (textareaRef.current) textareaRef.current.style.height = "3em"; };
  const submit = () => { if (disabled || !promptValue.trim()) return; reset?.(); handleSubmit(promptValue.trim()); setPromptValue(""); resetHeight(); };
  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); submit(); } };
  const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => { const target = event.target; target.style.height = "auto"; target.style.height = `${target.scrollHeight}px`; setPromptValue(target.value); };

  if (isStopped) return null;
  return <div className={`rounded-xl border bg-white shadow-[0_8px_30px_rgba(15,23,42,0.06)] transition-colors ${isFocused ? "border-teal-400 ring-4 ring-teal-500/10" : "border-slate-300"}`}>
    <form onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <textarea ref={textareaRef} rows={3} required value={promptValue} disabled={disabled} onChange={handleChange} onKeyDown={handleKeyDown} onFocus={() => setIsFocused(true)} onBlur={() => setIsFocused(false)} placeholder="描述你的研究目标、问题或想验证的假设..." className="block min-h-[104px] w-full resize-none bg-transparent px-5 pt-4 text-[15px] leading-6 text-slate-800 outline-none placeholder:text-slate-400 disabled:cursor-wait" />
      <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3">
        <span className="text-xs text-slate-400">Asteria 会组织检索、分析与报告生成</span>
        <button type="submit" disabled={disabled || !promptValue.trim()} className="flex h-9 w-9 items-center justify-center rounded-lg bg-teal-600 text-white transition-colors hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-slate-200">{disabled ? <TypeAnimation /> : <span className="text-lg leading-none">↑</span>}</button>
      </div>
    </form>
  </div>;
};

export default InputArea;
