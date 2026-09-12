import { useState, useEffect, useRef } from 'react';
import { toast } from 'react-hot-toast';
import { v4 as uuidv4 } from 'uuid';
import { ResearchHistoryItem, Data, ChatMessage } from '../types/data';
import { authFetch } from "@/helpers/auth";

export const useResearchHistory = () => {
  const [history, setHistory] = useState<ResearchHistoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const dataLoadedRef = useRef(false); // Track if data has been loaded
  useEffect(() => {
    const refresh = async () => {
      const response = await authFetch('/api/reports');
      if (!response.ok) return;
      const data = await response.json();
      if (Array.isArray(data.reports)) {
        const reports = [...data.reports].sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
        setHistory(reports);
        localStorage.setItem('researchHistory', JSON.stringify(reports));
      }
    };
    const listener = () => { void refresh().catch(console.error); };
    window.addEventListener('asteria:reports-changed', listener);
    return () => window.removeEventListener('asteria:reports-changed', listener);
  }, []);
  
  // Fetch all research history on mount
  useEffect(() => {
    // Skip if data is already loaded to prevent excessive API calls
    if (dataLoadedRef.current) {
      return;
    }

    const fetchHistory = async () => {
      try {
        console.log('Fetching research history from server...');
        // First, load data from localStorage for immediate display
        const localHistory = loadFromLocalStorage();
        
        // Set local history immediately to show something to user
        if (localHistory && localHistory.length > 0) {
          setHistory(localHistory);
        }
        
        // The database is the source of truth for saved reports. Local
        // storage is only an immediate cache and a place for legacy drafts;
        // do not skip the server request just because this browser has no
        // local history.
        const response = await authFetch('/api/reports');
        if (!response.ok) {
          console.warn('Failed to load history from server, status:', response.status);
          return;
        }

        const data = await response.json();
        if (!data.reports || !Array.isArray(data.reports)) {
          console.warn('Server response did not contain reports array', data);
          return;
        }

        console.log('Loaded research history from server:', data.reports.length, 'items');
        if (localHistory && localHistory.length > 0) {
          // Upload legacy local-only reports, then prefer the server copy for
          // every report that already has a durable record.
          await syncLocalHistoryWithServer(localHistory, data.reports);
        } else {
          const sortedHistory = [...data.reports].sort((a, b) =>
            (b.timestamp || 0) - (a.timestamp || 0),
          );
          setHistory(sortedHistory);
          localStorage.setItem('researchHistory', JSON.stringify(sortedHistory));
        }
      } catch (error) {
        console.error('Error fetching research history:', error);
        // We're already using local history from above
      } finally {
        dataLoadedRef.current = true; // Mark data as loaded
        setLoading(false);
      }
    };
    
    // Helper to load from localStorage
    const loadFromLocalStorage = () => {
      const localHistoryStr = localStorage.getItem('researchHistory');
      if (localHistoryStr) {
        try {
          const parsedHistory = JSON.parse(localHistoryStr);
          if (Array.isArray(parsedHistory)) {
            console.log('Loaded research history from localStorage:', parsedHistory.length, 'items');
            return parsedHistory;
          } else {
            console.warn('localStorage history is not an array');
            return [];
          }
        } catch (error) {
          console.error('Error parsing localStorage history:', error);
          return [];
        }
      } else {
        return [];
      }
    };
    
    // Helper to sync local history with server
    const syncLocalHistoryWithServer = async (localHistory: ResearchHistoryItem[], serverHistory: ResearchHistoryItem[]) => {
      console.log('Syncing local history with server...');
      
      // Create a map of server history IDs for quick lookup
      const serverIds = new Set(serverHistory.map(item => item.id));
      
      // Find local reports that aren't on the server
      const localOnlyReports = localHistory.filter(item => !serverIds.has(item.id));
      console.log('Found local-only reports:', localOnlyReports.length);
      
      // Upload local-only reports to server
      for (const report of localOnlyReports) {
        try {
          // Skip reports without questions or answers
          if (!report.question || !report.answer) continue;
          
          console.log(`Uploading local report to server: ${report.id}`);
          
          const response = await authFetch('/api/reports', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              id: report.id,
              question: report.question,
              answer: report.answer,
              orderedData: report.orderedData || [],
              chatMessages: report.chatMessages || []
            }),
          });
          
          if (!response.ok) {
            console.warn(`Failed to upload local report ${report.id} to server:`, response.status);
          }
        } catch (error) {
          console.error(`Error uploading local report ${report.id} to server:`, error);
        }
      }
      
      // Create a unified history with server data prioritized
      const combinedHistory = [...serverHistory];
      
      // Add local-only reports to the combined history
      for (const report of localOnlyReports) {
        if (!serverIds.has(report.id)) {
          combinedHistory.push(report);
        }
      }
      
      // Sort by timestamp if available, newest first
      const sortedHistory = combinedHistory.sort((a, b) => {
        const timeA = a.timestamp || 0;
        const timeB = b.timestamp || 0;
        return timeB - timeA;
      });
      
      setHistory(sortedHistory);
      
      // Update localStorage with the complete merged set
      localStorage.setItem('researchHistory', JSON.stringify(sortedHistory));
      
      console.log('History sync complete, total items:', sortedHistory.length);
    };
    
    fetchHistory();
  }, []); // Empty dependency array - only run once on mount
  
  // Save new research
  const saveResearch = async (
    question: string,
    answer: string,
    orderedData: Data[],
    existingConversationId?: string | null,
  ) => {
    let workspaceConversationCreated = false;
    const id = existingConversationId || uuidv4();
    try {
      // Keep the report and conversation addressable by one stable ID. The
      // report API remains compatible, while the workspace API owns the
      // project/conversation hierarchy.
      if (!existingConversationId) {
        const activeProjectId = typeof window !== 'undefined'
          ? window.localStorage.getItem('asteria.activeProjectId')
          : null;
        const conversationEndpoint = activeProjectId
          ? `/api/workspace/conversations?project_id=${encodeURIComponent(activeProjectId)}`
          : '/api/workspace/conversations';
        const conversationResponse = await authFetch(conversationEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id,
            title: question.trim().slice(0, 255) || '新任务',
            mode: 'research',
            metadata: { source: 'research-history' },
          }),
        });
        if (!conversationResponse.ok) {
          throw new Error(`workspace conversation API error: ${conversationResponse.status}`);
        }
      }
      workspaceConversationCreated = true;
      
      // Save to backend
      const response = await authFetch('/api/reports', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          id,
          question,
          answer,
          orderedData,
          chatMessages: []
        }),
      });
      
      if (response.ok) {
        const data = await response.json();
        for (const [role, content] of [['user', question], ['assistant', answer]] as const) {
          if (!content.trim()) continue;
          const messageResponse = await authFetch(`/api/workspace/conversations/${id}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role, content, metadata: { source: 'research-history' } }),
          });
          if (!messageResponse.ok) {
            console.error(`Failed to persist workspace ${role} message:`, messageResponse.status);
          }
        }
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('asteria:workspace-changed'));
        }
        const newId = data.id;
        
        // Update local state
        const newResearch = {
          id: newId,
          question,
          answer,
          orderedData,
          chatMessages: [],
          timestamp: Date.now(),
        };
        
        setHistory(prev => [newResearch, ...prev]);
        
        // Also save to localStorage as fallback
        const localHistory = localStorage.getItem('researchHistory');
        const parsedHistory = localHistory ? JSON.parse(localHistory) : [];
        localStorage.setItem(
          'researchHistory',
          JSON.stringify([newResearch, ...parsedHistory])
        );
        
        return newId;
      } else {
        throw new Error(`API error: ${response.status}`);
      }
    } catch (error) {
      console.error('Error saving research:', error);
      if (workspaceConversationCreated) {
        try {
          await authFetch(`/api/workspace/conversations/${id}`, { method: 'DELETE' });
        } catch (cleanupError) {
          console.error('Error cleaning up workspace conversation:', cleanupError);
        }
      }
      toast.error('Failed to save research to server. Saved locally only.');
      
      // Fallback: save to localStorage only
      const newResearch = {
        id: uuidv4(),
        question,
        answer,
        orderedData,
        chatMessages: [],
        timestamp: Date.now(),
      };
      
      // Update local state
      setHistory(prev => [newResearch, ...prev]);
      
      // Save to localStorage
      const localHistory = localStorage.getItem('researchHistory');
      const parsedHistory = localHistory ? JSON.parse(localHistory) : [];
      localStorage.setItem(
        'researchHistory',
        JSON.stringify([newResearch, ...parsedHistory])
      );
      
      return newResearch.id;
    }
  };
  
  // Update existing research
  const updateResearch = async (id: string, answer: string, orderedData: Data[]) => {
    try {
      // Update in backend
      const response = await authFetch(`/api/reports/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          answer,
          orderedData
        }),
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      // Update local state
      setHistory(prev => 
        prev.map(item => 
          item.id === id ? { ...item, answer, orderedData, timestamp: Date.now() } : item
        )
      );
      
      // Also update localStorage as fallback
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        const updatedHistory = parsedHistory.map((item: any) => 
          item.id === id ? { ...item, answer, orderedData, timestamp: Date.now() } : item
        );
        localStorage.setItem('researchHistory', JSON.stringify(updatedHistory));
      }
      
      return true;
    } catch (error) {
      console.error('Error updating research:', error);
      
      // Update local state anyway
      setHistory(prev => 
        prev.map(item => 
          item.id === id ? { ...item, answer, orderedData, timestamp: Date.now() } : item
        )
      );
      
      // Update localStorage
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        const updatedHistory = parsedHistory.map((item: any) => 
          item.id === id ? { ...item, answer, orderedData, timestamp: Date.now() } : item
        );
        localStorage.setItem('researchHistory', JSON.stringify(updatedHistory));
      }
      
      return false;
    }
  };

  // Get research by ID
  const getResearchById = async (id: string) => {
    try {
      const response = await authFetch(`/api/reports/${id}`);
      if (response.ok) {
        const data = await response.json();
        return data.report;
      } else if (response.status === 404) {
        // A conversation can exist before a final report (running or failed task).
        const conversationResponse = await authFetch(`/api/workspace/conversations/${id}`);
        if (conversationResponse.ok) {
          const conversation = await conversationResponse.json();
          const messagesResponse = await authFetch(`/api/workspace/conversations/${id}/messages`);
          if (!messagesResponse.ok) throw new Error(`Message API error: ${messagesResponse.status}`);
          const { messages = [] } = await messagesResponse.json();
          return {
            id, question: messages.find((m: any) => m.role === 'user')?.content || conversation.title,
            answer: messages.filter((m: any) => m.role === 'assistant').map((m: any) => m.content).join('\n\n'),
            orderedData: [], timestamp: conversation.updated_at,
          };
        }
        if (conversationResponse.status !== 404) throw new Error(`Conversation API error: ${conversationResponse.status}`);
        // Pre-migration local records have no server conversation.
        const localHistory = localStorage.getItem('researchHistory');
        if (localHistory) {
          const parsedHistory = JSON.parse(localHistory);
          return parsedHistory.find((item: any) => item.id === id) || null;
        }
      } else {
        throw new Error(`API error: ${response.status}`);
      }
    } catch (error) {
      console.error('Error getting research by ID:', error);
      
      // Try localStorage as fallback
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        return parsedHistory.find((item: any) => item.id === id) || null;
      }
      
      return null;
    }
  };

  // Delete research
  const deleteResearch = async (id: string) => {
    try {
      const conversationResponse = await authFetch(`/api/workspace/conversations/${id}`, {
        method: 'DELETE',
      });
      if (!conversationResponse.ok && conversationResponse.status !== 404) {
        const data = await conversationResponse.json();
        throw new Error(data.detail || `workspace API error: ${conversationResponse.status}`);
      }
      const response = await authFetch(`/api/reports/${id}`, {
        method: 'DELETE',
      });
      
      if (!response.ok && response.status !== 404) {
        throw new Error(`API error: ${response.status}`);
      }

      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event('asteria:workspace-changed'));
      }
      
      // Update local state
      setHistory(prev => prev.filter(item => item.id !== id));
      
      // Also update localStorage
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        const filteredHistory = parsedHistory.filter((item: any) => item.id !== id);
        localStorage.setItem('researchHistory', JSON.stringify(filteredHistory));
      }
      
      return true;
    } catch (error) {
      console.error('Error deleting research:', error);
      
      toast.error(error instanceof Error ? error.message : '删除失败');
      return false;
    }
  };

  // Add chat message
  const addChatMessage = async (id: string, message: ChatMessage) => {
    try {
      const response = await authFetch(`/api/reports/${id}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(message),
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const workspaceResponse = await authFetch(`/api/workspace/conversations/${id}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(message),
      });
      if (!workspaceResponse.ok) {
        console.error('Failed to persist workspace message:', workspaceResponse.status);
      }
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event('asteria:workspace-changed'));
      }
      
      // Update local state
      setHistory(prev => 
        prev.map(item => {
          if (item.id === id) {
            const chatMessages = item.chatMessages || [];
            return { ...item, chatMessages: [...chatMessages, message] };
          }
          return item;
        })
      );
      
      // Also update localStorage
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        const updatedHistory = parsedHistory.map((item: any) => {
          if (item.id === id) {
            const chatMessages = item.chatMessages || [];
            return { ...item, chatMessages: [...chatMessages, message] };
          }
          return item;
        });
        localStorage.setItem('researchHistory', JSON.stringify(updatedHistory));
      }
      
      return true;
    } catch (error) {
      console.error('Error adding chat message:', error);
      
      // Update local state anyway
      setHistory(prev => 
        prev.map(item => {
          if (item.id === id) {
            const chatMessages = item.chatMessages || [];
            return { ...item, chatMessages: [...chatMessages, message] };
          }
          return item;
        })
      );
      
      // Update localStorage
      const localHistory = localStorage.getItem('researchHistory');
      if (localHistory) {
        const parsedHistory = JSON.parse(localHistory);
        const updatedHistory = parsedHistory.map((item: any) => {
          if (item.id === id) {
            const chatMessages = item.chatMessages || [];
            return { ...item, chatMessages: [...chatMessages, message] };
          }
          return item;
        });
        localStorage.setItem('researchHistory', JSON.stringify(updatedHistory));
      }
      
      return false;
    }
  };

  // Get chat messages
  const getChatMessages = (id: string) => {
    // First try to get from local state
    // Add defensive check to ensure history is an array before using find
    if (Array.isArray(history)) {
      const research = history.find(item => item.id === id);
      if (research && research.chatMessages) {
        return research.chatMessages;
      }
    } else {
      console.warn('History is not an array when getting chat messages');
    }
    
    // Fallback to localStorage
    const localHistory = localStorage.getItem('researchHistory');
    if (localHistory) {
      try {
        const parsedHistory = JSON.parse(localHistory);
        // Check if parsedHistory is an array
        if (Array.isArray(parsedHistory)) {
          const research = parsedHistory.find((item: any) => item.id === id);
          if (research && research.chatMessages) {
            return research.chatMessages;
          }
        } else {
          console.warn('Parsed history from localStorage is not an array');
        }
      } catch (error) {
        console.error('Error parsing history from localStorage:', error);
      }
    }
    
    return [];
  };

  // Clear all history from local storage and server
  const clearHistory = async () => {
    try {
      // Not implementing bulk delete on the server for now
      // This would require a new API endpoint
      
      // Just clear local state and storage
      setHistory([]);
      localStorage.removeItem('researchHistory');
      
      return true;
    } catch (error) {
      console.error('Error clearing history:', error);
      return false;
    }
  };

  return {
    history,
    loading,
    saveResearch,
    updateResearch,
    getResearchById,
    deleteResearch,
    addChatMessage,
    getChatMessages,
    clearHistory
  };
};
