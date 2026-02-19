import React, { useState, useEffect } from 'react';

function ToolRegistryPanel({ apiUrl }) {
  const [registry, setRegistry] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [lastSync, setLastSync] = useState(null);
  const [syncResult, setSyncResult] = useState(null);

  useEffect(() => {
    loadRegistry();
  }, []);

  const loadRegistry = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/tools/registry`);
      const data = await response.json();
      setRegistry(data);
      setLastSync(data.last_sync);
    } catch (error) {
      console.error('Failed to load registry:', error);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncResult(null);

    try {
      const response = await fetch(`${apiUrl}/api/tools/sync`, {
        method: 'POST'
      });
      const data = await response.json();
      
      setSyncResult(data);
      
      if (data.success) {
        await loadRegistry();
      }
    } catch (error) {
      setSyncResult({
        success: false,
        message: `Error: ${error.message}`
      });
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div style={{ padding: '20px' }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: '20px'
      }}>
        <h2 style={{ margin: 0 }}>Tool Registry</h2>
        <button
          onClick={handleSync}
          disabled={syncing}
          style={{
            padding: '10px 20px',
            background: syncing ? '#666' : '#10b981',
            color: '#fff',
            border: 'none',
            borderRadius: '6px',
            cursor: syncing ? 'not-allowed' : 'pointer',
            fontWeight: 600
          }}
        >
          {syncing ? '🔄 Syncing...' : '🔄 Sync Tool Capabilities'}
        </button>
      </div>

      {lastSync && (
        <div style={{
          padding: '10px',
          background: '#1f2937',
          borderRadius: '6px',
          marginBottom: '15px',
          fontSize: '14px',
          color: '#9ca3af'
        }}>
          Last synced: {new Date(lastSync).toLocaleString()}
        </div>
      )}

      {syncResult && (
        <div style={{
          padding: '15px',
          background: syncResult.success ? '#065f46' : '#7f1d1d',
          borderRadius: '6px',
          marginBottom: '15px'
        }}>
          <div style={{ fontWeight: 600, marginBottom: '5px' }}>
            {syncResult.success ? '✅ Sync Complete' : '❌ Sync Failed'}
          </div>
          <div style={{ fontSize: '14px' }}>{syncResult.message}</div>
          {syncResult.synced && syncResult.synced.length > 0 && (
            <div style={{ marginTop: '10px', fontSize: '13px' }}>
              Synced: {syncResult.synced.join(', ')}
            </div>
          )}
          {syncResult.failed && syncResult.failed.length > 0 && (
            <div style={{ marginTop: '10px', fontSize: '13px', color: '#fca5a5' }}>
              Failed: {syncResult.failed.map((f) => {
                if (typeof f === 'string') return f;
                if (f.file && f.reason) return `${f.file}: ${f.reason}`;
                if (f.tool && f.error) return `${f.tool}: ${f.error}`;
                return JSON.stringify(f);
              }).join(' | ')}
            </div>
          )}
        </div>
      )}

      {registry && registry.tools && Object.keys(registry.tools).length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
          {Object.entries(registry.tools).map(([toolName, toolData]) => (
            <div
              key={toolName}
              style={{
                background: '#1f2937',
                borderRadius: '8px',
                padding: '15px',
                border: '1px solid #374151'
              }}
            >
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '10px'
              }}>
                <h3 style={{ margin: 0, color: '#10b981' }}>{toolData.name || toolName}</h3>
                {toolData.version && (
                  <span style={{
                    padding: '4px 8px',
                    background: '#374151',
                    borderRadius: '4px',
                    fontSize: '12px',
                    color: '#9ca3af'
                  }}>
                    v{toolData.version}
                  </span>
                )}
              </div>

              {toolData.description && (
                <p style={{ margin: '0 0 15px 0', color: '#d1d5db', fontSize: '14px' }}>
                  {toolData.description}
                </p>
              )}

              {toolData.operations && Object.keys(toolData.operations).length > 0 && (
                <div>
                  <div style={{ 
                    fontWeight: 600, 
                    marginBottom: '8px',
                    color: '#9ca3af',
                    fontSize: '13px'
                  }}>
                    Operations:
                  </div>
                  {Object.entries(toolData.operations).map(([opName, opData]) => (
                    <div
                      key={opName}
                      style={{
                        background: '#111827',
                        padding: '10px',
                        borderRadius: '6px',
                        marginBottom: '8px'
                      }}
                    >
                      <div style={{ 
                        fontFamily: 'monospace', 
                        color: '#60a5fa',
                        marginBottom: '5px'
                      }}>
                        {opName}({opData.parameters ? opData.parameters.join(', ') : ''})
                      </div>
                      {opData.description && (
                        <div style={{ fontSize: '13px', color: '#9ca3af' }}>
                          {opData.description}
                        </div>
                      )}
                      {opData.required && opData.required.length > 0 && (
                        <div style={{ 
                          fontSize: '12px', 
                          color: '#fbbf24',
                          marginTop: '5px'
                        }}>
                          Required: {opData.required.join(', ')}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {toolData.last_updated && (
                <div style={{
                  marginTop: '10px',
                  fontSize: '12px',
                  color: '#6b7280'
                }}>
                  Updated: {new Date(toolData.last_updated).toLocaleString()}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div style={{
          padding: '40px',
          textAlign: 'center',
          background: '#1f2937',
          borderRadius: '8px',
          color: '#9ca3af'
        }}>
          <div style={{ fontSize: '48px', marginBottom: '10px' }}>📋</div>
          <div>No tools registered yet</div>
          <div style={{ fontSize: '14px', marginTop: '5px' }}>
            Click "Sync Tool Capabilities" to analyze and register tools
          </div>
        </div>
      )}
    </div>
  );
}

export default ToolRegistryPanel;
