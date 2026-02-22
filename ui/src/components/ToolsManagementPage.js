import React, { useState, useEffect } from 'react';
import { ArrowLeft, RefreshCw, Zap, Eye, Code, Activity, AlertTriangle, CheckCircle, XCircle } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './ToolsManagementPage.css';

function ToolsManagementPage({ onBack }) {
  const [tools, setTools] = useState([]);
  const [selectedTool, setSelectedTool] = useState(null);
  const [toolDetail, setToolDetail] = useState(null);
  const [executions, setExecutions] = useState([]);
  const [toolCode, setToolCode] = useState(null);
  const [testResults, setTestResults] = useState(null);
  const [testHistory, setTestHistory] = useState([]);
  const [runningTests, setRunningTests] = useState(false);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const toast = useToast();

  useEffect(() => {
    fetchSummary();
    fetchTools();
  }, [statusFilter]);

  useEffect(() => {
    if (selectedTool) {
      fetchToolDetail(selectedTool);
      fetchExecutions(selectedTool);
      fetchTestHistory(selectedTool);
    }
  }, [selectedTool]);

  const fetchSummary = async () => {
    try {
      const res = await fetch(`${API_URL}/tools-management/summary?t=${Date.now()}`);
      const data = await res.json();
      setSummary(data);
    } catch (err) {
      console.error('Failed to fetch summary:', err);
    }
  };

  const fetchTools = async () => {
    try {
      const filter = statusFilter === 'all' ? '' : `?status_filter=${statusFilter}`;
      const separator = filter ? '&' : '?';
      const res = await fetch(`${API_URL}/tools-management/list${filter}${separator}t=${Date.now()}`);
      const data = await res.json();
      setTools(data);
    } catch (err) {
      console.error('Failed to fetch tools:', err);
      toast.error('Failed to load tools');
    }
  };

  const fetchToolDetail = async (toolName) => {
    try {
      const res = await fetch(`${API_URL}/tools-management/detail/${toolName}`);
      const data = await res.json();
      setToolDetail(data);
    } catch (err) {
      console.error('Failed to fetch tool detail:', err);
      toast.error('Failed to load tool details');
    }
  };

  const fetchExecutions = async (toolName) => {
    try {
      const res = await fetch(`${API_URL}/tools-management/executions/${toolName}?limit=10`);
      const data = await res.json();
      setExecutions(data);
    } catch (err) {
      console.error('Failed to fetch executions:', err);
    }
  };

  const fetchToolCode = async (toolName) => {
    try {
      const res = await fetch(`${API_URL}/tools-management/code/${toolName}`);
      const data = await res.json();
      setToolCode(data);
    } catch (err) {
      console.error('Failed to fetch tool code:', err);
      toast.error('Failed to load tool code');
    }
  };

  const fetchTestHistory = async (toolName) => {
    try {
      const res = await fetch(`${API_URL}/tools-management/executions/${toolName}?limit=50`);
      const data = await res.json();
      const tests = data.filter(e => e.metadata && e.metadata.test_name);
      setTestHistory(tests);
    } catch (err) {
      console.error('Failed to fetch test history:', err);
    }
  };

  const runTests = async (toolName) => {
    setRunningTests(true);
    try {
      const res = await fetch(`${API_URL}/api/tools/test/${toolName}`, {
        method: 'POST'
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`Tests passed: ${data.passed_tests}/${data.total_tests} (Quality: ${data.overall_quality_score})`);
        setTestResults(data);
        fetchTestHistory(toolName);
      } else {
        toast.error('Tests failed: ' + data.detail);
      }
    } catch (err) {
      toast.error('Failed to run tests: ' + err.message);
    } finally {
      setRunningTests(false);
    }
  };

  const triggerHealthCheck = async (toolName) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/tools-management/trigger-check/${toolName}`, {
        method: 'POST'
      });
      const data = await res.json();
      toast.success('Health check completed');
      fetchToolDetail(toolName);
    } catch (err) {
      toast.error('Health check failed');
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (recommendation) => {
    switch (recommendation) {
      case 'HEALTHY': return 'status-healthy';
      case 'MONITOR': return 'status-monitor';
      case 'IMPROVE': return 'status-improve';
      case 'QUARANTINE': return 'status-quarantine';
      case 'UNKNOWN': return 'status-unknown';
      default: return 'status-unknown';
    }
  };

  const filteredTools = tools.filter(tool =>
    tool.tool_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="tools-management-page">
      <div className="tools-header">
        <button className="back-btn" onClick={onBack}>
          <ArrowLeft size={20} /> Back
        </button>
        <h1>Tools Management</h1>
        <button className="refresh-btn" onClick={() => { fetchSummary(); fetchTools(); }}>
          <RefreshCw size={18} />
        </button>
      </div>

      {summary && (
        <div className="tools-summary">
          <div className="summary-card">
            <div className="summary-label">Total Tools</div>
            <div className="summary-value">{summary.total_tools}</div>
          </div>
          <div className="summary-card status-healthy">
            <div className="summary-label">Healthy</div>
            <div className="summary-value">{summary.healthy_tools}</div>
          </div>
          <div className="summary-card status-improve">
            <div className="summary-label">Weak</div>
            <div className="summary-value">{summary.weak_tools}</div>
          </div>
          <div className="summary-card status-quarantine">
            <div className="summary-label">Broken</div>
            <div className="summary-value">{summary.quarantine_tools}</div>
          </div>
          <div className="summary-card status-unknown">
            <div className="summary-label">Unknown</div>
            <div className="summary-value">{summary.unknown_tools || 0}</div>
          </div>
          <div className="summary-card">
            <div className="summary-label">With Errors</div>
            <div className="summary-value">{summary.tools_with_errors}</div>
          </div>
        </div>
      )}

      <div className="tools-content">
        <div className="tools-sidebar">
          <div className="sidebar-controls">
            <input
              type="text"
              placeholder="Search tools..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="search-input"
            />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="filter-select"
            >
              <option value="all">All Status</option>
              <option value="HEALTHY">Healthy</option>
              <option value="MONITOR">Monitor</option>
              <option value="IMPROVE">Improve</option>
              <option value="QUARANTINE">Quarantine</option>
            </select>
          </div>

          <div className="tools-list">
            {filteredTools.map(tool => (
              <div
                key={tool.tool_name}
                className={`tool-item ${selectedTool === tool.tool_name ? 'selected' : ''} ${getStatusColor(tool.recommendation)}`}
                onClick={() => setSelectedTool(tool.tool_name)}
              >
                <div className="tool-item-header">
                  <span className="tool-name">{tool.tool_name}</span>
                  {tool.has_recent_errors && <AlertTriangle size={16} className="error-icon" />}
                </div>
                <div className="tool-item-meta">
                  <span className="health-score">{tool.health_score ? tool.health_score.toFixed(0) : '0'}/100</span>
                  <span className={`status-badge ${getStatusColor(tool.recommendation)}`}>
                    {tool.recommendation}
                  </span>
                </div>
                <div className="tool-item-stats">
                  <span>Success: {((tool.success_rate || 0) * 100).toFixed(0)}%</span>
                  <span>Uses: {tool.usage_frequency || 0}</span>
                  {tool.issues_count > 0 && <span className="issues-count">{tool.issues_count} issues</span>}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="tools-main">
          {!selectedTool ? (
            <div className="no-selection">
              <Activity size={48} />
              <p>Select a tool to view details</p>
            </div>
          ) : toolDetail ? (
            <>
              <div className="tool-detail-header">
                <h2>{toolDetail.tool_name}</h2>
                <div className="tool-actions">
                  <button
                    className="action-btn"
                    onClick={() => runTests(selectedTool)}
                    disabled={runningTests}
                    style={{backgroundColor: '#f59e0b'}}
                  >
                    <Activity size={16} /> {runningTests ? 'Testing...' : 'Run Tests'}
                  </button>
                  <button
                    className="action-btn"
                    onClick={() => triggerHealthCheck(selectedTool)}
                    disabled={loading}
                  >
                    <Activity size={16} /> {loading ? 'Checking...' : 'Run Health Check'}
                  </button>
                  <button
                    className="action-btn"
                    onClick={() => window.location.href = `/?mode=evolution&tool=${selectedTool}`}
                  >
                    <Zap size={16} /> Start Evolution
                  </button>
                  <button
                    className="action-btn"
                    onClick={() => fetchToolCode(selectedTool)}
                  >
                    <Code size={16} /> View Code
                  </button>
                </div>
              </div>

              <div className="tool-metrics">
                <div className="metric-card">
                  <div className="metric-label">Health Score</div>
                  <div className={`metric-value ${getStatusColor(toolDetail.recommendation)}`}>
                    {toolDetail.health_score ? toolDetail.health_score.toFixed(0) : '0'}/100
                  </div>
                  <div className="metric-status">{toolDetail.recommendation}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">Success Rate</div>
                  <div className="metric-value">{((toolDetail.success_rate || 0) * 100).toFixed(1)}%</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">Usage</div>
                  <div className="metric-value">{toolDetail.usage_frequency || 0}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">Avg Time</div>
                  <div className="metric-value">{(toolDetail.avg_execution_time_ms || 0).toFixed(0)}ms</div>
                </div>
              </div>

              <div className="tool-info-section">
                <h3>Description</h3>
                <p>{toolDetail.description}</p>
              </div>

              {toolDetail.capabilities && toolDetail.capabilities.length > 0 && (
                <div className="tool-info-section">
                  <h3>Capabilities</h3>
                  <ul className="capabilities-list">
                    {toolDetail.capabilities.map((cap, idx) => (
                      <li key={idx}>{cap}</li>
                    ))}
                  </ul>
                </div>
              )}

              {toolDetail.issues && toolDetail.issues.length > 0 && (
                <div className="tool-info-section issues-section">
                  <h3>Issues ({toolDetail.issues.length})</h3>
                  <ul className="issues-list">
                    {toolDetail.issues.map((issue, idx) => (
                      <li key={idx}><AlertTriangle size={14} /> {issue}</li>
                    ))}
                  </ul>
                </div>
              )}

              {toolDetail.llm_analysis && (
                <div className="tool-info-section llm-section">
                  <h3>LLM Analysis</h3>
                  <p><strong>Purpose:</strong> {toolDetail.llm_analysis.purpose}</p>
                  
                  {toolDetail.llm_analysis.issues && toolDetail.llm_analysis.issues.length > 0 && (
                    <div className="analysis-subsection">
                      <h4>Issues Found ({toolDetail.llm_analysis.issues.length})</h4>
                      <ul>
                        {toolDetail.llm_analysis.issues.map((issue, idx) => (
                          <li key={idx} className={`issue-${issue.severity?.toLowerCase()}`}>
                            <span className="issue-badge">{issue.category}</span>
                            <span className="issue-severity">{issue.severity}</span>
                            <span>{issue.description}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {toolDetail.llm_analysis.improvements && toolDetail.llm_analysis.improvements.length > 0 && (
                    <div className="analysis-subsection">
                      <h4>Suggested Improvements ({toolDetail.llm_analysis.improvements.length})</h4>
                      <ul>
                        {toolDetail.llm_analysis.improvements.map((imp, idx) => (
                          <li key={idx}>
                            <span className="imp-badge">{imp.type}</span>
                            <span className="imp-priority">{imp.priority}</span>
                            <span>{imp.description}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {executions && executions.length > 0 && (
                <div className="tool-info-section">
                  <h3>Recent Executions</h3>
                  <div className="executions-list">
                    {executions.map((exec, idx) => (
                      <div key={idx} className={`execution-item ${exec.status}`}>
                        <div className="exec-header">
                          {exec.status === 'success' ? <CheckCircle size={16} /> : <XCircle size={16} />}
                          <span className="exec-operation">{exec.operation}</span>
                          <span className="exec-time">{exec.execution_time_ms}ms</span>
                        </div>
                        {exec.error_message && (
                          <div className="exec-error">{exec.error_message}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {testResults && (
                <div className="tool-info-section test-results-section">
                  <h3>Latest Test Run</h3>
                  <div className="test-summary">
                    <span>Quality Score: {testResults.overall_quality_score}/100</span>
                    <span>Passed: {testResults.passed_tests}/{testResults.total_tests}</span>
                  </div>
                  {testResults.results_by_capability.map((capResult, idx) => (
                    <div key={idx} className="capability-tests">
                      <h4>{capResult.capability} ({capResult.passed}/{capResult.total_tests} passed)</h4>
                      <div className="test-list">
                        {capResult.test_results.map((test, tidx) => (
                          <div key={tidx} className={`test-card ${test.skipped ? 'skipped' : test.passed ? 'passed' : 'failed'}`}>
                            <div className="test-card-header">
                              {test.skipped ? '⏭️' : test.passed ? <CheckCircle size={16} /> : <XCircle size={16} />}
                              <span className="test-name">{test.test_name}</span>
                              <span className="test-time">{test.execution_time_ms.toFixed(0)}ms</span>
                              <span className="test-quality">Quality: {test.quality_score}/100</span>
                            </div>
                            {test.skipped && test.skip_reason && (
                              <div className="test-skip-reason">
                                <strong>Skipped:</strong> {test.skip_reason}
                              </div>
                            )}
                            {test.inputs && Object.keys(test.inputs).length > 0 && (
                              <div className="test-data">
                                <strong>Input:</strong> <code>{JSON.stringify(test.inputs)}</code>
                              </div>
                            )}
                            {test.output && (
                              <div className="test-data">
                                <strong>Output:</strong> <code>{test.output}</code>
                              </div>
                            )}
                            {test.error && <div className="test-error">Error: {test.error}</div>}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {testHistory && testHistory.length > 0 && (
                <div className="tool-info-section">
                  <h3>Test History ({testHistory.length})</h3>
                  <div className="executions-list">
                    {testHistory.slice(0, 10).map((test, idx) => (
                      <div key={idx} className={`execution-item ${test.status}`}>
                        <div className="exec-header">
                          {test.status === 'success' ? <CheckCircle size={16} /> : <XCircle size={16} />}
                          <span className="exec-operation">{test.metadata.test_name}</span>
                          <span className="exec-time">{test.execution_time_ms}ms</span>
                          <span className="test-quality">Q: {test.metadata.quality_score}</span>
                        </div>
                        {test.error_message && (
                          <div className="exec-error">{test.error_message}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {toolCode && (
                <div className="code-modal" onClick={() => setToolCode(null)}>
                  <div className="code-content" onClick={(e) => e.stopPropagation()}>
                    <div className="code-header">
                      <h3>{toolCode.tool_name} - Source Code</h3>
                      <button onClick={() => setToolCode(null)}>×</button>
                    </div>
                    <pre className="code-block">{toolCode.code}</pre>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="loading">Loading...</div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ToolsManagementPage;
