import React from 'react';
import { Package, List, RefreshCw } from 'lucide-react';
import './FloatingActionBar.css';

function FloatingActionBar({ mode, onAction }) {
  const getButtons = () => {
    switch (mode) {
      case 'tools':
        return [
          { id: 'pending', label: 'Pending Tools', icon: Package },
          { id: 'registry', label: 'Registry', icon: List },
          { id: 'sync', label: 'Sync', icon: RefreshCw }
        ];
      case 'evolution':
        return [
          { id: 'pending', label: 'Pending', icon: Package }
        ];
      default:
        return [];
    }
  };

  const buttons = getButtons();

  if (buttons.length === 0) return null;

  return (
    <div className="floating-action-bar">
      {buttons.map(btn => {
        const Icon = btn.icon;
        return (
          <button
            key={btn.id}
            className="floating-btn"
            onClick={() => onAction(btn.id)}
          >
            <Icon size={16} />
            <span>{btn.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default FloatingActionBar;
