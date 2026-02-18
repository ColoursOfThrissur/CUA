import React, { useState } from 'react';
import { Wrench, Package, Database } from 'lucide-react';
import PendingToolsPanel from './PendingToolsPanel';
import PendingLibrariesPanel from './PendingLibrariesPanel';
import ToolRegistryPanel from './ToolRegistryPanel';
import './CombinedToolsPanel.css';

function CombinedToolsPanel({ pendingTools, onApprove, onReject, onViewCode, apiUrl }) {
  const [activeSubTab, setActiveSubTab] = useState('pending');

  return (
    <div className="combined-tools-panel">
      <div className="sub-tab-navigation">
        <button 
          className={`sub-tab-btn ${activeSubTab === 'pending' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('pending')}
        >
          <Wrench size={14} />
          Pending Tools
        </button>
        <button 
          className={`sub-tab-btn ${activeSubTab === 'libraries' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('libraries')}
        >
          <Package size={14} />
          Libraries
        </button>
        <button 
          className={`sub-tab-btn ${activeSubTab === 'registry' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('registry')}
        >
          <Database size={14} />
          Registry
        </button>
      </div>

      <div className="sub-tab-content">
        {activeSubTab === 'pending' && (
          <PendingToolsPanel 
            pendingTools={pendingTools}
            onApprove={onApprove}
            onReject={onReject}
            onViewCode={onViewCode}
          />
        )}
        {activeSubTab === 'libraries' && (
          <PendingLibrariesPanel apiUrl={apiUrl} />
        )}
        {activeSubTab === 'registry' && (
          <ToolRegistryPanel apiUrl={apiUrl} />
        )}
      </div>
    </div>
  );
}

export default CombinedToolsPanel;
