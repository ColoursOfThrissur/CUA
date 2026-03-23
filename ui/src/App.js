import React, { useState, useEffect } from 'react';
import { AlertTriangle } from 'lucide-react';
import { API_URL, WS_URL } from './config';
import { GlobalStateProvider, useGlobalState } from './GlobalState';
import { ToastProvider, useToast } from './components/Toast';
import ErrorBoundary from './components/ErrorBoundary';
import Header from './components/Header';
import ModeTabBar from './components/ModeTabBar';
import MainCanvas from './components/MainCanvas';
import AgentMode from './components/AgentMode';
import RightOverlay from './components/RightOverlay';
import QualityOverlay from './components/QualityOverlay';
import PendingEvolutionsOverlay from './components/PendingEvolutionsOverlay';
import SelfImprovementLog from './components/SelfImprovementLog';
import TaskManagerPanel from './components/TaskManagerPanel';
import PendingToolsPanel from './components/PendingToolsPanel';
import PendingSkillsPanel from './components/PendingSkillsPanel';
import ToolRegistryPanel from './components/ToolRegistryPanel';
import AutoEvolutionPanel from './components/AutoEvolutionPanel';
import CodePreviewModal from './components/CodePreviewModal';
import DiffModal from './components/DiffModal';
import ApprovalNotification from './components/ApprovalNotification';
import ObservabilityOverlay from './components/ObservabilityOverlay';
import ObservabilityPage from './components/ObservabilityPage';
import ToolsManagementPage from './components/ToolsManagementPage';
import SessionManagement from './components/SessionManagement';
import TraceOverlay from './components/TraceOverlay';
import './styles/variables.css';
import './styles/theme.css';
import './App.css';

