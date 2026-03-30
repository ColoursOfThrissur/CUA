import React, { useEffect, useState } from 'react';
import { Brain } from 'lucide-react';
import './ThinkingTrace.css';

const ThinkingTrace = () => {
  const [thinking, setThinking] = useState(null);

  useEffect(() => {
    const wsUrl = `ws://localhost:8000/ws/trace`;
    const websocket = new WebSocket(wsUrl);

    websocket.onopen = () => {
      console.log('Thinking trace WebSocket connected');
    };

    websocket.onmessage = (event) => {
      const trace = JSON.parse(event.data);
      
      // Only show thinking traces
      if (trace.type === 'thinking') {
        setThinking({
          message: trace.message,
          timestamp: Date.now(),
        });
        
        // Auto-clear after 4 seconds
        setTimeout(() => {
          setThinking(null);
        }, 4000);
      }
    };

    websocket.onerror = (error) => {
      console.error('Thinking trace WebSocket error:', error);
    };

    websocket.onclose = () => {
      console.log('Thinking trace WebSocket disconnected');
    };

    return () => {
      websocket.close();
    };
  }, []);

  if (!thinking) return null;

  return (
    <div className="thinking-trace">
      <div className="thinking-icon">
        <Brain size={16} className="brain-pulse" />
      </div>
      <div className="thinking-text">{thinking.message}</div>
    </div>
  );
};

export default ThinkingTrace;
