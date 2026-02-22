import React, { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Eye, Package, BarChart3, Settings } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './PendingEvolutionsOverlay.css';

function PendingEvolutionsOverlay({ onOpenQuality }) {
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showConfig, setShowConfig] = useState(false);
  const [config, setConfig] = useState({
    mode: 'balanced',
    scan_interval: 3600,
    max_concurrent: 2,
    min_health_threshold: 50,
    auto_approve_threshold: 90,
    learning_enabled: true,
    enable_enhancements: true
  });
  const [configLoading, setConfigLoading] = useState(false);
  const toast = useToast();

  useEffect(() => {
    fetchPending();
    fetchConfig();
  }, []);

  const fetchPending = async () => {
    try {
      const res = await fetch(`${API_URL}/evolution/pending`);
      const data = await res.json();
      console.log('Pending evolutions response:', data);
      setPending(data.pending_evolutions || []);
    } catch (err) {
      console.error('Failed to fetch pending evolutions:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchConfig = async () => {
    try {
      const res = await fetch('http://localhost:8000/auto-evolution/status');
      const data = await res.json();
      if (data.config) setConfig(data.config);
    } catch (err) {
      console.error('Failed to fetch config:', err);
    }
  };

  const handleUpdateConfig = async () => {
    setConfigLoading(true);
    try {
      const res = await fetch('http://localhost:8000/auto-evolution/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      if (res.ok) {
        toast.success('Configuration updated');
      } else {
        toast.error('Failed to update config');
      }
    } catch (err) {
      toast.error('Failed to update: ' + err.message);
    }
    setConfigLoading(false);
  };

  const handleApprove = async (toolName) => {
    try {
      const res = await fetch(`${API_URL}/evolution/approve/${toolName}`, { method: 'POST' });
      const data = await res.json();
      
      if (data.needs_dependencies) {
        toast.error(`Dependencies needed: ${data.dependencies.missing_libraries.concat(data.dependencies.missing_services).join(', ')}`);
        // TODO: Show dependency resolution modal
        return;
      }
      
      if (data.success) {
        toast.success(`Evolution approved: ${toolName}`);
        fetchPending();
      } else {
        toast.error(data.error || 'Failed to approve');
      }
    } catch (err) {
      toast.error('Failed to approve evolution');
    }
  };

  const handleReject = async (toolName) => {
    try {
      const res = await fetch(`${API_URL}/evolution/reject/${toolName}`, { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        toast.success(`Evolution rejected: ${toolName}`);
        fetchPending();
      } else {
        toast.error(data.error || 'Failed to reject');
      }
    } catch (err) {
      toast.error('Failed to reject evolution');
    }
  };

  if (loading) return <div className="pending-loading">Loading...</div>;

  if (pending.length === 0) {
    return <div className="pending-empty">No pending evolutions</div>;
  }

  return (
    <div className="pending-evolutions-overlay">
      <div className="overlay-actions">
        <button className="action-icon-btn" onClick={() => setShowConfig(!showConfig)} title="Evolution Settings">
          <Settings size={18} />
        </button>
        <button className="action-icon-btn" onClick={onOpenQuality} title="Quality Dashboard">
          <BarChart3 size={18} />
        </button>
      </div>

      {showConfig && (
        <div className="config-dropdown">
          <h4>Configuration</h4>
          <div className="config-grid">
            <div className="config-item">
              <label>Mode</label>
              <select value={config.mode} onChange={e => setConfig({...config, mode: e.target.value})}>
                <option value="reactive">Reactive</option>
                <option value="balanced">Balanced</option>
                <option value="proactive">Proactive</option>
                <option value="experimental">Experimental</option>
              </select>
            </div>
            <div className="config-item">
              <label>Scan Interval (seconds)</label>
              <input type="number" value={config.scan_interval} 
                onChange={e => setConfig({...config, scan_interval: parseInt(e.target.value)})} />
            </div>
            <div className="config-item">
              <label>Max Concurrent</label>
              <input type="number" value={config.max_concurrent} 
                onChange={e => setConfig({...config, max_concurrent: parseInt(e.target.value)})} />
            </div>
            <div className="config-item">
              <label>Min Health Threshold</label>
              <input type="number" value={config.min_health_threshold} 
                onChange={e => setConfig({...config, min_health_threshold: parseInt(e.target.value)})} />
            </div>
            <div className="config-item">
              <label>Auto-Approve Threshold</label>
              <input type="number" value={config.auto_approve_threshold} 
                onChange={e => setConfig({...config, auto_approve_threshold: parseInt(e.target.value)})} />
            </div>
            <div className="config-item">
              <label>Learning Enabled</label>
              <input type="checkbox" checked={config.learning_enabled} 
                onChange={e => setConfig({...config, learning_enabled: e.target.checked})} />
            </div>
            <div className="config-item">
              <label>Enable Enhancements</label>
              <input type="checkbox" checked={config.enable_enhancements !== false} 
                onChange={e => setConfig({...config, enable_enhancements: e.target.checked})} />
            </div>
          </div>
          <button onClick={handleUpdateConfig} disabled={configLoading} className="btn-update-config">
            Update Configuration
          </button>
        </div>
      )}
      
      {pending.map(item => (
        <div key={item.tool_name} className="evolution-card">
          <div className="evolution-header">
            <h4>{item.tool_name}</h4>
            <span className="confidence-badge">
              {(item.proposal.confidence * 100).toFixed(0)}% confidence
            </span>
          </div>
          
          <p className="evolution-description">{item.proposal.description}</p>
          
          {item.proposal.changes && item.proposal.changes.length > 0 && (
            <div className="changes-list">
              <strong>Changes:</strong>
              <ul>
                {item.proposal.changes.map((change, idx) => (
                  <li key={idx}>{change}</li>
                ))}
              </ul>
            </div>
          )}

          {item.proposal.expected_outcome && (
            <div className="expected-outcome">
              <strong>Expected:</strong> {item.proposal.expected_outcome}
            </div>
          )}
          
          {item.proposal.dependencies && (item.proposal.dependencies.missing_libraries?.length > 0 || item.proposal.dependencies.missing_services?.length > 0) && (
            <div className="dependencies-warning" style={{background: 'rgba(239, 68, 68, 0.1)', padding: '10px', borderRadius: '6px', marginTop: '10px'}}>
              <strong style={{color: '#ef4444'}}>⚠️ Missing Dependencies:</strong>
              {item.proposal.dependencies.missing_libraries?.length > 0 && (
                <div style={{marginTop: '5px'}}>
                  <span style={{color: 'var(--text-secondary)'}}>Libraries:</span> {item.proposal.dependencies.missing_libraries.join(', ')}
                </div>
              )}
              {item.proposal.dependencies.missing_services?.length > 0 && (
                <div style={{marginTop: '5px'}}>
                  <span style={{color: 'var(--text-secondary)'}}>Services:</span> {item.proposal.dependencies.missing_services.join(', ')}
                </div>
              )}
            </div>
          )}

          <div className="evolution-actions">
            <button className="btn-approve" onClick={() => handleApprove(item.tool_name)}>
              <CheckCircle size={16} /> Approve
            </button>
            <button className="btn-reject" onClick={() => handleReject(item.tool_name)}>
              <XCircle size={16} /> Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

export default PendingEvolutionsOverlay;
