import React, { useState, useEffect } from 'react';
import { Activity, Code2, Target, Zap, Loader2, AlertTriangle } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import AutoEvolutionPanel from './AutoEvolutionPanel';
import CapabilityGapsPanel from './CapabilityGapsPanel';
import PendingServicesPanel from './PendingServicesPanel';
import './EvolutionMode.css';

function EvolutionMode() {
  const [tab, setTab] = useState('manual');
  const [tools, setTools] = useState([]);
  const [selectedTool, setSelectedTool] = useState(() => {
    try {
      return localStorage.getItem('prefillEvolutionTool') || '';
    } catch (e) {
      return '';
    }
  });
  const [customPrompt, setCustomPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationLog, setConversationLog] = useState([]);
  const [toolInfo, setToolInfo] = useState(null);
  const [sourceMode, setSourceMode] = useState('recommended');
  const [llmAnalysis, setLlmAnalysis] = useState(null);
  const toast = useToast();

  useEffect(() => {
    fetchTools();
  }, [sourceMode]);

  useEffect(() => {
    if (selectedTool) {
      fetchToolInfo(selectedTool);
      fetchLLMAnalysis(selectedTool);
      try {
        localStorage.removeItem('prefillEvolutionTool');
      } catch (e) {
        // ignore
      }
    } else {
      setToolInfo(null);
      setLlmAnalysis(null);
    }
  }, [selectedTool]);

  const fetchTools = async () => {
    try {
      if (sourceMode === 'recommended') {
        // Get LLM-analyzed weak tools
        const res = await fetch(`${API_URL}/quality/llm-weak`);
        const data = await res.json();
        setTools((data || []).map(t => ({ tool_name: t.tool_name, category: t.category })));
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

  const fetchLLMAnalysis = async (toolName) => {
    try {
      const res = await fetch(`${API_URL}/quality/llm-analysis/${toolName}`);
      const data = await res.json();
      setLlmAnalysis(data);
    } catch (err) {
      console.error('Failed to fetch LLM analysis:', err);
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
      <div className="evolution-tabs">
        <button className={`evolution-tab ${tab === 'manual' ? 'active' : ''}`} onClick={() => setTab('manual')}>
          <Zap size={16} /> Manual Evolution
        </button>
        <button className={`evolution-tab ${tab === 'auto' ? 'active' : ''}`} onClick={() => setTab('auto')}>
          <Activity size={16} /> Auto-Evolution
        </button>
        <button className={`evolution-tab ${tab === 'gaps' ? 'active' : ''}`} onClick={() => setTab('gaps')}>
          <Target size={16} /> Gaps
        </button>
        <button className={`evolution-tab ${tab === 'services' ? 'active' : ''}`} onClick={() => setTab('services')}>
          <Code2 size={16} /> Services
        </button>
      </div>

      <div className="evolution-content">
        {tab === 'auto' && (
          <div className="evolution-tab-panel">
            <AutoEvolutionPanel embedded onClose={() => {}} />
          </div>
        )}

        {tab === 'gaps' && (
          <div className="evolution-tab-panel">
            <CapabilityGapsPanel />
          </div>
        )}

        {tab === 'services' && (
          <div className="evolution-tab-panel">
            <PendingServicesPanel />
          </div>
        )}

        {tab !== 'manual' ? null : (
        <>
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
                  {tool.tool_name}{tool.category ? ` - ${tool.category}` : ''}{tool.health_score ? ` - Health: ${tool.health_score.toFixed(0)}/100` : ''}
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

          {llmAnalysis && (
            <div className="llm-analysis-card">
              <h4>LLM Analysis</h4>
              <p className="analysis-purpose"><strong>Purpose:</strong> {llmAnalysis.purpose}</p>
              
              {llmAnalysis.issues && llmAnalysis.issues.length > 0 && (
                <div className="analysis-section">
                  <h5>Issues Found ({llmAnalysis.issues.length})</h5>
                  <ul className="issues-list">
                    {llmAnalysis.issues.map((issue, idx) => (
                      <li key={idx} className={`issue-${issue.severity?.toLowerCase()}`}>
                        <span className="issue-badge">{issue.category}</span>
                        <span className="issue-severity">{issue.severity}</span>
                        <span className="issue-desc">{issue.description}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              
              {llmAnalysis.improvements && llmAnalysis.improvements.length > 0 && (
                <div className="analysis-section">
                  <h5>Suggested Improvements ({llmAnalysis.improvements.length})</h5>
                  <ul className="improvements-list">
                    {llmAnalysis.improvements.map((imp, idx) => (
                      <li key={idx} className={`priority-${imp.priority?.toLowerCase()}`}>
                        <span className="imp-badge">{imp.type}</span>
                        <span className="imp-priority">{imp.priority}</span>
                        <span className="imp-desc">{imp.description}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
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
        </>
        )}
      </div>

      {tab === 'manual' && (
        <div className="evolution-input-area">
          <textarea
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            placeholder="Custom instructions (optional): e.g., improve error handling, add retry logic..."
            disabled={loading}
            rows={2}
            className="prompt-textarea"
          />
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
      )}
    </div>
  );
}

export default EvolutionMode;
