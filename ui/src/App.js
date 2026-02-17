import React, { useState, useEffect } from 'react';
import { API_URL, WS_URL } from './config';
import Header from './components/Header';
import ChatPanel from './components/ChatPanel';
import SelfImprovementLog from './components/SelfImprovementLog';
import AnalyticsDashboard from './components/AnalyticsDashboard';
import ScheduleManager from './components/ScheduleManager';
import HistoryViewer from './components/HistoryViewer';
import DiffModal from './components/DiffModal';
import ApprovalNotification from './components/ApprovalNotification';
import ErrorBoundary from './components/ErrorBoundary';
import './styles/variables.css';
import './App.css';

function App() {
  const [messages, setMessages] = useState([]);
  const [improvementLogs, setImprovementLogs] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [loopStatus, setLoopStatus] = useState({
    running: false,
    iteration: 0,
    maxIterations: 10
  });
  const [sessionId] = useState(() => {
    // Use crypto.randomUUID if available, fallback to timestamp-based
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  });
  const [selectedProposal, setSelectedProposal] = useState(null);
  const [pendingProposals, setPendingProposals] = useState({});
  const [connectionError, setConnectionError] = useState(false);
  const [customPrompt, setCustomPrompt] = useState('');
  const [shouldPoll, setShouldPoll] = useState(true);
  const [dryRun, setDryRun] = useState(false);
  const [availableModels, setAvailableModels] = useState({});
  const [currentModel, setCurrentModel] = useState('mistral:latest');
  const [activeTab, setActiveTab] = useState('logs');
  const [logsSynced, setLogsSynced] = useState(false); // logs, analytics, schedules, history

  useEffect(() => {
    // Fetch available models on mount
    fetch(`${API_URL}/settings/models`)
      .then(res => res.json())
      .then(data => {
        setAvailableModels(data.available_models || {});
        setCurrentModel(data.current_model || 'mistral:latest');
      })
      .catch(err => console.error('Failed to load models:', err));
  }, []);

  useEffect(() => {
    // Use WebSocket for real-time updates with exponential backoff
    let ws = null;
    let reconnectTimeout = null;
    let reconnectAttempts = 0;
    const maxReconnectDelay = 30000;
    
    const connect = () => {
      ws = new WebSocket(WS_URL);
      
      ws.onopen = () => {
        console.log('WebSocket connected');
        setConnectionError(false);
        setLogsSynced(false);
        reconnectAttempts = 0;
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('WebSocket message:', data.type);
          
          if (data.type === 'new_log') {
            console.log('New log:', data.data);
            setImprovementLogs(prev => [...prev, data.data]);
          } else if (data.type === 'improvement_status') {
            const status = data.data;
            console.log('Status update:', status.running, status.iteration);
            setLoopStatus({
              running: status.running || false,
              iteration: status.iteration || 0,
              maxIterations: status.maxIterations || 10
            });
            
            // Only sync full logs on initial connection or if we have no logs
            if (status.logs && status.logs.length > 0 && !logsSynced) {
              console.log('Initial log sync:', status.logs.length);
              setImprovementLogs(status.logs);
              setLogsSynced(true);
            }
            
            if (status.pending_approvals) {
              setPendingProposals(status.pending_approvals);
            }
          }
        } catch (error) {
          console.error('WebSocket message error:', error);
        }
      };
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionError(true);
      };
      
      ws.onclose = () => {
        console.log('WebSocket disconnected, reconnecting...');
        setConnectionError(true);
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), maxReconnectDelay);
        reconnectAttempts++;
        reconnectTimeout = setTimeout(connect, delay);
      };
    };
    
    connect();
    
    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, []);

  const handleClearLogs = async () => {
    try {
      await fetch(`${API_URL}/improvement/clear-logs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      setImprovementLogs([]);
      setLogsSynced(false);
    } catch (error) {
      console.error('Failed to clear logs:', error);
    }
  };
  
  const handleSaveLogs = () => {
    const logText = improvementLogs.map(log => 
      `[${log.timestamp}] ${log.type.toUpperCase()}: ${log.message}`
    ).join('\n');
    
    const blob = new Blob([logText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `improvement-logs-${new Date().toISOString().slice(0,10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleStartLoop = async () => {
    try {
      const response = await fetch(`${API_URL}/improvement/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          max_iterations: 10,
          custom_prompt: customPrompt || null,
          dry_run: dryRun
        })
      });
      
      const data = await response.json();
      
      if (response.ok) {
        setLoopStatus({ running: true, iteration: 0, maxIterations: 10 });
        setCustomPrompt('');
        setLogsSynced(false); // Reset sync flag when starting new loop
      } else {
        alert('Failed to start: ' + (data.detail || 'Unknown error'));
      }
    } catch (error) {
      alert('Failed to start loop: ' + error.message);
    }
  };

  const handleStopLoop = async (mode) => {
    try {
      const response = await fetch(`${API_URL}/improvement/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      });
      
      if (response.ok) {
        if (mode === 'immediate') {
          setLoopStatus({ running: false, iteration: 0, maxIterations: 10 });
        }
      }
    } catch (error) {
      alert('Failed to stop loop: ' + error.message);
    }
  };

  const handleModelChange = async (model) => {
    try {
      const response = await fetch(`${API_URL}/settings/model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model })
      });
      
      if (response.ok) {
        const data = await response.json();
        setCurrentModel(data.model);
      }
    } catch (error) {
      alert('Failed to change model: ' + error.message);
    }
  };

  const handleApprove = async (proposalId) => {
    try {
      await fetch(`${API_URL}/improvement/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ proposal_id: proposalId, approved: true })
      });
      setSelectedProposal(null);
    } catch (error) {
      alert('Failed to approve: ' + error.message);
    }
  };

  const handleReject = async (proposalId) => {
    try {
      await fetch(`${API_URL}/improvement/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ proposal_id: proposalId, approved: false })
      });
      setSelectedProposal(null);
    } catch (error) {
      alert('Failed to reject: ' + error.message);
    }
  };

  const handleViewDiff = async (proposalId) => {
    try {
      const response = await fetch(`${API_URL}/improvement/status`);
      if (!response.ok) {
        alert('Failed to fetch proposal');
        return;
      }
      
      const data = await response.json();
      
      if (data.pending_approvals && data.pending_approvals[proposalId]) {
        const proposal = data.pending_approvals[proposalId].proposal;
        
        // Validate proposal has required fields
        if (!proposal.patch || !proposal.description) {
          alert('Invalid proposal data');
          return;
        }
        
        setSelectedProposal({
          id: proposalId,
          ...proposal
        });
      } else {
        alert('Proposal not found');
      }
    } catch (error) {
      alert('Failed to load proposal: ' + error.message);
    }
  };

  const handleSendMessage = async (message) => {
    const userMsg = {
      role: 'user',
      content: message,
      timestamp: new Date().toLocaleTimeString()
    };
    
    setMessages(prev => [...prev, userMsg]);
    setIsProcessing(true);

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId })
      });

      const data = await response.json();
      
      const assistantMsg = {
        role: 'assistant',
        content: data.response,
        timestamp: new Date().toLocaleTimeString()
      };
      
      setMessages(prev => [...prev, assistantMsg]);
    } catch (error) {
      const errorMsg = {
        role: 'assistant',
        content: `Error: ${error.message}`,
        timestamp: new Date().toLocaleTimeString()
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <ErrorBoundary>
      <div className="app">
        {connectionError && (
          <div style={{
            position: 'fixed',
            top: '10px',
            right: '10px',
            background: '#ef4444',
            color: '#fff',
            padding: '10px 20px',
            borderRadius: '6px',
            zIndex: 9999
          }}>
            Connection lost - retrying...
          </div>
        )}
        
        <ApprovalNotification
          pendingProposals={pendingProposals}
          onViewDiff={handleViewDiff}
          onApprove={handleApprove}
          onReject={handleReject}
        />
        
        <Header 
          onStartLoop={handleStartLoop}
          onStopLoop={handleStopLoop}
          loopStatus={loopStatus}
          customPrompt={customPrompt}
          onCustomPromptChange={setCustomPrompt}
          dryRun={dryRun}
          onDryRunChange={setDryRun}
          availableModels={availableModels}
          currentModel={currentModel}
          onModelChange={handleModelChange}
        />
        
        <div className="main-content">
          <div className="left-panel">
            <ChatPanel 
              messages={messages}
              onSendMessage={handleSendMessage}
              isProcessing={isProcessing}
            />
          </div>
          
          <div className="right-panel">
            <div className="tab-navigation">
              <button 
                className={`tab-btn ${activeTab === 'logs' ? 'active' : ''}`}
                onClick={() => setActiveTab('logs')}
              >
                Activity Log
              </button>
              <button 
                className={`tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
                onClick={() => setActiveTab('analytics')}
              >
                Analytics
              </button>
              <button 
                className={`tab-btn ${activeTab === 'schedules' ? 'active' : ''}`}
                onClick={() => setActiveTab('schedules')}
              >
                Schedules
              </button>
              <button 
                className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`}
                onClick={() => setActiveTab('history')}
              >
                History
              </button>
            </div>

            <div className="tab-content">
              {activeTab === 'logs' && (
                <SelfImprovementLog 
                  logs={improvementLogs}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  onViewDiff={handleViewDiff}
                  onClearLogs={handleClearLogs}
                  onSaveLogs={handleSaveLogs}
                />
              )}
              {activeTab === 'analytics' && <AnalyticsDashboard />}
              {activeTab === 'schedules' && <ScheduleManager />}
              {activeTab === 'history' && <HistoryViewer onViewDiff={handleViewDiff} />}
            </div>
          </div>
        </div>
        
        {selectedProposal && (
          <DiffModal
            proposal={selectedProposal}
            onClose={() => setSelectedProposal(null)}
            onApprove={() => handleApprove(selectedProposal.id)}
            onReject={() => handleReject(selectedProposal.id)}
          />
        )}
      </div>
    </ErrorBoundary>
  );
}

export default App;
