import React, { useState, useEffect } from 'react';

function PendingLibrariesPanel({ apiUrl }) {
  const [pendingLibraries, setPendingLibraries] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadPendingLibraries();
    const interval = setInterval(loadPendingLibraries, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadPendingLibraries = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/libraries/pending`);
      const data = await response.json();
      setPendingLibraries(data.pending_libraries || []);
    } catch (error) {
      console.error('Failed to load pending libraries:', error);
    }
  };

  const handleApprove = async (libId) => {
    setLoading(true);
    try {
      const response = await fetch(`${apiUrl}/api/libraries/${libId}/approve`, {
        method: 'POST'
      });
      
      if (response.ok) {
        await loadPendingLibraries();
        alert('Library installed successfully!');
      } else {
        const data = await response.json();
        alert(`Failed to install: ${data.detail}`);
      }
    } catch (error) {
      alert(`Error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async (libId) => {
    if (!window.confirm('Reject this library installation?')) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${apiUrl}/api/libraries/${libId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'User rejected' })
      });
      
      if (response.ok) {
        await loadPendingLibraries();
      }
    } catch (error) {
      alert(`Error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  if (pendingLibraries.length === 0) {
    return (
      <div style={{
        padding: '40px',
        textAlign: 'center',
        background: '#1f2937',
        borderRadius: '8px',
        color: '#9ca3af'
      }}>
        <div style={{ fontSize: '48px', marginBottom: '10px' }}>📦</div>
        <div>No pending library approvals</div>
      </div>
    );
  }

  return (
    <div style={{ padding: '20px' }}>
      <h3 style={{ marginTop: 0, marginBottom: '20px' }}>Pending Library Approvals</h3>
      
      <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
        {pendingLibraries.map((lib) => (
          <div
            key={lib.id}
            style={{
              background: '#1f2937',
              borderRadius: '8px',
              padding: '15px',
              border: '2px solid #f59e0b'
            }}
          >
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              marginBottom: '10px'
            }}>
              <div style={{ flex: 1 }}>
                <div style={{
                  fontSize: '18px',
                  fontWeight: 600,
                  color: '#f59e0b',
                  marginBottom: '5px',
                  fontFamily: 'monospace'
                }}>
                  📦 {lib.library}
                </div>
                <div style={{ fontSize: '14px', color: '#d1d5db', marginBottom: '8px' }}>
                  {lib.reason}
                </div>
                <div style={{ fontSize: '12px', color: '#6b7280' }}>
                  Proposed by: {lib.proposed_by} • {new Date(lib.timestamp).toLocaleString()}
                </div>
              </div>
            </div>

            <div style={{
              display: 'flex',
              gap: '10px',
              marginTop: '15px'
            }}>
              <button
                onClick={() => handleApprove(lib.id)}
                disabled={loading}
                style={{
                  flex: 1,
                  padding: '10px',
                  background: loading ? '#666' : '#10b981',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  fontWeight: 600
                }}
              >
                {loading ? '⏳ Installing...' : '✅ Approve & Install'}
              </button>
              <button
                onClick={() => handleReject(lib.id)}
                disabled={loading}
                style={{
                  flex: 1,
                  padding: '10px',
                  background: loading ? '#666' : '#ef4444',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  fontWeight: 600
                }}
              >
                ❌ Reject
              </button>
            </div>

            <div style={{
              marginTop: '10px',
              padding: '10px',
              background: '#111827',
              borderRadius: '6px',
              fontSize: '12px',
              color: '#9ca3af'
            }}>
              <div style={{ fontWeight: 600, marginBottom: '5px' }}>⚠️ Security Notice:</div>
              <div>Installing third-party libraries can introduce security risks. Only approve if you trust the source.</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default PendingLibrariesPanel;
