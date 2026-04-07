import React from 'react';
import '../styles/DiffModal.css';
import DiffViewer from './output/DiffViewer';
import { buildDiffPayload } from '../utils/diffPayload';

function DiffModal({ proposal, onClose, onApprove, onReject }) {
  if (!proposal) return null;
  const diffPayload = proposal.diff_payload || buildDiffPayload(proposal.patch || '');

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
            <p><strong>Files:</strong> {diffPayload.files?.map((file) => file.path).join(', ') || proposal.files_changed?.join(', ')}</p>
            <p><strong>Lines Changed:</strong> {diffPayload.stats?.lines_changed || proposal.diff_lines || 0}</p>
          </div>

          <DiffViewer payload={diffPayload} title="Code Changes" />
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
