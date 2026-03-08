import React, { useState, useEffect } from 'react';
import { API_URL } from '../config';
import './HistoryViewer.css';

function HistoryViewer({ onViewDiff }) {
  const [history, setHistory] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState(null);

  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    try {
      const response = await fetch(`${API_URL}/improvement/history`);
      const data = await response.json();
      setHistory(data.history || []);
    } catch (error) {
      console.error('Failed to fetch history:', error);
    }
  };

  const handleViewDetails = async (planId) => {
    try {
      const response = await fetch(`${API_URL}/improvement/history/${planId}`);
      const data = await response.json();
      setSelectedPlan(data);
    } catch (error) {
      alert('Failed to load plan details: ' + error.message);
    }
  };

  const handleRollback = async (planId) => {
    if (!window.confirm('Rollback to this version? This will revert all changes made by this plan.')) {
      return;
    }

    try {
      const response = await fetch(`${API_URL}/improvement/rollback/${planId}`, {
        method: 'POST'
      });

      if (response.ok) {
        alert('Rollback successful!');
        fetchHistory();
        setSelectedPlan(null);
      } else {
        const error = await response.json();
        alert('Rollback failed: ' + error.detail);
      }
    } catch (error) {
      alert('Rollback error: ' + error.message);
    }
  };

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp * 1000).toLocaleString();
  };

  return (
    <div className="history-viewer">
      <div className="history-header">
        <h3>Plan History</h3>
        <button className="btn-icon" onClick={fetchHistory} title="Refresh">
          🔄
        </button>
      </div>

      <div className="history-list">
        {history.length === 0 ? (
          <div className="history-empty">No execution history yet</div>
        ) : (
          history.map((plan) => (
            <div 
              key={plan.plan_id} 
              className={`history-item ${plan.status === 'failed' ? 'failed' : ''}`}
              onClick={() => handleViewDetails(plan.plan_id)}
            >
              <div className="history-info">
                <div className="history-desc">{plan.description}</div>
                <div className="history-meta">
                  <span className="history-time">{formatTimestamp(plan.timestamp)}</span>
                  <span className={`history-risk risk-${plan.risk_level}`}>{plan.risk_level}</span>
                  <span className={`history-status status-${plan.status}`}>{plan.status}</span>
                </div>
              </div>
              <div className="history-actions" onClick={(e) => e.stopPropagation()}>
                {plan.rollback_commit && plan.rollback_commit !== 'skipped_no_git' && (
                  <button 
                    className="btn-small btn-warning"
                    onClick={() => handleRollback(plan.plan_id)}
                  >
                    Rollback
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {selectedPlan && (
        <div className="plan-details-modal" onClick={() => setSelectedPlan(null)}>
          <div className="plan-details-content" onClick={(e) => e.stopPropagation()}>
            <div className="plan-details-header">
              <h3>Plan Details</h3>
              <button className="btn-close" onClick={() => setSelectedPlan(null)}>×</button>
            </div>
            
            <div className="plan-details-body">
              <div className="detail-row">
                <span className="detail-label">Plan ID:</span>
                <span className="detail-value">{selectedPlan.plan_id}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Description:</span>
                <span className="detail-value">{selectedPlan.description}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Risk Level:</span>
                <span className={`detail-value risk-${selectedPlan.risk_level}`}>
                  {selectedPlan.risk_level}
                </span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Status:</span>
                <span className={`detail-value status-${selectedPlan.status}`}>
                  {selectedPlan.status}
                </span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Timestamp:</span>
                <span className="detail-value">{formatTimestamp(selectedPlan.timestamp)}</span>
              </div>
              
              {selectedPlan.patch && (
                <div className="detail-section">
                  <div className="detail-label">Patch:</div>
                  <pre className="patch-preview">{selectedPlan.patch.slice(0, 500)}...</pre>
                </div>
              )}
            </div>

            <div className="plan-details-footer">
              {selectedPlan.rollback_commit && selectedPlan.rollback_commit !== 'skipped_no_git' && (
                <button 
                  className="btn btn-warning"
                  onClick={() => {
                    handleRollback(selectedPlan.plan_id);
                    setSelectedPlan(null);
                  }}
                >
                  Rollback This Plan
                </button>
              )}
              <button className="btn btn-secondary" onClick={() => setSelectedPlan(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default HistoryViewer;
