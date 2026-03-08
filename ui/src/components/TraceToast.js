import React from 'react';
import { CheckCircle, XCircle, RefreshCw, Wrench, Zap, Bot, Circle } from 'lucide-react';
import './TraceToast.css';

const TraceToast = ({ trace, index }) => {
  const getIcon = () => {
    if (trace.status === 'success') return <CheckCircle size={16} />;
    if (trace.status === 'error') return <XCircle size={16} />;
    
    switch (trace.type) {
      case 'evolution': return <RefreshCw size={16} />;
      case 'creation': return <Wrench size={16} />;
      case 'chat': return <Zap size={16} />;
      case 'auto': return <Bot size={16} />;
      default: return <Circle size={16} />;
    }
  };

  return (
    <div 
      className={`trace-toast trace-${trace.status}`}
      style={{ top: `${80 + index * 50}px` }}
    >
      <span className="trace-icon">{getIcon()}</span>
      <span className="trace-message">{trace.message}</span>
    </div>
  );
};

export default TraceToast;
