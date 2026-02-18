import React, { useEffect, useRef } from 'react';
import { Rocket, RotateCw, Search, Lightbulb, Pause, CheckCircle, XCircle, TestTube, Check, AlertTriangle, Square, Save, Trash2 } from 'lucide-react';
import './SelfImprovementLog.css';

function SelfImprovementLog({ logs, onApprove, onReject, onViewDiff, onClearLogs, onSaveLogs }) {
  const logEndRef = useRef(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const getLogIcon = (type) => {
    const icons = {
      start: <Rocket size={16} />,
      iteration: <RotateCw size={16} />,
      analysis: <Search size={16} />,
      proposal: <Lightbulb size={16} />,
      approval_needed: <Pause size={16} />,
      approved: <CheckCircle size={16} />,
      rejected: <XCircle size={16} />,
      testing: <TestTube size={16} />,
      success: <Check size={16} />,
      error: <AlertTriangle size={16} />,
      stop: <Square size={16} />
    };
    return icons[type] || <Check size={16} />;
  };

  const getLogClass = (type) => {
    if (type === 'error') return 'log-error';
    if (type === 'success') return 'log-success';
    if (type === 'approval_needed') return 'log-warning';
    return 'log-info';
  };

  return (
    <div className="improvement-log">
      <div className="log-header">
        <h3>Self-Improvement Activity Log</h3>
        <div className="log-header-actions">
          <button className="btn-icon" onClick={onSaveLogs} title="Save logs">
            <Save size={16} />
          </button>
          <button className="btn-icon" onClick={onClearLogs} title="Clear logs">
            <Trash2 size={16} />
          </button>
        </div>
      </div>
      
      <div className="log-content">
        {logs.length === 0 ? (
          <div className="log-empty">
            <p>No activity yet. Start self-improvement to see logs here.</p>
          </div>
        ) : (
          logs.map((log, index) => (
            <div key={index} className={`log-entry ${getLogClass(log.type)}`}>
              <span className="log-time">{log.timestamp}</span>
              <span className="log-icon">{getLogIcon(log.type)}</span>
              <span className="log-message">{log.message}</span>
              
              {log.type === 'approval_needed' && log.proposalId && (
                <div className="log-actions">
                  <button 
                    className="btn-small btn-view" 
                    onClick={() => onViewDiff(log.proposalId)}
                  >
                    View Diff
                  </button>
                  <button 
                    className="btn-small btn-approve" 
                    onClick={() => onApprove(log.proposalId)}
                  >
                    Approve
                  </button>
                  <button 
                    className="btn-small btn-reject" 
                    onClick={() => onReject(log.proposalId)}
                  >
                    Reject
                  </button>
                </div>
              )}
            </div>
          ))
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}

export default SelfImprovementLog;
