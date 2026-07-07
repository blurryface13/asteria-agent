"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { getHost } from "@/helpers/getHost";
import { setAuth } from "@/helpers/auth";

type Step = "email" | "code";

export default function LoginPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const apiBase = getHost();

  const handleSendCode = async () => {
    if (!email.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${apiBase}/api/auth/send-code`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "发送失败");
      setInfo(data.message);
      setStep("code");
    } catch (e: any) {
      setError(e.message || "发送失败,请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async () => {
    if (!code.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${apiBase}/api/auth/verify-code`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "验证码错误");
      setAuth(data.access_token, data.email);
      router.push("/");
    } catch (e: any) {
      setError(e.message || "验证失败,请重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-white px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <img src="/img/asteria-logo.png?v=bunny1" alt="Asteria Agent" width={64} height={64} className="rounded-xl mb-3" />
          <h1 className="text-2xl font-bold text-gray-900">Asteria Agent</h1>
          <p className="text-sm text-gray-500 mt-1">组内专用,请用邮箱登录</p>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl shadow-lg p-6">
          {step === "email" ? (
            <>
              <label className="block text-sm font-medium text-gray-700 mb-2">邮箱地址</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500 transition-all"
                onKeyDown={(e) => e.key === "Enter" && handleSendCode()}
              />
              <button
                onClick={handleSendCode}
                disabled={loading || !email.trim()}
                className="w-full mt-4 px-4 py-2.5 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
              >
                {loading ? "发送中..." : "发送验证码"}
              </button>
            </>
          ) : (
            <>
              <p className="text-sm text-gray-500 mb-3">{info}</p>
              <label className="block text-sm font-medium text-gray-700 mb-2">验证码</label>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="6 位数字"
                className="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-gray-900 placeholder-gray-400 tracking-widest text-center text-lg focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500 transition-all"
                onKeyDown={(e) => e.key === "Enter" && handleVerify()}
              />
              <button
                onClick={handleVerify}
                disabled={loading || !code.trim()}
                className="w-full mt-4 px-4 py-2.5 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
              >
                {loading ? "验证中..." : "登录"}
              </button>
              <button
                onClick={() => { setStep("email"); setCode(""); setError(""); }}
                className="w-full mt-2 px-4 py-2 text-sm text-gray-500 hover:text-gray-700 transition-colors"
              >
                换个邮箱
              </button>
            </>
          )}

          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        </div>
      </div>
    </div>
  );
}
