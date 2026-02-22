import React, { useState, useEffect } from 'react';
import { Target, Play, Pause, CheckCircle, XCircle, Clock, Zap } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './AgentMode.css';

function AgentMode({ sessionId }) {
  const [goal, setGoal] = useState('');
  const [criteria, setCriteria] = useState(['']);
  const [maxIterations, setMaxIterations] = useState(5);
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState(null);
  const [executionState, setExecutionState] = useState(null);
  const toast = useToast();

  const addCriterion = () => {
    setCriteria([...criteria, '']);
  };

  const updateCriterion = (index, value) => {
    const updated = [...criteria];
    updated[index] = value;
    setCriteria(updated);
  };

  const removeCriterion = (index) => {
    setCriteria(criteria.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    if (!goal.trim()) {
      toast.error('Please enter a goal');
      return;
    }

    setExecuting(true);
    setResult(null);
    setExecutionState(null);

    try {
      const response = await fetch(`${API_URL}/agent/goal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: goal.trim(),
          success_criteria: criteria.filter(c => c.trim()),
          max_iterations: maxIterations,
          require_approval: false,
          session_id: sessionId
        })
      });

      const data = await response.json();
      setResult(data);

      if (data.success) {
        toast.success(`Goal achieved in ${data.iterations} iterations!`);
        
        // Fetch execution details
        if (data.execution_history && data.execution_history.length > 0) {
          const execId = data.execution_history[data.execution_history.length - 1];
          fetchExecutionState(execId);
        }
      } else {
        toast.error(data.message || 'Goal not achieved');
      }
    } catch (err) {
      toast.error('Failed to execute goal: ' + err.message);
    } finally {
      setExecuting(false);
    }
  };

  const fetchExecutionState = async (execId) => {
    try {
      const response = await fetch(`${API_URL}/agent/execution/${execId}`);
      const data = await response.json();
      setExecutionState(data);
    } catch (err) {
      console.error('Failed to fetch execution state:', err);
    }
  };

  return (
    <div className="agent-mode">
      <div className="agent-content">
        <div className="agent-header">
          <Target size={48} color="var(--mode-color)" />
          <h2>Autonomous Goal Achievement</h2>
          <p>Define a goal and let the agent plan and execute autonomously</p>
        </div>

        <div className="goal-form">
          <div className="form-group">
            <label>Goal</label>
            <textarea
              className="goal-input"
              placeholder="e.g., Analyze the sales data and create a summary report"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              rows={3}
              disabled={executing}
            />
          </div>

          <div className="form-group">
            <label>Success Criteria (optional)</label>
            {criteria.map((criterion, index) => (
              <div key={index} className="criterion-row">
                <input
                  type="text"
                  placeholder="e.g., Report contains sales trends"
                  value={criterion}
                  onChange={(e) => updateCriterion(index, e.target.value)}
                  disabled={executing}
                />
                {criteria.length > 1 && (
                  <button
                    className="btn-remove"
                    onClick={() => removeCriterion(index)}
                    disabled={executing}
                  >
                    <XCircle size={16} />
                  </button>
                )}
              </div>
            ))}
            <button className="btn-add-criterion" onClick={addCriterion} disabled={executing}>
              + Add Criterion
            </button>
          </div>

          <div className="form-group">
            <label>Max Iterations</label>
            <input
              type="number"
              min="1"
              max="10"
              value={maxIterations}
              onChange={(e) => setMaxIterations(parseInt(e.target.value))}
              disabled={executing}
            />
          </div>

          <button
            className="btn-execute"
            onClick={handleSubmit}
            disabled={executing || !goal.trim()}
          >
            {executing ? (
              <>
                <Clock size={20} className="spin" />
                Executing...
              </>
            ) : (
              <>
                <Play size={20} />
                Execute Goal
              </>
            )}
          </button>
        </div>

        {result && (
          <div className={`result-card ${result.success ? 'success' : 'failure'}`}>
            <div className="result-header">
              {result.success ? (
                <CheckCircle size={24} color="#10b981" />
              ) : (
                <XCircle size={24} color="#ef4444" />
              )}
              <h3>{result.message}</h3>
            </div>
            <div className="result-details">
              <div className="detail-item">
                <span className="label">Iterations:</span>
                <span className="value">{result.iterations}</span>
              </div>
              <div className="detail-item">
                <span className="label">Status:</span>
                <span className="value">{result.success ? 'Achieved' : 'Failed'}</span>
              </div>
            </div>
          </div>
        )}

        {executionState && (
          <div className="execution-details">
            <h3>Execution Steps</h3>
            <div className="steps-list">
              {executionState.steps.map((step, index) => (
                <div key={step.step_id} className={`step-card status-${step.status}`}>
                  <div className="step-header">
                    <span className="step-number">{index + 1}</span>
                    <span className="step-description">{step.description}</span>
                    <span className={`step-status ${step.status}`}>
                      {step.status === 'completed' && <CheckCircle size={16} />}
                      {step.status === 'failed' && <XCircle size={16} />}
                      {step.status}
                    </span>
                  </div>
                  {step.error && (
                    <div className="step-error">
                      Error: {step.error}
                    </div>
                  )}
                  {step.output && (
                    <div className="step-output">
                      <details>
                        <summary>Output</summary>
                        <pre>{JSON.stringify(step.output, null, 2)}</pre>
                      </details>
                    </div>
                  )}
                  <div className="step-meta">
                    <span>Tool: {step.step_id.split('_')[0]}</span>
                    <span>Time: {step.execution_time?.toFixed(2)}s</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AgentMode;
