import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const GlobalStateContext = createContext();

export const useGlobalState = () => {
  const context = useContext(GlobalStateContext);
  if (!context) {
    throw new Error('useGlobalState must be used within GlobalStateProvider');
  }
  return context;
};

export const GlobalStateProvider = ({ children }) => {
  const [state, setState] = useState(() => {
    // Load from localStorage on init
    try {
      const saved = localStorage.getItem('cua_state');
      return saved ? JSON.parse(saved) : {
        logs: [],
        running: false,
        iteration: 0,
        maxIterations: 0,
        pendingApprovals: {},
        pendingTools: [],
        skillCatalog: [],
        skillCategories: {},
        taskManager: { active: false },
        backendConnected: false,
        lastUpdate: null,
        agentPlan: null,
      };
    } catch (error) {
      console.error('Failed to load state from localStorage:', error);
      return {
        logs: [],
        running: false,
        iteration: 0,
        maxIterations: 0,
        pendingApprovals: {},
        pendingTools: [],
        skillCatalog: [],
        skillCategories: {},
        taskManager: { active: false },
        backendConnected: false,
        lastUpdate: null,
        agentPlan: null,
      };
    }
  });

  const [ws, setWs] = useState(null);
  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

  // Persist to localStorage on change (exclude transient runtime state)
  useEffect(() => {
    try {
      const { agentPlan, backendConnected, ...persistable } = state;
      localStorage.setItem('cua_state', JSON.stringify(persistable));
    } catch (error) {
      console.error('Failed to save state to localStorage:', error);
    }
  }, [state]);

  // Update state helper
  const updateState = useCallback((updates) => {
    setState(prev => ({
      ...prev,
      ...updates,
      lastUpdate: Date.now()
    }));
  }, []);

  // WebSocket connection
  useEffect(() => {
    const WS_URL = process.env.REACT_APP_WS_URL || 'ws://localhost:8000/ws';
    let socket = null;
    let reconnectTimer = null;
    let pingInterval = null;
    let isCleaningUp = false;

    const connect = () => {
      if (isCleaningUp) return;
      
      try {
        socket = new WebSocket(WS_URL);

        socket.onopen = () => {
          console.log('WebSocket connected');
          updateState({ backendConnected: true });

          // Send ping every 30s
          pingInterval = setInterval(() => {
            if (socket && socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: 'ping' }));
            }
          }, 30000);
        };

        socket.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);

            switch (msg.type) {
              case 'initial_state':
                updateState({
                  logs: msg.data.logs || [],
                  running: msg.data.running || false,
                  iteration: msg.data.iteration || 0,
                  maxIterations: msg.data.maxIterations || 0,
                  pendingApprovals: msg.data.pending_approvals || {},
                  pendingTools: msg.data.pending_tools || [],
                  taskManager: msg.data.task_manager || { active: false }
                });
                break;

              case 'log_added':
                setState(prev => ({
                  ...prev,
                  logs: [...prev.logs.slice(-19), msg.data],
                  lastUpdate: Date.now()
                }));
                break;

              case 'loop_started':
                updateState({
                  running: true,
                  iteration: 0,
                  maxIterations: msg.data.max_iterations
                });
                break;

              case 'loop_stopped':
                updateState({
                  running: false
                });
                break;

              case 'task_completed':
                updateState({ iteration: msg.data.iteration });
                break;

              case 'pending_tool_added':
                fetch(`${API_URL}/pending-tools/list`)
                  .then(r => r.json())
                  .then(data => updateState({ pendingTools: data.pending_tools }))
                  .catch(console.error);
                break;

              case 'agent_plan':
                updateState({ agentPlan: msg.data });
                break;

              case 'agent_step_update':
                setState(prev => {
                  if (!prev.agentPlan) return prev;
                  return {
                    ...prev,
                    lastUpdate: Date.now(),
                    agentPlan: {
                      ...prev.agentPlan,
                      steps: prev.agentPlan.steps.map(s =>
                        s.step_id === msg.data.step_id ? { ...s, status: msg.data.status, error: msg.data.error } : s
                      ),
                    },
                  };
                });
                break;

              case 'agent_plan_clear':
                updateState({ agentPlan: null });
                window.dispatchEvent(new CustomEvent('agentPlanCleared'));
                break;

              case 'pong':
                break;

              default:
                console.log('Unknown message type:', msg.type);
            }
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
          }
        };

        socket.onerror = (error) => {
          console.error('WebSocket error:', error);
        };

        socket.onclose = () => {
          console.log('WebSocket disconnected');
          updateState({ backendConnected: false });
          
          if (pingInterval) {
            clearInterval(pingInterval);
            pingInterval = null;
          }

          // Reconnect after 3s if not cleaning up
          if (!isCleaningUp) {
            reconnectTimer = setTimeout(connect, 3000);
          }
        };

        setWs(socket);
      } catch (error) {
        console.error('WebSocket connection failed:', error);
        updateState({ backendConnected: false });
        
        if (!isCleaningUp) {
          reconnectTimer = setTimeout(connect, 3000);
        }
      }
    };

    connect();

    return () => {
      isCleaningUp = true;
      clearTimeout(reconnectTimer);
      clearInterval(pingInterval);
      if (socket) {
        socket.close();
      }
    };
  }, []);

  const value = {
    ...state,
    updateState,
    ws
  };

  return (
    <GlobalStateContext.Provider value={value}>
      {children}
    </GlobalStateContext.Provider>
  );
};
