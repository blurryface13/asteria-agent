// /multi_agents/frontend/components/HumanFeedback.tsx

import React, { useState, useEffect } from "react";

interface HumanFeedbackProps {
  websocket: WebSocket | null;
  onFeedbackSubmit: (feedback: string | null) => void;
  questionForHuman: string | false;
}

const HumanFeedback: React.FC<HumanFeedbackProps> = ({
  questionForHuman,
  websocket,
  onFeedbackSubmit,
}) => {
  const [feedbackRequest, setFeedbackRequest] = useState<string | null>(null);
  const [userFeedback, setUserFeedback] = useState<string>("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onFeedbackSubmit(userFeedback === "" ? null : userFeedback);
    setFeedbackRequest(null);
    setUserFeedback("");
  };

  return (
    <div className="rounded-xl border border-white/20 bg-neutral-800 p-5 text-neutral-200">
      <h3 className="mb-3 text-base font-medium">确认研究计划</h3>
      <pre className="mb-4 max-h-72 overflow-auto whitespace-pre-wrap text-xs">
        {questionForHuman}
      </pre>
      <form onSubmit={handleSubmit}>
        <textarea
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
