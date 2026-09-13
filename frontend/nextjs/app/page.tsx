"use client";

import { useRef, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useDurableResearch } from '@/hooks/useDurableResearch';
import { useResearchHistoryContext } from '@/hooks/ResearchHistoryContext';
import { useScrollHandler } from '@/hooks/useScrollHandler';
import { startLanggraphResearch } from '../components/Langgraph/Langgraph';
import findDifferences from '../helpers/findDifferences';
import { Data, ChatBoxSettings, QuestionData, ChatMessage, ChatData } from '../types/data';
import { preprocessOrderedData } from '../utils/dataProcessing';
import { toast } from "react-hot-toast";
import { v4 as uuidv4 } from 'uuid';

import HumanFeedback from "@/components/HumanFeedback";
import { authFetch } from "@/helpers/auth";
import { getRetrieversForStrategy } from "@/utils/searchStrategy";
import ResearchHarness from '@/components/harness/ResearchHarness';
import { ResearchResults } from '@/components/ResearchResults';

export default function Home() {
  const router = useRouter();
  const [promptValue, setPromptValue] = useState("");
  const [chatPromptValue, setChatPromptValue] = useState("");
  const [showResult, setShowResult] = useState(false);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [isInChatMode, setIsInChatMode] = useState(false);
  const [chatBoxSettings, setChatBoxSettings] = useState<ChatBoxSettings>(() => {
    // Default settings
    const defaultSettings = {
      report_type: "research_report",
      report_source: "web",
      search_strategy: "general",
      tone: "Objective",
      domains: [],
      defaultReportType: "research_report",
      layoutType: 'copilot',
      mcp_enabled: false,
      mcp_configs: [],
      mcp_strategy: "fast",
    };

    // Try to load all settings from localStorage
    if (typeof window !== 'undefined') {
      const savedSettings = localStorage.getItem('chatBoxSettings');
      if (savedSettings) {
        try {
          const parsedSettings = JSON.parse(savedSettings);
          return {
            ...defaultSettings,
            ...parsedSettings, // Override defaults with saved settings
            skill_ids: [],
            format_profile: null,
          };
        } catch (e) {
          console.error('Error parsing saved settings:', e);
        }
      }
    }
    return defaultSettings;
  });
  useEffect(() => {
    const selection = localStorage.getItem('asteria.knowledgeSelection');
    if (!selection) return;
    localStorage.removeItem('asteria.knowledgeSelection');
    try {
      const {knowledge_ids} = JSON.parse(selection);
      if (Array.isArray(knowledge_ids) && knowledge_ids.length > 0 && knowledge_ids.length <= 3 && knowledge_ids.every(id => typeof id === 'string')) {
        setChatBoxSettings(settings => ({...settings, knowledge_mode: 'selected', knowledge_ids}));
      }
    } catch { toast.error('资料选择未恢复，请重新选择知识库'); }
  }, []);
  const [question, setQuestion] = useState("");
  const [orderedData, setOrderedData] = useState<Data[]>([]);
  const [showHumanFeedback, setShowHumanFeedback] = useState(false);
  const [questionForHuman, setQuestionForHuman] = useState<string | false>(false);
  const [allLogs, setAllLogs] = useState<any[]>([]);
  const [isStopped, setIsStopped] = useState(false);
  const mainContentRef = useRef<HTMLDivElement>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [currentResearchId, setCurrentResearchId] = useState<string | null>(null);
  const pendingWorkspaceConversationId = useRef<string | null>(null);
  const durableConversation = useRef<string | null>(null);
  const selectionGeneration = useRef(0);
  const selectionRetry = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => () => { selectionGeneration.current++; clearTimeout(selectionRetry.current); }, []);
  const [isMobile, setIsMobile] = useState(false);
  const [isProcessingChat, setIsProcessingChat] = useState(false);

  // Use our custom scroll handler
  const { showScrollButton, scrollToBottom } = useScrollHandler(mainContentRef);

  // Check if we're on mobile
  useEffect(() => {
    const checkIfMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    
    // Initial check
    checkIfMobile();
    
    // Add event listener for window resize
    window.addEventListener('resize', checkIfMobile);
    
    // Cleanup
    return () => window.removeEventListener('resize', checkIfMobile);
  }, []);

  const { 
    history, 
    saveResearch, 
    updateResearch,
    getResearchById, 
    deleteResearch,
    addChatMessage,
    getChatMessages
  } = useResearchHistoryContext();

  // Observe durable runs without starting work until an explicit submission.
  const durableResearch = useDurableResearch(
    setOrderedData,
    setAnswer,
    setLoading,
    setShowHumanFeedback,
    setQuestionForHuman,
    setIsStopped
  );

  const handleFeedbackSubmit = async (feedback: string | null) => {
    try { await durableResearch.feedback(feedback); }
    catch (error) { toast.error(error instanceof Error ? error.message : '计划确认未保存'); }
  };

  const handleChat = async (message: string) => {
    const normalizedMessage = message.trim();
    if (!normalizedMessage) return;

    // Chat is a continuation of an existing report. Research creation has a
    // separate composer and must never be reached from this handler, including
    // on mobile. Previously the mobile branch forwarded an empty-context chat
    // to handleDisplayResult(), which made the Chat entry unexpectedly start a
    // new research task.
    if (!answer.trim()) {
      toast.error("请先完成一份研究报告；文献知识库问答请从知识库入口进入。", {
        duration: 3500,
        position: "bottom-center",
      });
      return;
    }
    
    setShowResult(true);
    setIsProcessingChat(true);
    setChatPromptValue("");
    
    // Create a user message
    const userMessage: ChatMessage = {
      role: 'user',
      content: normalizedMessage,
      timestamp: Date.now()
    };
    
    // Add question to display in research results immediately
    const questionData: QuestionData = { type: 'question', content: normalizedMessage };
    setOrderedData(prevOrder => [...prevOrder, questionData]);
    
    // Add user message to history asynchronously
    if (currentResearchId) {
      addChatMessage(currentResearchId, userMessage).catch(error => {
        console.error('Error adding chat message to history:', error);
      });
    }
    
    // Mobile implementation - simplified for chat only
    if (isMobile) {
      try {
        // Direct API call instead of websockets
        const response = await authFetch('/api/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            messages: [{ role: 'user', content: message }],
            report: answer || '',
          }),
        });
        
        if (!response.ok) {
          throw new Error(`API error: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.response && data.response.content) {
          // Add AI response to chat history asynchronously
          if (currentResearchId) {
            addChatMessage(currentResearchId, data.response).catch(error => {
              console.error('Error adding AI response to history:', error);
            });
            
            // Also update the research with the new messages
            const chatData: ChatData = { 
              type: 'chat', 
              content: data.response.content,
              metadata: data.response.metadata 
            };
            
            setOrderedData(prevOrder => [...prevOrder, chatData]);
            
            // Get current ordered data and add new messages
            const updatedOrderedData = [...orderedData, questionData, chatData];
            
            // Update research in history
            updateResearch(
              currentResearchId, 
              answer, 
              updatedOrderedData
            ).catch(error => {
              console.error('Error updating research:', error);
            });
          } else {
            // If no research ID, just update the UI
            setOrderedData(prevOrder => [...prevOrder, { 
              type: 'chat', 
              content: data.response.content,
              metadata: data.response.metadata
            } as ChatData]);
          }
        } else {
          // Show error message
          setOrderedData(prevOrder => [...prevOrder, { 
            type: 'chat', 
            content: 'Sorry, something went wrong. Please try again.' 
          } as ChatData]);
        }
      } catch (error) {
        console.error('Error during chat:', error);
        
        // Add error message
        setOrderedData(prevOrder => [...prevOrder, { 
          type: 'chat', 
          content: 'Sorry, there was an error processing your request. Please try again.' 
        } as ChatData]);
      } finally {
        setIsProcessingChat(false);
      }
      return;
    }
    
    // Desktop implementation (unchanged)
    try {
      // Fetch all chat messages for this research
      let chatMessages: { role: string; content: string }[] = [];
      
      if (currentResearchId) {
        // If we have a research ID, get all messages from history
        chatMessages = getChatMessages(currentResearchId);
      }
      
      // Format messages to ensure they only contain role and content properties
      const formattedMessages = [...chatMessages, userMessage].map(msg => ({
        role: msg.role,
        content: msg.content
      }));
      
      // Call the chat API
      const response = await authFetch(`/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          report: answer || "",
          messages: formattedMessages
        }),
      });
      
      if (!response.ok) {
        throw new Error(`Failed to get chat response: ${response.status}`);
      }
      
      const data = await response.json();
      
      if (data.response) {
        // Check if response contains valid content
        if (!data.response.content) {
          console.error('Response content is null or empty');
          // Show error message in results
          setOrderedData(prevOrder => [...prevOrder, { 
            type: 'chat', 
            content: 'I apologize, but I couldn\'t generate a proper response. Please try asking your question again.' 
          }]);
        } else {
          // Add AI response to chat history asynchronously
          if (currentResearchId) {
            addChatMessage(currentResearchId, data.response).catch(error => {
              console.error('Error adding AI response to history:', error);
            });
          }
          
          // Add response to display in research results
          setOrderedData(prevOrder => {
            return [...prevOrder, { 
              type: 'chat', 
              content: data.response.content,
              metadata: data.response.metadata
            }];
          });
        }
        
        // Explicitly enable chat mode after getting a response
        if (!isInChatMode) {
          setIsInChatMode(true);
        }
      } else {
        // Show error message
        setOrderedData(prevOrder => [...prevOrder, { 
          type: 'chat', 
          content: 'Sorry, something went wrong. Please try again.' 
        }]);
      }
    } catch (error) {
      console.error('Error during chat:', error);
      
      // Add error message to display
      setOrderedData(prevOrder => [...prevOrder, { 
        type: 'chat', 
        content: 'Sorry, there was an error processing your request. Please try again.' 
      }]);
    } finally {
      setLoading(false);
      setIsProcessingChat(false);
    }
  };

  const handleEnterWorkspace = () => {
    setShowResult(true);
    setSidebarOpen(true);
    setLoading(false);
    setIsStopped(false);
    setIsInChatMode(false);
    setQuestion("");
    setAnswer("");
    setOrderedData([]);
    setCurrentResearchId(null);
  };

  const prepareWorkspaceConversation = async (
    task: string,
    mode: 'research' | 'chat' = 'research',
    source = 'research-start',
  ) => {
    const id = uuidv4();
    const activeProjectId = typeof window !== 'undefined'
      ? window.localStorage.getItem('asteria.activeProjectId')
      : null;
    const endpoint = activeProjectId
      ? `/api/workspace/conversations?project_id=${encodeURIComponent(activeProjectId)}`
      : '/api/workspace/conversations';
    const response = await authFetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id,
        title: task.trim().slice(0, 255) || '新任务',
        mode,
        metadata: { source },
      }),
    });
    if (!response.ok) {
      throw new Error(`workspace conversation API error: ${response.status}`);
    }
    pendingWorkspaceConversationId.current = id;
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('asteria:workspace-changed'));
    }
    return id;
  };

  const coordinatorBusy = useRef(false);
  const [conversationMode, setConversationMode] = useState<'research' | 'chat'>('research');

  const coordinatorRequest = async (path: string, body?: unknown) => {
    const response = await authFetch('/api/coordinator' + path, body === undefined ? {cache: 'no-store'} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.error || `协调服务错误 ${response.status}`);
    return data;
  };

  const waitForTurn = async (id: string, initial: any, selection: number) => {
    let turn = initial;
    while (turn?.status === 'running') {
      await new Promise(resolve => setTimeout(resolve, 800));
      if (selection !== selectionGeneration.current) return null;
      turn = (await coordinatorRequest(`?conversation_id=${encodeURIComponent(id)}&request_id=${encodeURIComponent(turn.request_id)}`)).turn;
    }
    if (selection !== selectionGeneration.current) return null;
    if (!turn) throw new Error('未找到协调请求');
    if (turn.status !== 'completed') throw new Error(turn.error || '协调请求未完成');
    return turn.result;
  };

  const handleDisplayResult = async (rawQuestion: string, continueConversation = false) => {
    const newQuestion = rawQuestion.trim();
    if (!newQuestion || coordinatorBusy.current || loading) return;
    coordinatorBusy.current = true;
    setIsProcessingChat(true);
    const selection = ++selectionGeneration.current;
    clearTimeout(selectionRetry.current);
    durableResearch.detach();
    setShowHumanFeedback(false);
    try {
      const id = continueConversation && currentResearchId
        ? currentResearchId : await prepareWorkspaceConversation(newQuestion, 'chat', 'coordinator');
      if (selection !== selectionGeneration.current) return;
      setCurrentResearchId(id);
      linkedConversation.current = id;
      window.history.replaceState(null, '', `/?conversation=${encodeURIComponent(id)}`);
      setShowResult(true);
      if (!continueConversation) {
        setQuestion(newQuestion); setAnswer(''); setOrderedData([]);
        setConversationMode('chat'); durableConversation.current = null;
      }
      setOrderedData(prev => [...prev, {type: 'question', content: newQuestion}]);
      setPromptValue(''); setChatPromptValue('');
      const retrievers = getRetrieversForStrategy(chatBoxSettings.search_strategy, chatBoxSettings.retrievers);
      const domains = JSON.parse(localStorage.getItem('domainFilters') || '[]').map((item: any) => item.value);
      const langgraphHost = JSON.parse(localStorage.getItem('apiVariables') || '{}').LANGGRAPH_HOST_URL;
      const externalResearch = chatBoxSettings.report_type === 'multi_agents' && Boolean(langgraphHost);
      const body = {
        request_id: uuidv4(), conversation_id: id, message: newQuestion,
        knowledge_mode: chatBoxSettings.knowledge_mode || 'auto',
        knowledge_ids: chatBoxSettings.knowledge_ids || [],
        research_request: externalResearch ? null : {
          task: newQuestion, report_type: chatBoxSettings.report_type,
          report_source: chatBoxSettings.report_source, tone: chatBoxSettings.tone,
          headers: {retrievers}, search_strategy: chatBoxSettings.search_strategy || 'general',
          online_rag: chatBoxSettings.online_rag !== false, skill_ids: chatBoxSettings.skill_ids || [],
          format_profile: chatBoxSettings.format_profile || null, query_domains: domains,
          mcp_enabled: chatBoxSettings.mcp_enabled || false, mcp_strategy: chatBoxSettings.mcp_strategy || 'fast',
          mcp_configs: chatBoxSettings.mcp_configs || [],
        },
      };
      // Reuse the request identity if the POST response was lost.
      let turn;
      try { turn = await coordinatorRequest('', body); }
      catch (error) {
        if (!(error instanceof TypeError)) throw error;
        turn = await coordinatorRequest('', body);
      }
      const result = await waitForTurn(id, turn, selection);
      if (!result) return;
      // Preserve the explicitly configured external LangGraph transport.
      // Ordinary conversation still exits through the shared Coordinator.
      if (externalResearch && !['general_chat','knowledge_chat'].includes(result.capability)) {
        setConversationMode('research'); setIsInChatMode(false); setLoading(true);
        const {streamResponse, host, thread_id} = await startLanggraphResearch(
          newQuestion, chatBoxSettings.report_source, langgraphHost,
          chatBoxSettings.search_strategy, retrievers);
        setOrderedData(prev => [...prev, {type: 'langgraphButton', link: `https://smith.langchain.com/studio/thread/${thread_id}?baseUrl=${host}`}]);
        let previousChunk: any = null;
        for await (const chunk of streamResponse) {
          if (selection !== selectionGeneration.current) return;
          if (chunk.data.report && chunk.data.report !== 'Full report content here') {
            setOrderedData(prev => [...prev, {...chunk.data, output: chunk.data.report, type: 'report'}]);
            setAnswer(chunk.data.report);
          } else if (previousChunk) {
            setOrderedData(prev => [...prev, {type: 'differences', content: 'differences', output: JSON.stringify(findDifferences(previousChunk, chunk))}]);
          }
          previousChunk = chunk;
        }
        setLoading(false);
        return;
      }
      window.dispatchEvent(new Event('asteria:workspace-changed'));
      await handleSelectResearch(id);
    } catch (error) {
      if (selection === selectionGeneration.current) {
        setLoading(false);
        toast.error(error instanceof Error ? error.message : '请求失败，重新打开对话可恢复已保存进度');
      }
    } finally {
      coordinatorBusy.current = false;
      setIsProcessingChat(false);
    }
  };

  // Mobile-specific chat handler
  const handleMobileChat = async (message: string) => {
    // Set states for UI feedback
    setIsProcessingChat(true);
    
    // Format user message
    const userMessage = {
      role: 'user',
      content: message
    };
    
    // Add question to UI immediately
    const questionData: QuestionData = { 
      type: 'question', 
      content: message 
    };
    
    setOrderedData(prevOrder => [...prevOrder, questionData]);
    
    try {
      // Direct API call instead of websockets
      const response = await authFetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          messages: [userMessage],
          report: answer || '',
          report_source: chatBoxSettings.report_source || 'web',
          tone: chatBoxSettings.tone || 'Objective'
        }),
        // Set reasonable timeout
        signal: AbortSignal.timeout(20000) // 20-second timeout
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      const data = await response.json();
      
      if (data.response && data.response.content) {
        // Add AI response to chat history asynchronously
        if (currentResearchId) {
          addChatMessage(currentResearchId, data.response).catch(error => {
            console.error('Error adding AI response to history:', error);
          });
          
          // Also update the research with the new messages
          const chatData: ChatData = { 
            type: 'chat', 
            content: data.response.content,
            metadata: data.response.metadata 
          };
          
          setOrderedData(prevOrder => [...prevOrder, chatData]);
          
          // Get current ordered data and add new messages
          const updatedOrderedData = [...orderedData, questionData, chatData];
          
          // Update research in history
          updateResearch(
            currentResearchId, 
            answer, 
            updatedOrderedData
          ).catch(error => {
            console.error('Error updating research:', error);
          });
        } else {
          // If no research ID, just update the UI
          setOrderedData(prevOrder => [...prevOrder, { 
            type: 'chat', 
            content: data.response.content,
            metadata: data.response.metadata
          } as ChatData]);
        }
      } else {
        // Show error message
        setOrderedData(prevOrder => [...prevOrder, { 
          type: 'chat', 
          content: 'Sorry, something went wrong. Please try again.' 
        } as ChatData]);
      }
    } catch (error) {
      console.error('Error during mobile chat:', error);
      
      // Add error message
      setOrderedData(prevOrder => [...prevOrder, { 
        type: 'chat', 
        content: 'Sorry, there was an error processing your request. Please try again.' 
      } as ChatData]);
    } finally {
      setIsProcessingChat(false);
      setChatPromptValue('');
    }
  };

  const reset = () => {
    selectionGeneration.current++;
    clearTimeout(selectionRetry.current);
    // Reset UI states
    setShowResult(false);
    setPromptValue("");
    setIsStopped(false);
    setIsInChatMode(false);
    setCurrentResearchId(null); // Reset research ID
    pendingWorkspaceConversationId.current = null;
    setChatPromptValue("");
    setConversationMode('research');
    setIsProcessingChat(false);
    
    // Clear previous research data
    setQuestion("");
    setAnswer("");
    setOrderedData([]);
    setAllLogs([]);

    // Reset feedback states
    setShowHumanFeedback(false);
    setQuestionForHuman(false);
    
    // Clean up connections
    durableResearch.detach();
    durableConversation.current = null;
    window.history.replaceState(null, '', '/');
    setLoading(false);
  };

  const handleClickSuggestion = (value: string) => {
    setPromptValue(value);
    const element = document.getElementById('input-area');
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  /**
   * Handles stopping the current research
   * Sends an explicit cancellation; only the worker's terminal event marks
   * research stopped. Closing or refreshing this view is not cancellation.
   */
  const handleStopResearch = async () => {
    try {
      await durableResearch.cancel();
      toast.success('已请求停止，等待后台确认');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '停止请求失败');
    }
  };

  /**
   * Handles starting a new research
   * - Clears all previous research data and states
   * - Resets UI to initial state
   * - Closes any existing WebSocket connections
   */
  const handleStartNewResearch = () => {
    setChatBoxSettings(v => ({...v, skill_ids: [], format_profile: null}));
    reset();
    setSidebarOpen(false);
  };

  const handleCopyUrl = () => {
    if (!currentResearchId) return;
    
    const url = `${window.location.origin}/research/${currentResearchId}`;
    navigator.clipboard.writeText(url)
      .then(() => {
        toast.success("URL copied to clipboard!");
      })
      .catch(() => {
        toast.error("Failed to copy URL");
      });
  };

  // Add a ref to track if an update is in progress to prevent infinite loops
  const isUpdatingRef = useRef(false);

  // Save or update research in history based on mode
  useEffect(() => {
    // Define an async function inside the effect
    const saveOrUpdateResearch = async () => {
      // Prevent infinite loops by checking if we're already updating
      if (isUpdatingRef.current) return;
      // The worker owns report persistence; never overwrite it with partial replay.
      if (durableConversation.current) return;
      
      if (showResult && !loading && answer && question && orderedData.length > 0) {
        if (isInChatMode && currentResearchId) {
          // Prevent redundant updates by checking if data has changed
          try {
            const currentResearch = await getResearchById(currentResearchId);
            if (currentResearch && (currentResearch.answer !== answer || JSON.stringify(currentResearch.orderedData) !== JSON.stringify(orderedData))) {
              isUpdatingRef.current = true;
              await updateResearch(currentResearchId, answer, orderedData);
              // Reset the flag after a short delay to allow state updates to complete
              setTimeout(() => {
                isUpdatingRef.current = false;
              }, 100);
            }
          } catch (error) {
            console.error('Error updating research:', error);
            isUpdatingRef.current = false;
          }
        } else if (!isInChatMode) {
          // Check if this is a new research (not loaded from history)
          const isNewResearch = !history.some(item => 
            item.question === question && item.answer === answer
          );
          
          if (isNewResearch) {
            isUpdatingRef.current = true;
            try {
              const newId = await saveResearch(
                question,
                answer,
                orderedData,
                pendingWorkspaceConversationId.current,
              );
              pendingWorkspaceConversationId.current = null;
              setCurrentResearchId(newId);
              
              // Don't navigate to the research page URL anymore
              // Just save the ID for sharing purposes
              
            } catch (error) {
              console.error('Error saving research:', error);
            } finally {
              // Reset the flag after a short delay to allow state updates to complete
              setTimeout(() => {
                isUpdatingRef.current = false;
              }, 100);
            }
          }
        }
      }
    };
    
    // Call the async function
    saveOrUpdateResearch();
  }, [showResult, loading, answer, question, orderedData, history, saveResearch, updateResearch, isInChatMode, currentResearchId, getResearchById]);

  // Handle selecting a research from history
  const handleSelectResearch = async (id: string) => {
    const selection = ++selectionGeneration.current;
    clearTimeout(selectionRetry.current);
    let retryObservation = true;
    try {
      durableResearch.detach();
      pendingWorkspaceConversationId.current = id;
      setCurrentResearchId(id);
      setShowResult(true);
      linkedConversation.current = id;
      window.history.replaceState(null, '', `/?conversation=${encodeURIComponent(id)}`);
      const latest = await authFetch(`/api/workspace/runs/latest?conversation_id=${encodeURIComponent(id)}`);
      retryObservation = latest.status >= 500;
      if (!latest.ok) throw new Error('无法读取后台任务状态');
      const snapshot = await latest.json();
      if (selection !== selectionGeneration.current) return;
      if (snapshot.run && ['queued', 'running', 'waiting_approval', 'cancel_requested'].includes(snapshot.run.status)) {
        setConversationMode('research');
        durableConversation.current = id;
        setQuestion(snapshot.run.request.task);
        setIsInChatMode(false);
        await durableResearch.restore(id);
        return;
      }
      const conversationResponse = await authFetch(`/api/workspace/conversations/${id}`);
      if (conversationResponse.ok) {
        const conversation = await conversationResponse.json();
        if (selection !== selectionGeneration.current) return;
        const turn = (await coordinatorRequest(`?conversation_id=${encodeURIComponent(id)}`)).turn;
        if (selection !== selectionGeneration.current) return;
        if (turn?.status === 'running') {
          setIsProcessingChat(true);
          try {
            await waitForTurn(id, turn, selection);
            if (selection === selectionGeneration.current) {
              setIsProcessingChat(false);
              await handleSelectResearch(id);
            }
          } finally {
            if (selection === selectionGeneration.current) setIsProcessingChat(false);
          }
          return;
        }
        if (turn && ['failed', 'interrupted'].includes(turn.status)) toast.error(turn.error);
        if (conversation.mode === 'chat') {
          const messagesResponse = await authFetch(`/api/workspace/conversations/${id}/messages`);
          if (!messagesResponse.ok) throw new Error('无法读取对话消息');
          const messagesData = await messagesResponse.json();
          if (selection !== selectionGeneration.current) return;
          const messages = Array.isArray(messagesData.messages) ? messagesData.messages : [];
          setConversationMode('chat');
          const firstUser = messages.find((message: any) => message.role === 'user');
          setQuestion(firstUser?.content || conversation.title);
          setAnswer('');
          setOrderedData(messages.map((message: any) => (
            message.role === 'user'
              ? { type: 'question', content: message.content }
              : { type: 'chat', content: message.content, metadata: message.metadata }
          )));
          setShowResult(true);
          setLoading(false);
          setIsStopped(false);
          setIsInChatMode(true);
          durableConversation.current = null;
          return;
        }
      }
      if (snapshot.run && snapshot.run.status !== 'completed') {
        setConversationMode('research');
        durableConversation.current = id;
        setQuestion(snapshot.run.request.task);
        setIsInChatMode(false);
        await durableResearch.restore(id);
        return;
      }
      durableConversation.current = snapshot.run ? id : null;
      const research = await getResearchById(id);
      if (selection !== selectionGeneration.current) return;
      if (research) {
        setConversationMode('research');
        setCurrentResearchId(id);
        setQuestion(research.question);
        setAnswer(research.answer || '');
        const response = await authFetch(`/api/workspace/conversations/${id}/messages`);
        if (!response.ok) throw new Error('无法读取报告追问');
        const messages = (await response.json()).messages || [];
        if (selection !== selectionGeneration.current) return;
        // Research source messages are already represented in orderedData.
        // Only append persisted Coordinator chat turns after the report.
        const lastResearchTime = snapshot.run?.finished_at ? Date.parse(snapshot.run.finished_at) : 0;
        const followups = messages.filter((m: any) => m.metadata?.turn_id && Date.parse(m.created_at) > lastResearchTime);
        setOrderedData([...(research.orderedData || []), ...followups.map((m: any) =>
          ({type: m.role === 'user' ? 'question' : 'chat', content: m.content, metadata: m.metadata}))]);
        setShowResult(true);
        setLoading(false);
        setIsStopped(false);
        setIsInChatMode(false);
      }
    } catch (error) {
      if (selection !== selectionGeneration.current) return;
      if (retryObservation) {
        setLoading(true);
        setOrderedData([{ type: 'logs', content: 'connection_warning', output: '正在重新连接后台任务，恢复后继续显示进度；不会重新提交。' } as Data]);
        selectionRetry.current = setTimeout(() => {
          if (selection === selectionGeneration.current) void handleSelectResearch(id);
        }, 3000);
        return;
      }
      console.error('Error selecting research:', error);
      toast.error('Could not load the selected research');
    }
  };

  // Deep links open an existing conversation in the same research harness.
  // This only restores saved state; it never submits a new research request.
  const linkedConversation = useRef<string | null>(null);
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('conversation');
    if (!id || linkedConversation.current === id) return;
    linkedConversation.current = id;
    void handleSelectResearch(id);
    // React StrictMode replays effects in development. Reset the guard so the
    // second setup can restore after cleanup invalidates the first request.
    return () => { linkedConversation.current = null; };
  // Deep-link restoration runs on mount, not on every history refresh.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Toggle sidebar
  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  /**
   * Processes ordered data into logs for display
   * Updates whenever orderedData changes
   */
  useEffect(() => {
    const groupedData = preprocessOrderedData(orderedData);
    const statusReports = ["agent_generated", "starting_research", "planning_research", "error"];
    
    const newLogs = groupedData.reduce((acc: any[], data) => {
      // Process accordion blocks (grouped data)
      if (data.type === 'accordionBlock') {
        const logs = data.items.map((item: any, subIndex: any) => ({
          header: item.content,
          text: item.output,
          metadata: item.metadata,
          key: `${item.type}-${item.content}-${subIndex}`,
        }));
        return [...acc, ...logs];
      } 
      // Process status reports
      else if (data.type === 'logs' || statusReports.includes(data.content)) {
        return [...acc, {
          header: data.content,
          text: typeof data.output === 'string' ? data.output : JSON.stringify(data.output),
          metadata: data.metadata,
          key: `${data.type}-${data.content}-${acc.length}`,
        }];
      }
      return acc;
    }, []);
    
    setAllLogs(newLogs);
  }, [orderedData]);

  // Save chatBoxSettings to localStorage when they change
  useEffect(() => {
    const {skill_ids, format_profile, ...preferences} = chatBoxSettings;
    localStorage.setItem('chatBoxSettings', JSON.stringify(preferences));
  }, [chatBoxSettings]);

  // Set chat mode when a report is complete
  useEffect(() => {
    if (showResult && !loading && answer && !isInChatMode) {
      setIsInChatMode(true);
    }
  }, [showResult, loading, answer, isInChatMode]);


  return (
    <ResearchHarness
      history={history} active={showResult} question={question} answer={answer}
      loading={loading} chatting={isProcessingChat} stopped={isStopped}
      prompt={promptValue} setPrompt={setPromptValue}
      chatPrompt={chatPromptValue} setChatPrompt={setChatPromptValue}
      // New research always uses the durable agent run. Viewport size only
      // changes layout; it must not select a legacy /api/chat path.
      onResearch={handleDisplayResult}
      onChat={message => handleDisplayResult(message, true)}
      conversationMode={conversationMode}
      onNew={handleStartNewResearch} onEnter={handleEnterWorkspace}
      onStop={handleStopResearch} onSelect={handleSelectResearch}
      onDelete={async id => {
        const deleted = await deleteResearch(id);
        if (deleted && id === (currentResearchId || pendingWorkspaceConversationId.current)) handleStartNewResearch();
        return deleted;
      }}
      selectedId={currentResearchId || pendingWorkspaceConversationId.current}
      skillsSupported={!isMobile}
      settings={chatBoxSettings} setSettings={setChatBoxSettings} logCount={allLogs.length}
      artifactPaths={preprocessOrderedData(orderedData).filter((item: any) => item.type === 'path').at(-1)?.output}
    >
      <ResearchResults compact isResearchRunning={loading} orderedData={orderedData} answer={answer} allLogs={allLogs}
        chatBoxSettings={chatBoxSettings} handleClickSuggestion={handleClickSuggestion}
        currentResearchId={currentResearchId || undefined} isProcessingChat={isProcessingChat}
        onShareClick={currentResearchId ? handleCopyUrl : undefined} showResearchActivity={conversationMode === 'research'}/>
      {showHumanFeedback && <HumanFeedback questionForHuman={questionForHuman}
        websocket={null} onFeedbackSubmit={handleFeedbackSubmit}/>}
    </ResearchHarness>
  );
}
