import React, { useState } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './ToolModeChat.css';

function ToolModeChat() {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/improvement/tools/create?description=${encodeURIComponent(input)}`, {
        method: 'POST'
      });
      
      const data = await res.json();
      
      if (res.ok) {
        toast.success(`Tool created: ${data.tool_name}`);
        setInput('');
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
      
      <form className="tool-input-form" onSubmit={handleSubmit}>
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
