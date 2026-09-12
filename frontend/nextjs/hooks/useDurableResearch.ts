import { useCallback, useEffect, useRef } from 'react';
import { authFetch } from '@/helpers/auth';
import { Data, ChatBoxSettings } from '@/types/data';
import { getRetrieversForStrategy } from '@/utils/searchStrategy';

const terminal = new Set(['completed', 'failed', 'cancelled', 'interrupted']);
type Setter<T> = React.Dispatch<React.SetStateAction<T>>;
class RunRequestError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function request(path: string, body?: unknown) {
  const response = await authFetch(`/api/workspace/runs${path}`, body === undefined ? { cache: 'no-store' } : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new RunRequestError(data.detail || data.error || `运行服务错误 ${response.status}`, response.status);
  return data;
}

// The cursor belongs to this mounted view. A fresh view replays from zero;
// reconnection keeps the cursor. Neither case submits another research job.
export function useDurableResearch(
  setOrderedData: Setter<Data[]>, setAnswer: Setter<string>, setLoading: Setter<boolean>,
  setShowHumanFeedback: Setter<boolean>, setQuestionForHuman: Setter<string | false>,
  setIsStopped: Setter<boolean>,
) {
  const generation = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const active = useRef<{ id: string; cursor: number; approval: string | null } | null>(null);
  const detach = useCallback(() => {
    generation.current++;
    clearTimeout(timer.current);
    active.current = null;
  }, []);
  useEffect(() => detach, [detach]);

  const observe = useCallback((run: any) => {
    detach();
    const version = generation.current;
    const observation = { id: run.id, cursor: 0, approval: null as string | null };
    active.current = observation;
    setOrderedData([{ type: 'question', content: run.request.task } as Data]);
    setAnswer(''); setLoading(true); setIsStopped(false); setShowHumanFeedback(false);
    let connectionWarning = false;
    const poll = async () => {
      try {
        const batch = await request(`/${run.id}/events?after=${observation.cursor}`);
        if (generation.current !== version) return;
        for (const record of batch.events) {
          if (record.sequence <= observation.cursor) continue;
          const data = record.payload;
          if (data.type === 'human_feedback') {
            observation.approval = data.approval_id;
            setQuestionForHuman(data.output); setShowHumanFeedback(true);
          } else if (data.type === 'approval_resolved') {
            observation.approval = null; setShowHumanFeedback(false);
          } else if (data.type === 'run_state') {
            if (terminal.has(data.status)) {
              setLoading(false); setShowHumanFeedback(false);
              setIsStopped(data.status === 'cancelled');
              if (data.error) setOrderedData(prev => [...prev, { type: 'logs', content: 'error', output: data.error } as Data]);
            }
          } else if (data.type !== 'usage') {
            setOrderedData(prev => [...prev, { ...data, contentAndType: `${data.content}-${data.type}` }]);
            if (data.type === 'report') setAnswer(prev => prev + data.output);
            if (data.type === 'report_complete') setAnswer(data.output);
            if (data.content === 'research_report') setAnswer(typeof data.output === 'string' ? data.output : data.output?.report || '');
          }
          observation.cursor = record.sequence;
        }
        const current = await request(`/${run.id}`);
        if (generation.current !== version) return;
        connectionWarning = false;
        if (terminal.has(current.status) && observation.cursor >= current.sequence) {
          window.dispatchEvent(new Event('asteria:workspace-changed'));
          window.dispatchEvent(new Event('asteria:reports-changed'));
          return;
        }
        timer.current = setTimeout(poll, batch.events.length === 200 ? 0 : 1000);
      } catch (error) {
        if (generation.current !== version) return;
        if (error instanceof RunRequestError && [401, 403, 404].includes(error.status)) {
          setLoading(false); setShowHumanFeedback(false);
          setOrderedData(prev => [...prev, { type: 'logs', content: 'connection_warning', output: `无法继续查看任务：${error.message}。后台任务不会因此取消。` } as Data]);
          return;
        }
        if (!connectionWarning) {
          setOrderedData(prev => [...prev, { type: 'logs', content: 'connection_warning', output: '连接暂时中断，正在恢复进度；不会重新提交研究任务。' } as Data]);
          connectionWarning = true;
        }
        timer.current = setTimeout(poll, 3000);
      }
    };
    void poll();
  }, [detach, setAnswer, setIsStopped, setLoading, setOrderedData, setQuestionForHuman, setShowHumanFeedback]);

  const restore = useCallback(async (conversationId: string) => {
    detach();
    const version = generation.current;
    const result = await request(`/latest?conversation_id=${encodeURIComponent(conversationId)}`);
    if (generation.current !== version) return false;
    if (!result.run) return false;
    observe(result.run);
    return true;
  }, [detach, observe]);

  const start = useCallback(async (task: string, settings: ChatBoxSettings, conversationId: string) => {
    detach();
    const version = generation.current;
    const domains = JSON.parse(localStorage.getItem('domainFilters') || '[]').map((item: any) => item.value);
    const submission = {
      request_id: crypto.randomUUID(), conversation_id: conversationId,
      request: { task, report_type: settings.report_type, report_source: settings.report_source, tone: settings.tone,
        headers: { retrievers: getRetrieversForStrategy(settings.search_strategy, settings.retrievers) },
        search_strategy: settings.search_strategy || 'general', online_rag: settings.online_rag !== false,
        skill_ids: settings.skill_ids || [], format_profile: settings.format_profile || null,
        query_domains: domains, mcp_enabled: settings.mcp_enabled || false,
        mcp_strategy: settings.mcp_strategy || 'fast', mcp_configs: settings.mcp_configs || [] },
    };
    // A request identity is created once; transport retry never creates a new job.
    let run;
    try { run = await request('', submission); }
    catch (error) {
      if (!(error instanceof TypeError)) throw error;
      run = await request('', submission);
    }
    if (generation.current === version) observe(run);
  }, [detach, observe]);

  const cancel = async () => {
    if (!active.current) throw new Error('当前没有可取消的后台任务');
    await request(`/${active.current.id}/cancel`, {});
  };
  const feedback = async (content: string | null) => {
    const run = active.current;
    if (!run?.approval) throw new Error('当前没有待确认的计划');
    await request(`/${run.id}/approvals/${run.approval}`, { content });
    setShowHumanFeedback(false);
  };
  return { start, restore, detach, cancel, feedback };
}
