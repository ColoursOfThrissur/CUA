import React, { useState } from 'react';
import { API_URL } from '../config';
import { Wrench, Sparkles, Loader2, CheckCircle2, XCircle, FileCode } from 'lucide-react';
import './ToolCreator.css';

function ToolCreator({ onCreated }) {
  const [description, setDescription] = useState('');
  const [toolName, setToolName] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleCreate = async () => {
    if (!description.trim()) {
      setError('Please describe what the tool should do');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const params = new URLSearchParams({ description });
      if (toolName.trim()) params.append('tool_name', toolName.trim());

      const response = await fetch(`${API_URL}/improvement/tools/create?${params}`, {
        method: 'POST'
      });

      const data = await response.json();

      if (response.ok) {
        setResult(data);
        setDescription('');
        setToolName('');
        if (onCreated) {
          onCreated(data);
        }
      } else {
        setError(data.detail || 'Failed to create tool');
      }
    } catch (err) {
      setError(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tool-creator">
      <div className="tool-creator-header">
        <Wrench size={20} />
        <h3>Create New Tool</h3>
      </div>
      
      <div className="form-group">
        <label>What should the tool do?</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="e.g., scrape websites and extract data, send emails, process images..."
          rows={3}
          disabled={loading}
        />
      </div>

      <div className="form-group">
        <label>Tool Name (optional)</label>
        <input
          type="text"
          value={toolName}
          onChange={(e) => setToolName(e.target.value)}
          placeholder="e.g., web_scraper"
          disabled={loading}
        />
      </div>

      <button 
        onClick={handleCreate} 
        disabled={loading || !description.trim()}
        className="create-btn"
      >
        {loading ? (
          <>
            <Loader2 size={18} className="spin" />
            Creating...
          </>
        ) : (
          <>
            <Sparkles size={18} />
            Create Tool
          </>
        )}
      </button>

      {error && (
        <div className="error-box">
          <XCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div className="success-box">
          <div className="success-header">
            <CheckCircle2 size={20} />
            <span>Tool Created Successfully!</span>
          </div>
          <div className="result-details">
            <div className="result-item">
              <Wrench size={16} />
              <span><strong>Name:</strong> {result.tool_name}</span>
            </div>
            <div className="result-item">
              <CheckCircle2 size={16} />
              <span><strong>Status:</strong> {result.status}</span>
            </div>
            <div className="result-item">
              <FileCode size={16} />
              <span><strong>File:</strong> {result.file_path}</span>
            </div>
            {result.capabilities && (
              <div className="result-item">
                <Sparkles size={16} />
                <span><strong>Capabilities:</strong> {result.capabilities.join(', ')}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default ToolCreator;
