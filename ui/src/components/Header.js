import React from 'react';
import './Header.css';

function Header({ onStartLoop, onStopLoop, loopStatus, customPrompt, onCustomPromptChange, 
                  dryRun, onDryRunChange, availableModels, currentModel, onModelChange }) {
  return (
    <header className="header">
      <div className="header-left">
        <h1 className="logo">CUA Agent</h1>
        <span className="status-badge">
          <span className={`status-dot ${loopStatus.running ? 'running' : 'stopped'}`}></span>
          {loopStatus.running ? `Running (${loopStatus.iteration}/${loopStatus.maxIterations})` : 'Idle'}
        </span>
        {!loopStatus.running && Object.keys(availableModels).length > 0 && (
          <select 
            value={Object.keys(availableModels).find(key => availableModels[key].name === currentModel) || 'mistral'}
            onChange={(e) => onModelChange(e.target.value)}
            style={{ marginLeft: '15px', padding: '5px 10px', borderRadius: '4px' }}
          >
            {Object.entries(availableModels).map(([key, model]) => (
              <option key={key} value={key}>
                {model.description || model.name}
              </option>
            ))}
          </select>
        )}
      </div>
      
      <div className="header-right">
        {!loopStatus.running && (
          <>
            <input
              type="text"
              className="custom-prompt-input"
              placeholder="Custom focus (optional): e.g., 'Add tests for HTTP tool'"
              value={customPrompt}
              onChange={(e) => onCustomPromptChange(e.target.value)}
            />
            <label style={{ marginLeft: '10px', display: 'flex', alignItems: 'center', gap: '5px' }}>
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(e) => onDryRunChange(e.target.checked)}
              />
              <span>Preview Only (Dry-run)</span>
            </label>
          </>
        )}
        
        {!loopStatus.running ? (
          <button className="btn btn-primary" onClick={onStartLoop}>
            <span className="btn-icon">▶</span>
            Start Self-Improvement
          </button>
        ) : (
          <>
            <button className="btn btn-warning" onClick={() => onStopLoop('graceful')}>
              <span className="btn-icon">⏸</span>
              Stop After Current
            </button>
            <button className="btn btn-danger" onClick={() => onStopLoop('immediate')}>
              <span className="btn-icon">⏹</span>
              Emergency Stop
            </button>
          </>
        )}
      </div>
    </header>
  );
}

export default Header;
