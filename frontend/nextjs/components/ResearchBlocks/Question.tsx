import React from 'react';
import Image from "next/image";

interface QuestionProps {
  question: string;
}

const Question: React.FC<QuestionProps> = ({ question }) => {
  return (
    <div className="container mt-5 mb-5 flex w-full flex-col items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.04] px-4 py-4 pt-5 backdrop-blur-sm sm:flex-row sm:px-6">
      <div className="flex items-center gap-2 sm:gap-4">
        <img
          src={"/img/message-question-circle.svg"}
          alt="message"
          width={24}
          height={24}
          className="w-6 h-6"
        />
        {/*<p className="font-bold uppercase leading-[152%] text-teal-200">
          Research Task:
        </p>*/}
      </div>
      <div className="log-message mt-1 max-w-full grow break-words font-medium text-white/80 sm:mt-0">{question}</div>
    </div>
  );
};

export default Question;
