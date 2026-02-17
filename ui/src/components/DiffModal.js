import React from 'react';
import '../styles/DiffModal.css';

function DiffModal({ proposal, onClose, onApprove, onReject }) {
  if (!proposal) return null;

  const parseDiff = (patch) => {
    const lines = patch.split('\n');
    const changes = [];
    
    for (let line of lines) {
      if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@')) {
        changes.push({ type: 'meta', content: line });
      } else if (line.startsWith('+')) {
        changes.push({ type: 'add', content: line.substring(1) });
      } else if (line.startsWith('-')) {
        changes.push({ type: 'remove', content: line.substring(1) });
      } else {
        changes.push({ type: 'context', content: line });
      }
    }
    
    return changes;
  };

  const changes = parseDiff(proposal.patch || '');

  return (
    <div className="diff-modal-overlay" onClick={onClose}>
      <div className="diff-modal" onClick={(e) => e.stopPropagation()}>
        <div className="diff-modal-header">
          <h2>Code Changes</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        
        <div className="diff-modal-body">
          <div className="diff-info">
            <p><strong>Description:</strong> {proposal.description}</p>
            <p><strong>Files:</strong> {proposal.files_changed?.join(', ')}</p>
            <p><strong>Lines Changed:</strong> {proposal.diff_lines}</p>
          </div>
          
          <div className="diff-viewer">
            {changes.map((change, idx) => (
              <div key={idx} className={`diff-line diff-${change.type}`}>
                <span className="line-number">{idx + 1}</span>
                <span className="line-content">{change.content}</span>
              </div>
            ))}
          </div>
        </div>
        
        <div className="diff-modal-footer">
          <button className="btn-reject" onClick={onReject}>Reject</button>
          <button className="btn-approve" onClick={onApprove}>Approve</button>
        </div>
      </div>
    </div>
  );
}

export default DiffModal;
