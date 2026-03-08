import React, { useState, useEffect } from 'react';
import { Play, Pause, Square, Repeat, Zap, Wrench } from 'lucide-react';
import { API_URL } from '../config';
import TaskManagerPanel from './TaskManagerPanel';
import SelfImprovementLog from './SelfImprovementLog';
import CollapsibleSection from './CollapsibleSection';
import './AgentControlPanel.css';

function AgentControlPanel({ 
  loopStatus, 
  onStartLoop,
  onStartContinuous,
  onStopLoop, 
  customPrompt, 
  onCustomPromptChange,
  taskStatus,
  onAbortTask,
  onViewStaging,
  logs,
  onApprove,
  onReject,
  onViewDiff,
  onClearLogs,
  onSaveLogs
}) {
  const [evolutionMode, setEvolutionMode] = useState(false);

  useEffect(() => {
    if (loopStatus.evolution_mode !== undefined) {
      setEvolutionMode(loopStatus.evolution_mode);
    }
  }, [loopStatus.evolution_mode]);

  const toggleEvolution = async () => {
    const endpoint = evolutionMode ? '/improvement/evolution/disable' : '/improvement/evolution/enable';
    try {
      await fetch(`${API_URL}${endpoint}`, { method: 'POST' });
      setEvolutionMode(!evolutionMode);
    } catch (err) {
      console.error('Failed to toggle evolution mode:', err);
    }
  };
  return (
    <div className="agent-control-panel">
      <div className="control-section">
        <CollapsibleSection title="Self-Improvement" defaultOpen={true}>
          <div className="control-card">
          <div className="status-display">
            <div className="status-info">
              <span className={`status-indicator ${loopStatus.running ? 'running' : 'idle'}`}></span>
              <span className="status-text">
                {loopStatus.running ? 'Active' : 'Idle'}
              </span>
            </div>
            {loopStatus.running && (
              <span className="status-badge">
                {loopStatus.iteration}/{loopStatus.maxIterations} iterations
              </span>
            )}
          </div>

          {!loopStatus.running && (
            <input
              type="text"
              className="prompt-input"
              placeholder="Custom focus (optional): e.g., 'Add tests for HTTP tool'"
              value={customPrompt}
              onChange={(e) => onCustomPromptChange(e.target.value)}
            />
          )}

          <div className="control-actions">
            {!loopStatus.running && (
              <button 
                className="control-btn" 
                onClick={toggleEvolution}
                style={{background: evolutionMode ? '#10b981' : '#6b7280', marginBottom: '8px'}}
              >
                {evolutionMode ? <Zap size={16} /> : <Wrench size={16} />}
                {evolutionMode ? 'Evolution Mode' : 'Deterministic Mode'}
              </button>
            )}
            {!loopStatus.running ? (
              <>
                <button className="control-btn primary" onClick={onStartLoop}>
                  <Play size={16} />
                  Start (1 iteration)
                </button>
                <button className="control-btn primary" onClick={onStartContinuous} style={{background: '#8b5cf6'}}>
                  <Repeat size={16} />
                  Start Continuous
                </button>
              </>
            ) : (
              <>
                <button className="control-btn warning" onClick={() => onStopLoop('graceful')}>
                  <Pause size={16} />
                  Stop After Current
                </button>
                <button className="control-btn danger" onClick={() => onStopLoop('immediate')}>
                  <Square size={16} />
                  Stop Immediately
                </button>
              </>
            )}
          </div>
          </div>
        </CollapsibleSection>
      </div>

      <div className="scrollable-content">
        <CollapsibleSection title="Activity Logs" defaultOpen={true}>
        <SelfImprovementLog 
          logs={logs}
          onApprove={onApprove}
          onReject={onReject}
          onViewDiff={onViewDiff}
          onClearLogs={onClearLogs}
          onSaveLogs={onSaveLogs}
        />
      </CollapsibleSection>

      <CollapsibleSection title="Active Tasks" defaultOpen={true}>
        <TaskManagerPanel 
          taskStatus={taskStatus}
          onAbortTask={onAbortTask}
          onViewStaging={onViewStaging}
        />
        </CollapsibleSection>
      </div>
    </div>
  );
}

export default AgentControlPanel;
