import React from 'react';
import { MessageSquare, Wrench, Zap, Database } from 'lucide-react';
import './ModeTabBar.css';

function ModeTabBar({ activeMode, onModeChange }) {
  const modes = [
    { id: 'chat', label: 'CUA Chat', icon: MessageSquare },
    { id: 'tools', label: 'Tools', icon: Wrench },
    { id: 'evolution', label: 'Evolution', icon: Zap },
    { id: 'observability', label: 'Observability', icon: Database }
  ];

  return (
    <div className="mode-tab-bar">
      {modes.map(mode => {
        const Icon = mode.icon;
        return (
          <button
            key={mode.id}
            className={`mode-tab ${activeMode === mode.id ? 'active' : ''}`}
            onClick={() => onModeChange(mode.id)}
          >
            <Icon size={18} />
            <span>{mode.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default ModeTabBar;
