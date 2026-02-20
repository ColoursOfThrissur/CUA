import React, { useState, useEffect } from 'react';
import { Zap, Loader2, AlertTriangle } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './EvolutionMode.css';

function EvolutionMode() {
  const [tools, setTools] = useState([]);
  const [selectedTool, setSelectedTool] = useState('');
  const [customPrompt, setCustomPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationLog, setConversationLog] = useState([]);
  const [toolInfo, setToolInfo] = useState(null);
  const [sourceMode, setSourceMode] = useState('recommended');
  const toast = useToast();

  useEffect(() => {
    fetchTools();
  }, [sourceMode]);

  useEffect(() => {
    if (selectedTool) {
      fetchToolInfo(selectedTool);
    } else {
      setToolInfo(null);
    }
  }, [selectedTool]);

  const fetchTools = async () => {
    try {
      if (sourceMode === 'recommended') {
        // Get tools with quality data
        const res = await fetch(`${API_URL}/quality/all`);
        const data = await res.json();
        const weakTools = (data || []).filter(t => t.health_score < 70);
        setTools(weakTools);
      } else {
        // Get all actual tool files
        const res = await fetch(`${API_URL}/tools/list`);
        const data = await res.json();
        setTools(data.tools || []);
      }
    } catch (err) {
      console.error('Failed to fetch tools:', err);
      toast.error('Failed to load tools');
    }
  };

  const fetchToolInfo = async (toolName) => {
    try {
      const res = await fetch(`${API_URL}/tools/info/${toolName}`);
      const data = await res.json();
      setToolInfo(data);
    } catch (err) {
      console.error('Failed to fetch tool info:', err);
    }
  };

  const handleEvolve = async () => {
    if (!selectedTool) {
      toast.error('Please select a tool');
      return;
    }

    setLoading(true);
    setConversationLog([]);

    try {
      const res = await fetch(`${API_URL}/evolution/evolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool_name: selectedTool,
          user_prompt: customPrompt || null
        })
      });

      const data = await res.json();

      if (data.success) {
        toast.success(data.message);
        setConversationLog(data.conversation_log || []);
        setSelectedTool('');
        setCustomPrompt('');
      } else {
        toast.error(data.message || 'Evolution failed');
      }
    } catch (err) {
      toast.error('Error: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="evolution-mode">
      <div className="evolution-header">
        <Zap size={32} />
        <h2>Tool Evolution</h2>
        <p>Improve existing tools based on quality metrics</p>
      </div>

      <div className="evolution-form">
        <div className="form-group">
          <label>Tool Source</label>
          <div className="source-toggle">
            <button 
              className={`toggle-btn ${sourceMode === 'recommended' ? 'active' : ''}`}
              onClick={() => setSourceMode('recommended')}
            >
              Recommended (Weak Tools)
            </button>
            <button 
              className={`toggle-btn ${sourceMode === 'all' ? 'active' : ''}`}
              onClick={() => setSourceMode('all')}
            >
              All Tools
            </button>
          </div>
        </div>

        <div className="form-group">
          <label>Select Tool to Improve</label>
          <select
            value={selectedTool}
            onChange={(e) => setSelectedTool(e.target.value)}
            disabled={loading}
            className="tool-select"
          >
            <option value="">Choose a tool...</option>
            {tools.map(tool => (
              <option key={tool.tool_name} value={tool.tool_name}>
                {tool.tool_name}{tool.health_score ? ` - Health: ${tool.health_score.toFixed(0)}/100 (${tool.recommendation})` : ''}
              </option>
            ))}
          </select>
        </div>

        {toolInfo && (
          <div className="tool-info-card">
            <h4>Current Capabilities</h4>
            <p className="tool-description">{toolInfo.description}</p>
            {toolInfo.capabilities && toolInfo.capabilities.length > 0 && (
              <ul className="capabilities-list">
                {toolInfo.capabilities.map((cap, idx) => (
                  <li key={idx}>{cap}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="form-group">
          <label>Custom Instructions (Optional)</label>
          <textarea
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            placeholder="e.g., improve error handling, add retry logic..."
            disabled={loading}
            rows={3}
            className="prompt-textarea"
          />
        </div>

        <button
          onClick={handleEvolve}
          disabled={loading || !selectedTool}
          className="evolve-btn"
        >
          {loading ? (
            <>
              <Loader2 size={18} className="spin" /> Evolving...
            </>
          ) : (
            <>
              <Zap size={18} /> Start Evolution
            </>
          )}
        </button>
      </div>

      {conversationLog.length > 0 && (
        <div className="conversation-log">
          <h3>Evolution Log</h3>
          {conversationLog.map((entry, idx) => (
            <div key={idx} className={`log-entry ${entry.type}`}>
              <span className="log-step">{entry.step}</span>
              <span className="log-message">{entry.message}</span>
            </div>
          ))}
        </div>
      )}

      {tools.length === 0 && (
        <div className="no-tools">
          <AlertTriangle size={24} />
          <p>No tools need improvement</p>
        </div>
      )}
    </div>
  );
}

export default EvolutionMode;
