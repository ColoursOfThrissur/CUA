import React, { useState } from 'react';
import { ChevronDown, ChevronRight, CheckCircle, XCircle, Clock } from 'lucide-react';
import './ToolExecutionSteps.css';

const ToolExecutionSteps = ({ toolHistory }) => {
  const [expanded, setExpanded] = useState(false);

  if (!toolHistory || toolHistory.length === 0) return null;

  const hasErrors = toolHistory.some(step => !step.success);

  return (
    <div className="tool-execution-steps">
      <div 
        className="steps-header"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <span className="steps-title">
          Execution Steps ({toolHistory.length})
          {hasErrors && <span className="error-badge">Errors</span>}
        </span>
      </div>
      
      {expanded && (
        <div className="steps-list">
          {toolHistory.map((step, index) => (
            <div 
              key={index}
              className={`step-item ${step.success ? 'success' : 'error'}`}
            >
              <div className="step-header">
                <div className="step-icon">
                  {step.success ? (
                    <CheckCircle size={14} className="success-icon" />
                  ) : (
                    <XCircle size={14} className="error-icon" />
                  )}
                </div>
                <div className="step-info">
                  <span className="step-number">Step {step.step}</span>
                  <span className="step-tool">{step.tool}.{step.operation}</span>
                </div>
                <div className="step-duration">
                  <Clock size={12} />
                  {step.duration}
                </div>
              </div>
              
              {step.error && (
                <div className="step-error">
                  <strong>Error:</strong> {step.error}
                </div>
              )}
              
              {step.data_preview && (
                <div className="step-preview">
                  {step.data_preview}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ToolExecutionSteps;
