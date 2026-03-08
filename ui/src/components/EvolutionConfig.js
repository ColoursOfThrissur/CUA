import React, { useState, useEffect } from 'react';
import { Settings } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './EvolutionConfig.css';

function EvolutionConfig() {
  const toast = useToast();
  const [config, setConfig] = useState({
    mode: 'balanced',
    scan_interval: 3600,
    max_concurrent: 2,
    min_health_threshold: 50,
    auto_approve_threshold: 90,
    learning_enabled: true,
    enable_enhancements: true,
    max_new_tools_per_scan: 1
  });
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    try {
      const res = await fetch(`${API_URL}/auto-evolution/status`);
      const data = await res.json();
      if (data.config) setConfig(data.config);
    } catch (err) {
      console.error('Failed to fetch config:', err);
    }
  };

  const handleUpdate = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/auto-evolution/config`, {
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
      toast.error('Failed to update config: ' + err.message);
    }
    setLoading(false);
  };

  return (
    <div className="evolution-config">
      <button className="config-toggle" onClick={() => setIsOpen(!isOpen)}>
        <Settings size={16} />
        <span>Configuration</span>
        <span className={`arrow ${isOpen ? 'open' : ''}`}>▼</span>
      </button>

      {isOpen && (
        <div className="config-content">
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

            <div className="config-item">
              <label>Max New Tools / Scan</label>
              <input type="number" value={config.max_new_tools_per_scan ?? 1}
                onChange={e => setConfig({...config, max_new_tools_per_scan: parseInt(e.target.value)})} />
            </div>
          </div>

          <button onClick={handleUpdate} disabled={loading} className="btn-update">
            Update Configuration
          </button>
        </div>
      )}
    </div>
  );
}

export default EvolutionConfig;
