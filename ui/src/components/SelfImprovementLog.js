import React, { useEffect, useRef } from 'react';
import './SelfImprovementLog.css';

function SelfImprovementLog({ logs, onApprove, onReject, onViewDiff, onClearLogs, onSaveLogs }) {
  const logEndRef = useRef(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const getLogIcon = (type) => {
    const icons = {
      start: '🚀',
      iteration: '🔄',
      analysis: '🔍',
      proposal: '💡',
      approval_needed: '⏸',
      approved: '✅',
      rejected: '❌',
      testing: '🧪',
      success: '✓',
      error: '⚠',
      stop: '⏹'
    };
    return icons[type] || '•';
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
            💾
          </button>
          <button className="btn-icon" onClick={onClearLogs} title="Clear logs">
            🗑️
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
