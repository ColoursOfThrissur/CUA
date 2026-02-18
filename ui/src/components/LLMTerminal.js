import React, { useState, useEffect, useRef } from 'react';
import './LLMTerminal.css';

const LLMTerminal = ({ apiUrl }) => {
  const [logs, setLogs] = useState([]);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [lastLogHash, setLastLogHash] = useState('');
  const terminalRef = useRef(null);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch(`${apiUrl}/llm-logs/latest?limit=300`);
        const data = await response.json();
        if (data.logs && data.logs.length > 0) {
          // Create hash of log content to detect changes
          const newHash = JSON.stringify(data.logs.map(l => l.prompt_preview + l.response_preview));
          
          // Only update if content actually changed
          if (newHash !== lastLogHash) {
            setLogs(data.logs);
            setLastUpdate(new Date().toLocaleTimeString());
            setLastLogHash(newHash);
          }
        }
      } catch (error) {
        console.error('Failed to fetch LLM logs:', error);
      }
    };

    fetchLogs();
    const interval = setInterval(fetchLogs, 3000);
    return () => clearInterval(interval);
  }, [apiUrl, lastLogHash]);

  useEffect(() => {
    // Auto-scroll to bottom
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="llm-terminal">
      <div className="terminal-header">
        <span className="terminal-title">🤖 LLM Activity</span>
        <span className="terminal-stats">
          {logs.length > 0 && (
            <>
              <span style={{color: '#6b7280', fontSize: '10px', marginRight: '8px'}}>
                {logs.length} interactions
              </span>
              {lastUpdate && (
                <span style={{color: '#6b7280', fontSize: '10px', marginRight: '8px'}}>
                  Updated: {lastUpdate}
                </span>
              )}
            </>
          )}
          <span className="terminal-indicator">●</span>
        </span>
      </div>
      <div className="terminal-body" ref={terminalRef}>
        {logs.length === 0 ? (
          <div className="terminal-empty">Waiting for LLM activity...</div>
        ) : (
          logs.map((log, idx) => (
            <div key={idx} className="terminal-entry">
              <div className="terminal-prompt">
                <span className="terminal-arrow">→</span>
                <span className="terminal-text">{log.prompt_preview}</span>
              </div>
              <div className="terminal-response">
                <span className="terminal-arrow">←</span>
                <span className="terminal-text">{log.response_preview}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default LLMTerminal;
