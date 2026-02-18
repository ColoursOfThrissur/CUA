import React from 'react';
import { Play, Pause, Square, Repeat } from 'lucide-react';
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
            {!loopStatus.running ? (
              <>
                <button className="control-btn primary" onClick={onStartLoop}>
                  <Play size={16} />
                  Start (5 iterations)
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
