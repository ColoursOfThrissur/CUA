import React, { useState } from 'react';
import { Send, Loader2, Sparkles, CheckCircle2 } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './ToolModeChat.css';

function ToolModeChat({ onModeChange }) {
  const [input, setInput] = useState(() => {
    try {
      const prefill = localStorage.getItem('prefillToolDescription');
      if (prefill) { localStorage.removeItem('prefillToolDescription'); return prefill; }
    } catch (e) {}
    return '';
  });
  const [toolName, setToolName] = useState('');
  const [loading, setLoading] = useState(false);
  const [suggestion, setSuggestion] = useState(null);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestionIndex, setSuggestionIndex] = useState(0);
  const toast = useToast();

  const fetchSuggestion = async () => {
    setSuggesting(true);
    const currentIndex = suggestionIndex;
    try {
      const res = await fetch(`${API_URL}/improvement/tools/suggest?skip=${currentIndex}`);
      const data = await res.json();
      if (!res.ok) {
        toast.error(data.detail || 'Failed to get suggestion');
        return;
      }
      setSuggestion(data);
      setSuggestionIndex(currentIndex + 1);
    } catch (err) {
      toast.error('Error: ' + err.message);
    } finally {
      setSuggesting(false);
    }
  };

  const applySuggestion = () => {
    if (!suggestion) return;
    if (suggestion.action === 'evolve_tool' && suggestion.target_tool) {
      try {
        localStorage.setItem('prefillEvolutionTool', suggestion.target_tool);
      } catch (e) {
        // ignore
      }
      if (onModeChange) {
        onModeChange('evolution');
        toast.success('Opened Evolution mode');
      } else {
        toast.success('Suggestion is to evolve an existing tool. Switch to Evolution mode.');
      }
      return;
    }

    setToolName(suggestion.tool_name || '');
    setInput(suggestion.description || '');
    toast.success('Applied suggestion to tool creation');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    setLoading(true);
    try {
      const params = new URLSearchParams({ description: input });
      if (toolName.trim()) {
        params.append('tool_name', toolName.trim());
      }
      
      const res = await fetch(`${API_URL}/improvement/tools/create?${params.toString()}`, {
        method: 'POST'
      });
      
      const data = await res.json();
      
      if (res.ok) {
        toast.success(`Tool created: ${data.tool_name}`);
        setInput('');
        setToolName('');
      } else {
        toast.error(data.detail || 'Failed to create tool');
      }
    } catch (err) {
      toast.error('Error: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tool-mode-chat">
      <div className="tool-welcome">
        <h2>Create New Tool</h2>
        <p>Describe what you want the tool to do</p>
      </div>

      <div className="tool-suggest-row">
        <button
          type="button"
          className="tool-suggest-btn"
          onClick={fetchSuggestion}
          disabled={loading || suggesting}
          title="Let Forge propose the next most important tool based on observed capability gaps"
        >
          {suggesting ? <Loader2 size={18} className="spin" /> : <Sparkles size={18} />}
          {suggesting ? 'Thinking…' : suggestionIndex === 0 ? 'Suggest tool for me' : 'Next suggestion'}
        </button>

        {suggestion && (
          <button
            type="button"
            className="tool-apply-btn"
            onClick={applySuggestion}
            disabled={loading || !suggestion}
            title="Fill the tool name and description from the suggestion"
          >
            <CheckCircle2 size={18} />
            Use suggestion
          </button>
        )}
      </div>

      {suggestion && (
        <div className="tool-suggestion-card">
          <div className="tool-suggestion-title">
            <span className="name">{suggestion.tool_name}</span>
            <span className="meta">
              {suggestion.source}
              {suggestion.action ? ` • ${suggestion.action}` : ''}
              {typeof suggestion.confidence === 'number' ? ` • conf ${(suggestion.confidence * 100).toFixed(0)}%` : ''}
            </span>
          </div>
          {suggestion.action === 'evolve_tool' && suggestion.target_tool && (
            <div className="tool-suggestion-sub">
              target: <strong>{suggestion.target_tool}</strong>
            </div>
          )}
          {suggestion.capability_gap && (
            <div className="tool-suggestion-sub">
              gap: <strong>{suggestion.capability_gap}</strong>
              {suggestion.suggested_library ? <> • lib: <strong>{suggestion.suggested_library}</strong></> : null}
            </div>
          )}
          <div className="tool-suggestion-desc">{suggestion.description}</div>
          <div className="tool-suggestion-why">{suggestion.rationale}</div>
        </div>
      )}
      
      <form className="tool-input-form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={toolName}
          onChange={(e) => setToolName(e.target.value)}
          placeholder="Tool name (optional, e.g., PerformanceMetricsAnalyzer)"
          disabled={loading}
          className="tool-input tool-name-input"
        />
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g., scrape websites and extract data, send emails..."
          disabled={loading}
          className="tool-input"
        />
        <button type="submit" disabled={loading || !input.trim()} className="tool-submit">
          {loading ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
        </button>
      </form>
    </div>
  );
}

export default ToolModeChat;
