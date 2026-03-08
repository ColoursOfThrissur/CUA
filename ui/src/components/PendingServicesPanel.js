import React, { useEffect, useState } from 'react';
import { CheckCircle, Code2, RefreshCw, XCircle } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './PendingServicesPanel.css';

function PendingServicesPanel() {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState([]);
  const [expanded, setExpanded] = useState({});
  const [rejectReasons, setRejectReasons] = useState({});

  const fetchPending = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/services/pending`);
      const json = await res.json();
      if (json?.success) setPending(json.pending_services || []);
      else setPending([]);
    } catch (e) {
      toast.error('Failed to load pending services');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPending();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const approve = async (serviceId) => {
    try {
      const res = await fetch(`${API_URL}/api/services/${serviceId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: '' })
      });
      const json = await res.json();
      if (json?.success) {
        toast.success('Service approved and injected');
        toast.info('Backend restart may be required to load injected service changes');
        fetchPending();
      } else {
        toast.error(json?.detail || 'Approval failed');
      }
    } catch (e) {
      toast.error('Approval failed');
    }
  };

  const reject = async (serviceId) => {
    const reason = rejectReasons[serviceId] || 'Not needed';
    try {
      const res = await fetch(`${API_URL}/api/services/${serviceId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason })
      });
      const json = await res.json();
      if (json?.success) {
        toast.success('Service rejected');
        fetchPending();
      } else {
        toast.error(json?.detail || 'Rejection failed');
      }
    } catch (e) {
      toast.error('Rejection failed');
    }
  };

  return (
    <div className="pending-services-panel">
      <div className="psp-header">
        <div className="psp-title">
          <Code2 size={18} />
          <h3>Pending Services</h3>
        </div>
        <button className="psp-refresh" onClick={fetchPending} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} />
          Refresh
        </button>
      </div>

      {pending.length === 0 ? (
        <div className="psp-empty">No pending service approvals</div>
      ) : (
        <div className="psp-list">
          {pending.map((s) => (
            <div key={s.id} className="psp-item">
              <div className="psp-row">
                <div className="psp-left">
                  <div className="psp-name">
                    <span className="service">{s.service_name}</span>
                    {s.method_name ? <span className="method">.{s.method_name}</span> : null}
                  </div>
                  <div className="psp-meta">
                    <span className="badge">{s.type}</span>
                    <span className="muted">requested_by: {s.requested_by}</span>
                  </div>
                </div>

                <div className="psp-actions">
                  <button className="btn-approve" onClick={() => approve(s.id)}>
                    <CheckCircle size={16} /> Approve
                  </button>
                  <button className="btn-reject" onClick={() => reject(s.id)}>
                    <XCircle size={16} /> Reject
                  </button>
                  <button
                    className="btn-code"
                    onClick={() => setExpanded(prev => ({ ...prev, [s.id]: !prev[s.id] }))}
                    title="Show generated code"
                  >
                    <Code2 size={16} /> Code
                  </button>
                </div>
              </div>

              <div className="psp-reject">
                <input
                  type="text"
                  placeholder="Reject reason (optional)"
                  value={rejectReasons[s.id] || ''}
                  onChange={(e) => setRejectReasons(prev => ({ ...prev, [s.id]: e.target.value }))}
                />
              </div>

              {expanded[s.id] && (
                <pre className="psp-code">
{s.code || ''}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default PendingServicesPanel;

