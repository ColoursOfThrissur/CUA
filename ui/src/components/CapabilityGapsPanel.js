import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, RefreshCw, Target, PlusCircle } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './CapabilityGapsPanel.css';

function CapabilityGapsPanel() {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);

  const gapsList = useMemo(() => {
    const list = data?.gaps?.gaps || [];
    return Array.isArray(list) ? list : [];
  }, [data]);

  const actionable = useMemo(() => {
    return gapsList.filter(g => (g.occurrences || 0) >= 3 && (g.confidence || 0) >= 0.7);
  }, [gapsList]);

  const fetchGaps = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/improvement/evolution/capability-gaps`);
      const json = await res.json();
      setData(json);
    } catch (e) {
      toast.error('Failed to load capability gaps');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGaps();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreateTool = (gap) => {
    localStorage.setItem('prefillToolDescription', `Create a tool for: ${gap.capability}`);
    window.dispatchEvent(new CustomEvent('switchMode', { detail: 'tools' }));
  };

  const summary = data?.gaps || {};

  return (
    <div className="capability-gaps-panel">
      <div className="cgp-header">
        <div className="cgp-title">
          <Target size={18} />
          <h3>Capability Gaps</h3>
        </div>
        <button className="cgp-refresh" onClick={fetchGaps} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="cgp-summary">
        <div className="cgp-metric">
          <div className="label">Total</div>
          <div className="value">{summary.total_gaps || 0}</div>
        </div>
        <div className="cgp-metric">
          <div className="label">Persistent</div>
          <div className="value">{summary.persistent_gaps || 0}</div>
        </div>
        <div className="cgp-metric">
          <div className="label">High confidence</div>
          <div className="value">{summary.high_confidence_gaps || 0}</div>
        </div>
        <div className="cgp-metric">
          <div className="label">Actionable</div>
          <div className="value">{summary.actionable_gaps || 0}</div>
        </div>
      </div>

      {actionable.length > 0 && (
        <div className="cgp-section">
          <h4>Actionable (likely to trigger self-feature creation)</h4>
          <div className="cgp-list">
            {actionable.map((g) => (
              <div key={g.capability} className="cgp-item actionable">
                <div className="cap">{g.capability}</div>
                <div className="cgp-item-footer">
                  <div className="meta">
                    <span>{g.occurrences} occurrences</span>
                    <span>{Math.round((g.confidence || 0) * 100)}% confidence</span>
                    {g.suggested_library ? <span>lib: {g.suggested_library}</span> : null}
                  </div>
                  <button className="cgp-create-btn" onClick={() => handleCreateTool(g)} title="Create tool for this gap">
                    <PlusCircle size={14} /> Create Tool
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="cgp-section">
        <h4>All gaps</h4>
        {gapsList.length === 0 ? (
          <div className="cgp-empty">
            <AlertTriangle size={18} />
            <span>No gaps recorded yet</span>
          </div>
        ) : (
          <div className="cgp-list">
            {gapsList.map((g) => (
              <div key={g.capability} className="cgp-item">
                <div className="cap">{g.capability}</div>
                <div className="cgp-item-footer">
                  <div className="meta">
                    <span>{g.occurrences} occurrences</span>
                    <span>{Math.round((g.confidence || 0) * 100)}% confidence</span>
                    {g.suggested_library ? <span>lib: {g.suggested_library}</span> : null}
                  </div>
                  <button className="cgp-create-btn" onClick={() => handleCreateTool(g)} title="Create tool for this gap">
                    <PlusCircle size={14} /> Create Tool
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default CapabilityGapsPanel;

