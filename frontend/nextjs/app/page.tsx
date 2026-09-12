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

  const persistWorkspaceMessage = async (conversationId: string, message: ChatMessage) => {
    const response = await authFetch(`/api/workspace/conversations/${conversationId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // The workspace API owns persistence metadata; do not forward the
      // browser-only timestamp field to its strict message contract.
      body: JSON.stringify({
        role: message.role,
        content: message.content,
        metadata: message.metadata || {},
      }),
    });
    if (!response.ok) throw new Error(`workspace message API error: ${response.status}`);
  };

  const handleCoordinatorChat = async (task: string, response: any) => {
    const workspaceConversationId = await prepareWorkspaceConversation(task, 'chat', 'coordinator-chat');
    const userMessage: ChatMessage = { role: 'user', content: task, timestamp: Date.now() };
    const assistantMessage: ChatMessage = {
      role: 'assistant',
      content: response.content,
      timestamp: response.timestamp || Date.now(),
      metadata: response.metadata,
    };
    await Promise.all([
      persistWorkspaceMessage(workspaceConversationId, userMessage),
      persistWorkspaceMessage(workspaceConversationId, assistantMessage),
    ]);
    pendingWorkspaceConversationId.current = null;
    setCurrentResearchId(workspaceConversationId);
    setIsInChatMode(true);
    setSidebarOpen(true);
    setShowResult(true);
    setLoading(false);
    setIsStopped(false);
    setQuestion(task);
    setAnswer('');
    setPromptValue('');
    setOrderedData([
      { type: 'question', content: task },
      { type: 'chat', content: response.content, metadata: response.metadata },
    ]);
    window.history.replaceState(null, '', `/?conversation=${encodeURIComponent(workspaceConversationId)}`);
    window.dispatchEvent(new Event('asteria:workspace-changed'));
  };

  const handleDisplayResult = async (newQuestion: string) => {
    selectionGeneration.current++;
    clearTimeout(selectionRetry.current);
    let coordination: any;
    try {
      const response = await authFetch('/api/coordinator', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: newQuestion }),
      });
      coordination = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(coordination.detail || coordination.error || `Coordinator API error: ${response.status}`);
      if (coordination.capability === 'general_chat') {
        if (!coordination.response?.content) throw new Error('Coordinator returned an empty chat response');
        await handleCoordinatorChat(newQuestion, coordination.response);
        return;
      }
      if (!['literature_review', 'experiment_design', 'general_research'].includes(coordination.capability)) {
        throw new Error('Coordinator returned an unsupported capability');
      }
    } catch (error) {
      console.error('Coordinator routing failed:', error);
      toast.error(error instanceof Error ? error.message : '无法完成任务意图识别，请重试。');
      return;
    }
    let workspaceConversationId: string;
    try {
      workspaceConversationId = await prepareWorkspaceConversation(newQuestion);
    } catch (error) {
      console.error('Error creating workspace conversation:', error);
      toast.error('无法创建项目子任务，请检查工作区服务后重试。');
      return;
    }
    // Exit chat mode when starting a new research
    setIsInChatMode(false);
    setSidebarOpen(true);
    setShowResult(true);
    setLoading(true);
    setQuestion(newQuestion);
    setPromptValue("");
    setAnswer("");
    setCurrentResearchId(null); // Reset current research ID for new research
    setOrderedData((prevOrder) => [...prevOrder, { type: 'question', content: newQuestion }]);

    const storedConfig = localStorage.getItem('apiVariables');
    const apiVariables = storedConfig ? JSON.parse(storedConfig) : {};
    const langgraphHostUrl = apiVariables.LANGGRAPH_HOST_URL;

    // Starting new research - tracking for redirection once complete
    const newResearchStarted = Date.now().toString();
    // We'll use this as a temporary ID to keep track of this research
    const tempResearchId = `temp-${newResearchStarted}`;

    if (chatBoxSettings.report_type === 'multi_agents' && langgraphHostUrl) {
      const retrievers = getRetrieversForStrategy(chatBoxSettings.search_strategy, chatBoxSettings.retrievers);
      let { streamResponse, host, thread_id } = await startLanggraphResearch(
        newQuestion,
        chatBoxSettings.report_source,
        langgraphHostUrl,
        chatBoxSettings.search_strategy,
        retrievers
      );
      const langsmithGuiLink = `https://smith.langchain.com/studio/thread/${thread_id}?baseUrl=${host}`;
      setOrderedData((prevOrder) => [...prevOrder, { type: 'langgraphButton', link: langsmithGuiLink }]);

      let previousChunk = null;
      for await (const chunk of streamResponse) {
        if (chunk.data.report != null && chunk.data.report != "Full report content here") {
          setOrderedData((prevOrder) => [...prevOrder, { ...chunk.data, output: chunk.data.report, type: 'report' }]);
          setLoading(false);
        
          // Save research and navigate to its unique URL once it's complete
          setAnswer(chunk.data.report);
        } else if (previousChunk) {
          const differences = findDifferences(previousChunk, chunk);
          setOrderedData((prevOrder) => [...prevOrder, { type: 'differences', content: 'differences', output: JSON.stringify(differences) }]);
        }
        previousChunk = chunk;
      }
    } else {
      setCurrentResearchId(workspaceConversationId);
      window.history.replaceState(null, '', `/?conversation=${encodeURIComponent(workspaceConversationId)}`);
      linkedConversation.current = workspaceConversationId;
      durableConversation.current = workspaceConversationId;
      try {
        await durableResearch.start(newQuestion, chatBoxSettings, workspaceConversationId, coordination.capability);
      } catch (error) {
        setLoading(false);
        setOrderedData(prev => [...prev, {type: 'logs', content: 'error', output: error instanceof Error ? error.message : '任务提交失败'} as Data]);
      }
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
      if (durableConversation.current && !isInChatMode) return;
      
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
      if (snapshot.run && snapshot.run.status !== 'completed') {
        durableConversation.current = id;
        setQuestion(snapshot.run.request.task);
        setIsInChatMode(false);
        await durableResearch.restore(id);
        return;
      }
      const conversationResponse = await authFetch(`/api/workspace/conversations/${id}`);
      if (conversationResponse.ok) {
        const conversation = await conversationResponse.json();
        if (conversation.mode === 'chat') {
          const messagesResponse = await authFetch(`/api/workspace/conversations/${id}/messages`);
          const messagesData = messagesResponse.ok ? await messagesResponse.json() : { messages: [] };
          const messages = Array.isArray(messagesData.messages) ? messagesData.messages : [];
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
      durableConversation.current = snapshot.run ? id : null;
      const research = await getResearchById(id);
      if (selection !== selectionGeneration.current) return;
      if (research) {
        setCurrentResearchId(id);
        setQuestion(research.question);
        setAnswer(research.answer || '');
        setOrderedData(research.orderedData || []);
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
      onChat={isMobile ? handleMobileChat : handleChat}
      onNew={handleStartNewResearch} onEnter={handleEnterWorkspace}
      onStop={handleStopResearch} onSelect={handleSelectResearch}
      selectedId={currentResearchId || pendingWorkspaceConversationId.current}
      skillsSupported={!isMobile}
      settings={chatBoxSettings} setSettings={setChatBoxSettings} logCount={allLogs.length}
      artifactPaths={preprocessOrderedData(orderedData).filter((item: any) => item.type === 'path').at(-1)?.output}
    >
      <ResearchResults compact isResearchRunning={loading} orderedData={orderedData} answer={answer} allLogs={allLogs}
        chatBoxSettings={chatBoxSettings} handleClickSuggestion={handleClickSuggestion}
        currentResearchId={currentResearchId || undefined} isProcessingChat={isProcessingChat}
        onShareClick={currentResearchId ? handleCopyUrl : undefined} showResearchActivity={!isInChatMode}/>
      {showHumanFeedback && <HumanFeedback questionForHuman={questionForHuman}
        websocket={null} onFeedbackSubmit={handleFeedbackSubmit}/>}
    </ResearchHarness>
  );
}
