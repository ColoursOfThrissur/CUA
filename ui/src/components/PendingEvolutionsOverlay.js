import React, { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Eye } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './PendingEvolutionsOverlay.css';

function PendingEvolutionsOverlay() {
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  useEffect(() => {
    fetchPending();
  }, []);

  const fetchPending = async () => {
    try {
      const res = await fetch(`${API_URL}/evolution/pending`);
      const data = await res.json();
      console.log('Pending evolutions response:', data);
      setPending(data.pending_evolutions || []);
    } catch (err) {
      console.error('Failed to fetch pending evolutions:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (toolName) => {
    try {
      const res = await fetch(`${API_URL}/evolution/approve/${toolName}`, { method: 'POST' });
      const data = await res.json();
      
      if (data.needs_dependencies) {
        toast.error(`Dependencies needed: ${data.dependencies.missing_libraries.concat(data.dependencies.missing_services).join(', ')}`);
        // TODO: Show dependency resolution modal
        return;
      }
      
      if (data.success) {
        toast.success(`Evolution approved: ${toolName}`);
        fetchPending();
      } else {
        toast.error(data.error || 'Failed to approve');
      }
    } catch (err) {
      toast.error('Failed to approve evolution');
    }
  };

  const handleReject = async (toolName) => {
    try {
      const res = await fetch(`${API_URL}/evolution/reject/${toolName}`, { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        toast.success(`Evolution rejected: ${toolName}`);
        fetchPending();
      } else {
        toast.error(data.error || 'Failed to reject');
      }
    } catch (err) {
      toast.error('Failed to reject evolution');
    }
  };

  if (loading) return <div className="pending-loading">Loading...</div>;

  if (pending.length === 0) {
    return <div className="pending-empty">No pending evolutions</div>;
  }

  return (
    <div className="pending-evolutions-overlay">
      {pending.map(item => (
        <div key={item.tool_name} className="evolution-card">
          <div className="evolution-header">
            <h4>{item.tool_name}</h4>
            <span className="confidence-badge">
              {(item.proposal.confidence * 100).toFixed(0)}% confidence
            </span>
          </div>
          
          <p className="evolution-description">{item.proposal.description}</p>
          
          {item.proposal.changes && item.proposal.changes.length > 0 && (
            <div className="changes-list">
              <strong>Changes:</strong>
              <ul>
                {item.proposal.changes.map((change, idx) => (
                  <li key={idx}>{change}</li>
                ))}
              </ul>
            </div>
          )}

          {item.proposal.expected_outcome && (
            <div className="expected-outcome">
              <strong>Expected:</strong> {item.proposal.expected_outcome}
            </div>
          )}
          
          {item.proposal.dependencies && (item.proposal.dependencies.missing_libraries?.length > 0 || item.proposal.dependencies.missing_services?.length > 0) && (
            <div className="dependencies-warning" style={{background: 'rgba(239, 68, 68, 0.1)', padding: '10px', borderRadius: '6px', marginTop: '10px'}}>
              <strong style={{color: '#ef4444'}}>⚠️ Missing Dependencies:</strong>
              {item.proposal.dependencies.missing_libraries?.length > 0 && (
                <div style={{marginTop: '5px'}}>
                  <span style={{color: 'var(--text-secondary)'}}>Libraries:</span> {item.proposal.dependencies.missing_libraries.join(', ')}
                </div>
              )}
              {item.proposal.dependencies.missing_services?.length > 0 && (
                <div style={{marginTop: '5px'}}>
                  <span style={{color: 'var(--text-secondary)'}}>Services:</span> {item.proposal.dependencies.missing_services.join(', ')}
                </div>
              )}
            </div>
          )}

          <div className="evolution-actions">
            <button className="btn-approve" onClick={() => handleApprove(item.tool_name)}>
              <CheckCircle size={16} /> Approve
            </button>
            <button className="btn-reject" onClick={() => handleReject(item.tool_name)}>
              <XCircle size={16} /> Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

export default PendingEvolutionsOverlay;
