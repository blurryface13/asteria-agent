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
  return <div className={`rounded-2xl border bg-white/75 shadow-[0_12px_38px_rgba(15,23,42,0.08)] backdrop-blur-xl transition-colors ${isFocused ? "border-sky-400 ring-4 ring-sky-500/10" : "border-slate-200"}`}>
    <form onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <textarea ref={textareaRef} rows={3} required value={promptValue} disabled={disabled} onChange={handleChange} onKeyDown={handleKeyDown} onFocus={() => setIsFocused(true)} onBlur={() => setIsFocused(false)} placeholder="What would you like to research today?" className="block min-h-[132px] w-full resize-none bg-transparent px-7 pt-6 text-[17px] leading-7 text-slate-800 outline-none placeholder:text-slate-400 disabled:cursor-wait" />
      <div className="flex justify-end px-5 pb-5">
        <button type="submit" disabled={disabled || !promptValue.trim()} className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition-colors hover:bg-sky-100 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60">{disabled ? <TypeAnimation /> : <span className="text-2xl leading-none">→</span>}</button>
      </div>
    </form>
  </div>;
};

export default InputArea;
