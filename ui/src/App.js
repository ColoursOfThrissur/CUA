import React, { useState, useEffect } from 'react';
import { Wrench, Cpu, Activity, History, AlertTriangle } from 'lucide-react';
import { API_URL, WS_URL } from './config';
import { GlobalStateProvider, useGlobalState } from './GlobalState';
import { ToastProvider, useToast } from './components/Toast';
import Header from './components/Header';
import ChatPanel from './components/ChatPanel';
import AgentControlPanel from './components/AgentControlPanel';
import SelfImprovementLog from './components/SelfImprovementLog';
import StagingPreviewModal from './components/StagingPreviewModal';
import CombinedToolsPanel from './components/CombinedToolsPanel';
import CodePreviewModal from './components/CodePreviewModal';
import AnalyticsDashboard from './components/AnalyticsDashboard';
import ScheduleManager from './components/ScheduleManager';
import HistoryViewer from './components/HistoryViewer';
import DiffModal from './components/DiffModal';
import ApprovalNotification from './components/ApprovalNotification';
import ErrorBoundary from './components/ErrorBoundary';
import './styles/variables.css';
import './App.css';

function AppContent() {
  const globalState = useGlobalState();
  const toast = useToast();
  const [messages, setMessages] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [sessionId] = useState(() => {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  });
  const [selectedProposal, setSelectedProposal] = useState(null);
  const [customPrompt, setCustomPrompt] = useState('');
  const [dryRun, setDryRun] = useState(false);
  const [availableModels, setAvailableModels] = useState({});
  const [currentModel, setCurrentModel] = useState('mistral:latest');
  const [activeTab, setActiveTab] = useState('agent');
  const [showStagingModal, setShowStagingModal] = useState(false);
  const [stagingParentId, setStagingParentId] = useState(null);
  const [codePreview, setCodePreview] = useState(null);

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

  const handleClearLogs = async () => {
    if (!window.confirm('Clear all logs?')) return;
    
    try {
      globalState.updateState({ logs: [] });
      
      await fetch(`${API_URL}/improvement/clear-logs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      toast.success('Logs cleared successfully');
    } catch (error) {
      console.error('Failed to clear logs:', error);
      toast.error('Failed to clear logs: ' + error.message);
    }
  };
  
  const handleSaveLogs = () => {
    const logText = globalState.logs.map(log => 
      `[${log.timestamp}] ${log.type.toUpperCase()}: ${log.message}`
    ).join('\n');
    
    const blob = new Blob([logText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `improvement-logs-${new Date().toISOString().slice(0,10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Logs saved successfully');
  };

  const handleStartLoop = async () => {
    try {
      globalState.updateState({ running: true });
      
      const response = await fetch(`${API_URL}/improvement/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          max_iterations: 5,
          custom_prompt: customPrompt || null,
          dry_run: dryRun
        })
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        globalState.updateState({ running: false });
        toast.error('Failed to start: ' + (data.detail || 'Unknown error'));
      } else {
        setCustomPrompt('');
        toast.success('Self-improvement started');
      }
    } catch (error) {
      globalState.updateState({ running: false });
      toast.error('Failed to start loop: ' + error.message);
    }
  };

  const handleStartContinuous = async () => {
    try {
      globalState.updateState({ running: true });
      
      const response = await fetch(`${API_URL}/improvement/start-continuous`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        globalState.updateState({ running: false });
        toast.error('Failed to start: ' + (data.detail || 'Unknown error'));
      } else {
        toast.success('Continuous mode started - will run until stopped');
      }
    } catch (error) {
      globalState.updateState({ running: false });
      toast.error('Failed to start continuous: ' + error.message);
    }
  };

  const handleStopLoop = async (mode) => {
    try {
      // Optimistically update UI
      if (mode === 'immediate') {
        globalState.updateState({ running: false, iteration: 0 });
      }
      
      const response = await fetch(`${API_URL}/improvement/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      });
      
      const data = await response.json();
      
      if (response.ok) {
        if (data.mode === 'immediate' || data.status === 'stopped') {
          globalState.updateState({ running: false, iteration: 0 });
          toast.info('Self-improvement stopped');
        } else if (data.mode === 'deferred') {
          toast.warning('In critical section - will stop at safe point');
        } else {
          toast.info('Stop requested - finishing current task');
        }
      } else {
        if (mode === 'immediate') {
          globalState.updateState({ running: true });
        }
        toast.error('Failed to stop: ' + (data.detail || 'Unknown error'));
      }
    } catch (error) {
      if (mode === 'immediate') {
        globalState.updateState({ running: true });
      }
      toast.error('Failed to stop loop: ' + error.message);
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
        toast.success('Model changed to ' + data.model);
      }
    } catch (error) {
      toast.error('Failed to change model: ' + error.message);
    }
  };

  const handleApprove = async (proposalId) => {
    try {
      globalState.updateState({
        pendingApprovals: Object.fromEntries(
          Object.entries(globalState.pendingApprovals).filter(([k]) => k !== proposalId)
        )
      });
      
      await fetch(`${API_URL}/improvement/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ proposal_id: proposalId, approved: true })
      });
      setSelectedProposal(null);
      toast.success('Proposal approved');
    } catch (error) {
      toast.error('Failed to approve: ' + error.message);
    }
  };

  const handleReject = async (proposalId) => {
    try {
      globalState.updateState({
        pendingApprovals: Object.fromEntries(
          Object.entries(globalState.pendingApprovals).filter(([k]) => k !== proposalId)
        )
      });
      
      await fetch(`${API_URL}/improvement/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ proposal_id: proposalId, approved: false })
      });
      setSelectedProposal(null);
      toast.success('Proposal rejected');
    } catch (error) {
      toast.error('Failed to reject: ' + error.message);
    }
  };

  const handleViewDiff = async (proposalId) => {
    try {
      const response = await fetch(`${API_URL}/improvement/status`);
      if (!response.ok) {
        toast.error('Failed to fetch proposal');
        return;
      }
      
      const data = await response.json();
      
      if (data.pending_approvals && data.pending_approvals[proposalId]) {
        const proposal = data.pending_approvals[proposalId].proposal;
        
        // Validate proposal has required fields
        if (!proposal.patch || !proposal.description) {
          toast.error('Invalid proposal data');
          return;
        }
        
        setSelectedProposal({
          id: proposalId,
          ...proposal
        });
      } else {
        toast.error('Proposal not found');
      }
    } catch (error) {
      toast.error('Failed to load proposal: ' + error.message);
    }
  };

  const handleAbortTask = async (parentId) => {
    if (!window.confirm('Abort this parent task? All staged changes will be rolled back.')) return;

    try {
      const response = await fetch(`${API_URL}/tasks/${parentId}/abort`, {
        method: 'POST'
      });
      
      if (response.ok) {
        globalState.updateState({ taskManager: { active: false } });
        toast.success('Task aborted');
      } else {
        const data = await response.json();
        toast.error('Failed to abort: ' + (data.detail || 'Unknown error'));
      }
    } catch (error) {
      toast.error('Failed to abort task: ' + error.message);
    }
  };

  const handleViewStaging = (parentId) => {
    setStagingParentId(parentId);
    setShowStagingModal(true);
  };

  const handleApproveTool = async (toolId) => {
    try {
      const response = await fetch(`${API_URL}/pending-tools/${toolId}/approve`, {
        method: 'POST'
      });
      const data = await response.json();
      if (data.success) {
        toast.success(`Tool activated: ${data.tool_name}`);
        // Fetch updated list
        const listRes = await fetch(`${API_URL}/pending-tools/list`);
        const listData = await listRes.json();
        globalState.updateState({ pendingTools: listData.pending_tools || [] });
      } else {
        toast.error(`Failed to activate tool: ${data.error}`);
      }
    } catch (error) {
      console.error('Error approving tool:', error);
    }
  };

  const handleRejectTool = async (toolId) => {
    if (!window.confirm('Are you sure you want to reject this tool?')) return;
    
    try {
      const response = await fetch(`${API_URL}/pending-tools/${toolId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'User rejected' })
      });
      const data = await response.json();
      if (data.success) {
        const listRes = await fetch(`${API_URL}/pending-tools/list`);
        const listData = await listRes.json();
        globalState.updateState({ pendingTools: listData.pending_tools || [] });
      }
    } catch (error) {
      console.error('Error rejecting tool:', error);
    }
  };

  const handleViewCode = (tool) => {
    setCodePreview(tool);
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
        {!globalState.backendConnected && (
          <div style={{
            position: 'fixed',
            top: '10px',
            left: '50%',
            transform: 'translateX(-50%)',
            background: '#ef4444',
            color: '#fff',
            padding: '12px 24px',
            borderRadius: '8px',
            zIndex: 10000,
            fontWeight: 600,
            boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            <AlertTriangle size={20} /> Backend Disconnected - Start server with: python api/server.py
          </div>
        )}
        
        {!globalState.backendConnected && (
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
          pendingProposals={globalState.pendingApprovals}
          onViewDiff={handleViewDiff}
          onApprove={handleApprove}
          onReject={handleReject}
        />
        
        <Header 
          loopStatus={{
            running: globalState.running,
            iteration: globalState.iteration,
            maxIterations: globalState.maxIterations
          }}
          availableModels={availableModels}
          currentModel={currentModel}
          onModelChange={handleModelChange}
          onOpenAnalytics={() => setActiveTab('analytics')}
          onOpenScheduler={() => setActiveTab('scheduler')}
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
                className={`tab-btn ${activeTab === 'agent' ? 'active' : ''}`}
                onClick={() => setActiveTab('agent')}
              >
                <Cpu size={16} /> Agent
              </button>
              <button 
                className={`tab-btn ${activeTab === 'tools' ? 'active' : ''}`}
                onClick={() => setActiveTab('tools')}
              >
                <Wrench size={16} /> Tools
              </button>
              <button 
                className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`}
                onClick={() => setActiveTab('history')}
              >
                <History size={16} /> History
              </button>
            </div>

            <div className="tab-content">
              {activeTab === 'agent' && (
                <AgentControlPanel 
                  loopStatus={{
                    running: globalState.running,
                    iteration: globalState.iteration,
                    maxIterations: globalState.maxIterations
                  }}
                  onStartLoop={handleStartLoop}
                  onStartContinuous={handleStartContinuous}
                  onStopLoop={handleStopLoop}
                  customPrompt={customPrompt}
                  onCustomPromptChange={setCustomPrompt}
                  taskStatus={globalState.taskManager}
                  onAbortTask={handleAbortTask}
                  onViewStaging={handleViewStaging}
                  logs={globalState.logs}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  onViewDiff={handleViewDiff}
                  onClearLogs={handleClearLogs}
                  onSaveLogs={handleSaveLogs}
                />
              )}
              {activeTab === 'tools' && (
                <CombinedToolsPanel 
                  pendingTools={globalState.pendingTools}
                  onApprove={handleApproveTool}
                  onReject={handleRejectTool}
                  onViewCode={handleViewCode}
                  apiUrl={API_URL}
                />
              )}
              {activeTab === 'analytics' && <AnalyticsDashboard />}
              {activeTab === 'scheduler' && <ScheduleManager />}
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
        
        {showStagingModal && stagingParentId && (
          <StagingPreviewModal
            parentId={stagingParentId}
            onClose={() => setShowStagingModal(false)}
          />
        )}
        
        {codePreview && (
          <CodePreviewModal
            tool={codePreview}
            onClose={() => setCodePreview(null)}
          />
        )}
      </div>
    </ErrorBoundary>
  );
}

function App() {
  return (
    <GlobalStateProvider>
      <ToastProvider>
        <AppContent />
      </ToastProvider>
    </GlobalStateProvider>
  );
}

export default App;
