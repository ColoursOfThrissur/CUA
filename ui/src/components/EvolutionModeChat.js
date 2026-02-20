import React, { useState } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './EvolutionModeChat.css';

function EvolutionModeChat() {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/evolution/evolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request: input })
      });
      
      const data = await res.json();
      
      if (res.ok) {
        toast.success(data.message || 'Evolution started');
        setInput('');
      } else {
        toast.error(data.error || 'Failed to start evolution');
      }
    } catch (err) {
      toast.error('Error: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="evolution-mode-chat">
      <div className="evolution-welcome">
        <h2>Tool Evolution</h2>
        <p>Request improvements for existing tools</p>
      </div>
      
      <form className="evolution-input-form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g., improve error handling in http_tool, add retry logic..."
          disabled={loading}
          className="evolution-input"
        />
        <button type="submit" disabled={loading || !input.trim()} className="evolution-submit">
          {loading ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
        </button>
      </form>
    </div>
  );
}

export default EvolutionModeChat;
