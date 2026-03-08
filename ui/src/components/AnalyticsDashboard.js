import React, { useState, useEffect } from 'react';
import { API_URL } from '../config';
import './AnalyticsDashboard.css';

function AnalyticsDashboard() {
  const [analytics, setAnalytics] = useState(null);
  const [days, setDays] = useState(30);

  useEffect(() => {
    fetchAnalytics();
    const interval = setInterval(fetchAnalytics, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [days]);

  const fetchAnalytics = async () => {
    try {
      const response = await fetch(`${API_URL}/improvement/analytics?days=${days}`);
      const data = await response.json();
      setAnalytics(data);
    } catch (error) {
      console.error('Failed to fetch analytics:', error);
    }
  };

  if (!analytics) {
    return <div className="analytics-loading">Loading analytics...</div>;
  }

  return (
    <div className="analytics-dashboard">
      <div className="analytics-header">
        <h3>Improvement Analytics</h3>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      <div className="analytics-grid">
        <div className="analytics-card">
          <div className="card-label">Total Attempts</div>
          <div className="card-value">{analytics.total_attempts}</div>
        </div>

        <div className="analytics-card">
          <div className="card-label">Success Rate</div>
          <div className="card-value">{(analytics.success_rate || 0).toFixed(1)}%</div>
          <div className="card-subtext">
            {analytics.successful_attempts} / {analytics.total_attempts}
          </div>
        </div>

        <div className="analytics-card">
          <div className="card-label">Avg Duration</div>
          <div className="card-value">{analytics.avg_duration_seconds || 0}s</div>
        </div>

        <div className="analytics-card">
          <div className="card-label">Risk Distribution</div>
          <div className="risk-bars">
            {Object.entries(analytics.risk_distribution || {}).map(([level, count]) => (
              <div key={level} className="risk-bar">
                <span className={`risk-label risk-${level.toLowerCase()}`}>{level}</span>
                <div className="risk-bar-fill" style={{ width: `${(count / analytics.total_attempts) * 100}%` }}>
                  {count}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {(analytics.common_errors || []).length > 0 && (
        <div className="analytics-section">
          <h4>Common Errors</h4>
          <div className="error-list">
            {(analytics.common_errors || []).map((err, idx) => (
              <div key={idx} className="error-item">
                <span className="error-type">{err.error}</span>
                <span className="error-count">{err.count} occurrences</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(analytics.daily_trend || []).length > 0 && (
        <div className="analytics-section">
          <h4>Daily Trend</h4>
          <div className="trend-chart">
            {(analytics.daily_trend || []).slice(0, 14).reverse().map((day, idx) => (
              <div key={idx} className="trend-bar">
                <div className="trend-date">{day.date.slice(5)}</div>
                <div className="trend-bars">
                  <div 
                    className="trend-success" 
                    style={{ height: `${(day.successes / Math.max(...(analytics.daily_trend || []).map(d => d.attempts))) * 100}px` }}
                    title={`${day.successes} successes`}
                  />
                  <div 
                    className="trend-total" 
                    style={{ height: `${(day.attempts / Math.max(...(analytics.daily_trend || []).map(d => d.attempts))) * 100}px` }}
                    title={`${day.attempts} total`}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default AnalyticsDashboard;
