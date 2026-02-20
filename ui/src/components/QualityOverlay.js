import React, { useState, useEffect } from 'react';
import { AlertTriangle, CheckCircle, TrendingUp, Clock, RefreshCw, Trash2 } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './QualityOverlay.css';

function QualityOverlay() {
  const [qualityData, setQualityData] = useState(null);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  useEffect(() => {
    fetchQualityData();
  }, []);

  const fetchQualityData = async () => {
    try {
      const res = await fetch(`${API_URL}/quality/all`);
      const tools = await res.json();
      
      const weakTools = (tools || []).filter(t => t.health_score < 70);
      const healthyTools = (tools || []).filter(t => t.health_score >= 70);
      const avgSuccess = tools.length > 0 
        ? tools.reduce((sum, t) => sum + t.success_rate, 0) / tools.length 
        : 0;
      const totalExec = tools.reduce((sum, t) => sum + (t.usage_frequency || 0), 0);
      
      setQualityData({
        healthy_tools: healthyTools.length,
        weak_tools: weakTools.length,
        avg_success_rate: avgSuccess,
        total_executions: totalExec,
        weak_tools_list: weakTools
      });
    } catch (err) {
      console.error('Failed to fetch quality data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCleanup = async () => {
    if (!window.confirm('Remove execution logs for non-existent tools?')) return;
    try {
      const res = await fetch(`${API_URL}/observability/cleanup`, { method: 'POST' });
      const data = await res.json();
      toast.success(data.message);
      fetchQualityData();
    } catch (err) {
      toast.error('Cleanup failed');
    }
  };

  const handleRefresh = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/observability/refresh`, { method: 'POST' });
      const data = await res.json();
      toast.success(data.message);
      fetchQualityData();
    } catch (err) {
      toast.error('Refresh failed');
    }
  };

  if (loading) return <div className="quality-loading">Loading quality data...</div>;
  if (!qualityData) return <div className="quality-error">Failed to load quality data</div>;

  return (
    <div className="quality-overlay">
      <div className="quality-actions">
        <button onClick={handleRefresh} className="action-btn" disabled={loading}>
          <RefreshCw size={16} /> Refresh
        </button>
        <button onClick={handleCleanup} className="action-btn danger">
          <Trash2 size={16} /> Clean Stale Data
        </button>
      </div>

      <div className="quality-stats">
        <div className="stat-card">
          <div className="stat-icon healthy"><CheckCircle size={24} /></div>
          <div className="stat-info">
            <div className="stat-value">{qualityData.healthy_tools || 0}</div>
            <div className="stat-label">Healthy Tools</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon warning"><AlertTriangle size={24} /></div>
          <div className="stat-info">
            <div className="stat-value">{qualityData.weak_tools || 0}</div>
            <div className="stat-label">Weak Tools</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon"><TrendingUp size={24} /></div>
          <div className="stat-info">
            <div className="stat-value">{qualityData.avg_success_rate?.toFixed(1) || 0}%</div>
            <div className="stat-label">Avg Success Rate</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon"><Clock size={24} /></div>
          <div className="stat-info">
            <div className="stat-value">{qualityData.total_executions || 0}</div>
            <div className="stat-label">Total Executions</div>
          </div>
        </div>
      </div>

      {qualityData.weak_tools_list && qualityData.weak_tools_list.length > 0 && (
        <div className="weak-tools-section">
          <h4>Tools Needing Attention</h4>
          {qualityData.weak_tools_list.map(tool => (
            <div key={tool.tool_name} className="weak-tool-card">
              <div className="tool-header">
                <span className="tool-name">{tool.tool_name}</span>
                <span className={`health-badge ${(tool.recommendation || '').toLowerCase()}`}>
                  {tool.recommendation || 'MONITOR'}
                </span>
              </div>
              <div className="tool-metrics">
                <span>Success: {(tool.success_rate || 0).toFixed(1)}%</span>
                <span>Health: {(tool.health_score || 0).toFixed(0)}/100</span>
                <span>Risk: {(tool.avg_risk_score || 0).toFixed(2)}</span>
              </div>
              {tool.issues && tool.issues.length > 0 && (
                <div className="tool-issues">
                  {tool.issues.map((issue, idx) => (
                    <div key={idx} className="issue-tag">{issue}</div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default QualityOverlay;
