import React from 'react';

function TestApp() {
  return (
    <div style={{ padding: '20px', fontFamily: 'Arial' }}>
      <h1>CUA Test UI</h1>
      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
        <button style={{ padding: '10px 20px', background: '#007bff', color: 'white', border: 'none', borderRadius: '4px' }}>
          Chat
        </button>
        <button style={{ padding: '10px 20px', background: '#28a745', color: 'white', border: 'none', borderRadius: '4px' }}>
          Tools
        </button>
        <button style={{ padding: '10px 20px', background: '#ffc107', color: 'black', border: 'none', borderRadius: '4px' }}>
          Evolution
        </button>
      </div>
      <div style={{ border: '1px solid #ccc', padding: '20px', borderRadius: '4px' }}>
        <h2>Test Chat Interface</h2>
        <div style={{ marginBottom: '10px', padding: '10px', background: '#f8f9fa', borderRadius: '4px' }}>
          <strong>System:</strong> CUA Test UI is working!
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <input 
            type="text" 
            placeholder="Type a message..." 
            style={{ flex: 1, padding: '10px', border: '1px solid #ccc', borderRadius: '4px' }}
          />
          <button style={{ padding: '10px 20px', background: '#007bff', color: 'white', border: 'none', borderRadius: '4px' }}>
            Send
          </button>
        </div>
      </div>
      <div style={{ marginTop: '20px', fontSize: '12px', color: '#666' }}>
        <p>✓ React is working</p>
        <p>✓ Basic styling is working</p>
        <p>✓ Components are rendering</p>
        <p>API URL: {process.env.REACT_APP_API_URL || 'Not set'}</p>
        <p>WS URL: {process.env.REACT_APP_WS_URL || 'Not set'}</p>
      </div>
    </div>
  );
}

export default TestApp;