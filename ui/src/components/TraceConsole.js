import React from 'react';
import { useTraceWebSocket } from '../hooks/useTraceWebSocket';
import './TraceConsole.css';

const TraceConsole = () => {
  const traces = useTraceWebSocket({ limit: 30, persist: true });

  return (
    <div className="trace-console">
      <div className="trace-console-header">
        <h3>Live Trace</h3>
        <span>{traces.length} events</span>
      </div>
      <div className="trace-console-list">
        {traces.length === 0 ? (
          <div className="trace-console-empty">No live trace events yet.</div>
        ) : (
          traces.map((trace) => (
            <div key={trace.id} className={`trace-console-item status-${trace.status}`}>
              <div className="trace-console-meta">
                <span className="trace-type">{trace.type}</span>
                {trace.details?.stage && <span className="trace-stage">{trace.details.stage}</span>}
                {trace.details?.tool_name && <span className="trace-tool">{trace.details.tool_name}</span>}
                {trace.details?.kind && <span className="trace-kind">{trace.details.kind}</span>}
              </div>
              <div className="trace-console-message">{trace.message}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default TraceConsole;
