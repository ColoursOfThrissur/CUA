import React, { useState, useEffect } from 'react';
import { Settings, BarChart3, Calendar, Database, MessageSquare, Wrench, Zap, Sun, Moon, Activity, Bot } from 'lucide-react';
import './Header.css';

function Header({ loopStatus, availableModels, currentModel, onModelChange, onOpenObservability, activeMode, onModeChange, theme, onThemeToggle, onOpenAutoEvolution }) {
  const [showSettings, setShowSettings] = useState(false);

  const modes = [
    { id: 'chat', label: 'CUA Chat', icon: MessageSquare },
    { id: 'tools', label: 'Tools', icon: Wrench },
    { id: 'evolution', label: 'Evolution', icon: Zap }
  ];

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Tab' && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey) {
        const activeElement = document.activeElement;
        if (activeElement.tagName !== 'INPUT' && activeElement.tagName !== 'TEXTAREA') {
          e.preventDefault();
          const currentIndex = modes.findIndex(m => m.id === activeMode);
          const nextIndex = (currentIndex + 1) % modes.length;
          onModeChange(modes[nextIndex].id);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeMode, onModeChange]);

  return (
    <header className="header">
      <div className="header-left">
        <h1 className="logo">CUA Agent</h1>
        <span className="status-badge">
          <span className={`status-dot ${loopStatus.running ? 'running' : 'stopped'}`}></span>
          {loopStatus.running ? `Running (${loopStatus.iteration}/${loopStatus.maxIterations})` : 'Idle'}
        </span>
      </div>
      
      <div className="header-center">
        {modes.map(mode => {
          const Icon = mode.icon;
          return (
            <button
              key={mode.id}
              className={`mode-tab ${activeMode === mode.id ? 'active' : ''} mode-${mode.id}`}
              onClick={() => onModeChange(mode.id)}
            >
              <Icon size={18} />
              <span>{mode.label}</span>
            </button>
          );
        })}
      </div>
      
      <div className="header-right">
        <button 
          className="btn btn-auto-evolution" 
          onClick={onOpenAutoEvolution}
          title="Auto-Evolution"
        >
          <Bot size={18} />
        </button>
        <button 
          className="btn btn-theme" 
          onClick={onThemeToggle}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        >
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        <button 
          className="btn btn-settings" 
          onClick={() => onModeChange('tools-management')}
          title="Tools Management"
        >
          <Activity size={18} />
        </button>
        <button className="btn btn-settings" onClick={onOpenObservability}>
          <Database size={18} />
        </button>
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
          <button className="settings-menu-item" onClick={() => setShowSettings(false)}>
            <Database size={16} />
            Observability
          </button>
        </div>
      )}
    </header>
  );
}

export default Header;
