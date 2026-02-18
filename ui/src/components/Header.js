import React, { useState } from 'react';
import { Settings, BarChart3, Calendar } from 'lucide-react';
import './Header.css';

function Header({ loopStatus, availableModels, currentModel, onModelChange, onOpenAnalytics, onOpenScheduler }) {
  const [showSettings, setShowSettings] = useState(false);

  return (
    <header className="header">
      <div className="header-left">
        <h1 className="logo">CUA Agent</h1>
        <span className="status-badge">
          <span className={`status-dot ${loopStatus.running ? 'running' : 'stopped'}`}></span>
          {loopStatus.running ? `Running (${loopStatus.iteration}/${loopStatus.maxIterations})` : 'Idle'}
        </span>
      </div>
      
      <div className="header-right">
        <button className="btn btn-settings" onClick={() => setShowSettings(!showSettings)}>
          <Settings size={18} />
        </button>
      </div>

      {showSettings && (
        <div className="settings-dropdown">
          <div className="settings-item">
            <label>Model:</label>
            <select 
              value={Object.keys(availableModels).find(key => availableModels[key].name === currentModel) || 'mistral'}
              onChange={(e) => onModelChange(e.target.value)}
            >
              {Object.entries(availableModels).map(([key, model]) => (
                <option key={key} value={key}>
                  {model.description || model.name}
                </option>
              ))}
            </select>
          </div>
          <div className="settings-divider"></div>
          <button className="settings-menu-item" onClick={() => { onOpenAnalytics(); setShowSettings(false); }}>
            <BarChart3 size={16} />
            Analytics
          </button>
          <button className="settings-menu-item" onClick={() => { onOpenScheduler(); setShowSettings(false); }}>
            <Calendar size={16} />
            Scheduler
          </button>
        </div>
      )}
    </header>
  );
}

export default Header;
