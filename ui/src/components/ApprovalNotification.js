import React from 'react';
import '../styles/ApprovalNotification.css';

function ApprovalNotification({ pendingProposals, onViewDiff, onApprove, onReject }) {
  const proposals = Object.entries(pendingProposals || {}).filter(
    ([id, data]) => data.approved === null
  );

  if (proposals.length === 0) return null;

  return (
    <div className="approval-notification">
      <div className="notification-header">
        <span className="notification-icon">⚠️</span>
        <h3>Approval Required</h3>
        <span className="notification-count">{proposals.length}</span>
      </div>
      
      <div className="notification-body">
        {proposals.map(([proposalId, data]) => (
          <div key={proposalId} className="proposal-item">
            <div className="proposal-info">
              <div className="proposal-title">
                {data.proposal?.description || 'Improvement proposal'}
              </div>
              <div className="proposal-meta">
                <span className={`risk-badge risk-${data.risk_score?.level?.value || 'medium'}`}>
                  {data.risk_score?.level?.value?.toUpperCase() || 'MEDIUM'} RISK
                </span>
                <span className="files-changed">
                  {data.proposal?.files_changed?.length || 0} file(s)
                </span>
              </div>
            </div>
            
            <div className="proposal-actions">
              <button 
                className="btn-view-small" 
                onClick={() => onViewDiff(proposalId)}
              >
                View Diff
              </button>
              <button 
                className="btn-approve-small" 
                onClick={() => onApprove(proposalId)}
              >
                ✓ Approve
              </button>
              <button 
                className="btn-reject-small" 
                onClick={() => onReject(proposalId)}
              >
                ✗ Reject
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ApprovalNotification;
