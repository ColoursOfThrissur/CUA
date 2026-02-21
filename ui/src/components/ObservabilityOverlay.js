import React, { useState, useEffect } from 'react';
import { Database, Activity, Wrench, Zap, MessageSquare, RefreshCw, Brain } from 'lucide-react';
import { API_URL } from '../config';
import './ObservabilityOverlay.css';

function ObservabilityOverlay() {
  const [activeDb, setActiveDb] = useState('logs');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [refreshingLLM, setRefreshingLLM] = useState(false);

  useEffect(() => {
    fetchData();
  }, [activeDb]);

  const fetchData = async () => {
    setLoading(true);
    try {
      let endpoint = '';
      switch (activeDb) {
        case 'logs':
          endpoint = '/observability/logs';
          break;
        case 'tool_executions':
          endpoint = '/observability/tool-executions';
          break;
        case 'tool_creation':
          endpoint = '/observability/tool-creation';
          break;
        case 'tool_evolution':
          endpoint = '/observability/tool-evolution';
          break;
        case 'chat':
          endpoint = '/observability/chat';
          break;
        case 'llm_health':
          endpoint = '/quality/llm-analysis-all';
          break;
        default:
          endpoint = '/observability/logs';
      }
      
      const res = await fetch(`${API_URL}${endpoint}${activeDb === 'llm_health' ? '' : '?limit=50'}`);
      const result = await res.json();
      
      if (activeDb === 'llm_health') {
        // Convert object to array for display
        setData(Object.values(result));
      } else {
        setData(result.data || []);
      }
    } catch (err) {
      console.error('Failed to fetch data:', err);
    } finally {
      setLoading(false);
    }
  };

  const refreshLLMAnalysis = async () => {
    setRefreshingLLM(true);
    try {
      await fetch(`${API_URL}/quality/refresh-llm-analysis`, { method: 'POST' });
      if (activeDb === 'llm_health') {
        fetchData();
      }
    } catch (err) {
      console.error('Failed to refresh LLM analysis:', err);
    } finally {
      setRefreshingLLM(false);
    }
  };

  const databases = [
    { id: 'logs', label: 'System Logs', icon: Activity },
    { id: 'tool_executions', label: 'Tool Executions', icon: Wrench },
    { id: 'tool_creation', label: 'Tool Creation', icon: Database },
    { id: 'tool_evolution', label: 'Tool Evolution', icon: Zap },
    { id: 'chat', label: 'Chat History', icon: MessageSquare },
    { id: 'llm_health', label: 'LLM Health Analysis', icon: Brain }
  ];

  return (
    <div className="observability-overlay">
      <div className="obs-header">
        <div className="obs-tabs">
          {databases.map(db => {
            const Icon = db.icon;
            return (
              <button
                key={db.id}
                className={`obs-tab ${activeDb === db.id ? 'active' : ''}`}
                onClick={() => setActiveDb(db.id)}
              >
                <Icon size={16} />
                {db.label}
              </button>
            );
          })}
        </div>
        <div className="obs-actions">
          {activeDb === 'llm_health' && (
            <button 
              className="obs-refresh-llm" 
              onClick={refreshLLMAnalysis} 
              disabled={refreshingLLM}
              title="Refresh LLM Analysis"
            >
              <Brain size={16} className={refreshingLLM ? 'spin' : ''} />
              {refreshingLLM ? 'Analyzing...' : 'Refresh Analysis'}
            </button>
          )}
          <button className="obs-refresh" onClick={fetchData} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      <div className="obs-content">
        {loading ? (
          <div className="obs-loading">Loading...</div>
        ) : data.length === 0 ? (
          <div className="obs-empty">No data</div>
        ) : (
          <div className="obs-table">
            <table>
              <thead>
                <tr>
                  {Object.keys(data[0] || {}).map(key => (
                    <th key={key}>{key}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((row, idx) => (
                  <tr key={idx}>
                    {Object.values(row).map((val, i) => (
                      <td key={i}>{typeof val === 'object' ? JSON.stringify(val) : String(val)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default ObservabilityOverlay;
