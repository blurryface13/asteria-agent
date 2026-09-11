import { useRef, useState, useEffect, useCallback } from 'react';
import { Data, ChatBoxSettings, QuestionData } from '../types/data';
import { getHost } from '../helpers/getHost';
import { getToken, clearAuth, isLocalAuthBypassEnabled } from '../helpers/auth';
import { getRetrieversForStrategy } from '../utils/searchStrategy';

export const useWebSocket = (
  setOrderedData: React.Dispatch<React.SetStateAction<Data[]>>,
  setAnswer: React.Dispatch<React.SetStateAction<string>>, 
  setLoading: React.Dispatch<React.SetStateAction<boolean>>,
  setShowHumanFeedback: React.Dispatch<React.SetStateAction<boolean>>,
  setQuestionForHuman: React.Dispatch<React.SetStateAction<string | false>>
) => {
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const heartbeatInterval = useRef<number>();
  const connectionTimeout = useRef<number>();

  // Cleanup function for heartbeat and socket on unmount
  useEffect(() => {
    return () => {
      // Clear heartbeat interval
      if (heartbeatInterval.current) {
        clearInterval(heartbeatInterval.current);
      }
      if (connectionTimeout.current) {
        clearTimeout(connectionTimeout.current);
      }
      
      // Close socket on unmount if it exists and is open
      if (socket && socket.readyState === WebSocket.OPEN) {
        console.log('Closing WebSocket due to component unmount');
        socket.close(1000, "Component unmounted");
      }
    };
  }, [socket]);

  const startHeartbeat = (ws: WebSocket) => {
    // Clear any existing heartbeat
    if (heartbeatInterval.current) {
      clearInterval(heartbeatInterval.current);
    }
    
    // Start new heartbeat
    heartbeatInterval.current = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
      }
    }, 30000); // Send ping every 30 seconds
  };

  const initializeWebSocket = useCallback((
    promptValue: string, 
    chatBoxSettings: ChatBoxSettings
  ) => {
    // Close existing socket if any
    if (socket && socket.readyState === WebSocket.OPEN) {
      console.log('Closing existing WebSocket connection');
      socket.close(1000, "New connection requested");
    }

    const storedConfig = localStorage.getItem('apiVariables');
    const apiVariables = storedConfig ? JSON.parse(storedConfig) : {};

    if (typeof window !== 'undefined') {
      
      let fullHost = getHost()
      const protocol = fullHost.includes('https') ? 'wss:' : 'ws:'
      const cleanHost = fullHost.replace('http://', '').replace('https://', '')
      // Browsers can't set custom headers on a WS handshake, so the JWT
      // travels as a query param instead - the backend validates it before
      // accepting the connection (see backend/server/app.py websocket_endpoint).
      const token = getToken()
      const ws_uri = `${protocol}//${cleanHost}/ws${token ? `?token=${encodeURIComponent(token)}` : ''}`

      console.log(`Creating new WebSocket connection to ${ws_uri}`);
      const newSocket = new WebSocket(ws_uri);
      setSocket(newSocket);
      connectionTimeout.current = window.setTimeout(() => {
        if (newSocket.readyState === WebSocket.CONNECTING) {
          newSocket.close(4000, "Connection timed out");
        }
      }, 15000);

      // WebSocket connection opened handler
      newSocket.onopen = () => {
        console.log('WebSocket connection opened');
        if (connectionTimeout.current) {
          clearTimeout(connectionTimeout.current);
        }
        
        const domainFilters = JSON.parse(localStorage.getItem('domainFilters') || '[]');
        const domains = domainFilters ? domainFilters.map((domain: any) => domain.value) : [];
        const { report_type, report_source, tone, mcp_enabled, mcp_configs, mcp_strategy, search_strategy, retrievers } = chatBoxSettings;
        const selectedRetrievers = getRetrieversForStrategy(search_strategy, retrievers);
        
        // Start a new research
        try {
          console.log(`Starting new research for: ${promptValue}`);
          const dataToSend = { 
            task: promptValue,
            report_type, 
            report_source, 
            tone,
            headers: {
              retrievers: selectedRetrievers,
            },
            search_strategy: search_strategy || "general",
            online_rag: chatBoxSettings.online_rag !== false,
            query_domains: domains,
            mcp_enabled: mcp_enabled || false,
            mcp_strategy: mcp_strategy || "fast",
            mcp_configs: mcp_configs || []
          };
          
          // Make sure we have a properly formatted command with a space after start
          const message = `start ${JSON.stringify(dataToSend)}`;
          console.log(`Sending start message, length: ${message.length}`);
          newSocket.send(message);
        } catch (error) {
          console.error("Error preparing start message:", error);
        }
        
        startHeartbeat(newSocket);
      };

      newSocket.onmessage = (event) => {
        try {
          // Handle ping response
          if (event.data === 'pong') return;

          // Try to parse JSON data
          console.log(`Received WebSocket message: ${event.data.substring(0, 100)}...`);
          const data = JSON.parse(event.data);
          
          if (data.type === 'error' || (data.type === 'logs' && data.content === 'error')) {
            const errorMessage = data.output || 'Research task failed.';
            console.error(`Server error: ${errorMessage}`);
            setLoading(false);
            setOrderedData((prevOrder) => [...prevOrder, {
              type: 'logs',
              content: 'error',
              output: errorMessage,
            } as Data]);
          } else if (data.type === 'human_feedback' && data.content === 'request') {
            setQuestionForHuman(data.output);
            setShowHumanFeedback(true);
          } else {
            const contentAndType = `${data.content}-${data.type}`;
            setOrderedData((prevOrder) => [...prevOrder, { ...data, contentAndType }]);

            if (data.type === 'report') {
              setAnswer((prev: string) => prev + data.output);
            } else if (data.type === 'report_complete') {
              // Replace entire report with the complete version (includes images)
              console.log('Received complete report with images');
              setAnswer(data.output);
            } else if (data.type === 'logs' && data.content === 'research_report') {
              const report = typeof data.output === 'string' ? data.output : data.output?.report;
              if (typeof report === 'string') {
                setAnswer(report);
              }
            } else if (data.type === 'path') {
              setLoading(false);
            }
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error, event.data);
        }
      };

      newSocket.onclose = (event) => {
        console.log(`WebSocket connection closed: code=${event.code}, reason=${event.reason}`);
        if (heartbeatInterval.current) {
          clearInterval(heartbeatInterval.current);
        }
        if (connectionTimeout.current) {
          clearTimeout(connectionTimeout.current);
        }
        setSocket(null);
        if (event.code !== 1000 && event.code !== 1001 && event.code !== 4401) {
          setLoading(false);
          setOrderedData((prevOrder) => [...prevOrder, {
            type: 'logs',
            content: 'error',
            output: event.reason || 'Research connection closed unexpectedly.',
          } as Data]);
        }
        // 4401 = backend rejected the handshake token. In normal mode the
        // stored session is stale, so clear it and go to /login. In explicit
        // local bypass mode, a 4401 means frontend/backend startup flags or
        // API targets are inconsistent; keep the real error visible instead
        // of sending the user through a login loop.
        if (event.code === 4401) {
          if (isLocalAuthBypassEnabled()) {
            setLoading(false);
            setOrderedData((prevOrder) => [...prevOrder, {
              type: 'logs',
              content: 'error',
              output: '本地免登录已开启，但后端拒绝了 WebSocket 鉴权。请检查后端是否使用 ASTERIA_DEV_AUTH_BYPASS=1 启动，以及前端 API 地址是否指向同一后端。',
            } as Data]);
          } else {
            clearAuth();
            window.location.href = '/login';
          }
        }
      };

      newSocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        if (heartbeatInterval.current) {
          clearInterval(heartbeatInterval.current);
        }
        setLoading(false);
      };
    }
  }, [socket, setOrderedData, setAnswer, setLoading, setShowHumanFeedback, setQuestionForHuman]);

  return { socket, setSocket, initializeWebSocket };
};
