import React, { useState, useEffect } from 'react';
import { Play, Square, Settings, RefreshCw, Activity } from 'lucide-react';
import { useToast } from './Toast';
import './AutoEvolutionPanel.css';

const AutoEvolutionPanel = ({ onClose }) => {
  const toast = useToast();
  const [status, setStatus] = useState(null);
  const [queue, setQueue] = useState([]);
  const [scanning, setScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(null);
  const [config, setConfig] = useState({
    mode: 'balanced',
    scan_interval: 3600,
    max_concurrent: 2,
    min_health_threshold: 50,
    auto_approve_threshold: 90,
    learning_enabled: true
  });
  const [loading, setLoading] = useState(false);
  const [showConfig, setShowConfig] = useState(false);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, scanning ? 2000 : 5000);
    return () => clearInterval(interval);
  }, [scanning]);

  const fetchStatus = async () => {
    try {
      const res = await fetch('http://localhost:8000/auto-evolution/status');
      const data = await res.json();
      setStatus(data);
      setScanning(data.scanning || false);
      setScanProgress(data.scan_progress);
      if (data.config) setConfig(data.config);
      
      if (data.running || data.scanning) {
        const queueRes = await fetch('http://localhost:8000/auto-evolution/queue');
        const queueData = await queueRes.json();
        setQueue(queueData.queue || []);
      }
    } catch (err) {
      console.error('Failed to fetch status:', err);
    }
  };

  const handleStart = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/auto-evolution/start', { method: 'POST' });
      if (res.ok) {
        toast.success('Auto-evolution started');
        await fetchStatus();
      } else {
        const data = await res.json();
        toast.error('Failed to start: ' + (data.detail || 'Unknown error'));
      }
    } catch (err) {
      toast.error('Failed to start: ' + err.message);
    }
    setLoading(false);
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/auto-evolution/stop', { method: 'POST' });
      if (res.ok) {
        toast.success('Auto-evolution stopped');
        await fetchStatus();
      } else {
        toast.error('Failed to stop');
      }
    } catch (err) {
      toast.error('Failed to stop: ' + err.message);
    }
    setLoading(false);
  };

  const handleConfigUpdate = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/auto-evolution/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      if (res.ok) {
        toast.success('Configuration updated');
        await fetchStatus();
      } else {
        toast.error('Failed to update config');
      }
    } catch (err) {
      toast.error('Failed to update config: ' + err.message);
    }
    setLoading(false);
  };

  const handleTriggerScan = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/auto-evolution/trigger-scan', { method: 'POST' });
      if (res.ok) {
        toast.success('Tool scan completed - check queue');
        await fetchStatus();
      } else {
        const data = await res.json();
        toast.error('Scan failed: ' + (data.detail || 'Unknown error'));
      }
    } catch (err) {
      toast.error('Scan failed: ' + err.message);
    }
    setLoading(false);
  };

  return (
    <div className="auto-evolution-panel">
      <div className="panel-header">
        <h2><Activity size={24} /> Auto-Evolution</h2>
        <button onClick={onClose} className="close-btn">×</button>
      </div>

      <div className="panel-content">
        {/* Status Section */}
        <div className="status-section">
          <div className="status-indicator">
            <div className={`status-dot ${status?.running ? 'running' : 'stopped'}`} />
            <span>{status?.running ? 'Running' : 'Stopped'}</span>
          </div>
          
          <div className="control-buttons">
            {!status?.running ? (
              <button onClick={handleStart} disabled={loading || scanning} className="btn-start">
                <Play size={16} /> Start
              </button>
            ) : (
              <button onClick={handleStop} disabled={loading} className="btn-stop">
                <Square size={16} /> Stop
              </button>
            )}
            <button onClick={handleTriggerScan} disabled={loading || scanning} className="btn-scan">
              <RefreshCw size={16} className={scanning ? 'spin' : ''} /> {scanning ? 'Scanning...' : 'Scan Now'}
            </button>
          </div>
        </div>

        {/* Scan Progress */}
        {scanning && scanProgress && (
          <div className="scan-progress-section">
            <div className="progress-bar">
              <div 
                className="progress-fill" 
                style={{width: `${(scanProgress.current / scanProgress.total) * 100}%`}}
              />
            </div>
            <div className="progress-text">
              Analyzing {scanProgress.tool}... ({scanProgress.current}/{scanProgress.total})
            </div>
          </div>
        )}

        {/* Config Section */}
        <div className="config-section">
          <button className="config-toggle" onClick={() => setShowConfig(!showConfig)}>
            <Settings size={18} /> Configuration
          </button>
          
          {showConfig && (
          <>
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

          <button onClick={handleConfigUpdate} disabled={loading} className="btn-update">
            Update Configuration
          </button>
          </>
          )}
        </div>

        {/* Queue Section - Always show if there are items */}
        {queue.length > 0 && (
          <div className="queue-section">
            <h3>Evolution Queue ({queue.length})</h3>
            <div className="queue-list">
                {queue.map((item, idx) => (
                  <div key={idx} className="queue-item">
                    <div className="queue-tool">{item.tool_name}</div>
                    <div className="queue-priority">Priority: {(item.priority_score || 0).toFixed(1)}</div>
                    <div className="queue-reason">{item.reason}</div>
                    <div className="queue-status">{item.status}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default AutoEvolutionPanel;
