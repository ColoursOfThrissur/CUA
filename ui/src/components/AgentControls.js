import React, { useState } from 'react';
import { Play, Square, Repeat, Zap, Wrench } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './AgentControls.css';

function AgentControls({ loopStatus, onStatusChange }) {
  const [customPrompt, setCustomPrompt] = useState('');
  const [evolutionMode, setEvolutionMode] = useState(false);
  const toast = useToast();

  const handleStart = async () => {
    try {
      const res = await fetch(`${API_URL}/improvement/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          max_iterations: 1,
          custom_prompt: customPrompt || null
        })
      });
      
      if (res.ok) {
        toast.success('Self-improvement started');
        setCustomPrompt('');
        onStatusChange({ running: true });
      } else {
        const data = await res.json();
        toast.error(data.detail || 'Failed to start');
      }
    } catch (err) {
      toast.error('Failed to start: ' + err.message);
    }
  };

  const handleStartContinuous = async () => {
    try {
      const res = await fetch(`${API_URL}/improvement/start-continuous`, {
        method: 'POST'
      });
      
      if (res.ok) {
        toast.success('Continuous mode started');
        onStatusChange({ running: true });
      } else {
        const data = await res.json();
        toast.error(data.detail || 'Failed to start');
      }
    } catch (err) {
      toast.error('Failed to start: ' + err.message);
    }
  };

  const handleStop = async (mode) => {
    try {
      const res = await fetch(`${API_URL}/improvement/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      });
      
      if (res.ok) {
        toast.info('Stopping...');
        if (mode === 'immediate') {
          onStatusChange({ running: false });
        }
      }
    } catch (err) {
      toast.error('Failed to stop: ' + err.message);
    }
  };

  const toggleEvolution = async () => {
    const endpoint = evolutionMode ? '/improvement/evolution/disable' : '/improvement/evolution/enable';
    try {
      await fetch(`${API_URL}${endpoint}`, { method: 'POST' });
      setEvolutionMode(!evolutionMode);
      toast.success(evolutionMode ? 'Evolution disabled' : 'Evolution enabled');
    } catch (err) {
      toast.error('Failed to toggle evolution');
    }
  };

  return (
    <div className="agent-controls">
      <div className="status-bar">
        <div className="status-indicator-group">
          <span className={`status-dot ${loopStatus.running ? 'active' : 'idle'}`}></span>
          <span className="status-text">
            {loopStatus.running ? 'Active' : 'Idle'}
          </span>
        </div>
        {loopStatus.running && loopStatus.iteration && (
          <span className="iteration-badge">
            {loopStatus.iteration}/{loopStatus.maxIterations}
          </span>
        )}
      </div>

      {!loopStatus.running && (
        <>
          <input
            type="text"
            className="prompt-input"
            placeholder="Custom focus (optional): e.g., 'Add tests for HTTP tool'"
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
          />
          
          <div className="control-buttons">
            <button className="ctrl-btn mode-toggle" onClick={toggleEvolution}>
              {evolutionMode ? <Zap size={16} /> : <Wrench size={16} />}
              {evolutionMode ? 'Evolution' : 'Deterministic'}
            </button>
            <button className="ctrl-btn primary" onClick={handleStart}>
              <Play size={16} /> Start (1 iteration)
            </button>
            <button className="ctrl-btn continuous" onClick={handleStartContinuous}>
              <Repeat size={16} /> Continuous
            </button>
          </div>
        </>
      )}

      {loopStatus.running && (
        <div className="control-buttons">
          <button className="ctrl-btn warning" onClick={() => handleStop('graceful')}>
            Stop After Current
          </button>
          <button className="ctrl-btn danger" onClick={() => handleStop('immediate')}>
            <Square size={16} /> Stop Now
          </button>
        </div>
      )}
    </div>
  );
}

export default AgentControls;
