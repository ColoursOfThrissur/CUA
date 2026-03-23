import { useEffect, useState } from 'react';

export const useTraceWebSocket = ({ limit = 4, persist = false, ttlMs = 3000 } = {}) => {
  const [traces, setTraces] = useState([]);

  useEffect(() => {
    const wsUrl = `ws://localhost:8000/ws/trace`;
    const websocket = new WebSocket(wsUrl);

    websocket.onopen = () => {
      console.log('Trace WebSocket connected');
    };

    websocket.onmessage = (event) => {
      const trace = JSON.parse(event.data);
      const traceWithId = {
        ...trace,
        id: `trace_${Date.now()}_${Math.random()}`,
      };

      setTraces((prev) => {
        const newTraces = [traceWithId, ...prev].slice(0, limit);
        return newTraces;
      });

      if (!persist) {
        setTimeout(() => {
          setTraces((prev) => prev.filter((t) => t.id !== traceWithId.id));
        }, ttlMs);
      }
    };

    websocket.onerror = (error) => {
      console.error('Trace WebSocket error:', error);
    };

    websocket.onclose = () => {
      console.log('Trace WebSocket disconnected');
    };

    return () => {
      websocket.close();
    };
  }, []);

  return traces;
};
