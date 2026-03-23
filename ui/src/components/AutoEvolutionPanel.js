import React, { useState, useEffect } from 'react';
import { Play, Square, Settings, RefreshCw, Activity, PauseCircle, FastForward } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import TraceConsole from './TraceConsole';
import './AutoEvolutionPanel.css';

const AutoEvolutionPanel = ({ onClose, embedded = false }) => {
  const toast = useToast();
  const [status, setStatus] = useState(null);
  const [coordinatedStatus, setCoordinatedStatus] = useState(null);
  const [queue, setQueue] = useState([]);
  const [scanning, setScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(null);
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
  const [showConfig, setShowConfig] = useState(false);
  const [coordinatedConfig, setCoordinatedConfig] = useState({
    interval_seconds: 21600,
    improvement_iterations_per_cycle: 3,
    max_evolutions_per_cycle: 2,
    dry_run: false,
    min_usefulness_score: 0.35,
    max_consecutive_low_value_cycles: 2,
    pause_on_low_value: true
  });

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, scanning ? 2000 : 5000);
    return () => clearInterval(interval);
  }, [scanning]);

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/auto-evolution/status`);
      const data = await res.json();
      setStatus(data);
      setScanning(data.scanning || false);
      setScanProgress(data.scan_progress);
      if (data.config) setConfig(data.config);
      
      // Always fetch queue to show items even when not running
      try {
        const queueRes = await fetch(`${API_URL}/auto-evolution/queue`);
        const queueData = await queueRes.json();
        setQueue(queueData.queue || []);
      } catch (err) {
        // Queue fetch failed, keep existing queue
      }

      try {
        const coordinatedRes = await fetch(`${API_URL}/auto-evolution/coordinated/status`);
        const coordinatedData = await coordinatedRes.json();
        setCoordinatedStatus(coordinatedData);
        if (coordinatedData.config) {
          setCoordinatedConfig(prev => ({ ...prev, ...coordinatedData.config }));
        }
      } catch (err) {
        // Coordinated status fetch failed, keep existing state
      }
    } catch (err) {
      console.error('Failed to fetch status:', err);
    }
  };

  const handleStart = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/auto-evolution/start`, { method: 'POST' });
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
      const res = await fetch(`${API_URL}/auto-evolution/stop`, { method: 'POST' });
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
      const res = await fetch(`${API_URL}/auto-evolution/config`, {
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
      const res = await fetch(`${API_URL}/auto-evolution/trigger-scan`, { method: 'POST' });
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

  const handleStartCoordinated = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/auto-evolution/coordinated/start`, { method: 'POST' });
      if (res.ok) {
        toast.success('Coordinated autonomy started');
        await fetchStatus();
      } else {
        const data = await res.json();
        toast.error('Failed to start coordinated mode: ' + (data.detail || 'Unknown error'));
      }
    } catch (err) {
      toast.error('Failed to start coordinated mode: ' + err.message);
    }
    setLoading(false);
  };

  const handleStopCoordinated = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/auto-evolution/coordinated/stop`, { method: 'POST' });
      if (res.ok) {
        toast.success('Coordinated autonomy stopped');
        await fetchStatus();
      } else {
        const data = await res.json();
        toast.error('Failed to stop coordinated mode: ' + (data.detail || 'Unknown error'));
      }
    } catch (err) {
      toast.error('Failed to stop coordinated mode: ' + err.message);
    }
    setLoading(false);
  };

  const handleRunCoordinatedCycle = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/auto-evolution/coordinated/run-cycle`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        toast.success(`Coordinated cycle completed${data?.quality_gate?.should_pause ? ' and paused' : ''}`);
        await fetchStatus();
      } else {
        const data = await res.json();
        toast.error('Failed to run coordinated cycle: ' + (data.detail || 'Unknown error'));
      }
    } catch (err) {
      toast.error('Failed to run coordinated cycle: ' + err.message);
    }
    setLoading(false);
  };

  const handleCoordinatedConfigUpdate = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/auto-evolution/coordinated/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(coordinatedConfig)
      });
      if (res.ok) {
        toast.success('Coordinated config updated');
        await fetchStatus();
      } else {
        const data = await res.json();
        toast.error('Failed to update coordinated config: ' + (data.detail || 'Unknown error'));
      }
    } catch (err) {
      toast.error('Failed to update coordinated config: ' + err.message);
    }
    setLoading(false);
  };

  return (
    <div className="auto-evolution-panel">
      <div className="panel-header">
        <h2><Activity size={24} /> Auto-Evolution</h2>
        {!embedded && <button onClick={onClose} className="close-btn">×</button>}
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

        <div className="status-section coordinated-section">
          <div className="section-heading">Coordinated Autonomy</div>
          {coordinatedStatus?.reload_blocked && (
            <div className="quality-banner warning">
              <span>{coordinatedStatus.reload_warning || 'Reload mode is enabled. Coordinated autonomy is blocked.'}</span>
            </div>
          )}
          <div className="status-indicator">
            <div className={`status-dot ${coordinatedStatus?.running ? 'running' : 'stopped'}`} />
            <span>{coordinatedStatus?.running ? 'Running' : 'Stopped'}</span>
          </div>

          {coordinatedStatus?.paused_reason && (
            <div className="quality-banner paused">
              <PauseCircle size={16} />
              <span>Paused: {coordinatedStatus.paused_reason}</span>
            </div>
          )}

          {coordinatedStatus?.last_cycle?.quality_gate && (
            <div className={`quality-banner ${coordinatedStatus.last_cycle.quality_gate.low_value ? 'warning' : 'ok'}`}>
              <span>
                Quality score: {coordinatedStatus.last_cycle.quality_gate.score}
                {' '}| Low-value cycles: {coordinatedStatus.last_cycle.quality_gate.consecutive_low_value_cycles}
              </span>
              <span>{coordinatedStatus.last_cycle.quality_gate.reason}</span>
            </div>
          )}

          <div className="coordinated-metrics">
            <div className="metric-card">
              <div className="metric-label">Cycles</div>
              <div className="metric-value">{coordinatedStatus?.cycle_count ?? 0}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Pending Tools</div>
              <div className="metric-value">{coordinatedStatus?.last_cycle?.pending_summary?.after?.pending_tools ?? 0}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Pending Evolutions</div>
              <div className="metric-value">{coordinatedStatus?.last_cycle?.pending_summary?.after?.pending_evolutions ?? 0}</div>
            </div>
          </div>

          <div className="control-buttons">
            {!coordinatedStatus?.running ? (
              <button onClick={handleStartCoordinated} disabled={loading || coordinatedStatus?.reload_blocked} className="btn-start">
                <Play size={16} /> Start Cycle Loop
              </button>
            ) : (
              <button onClick={handleStopCoordinated} disabled={loading} className="btn-stop">
                <Square size={16} /> Stop Cycle Loop
              </button>
            )}
            <button onClick={handleRunCoordinatedCycle} disabled={loading || coordinatedStatus?.running || coordinatedStatus?.reload_blocked} className="btn-scan">
              <FastForward size={16} /> Run One Cycle
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

            <div className="config-item">
              <label>Max New Tools / Scan</label>
              <input
                type="number"
                value={config.max_new_tools_per_scan ?? 1}
                onChange={e => setConfig({...config, max_new_tools_per_scan: parseInt(e.target.value)})}
              />
            </div>
          </div>

          <button onClick={handleConfigUpdate} disabled={loading} className="btn-update">
            Update Configuration
          </button>

          <div className="coordinated-config-block">
            <h3>Coordinated Cycle Config</h3>
            <div className="config-grid">
              <div className="config-item">
                <label>Cycle Interval (seconds)</label>
                <input type="number" value={coordinatedConfig.interval_seconds}
                  onChange={e => setCoordinatedConfig({...coordinatedConfig, interval_seconds: parseInt(e.target.value)})} />
              </div>
              <div className="config-item">
                <label>Improvement Iterations / Cycle</label>
                <input type="number" value={coordinatedConfig.improvement_iterations_per_cycle}
                  onChange={e => setCoordinatedConfig({...coordinatedConfig, improvement_iterations_per_cycle: parseInt(e.target.value)})} />
              </div>
              <div className="config-item">
                <label>Max Evolutions / Cycle</label>
                <input type="number" value={coordinatedConfig.max_evolutions_per_cycle}
                  onChange={e => setCoordinatedConfig({...coordinatedConfig, max_evolutions_per_cycle: parseInt(e.target.value)})} />
              </div>
              <div className="config-item">
                <label>Min Usefulness Score</label>
                <input type="number" step="0.05" value={coordinatedConfig.min_usefulness_score}
                  onChange={e => setCoordinatedConfig({...coordinatedConfig, min_usefulness_score: parseFloat(e.target.value)})} />
              </div>
              <div className="config-item">
                <label>Max Low-Value Cycles</label>
                <input type="number" value={coordinatedConfig.max_consecutive_low_value_cycles}
                  onChange={e => setCoordinatedConfig({...coordinatedConfig, max_consecutive_low_value_cycles: parseInt(e.target.value)})} />
              </div>
              <div className="config-item">
                <label>Pause On Low Value</label>
                <input type="checkbox" checked={coordinatedConfig.pause_on_low_value}
                  onChange={e => setCoordinatedConfig({...coordinatedConfig, pause_on_low_value: e.target.checked})} />
              </div>
              <div className="config-item">
                <label>Dry Run</label>
                <input type="checkbox" checked={coordinatedConfig.dry_run}
                  onChange={e => setCoordinatedConfig({...coordinatedConfig, dry_run: e.target.checked})} />
              </div>
            </div>
            <button onClick={handleCoordinatedConfigUpdate} disabled={loading} className="btn-update">
              Update Coordinated Config
            </button>
          </div>
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
          </div>
        )}

        <TraceConsole />
      </div>
    </div>
  );
};

export default AutoEvolutionPanel;