function AppContent() {
  const globalState = useGlobalState();
  const toast = useToast();
  const [messages, setMessages] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark');
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
  const [activeMode, setActiveMode] = useState('chat');
  const [overlayOpen, setOverlayOpen] = useState(null);
  const [showStagingModal, setShowStagingModal] = useState(false);
  const [stagingParentId, setStagingParentId] = useState(null);
  const [codePreview, setCodePreview] = useState(null);

  const refreshPendingTools = async () => {
    const listRes = await fetch(`${API_URL}/pending-tools/list`);
    const listData = await listRes.json();
    globalState.updateState({ pendingTools: listData.pending_tools || [] });
  };

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  useEffect(() => {
    // Fetch available models on mount
    fetch(`${API_URL}/settings/models`)
      .then(res => res.json())
      .then(data => {
        setAvailableModels(data.available_models || {});
        setCurrentModel(data.current_model || 'mistral:latest');
      })
      .catch(err => {
        console.error('Failed to load models:', err);
        setAvailableModels({});
        setCurrentModel('mistral:latest');
      });
    
    // Listen for overlay open events from Header
    const handleOpenOverlay = (e) => {
      setOverlayOpen(e.detail);
    };
    window.addEventListener('openOverlay', handleOpenOverlay);
    return () => window.removeEventListener('openOverlay', handleOpenOverlay);
  }, []);

  useEffect(() => {
    // Fetch skills
    fetch(`${API_URL}/skills/list`)
      .then(res => res.json())
      .then(data => {
        globalState.updateState({
          skillCatalog: data.skills || [],
          skillCategories: data.categories || {}
        });
      })
      .catch(err => {
        console.error('Failed to load skills:', err);
        globalState.updateState({
          skillCatalog: [],
          skillCategories: {}
        });
      });
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
          max_iterations: 1,
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
      if (response.ok && data.success) {
        toast.success(`Tool activated: ${data.tool_name}`);
        await refreshPendingTools();
      } else {
        toast.error(`Failed to activate tool: ${data.detail || data.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error approving tool:', error);
      toast.error(`Failed to activate tool: ${error.message}`);
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
        await refreshPendingTools();
      }
    } catch (error) {
      console.error('Error rejecting tool:', error);
    }
  };

  const handleViewCode = (tool) => {
    setCodePreview(tool);
  };

  const handleRunToolTests = async (toolId) => {
    try {
      const response = await fetch(`${API_URL}/pending-tools/${toolId}/test`, {
        method: 'POST'
      });
      const data = await response.json();
      if (response.ok && data.success) {
        toast.success(`Tests passed: ${data.passed_tests}/${data.total_tests} (Quality: ${data.overall_quality_score})`);
        await refreshPendingTools();
      } else {
        toast.error(`Tests failed: ${data.detail || 'Unknown error'}`);
      }
    } catch (error) {
      toast.error(`Failed to run tests: ${error.message}`);
    }
  };

  const handleClearCache = async () => {
    if (!window.confirm('Clear all caches? This will clear LLM cache, tool execution cache, and temporary data.')) return;
    
    try {
      const response = await fetch(`${API_URL}/cache/clear`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      if (response.ok) {
        toast.success('All caches cleared successfully');
      } else {
        const data = await response.json();
        toast.error('Failed to clear cache: ' + (data.detail || 'Unknown error'));
      }
    } catch (error) {
      toast.error('Failed to clear cache: ' + error.message);
    }
  };

  const handleThemeToggle = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
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
      // Let backend/LLM decide: task planning or direct answer
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId })
      });

      const data = await response.json();
      
      if (data.response) {
        const assistantMsg = {
          role: 'assistant',
          content: data.response,
          timestamp: new Date().toLocaleTimeString(),
          components: data.execution_result?.components || null,
          execution_result: data.execution_result || null,
          skill: data.execution_result?.selected_skill || null,
          category: data.execution_result?.selected_category || null,
          ui_renderer: data.execution_result?.ui_renderer || null
        };
        setMessages(prev => [...prev, assistantMsg]);
      }
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

  const handleFloatingAction = (action) => {
    if (action === 'observability') {
      setActiveMode('observability');
    } else if (action === 'tools-management') {
      setActiveMode('tools-management');
    } else {
      setOverlayOpen(action);
    }
  };

  const renderOverlayContent = () => {
    switch (overlayOpen) {
      case 'logs':
        return (
          <SelfImprovementLog 
            logs={globalState.logs}
            onApprove={handleApprove}
            onReject={handleReject}
            onViewDiff={handleViewDiff}
            onClearLogs={handleClearLogs}
            onSaveLogs={handleSaveLogs}
          />
        );
      case 'tasks':
        return (
          <TaskManagerPanel 
            taskStatus={globalState.taskManager}
            onAbortTask={handleAbortTask}
            onViewStaging={handleViewStaging}
          />
        );
      case 'pending':
        if (activeMode === 'tools') {
          return (
            <PendingToolsPanel 
              pendingTools={globalState.pendingTools}
              onApprove={handleApproveTool}
              onReject={handleRejectTool}
              onViewCode={handleViewCode}
              onRunTests={handleRunToolTests}
            />
          );
        } else if (activeMode === 'evolution') {
          return <PendingEvolutionsOverlay 
            onOpenQuality={() => setOverlayOpen('quality')}
          />;
        }
        return null;
      case 'pending-skills':
        return <PendingSkillsPanel />;
      case 'registry':
        return <ToolRegistryPanel apiUrl={API_URL} />;
      case 'sync':
        return <ToolRegistryPanel apiUrl={API_URL} />;
      case 'observability':
        return <ObservabilityOverlay />;
      case 'quality':
        return <QualityOverlay />;
      case 'auto-evolution':
        return <AutoEvolutionPanel onClose={() => setOverlayOpen(null)} />;
      case 'sessions':
        return <SessionManagement onClose={() => setOverlayOpen(null)} />;
      case 'history':
        return <div style={{padding: '40px', textAlign: 'center', color: 'white'}}>Evolution History</div>;
      case 'tasks':
        return (
          <TaskManagerPanel 
            taskStatus={globalState.taskManager}
            onAbortTask={handleAbortTask}
            onViewStaging={handleViewStaging}
          />
        );
      default:
        return null;
    }
  };

  const getOverlayTitle = () => {
    const titles = {
      logs: 'Activity Logs',
      tasks: 'Active Tasks',
      pending: activeMode === 'tools' ? 'Pending Tools' : 'Pending Evolutions',
      'pending-skills': 'Pending Skills',
      registry: 'Tool Registry',
      sync: 'Tool Registry',
      quality: 'Quality Dashboard',
      'auto-evolution': 'Auto-Evolution',
      sessions: 'Session Management',
      history: 'Evolution History',
    };
    return titles[overlayOpen] || '';
  };

  return (
    <ErrorBoundary>
      <div className={`app mode-${activeMode}`}>
        <TraceOverlay />
        
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
            <AlertTriangle size={20} /> Backend Disconnected
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
          onOpenObservability={() => setActiveMode('observability')}
          onOpenAutoEvolution={() => setOverlayOpen('auto-evolution')}
          activeMode={activeMode}
          onModeChange={setActiveMode}
          theme={theme}
          onThemeToggle={handleThemeToggle}
        />
        
        {activeMode === 'observability' ? (
          <ObservabilityPage onBack={() => setActiveMode('chat')} />
        ) : activeMode === 'tools-management' ? (
          <ToolsManagementPage onBack={() => setActiveMode('chat')} />
        ) : (
          <MainCanvas 
            mode={activeMode}
            messages={messages}
            onSendMessage={handleSendMessage}
            isProcessing={isProcessing}
            skills={globalState.skillCatalog || []}
            onFloatingAction={handleFloatingAction}
            onModeChange={setActiveMode}
            loopStatus={{
              running: globalState.running,
              iteration: globalState.iteration,
              maxIterations: globalState.maxIterations
            }}
            onStatusChange={(status) => globalState.updateState(status)}
          />
        )}
        
        <RightOverlay
          isOpen={overlayOpen !== null}
          onClose={() => setOverlayOpen(null)}
          title={getOverlayTitle()}
          width={overlayOpen === 'quality' ? '60%' : overlayOpen === 'auto-evolution' ? '500px' : '50%'}
        >
          {renderOverlayContent()}
        </RightOverlay>
        
        {selectedProposal && (
          <DiffModal
            proposal={selectedProposal}
            onClose={() => setSelectedProposal(null)}
            onApprove={() => handleApprove(selectedProposal.id)}
            onReject={() => handleReject(selectedProposal.id)}
          />
        )}
        
        {codePreview && (
          <CodePreviewModal
            tool={codePreview}
            onClose={() => setCodePreview(null)}
          />
        )}
        
        <button
          onClick={handleClearCache}
          className="clear-cache-button"
          title="Clear all caches"
        >
          🗑️ Clear Cache
        </button>
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
