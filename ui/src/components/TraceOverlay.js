import React from 'react';
import { useTraceWebSocket } from '../hooks/useTraceWebSocket';
import TraceToast from './TraceToast';

const TraceOverlay = () => {
  const traces = useTraceWebSocket();

  return (
    <>
      {traces.map((trace, index) => (
        <TraceToast key={trace.id} trace={trace} index={index} />
      ))}
    </>
  );
};

export default TraceOverlay;
