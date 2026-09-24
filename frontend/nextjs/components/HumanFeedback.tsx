// /multi_agents/frontend/components/HumanFeedback.tsx

import React, { useState } from "react";

interface HumanFeedbackProps {
  onFeedbackSubmit: (feedback: string | null) => void;
  questionForHuman: string | false;
}

interface ResearchPlan {
  scope: string;
  perspectives?: { name: string; query: string }[];
  required_goals?: { id: string; description: string }[];
}

function parseResearchPlan(question: string | false): ResearchPlan | null {
  if (!question) return null;
  const start = question.indexOf("{");
  if (start < 0) return null;
  try {
    const value: unknown = JSON.parse(question.slice(start));
    if (!value || typeof value !== "object" || !('scope' in value) || typeof value.scope !== 'string') return null;
    return value as ResearchPlan;
  } catch {
    return null;
  }
}

const HumanFeedback: React.FC<HumanFeedbackProps> = ({
  questionForHuman,
  onFeedbackSubmit,
}) => {
  const [userFeedback, setUserFeedback] = useState<string>("");
  const plan = parseResearchPlan(questionForHuman);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onFeedbackSubmit(userFeedback === "" ? null : userFeedback);
    setUserFeedback("");
  };

  return (
    <div className="min-w-0 rounded-xl border border-white/20 bg-neutral-800 p-5 text-neutral-200">
      <h3 className="mb-3 text-base font-medium">确认研究计划</h3>
      {plan ? (
        <div className="mb-4 space-y-3 text-sm leading-relaxed">
          <p className="text-neutral-400">请核对研究范围；如需调整，在下方填写修改意见。</p>
          <div>
            <p className="font-medium">研究范围</p>
            <p className="break-words text-neutral-300">{plan.scope}</p>
          </div>
          {Array.isArray(plan.perspectives) && plan.perspectives.length > 0 && (
            <div>
              <p className="font-medium">并行调研方向</p>
              <ul className="list-disc pl-5 text-neutral-300">
                {plan.perspectives.map((item, index) => <li key={index}>{item.name}</li>)}
              </ul>
            </div>
          )}
          {Array.isArray(plan.required_goals) && plan.required_goals.length > 0 && (
            <div>
              <p className="font-medium">交付重点</p>
              <ol className="list-decimal pl-5 text-neutral-300">
                {plan.required_goals.map((item, index) => <li key={item.id || index}>{item.description}</li>)}
              </ol>
            </div>
          )}
          <details className="rounded-lg border border-white/10 p-3">
            <summary className="cursor-pointer text-neutral-300">查看完整计划与检索细节</summary>
            <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs">{questionForHuman}</pre>
          </details>
        </div>
      ) : (
        <p className="mb-4 whitespace-pre-wrap break-words text-sm">{questionForHuman}</p>
      )}
      <form onSubmit={handleSubmit}>
        <textarea
          aria-label="研究计划修改意见"
          className="w-full rounded-lg border border-white/20 bg-neutral-900 p-3 text-neutral-200"
          value={userFeedback}
          onChange={(e) => setUserFeedback(e.target.value)}
          placeholder="填写修改意见，或留空确认计划"
        />
        <button
          type="submit"
          className="mt-3 rounded-full bg-neutral-200 px-4 py-2 text-sm text-neutral-900"
        >
          {userFeedback.trim() ? "提交修改意见" : "确认并继续"}
        </button>
      </form>
    </div>
  );
};

export default HumanFeedback;
