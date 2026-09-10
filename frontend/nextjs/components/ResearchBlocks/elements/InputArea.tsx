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
  allowEmptySubmit?: boolean;
};

const InputArea: FC<InputAreaProps> = ({ promptValue, setPromptValue, handleSubmit, disabled, reset, isStopped, allowEmptySubmit = false }) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isFocused, setIsFocused] = useState(false);

  useEffect(() => { textareaRef.current?.focus(); }, []);

  const resetHeight = () => { if (textareaRef.current) textareaRef.current.style.height = "3em"; };
  const submit = () => { if (disabled || (!allowEmptySubmit && !promptValue.trim())) return; reset?.(); handleSubmit(promptValue.trim()); setPromptValue(""); resetHeight(); };
  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); submit(); } };
  const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => { const target = event.target; target.style.height = "auto"; target.style.height = `${target.scrollHeight}px`; setPromptValue(target.value); };

  if (isStopped) return null;
  return <div className={`rounded-2xl border bg-[oklch(19%_0.016_255_/_0.92)] shadow-[0_20px_60px_rgba(2,6,23,0.28)] backdrop-blur-2xl transition-colors ${isFocused ? "border-sky-300/70 ring-4 ring-sky-300/10" : "border-white/[0.12]"}`}>
    <form onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <textarea ref={textareaRef} rows={3} required={!allowEmptySubmit} value={promptValue} disabled={disabled} onChange={handleChange} onKeyDown={handleKeyDown} onFocus={() => setIsFocused(true)} onBlur={() => setIsFocused(false)} placeholder="描述你的研究任务..." className="block min-h-[132px] w-full resize-none bg-transparent px-7 pt-6 text-[17px] leading-7 text-white/85 outline-none placeholder:text-white/30 disabled:cursor-wait" />
      <div className="flex items-center justify-between px-5 pb-5">
        <div className="flex items-center gap-2 text-xs text-white/35"><span className="rounded-lg border border-white/[0.10] bg-white/[0.04] px-2 py-1">本地工作区</span><span>·</span><span>自动分配</span><span>·</span><span>Research</span></div>
        <button type="submit" disabled={disabled || (!allowEmptySubmit && !promptValue.trim())} aria-label="进入研究工作区" className="flex h-11 w-11 items-center justify-center rounded-full bg-white/[0.08] text-white/55 transition-colors hover:bg-[oklch(72%_0.15_55)] hover:text-[oklch(18%_0.02_55)] disabled:cursor-not-allowed disabled:opacity-60">{disabled ? <TypeAnimation /> : <span className="text-2xl leading-none">↑</span>}</button>
      </div>
    </form>
  </div>;
};

export default InputArea;
