import React, { useEffect, useState } from 'react';
import { Trash2, MessageSquare, Clock, User, RefreshCw, GitBranch, Wrench } from 'lucide-react';
import { API_URL } from '../config';
import './SessionManagement.css';

function SessionManagement({ onClose, currentSessionId, onRunCommand }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSession, setSelectedSession] = useState(null);
  const [sessionSummary, setSessionSummary] = useState('');
  const [sessionActionState, setSessionActionState] = useState({ loading: false, message: '' });
  const [worktreeData, setWorktreeData] = useState({ worktrees: [], readiness: null, managed_count: 0 });
  const [worktreeLoading, setWorktreeLoading] = useState(false);
  const [worktreeLabel, setWorktreeLabel] = useState('');
  const [handoffOwner, setHandoffOwner] = useState('operator');
  const [worktreeMessage, setWorktreeMessage] = useState('');

  useEffect(() => {
    loadSessions();
    loadWorktrees();
  }, []);

  const loadSessions = async () => {
    try {
      const response = await fetch(`${API_URL}/sessions/list`);
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadWorktrees = async () => {
    setWorktreeLoading(true);
    setWorktreeMessage('');
    try {
      const response = await fetch(`${API_URL}/api/worktrees/list`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Failed to load worktrees');
      }
      setWorktreeData(data);
    } catch (error) {
      console.error('Failed to load worktrees:', error);
      setWorktreeMessage(error.message);
      setWorktreeData({ worktrees: [], readiness: null, managed_count: 0 });
    } finally {
      setWorktreeLoading(false);
    }
  };

  const handleDeleteSession = async (sessionId) => {
    if (!window.confirm('Delete this session and all its messages?')) return;

    try {
      await fetch(`${API_URL}/sessions/${sessionId}`, { method: 'DELETE' });
      setSessions(sessions.filter(s => s.session_id !== sessionId));
      if (selectedSession?.session_id === sessionId) {
        setSelectedSession(null);
        setSessionSummary('');
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  const handleViewSession = async (session) => {
    try {
      const response = await fetch(`${API_URL}/sessions/${session.session_id}`);
      const data = await response.json();
      setSelectedSession(data);
      setSessionSummary('');
      setSessionActionState({ loading: false, message: '' });
    } catch (error) {
      console.error('Failed to load session details:', error);
    }
  };

  const handleSessionAction = async (action) => {
    if (!selectedSession) return;
    setSessionActionState({ loading: true, message: '' });
    try {
      let response;
      let data;
      if (action === 'summary') {
        response = await fetch(`${API_URL}/sessions/${selectedSession.session_id}/summary`);
        data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Failed to summarize session');
        setSessionSummary(data.summary_text || '');
        setSessionActionState({ loading: false, message: 'Session summary refreshed.' });
        return;
      }
      if (action === 'resume') {
        response = await fetch(`${API_URL}/sessions/${selectedSession.session_id}/resume`, { method: 'POST' });
        data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Failed to resume session');
        setSessionActionState({ loading: false, message: `Restored ${data.message_count || 0} messages into live runtime.` });
        await loadSessions();
        return;
      }
      if (action === 'compact') {
        response = await fetch(`${API_URL}/sessions/${selectedSession.session_id}/compact?keep_recent=8`, { method: 'POST' });
        data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Failed to compact session');
        setSessionSummary(data.summary_text || '');
        setSessionActionState({
          loading: false,
          message: data.already_compact ? 'Session was already compact.' : `Compacted session and removed ${data.removed_count || 0} older messages.`,
        });
        await handleViewSession({ session_id: selectedSession.session_id });
        await loadSessions();
        return;
      }
      if (action === 'export') {
        response = await fetch(`${API_URL}/sessions/${selectedSession.session_id}/export`, { method: 'POST' });
        data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Failed to export session');
        setSessionActionState({ loading: false, message: `Export ready at ${data.path}` });
        return;
      }
    } catch (error) {
      console.error(`Failed to run session action ${action}:`, error);
      setSessionActionState({ loading: false, message: error.message });
    }
  };

  const handleRuntimeCommand = async (command) => {
    if (!onRunCommand) return;
    setSessionActionState({ loading: true, message: '' });
    try {
      await onRunCommand(command);
      setSessionActionState({ loading: false, message: `Sent ${command} to the active chat session.` });
    } catch (error) {
      console.error(`Failed to send command ${command}:`, error);
      setSessionActionState({ loading: false, message: error.message });
    }
  };

  const handleCreateWorktree = async () => {
    const trimmed = worktreeLabel.trim();
    if (!trimmed) return;
    setWorktreeLoading(true);
    setWorktreeMessage('');
    try {
      const response = await fetch(`${API_URL}/api/worktrees/${encodeURIComponent(trimmed)}`, { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to create worktree');
      setWorktreeLabel('');
      setWorktreeMessage(`Created worktree ${data.label} at ${data.worktree_path}`);
      await loadWorktrees();
    } catch (error) {
      console.error('Failed to create worktree:', error);
      setWorktreeMessage(error.message);
    } finally {
      setWorktreeLoading(false);
    }
  };

  const handleRemoveWorktree = async (label, dirty) => {
    if (!label) return;
    const confirmMessage = dirty
      ? `Remove worktree ${label}? It has local changes and will be removed with force.`
      : `Remove worktree ${label}?`;
    if (!window.confirm(confirmMessage)) return;

    setWorktreeLoading(true);
    setWorktreeMessage('');
    try {
      const suffix = dirty ? '?force=true' : '';
      const response = await fetch(`${API_URL}/api/worktrees/${encodeURIComponent(label)}${suffix}`, { method: 'DELETE' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to remove worktree');
      setWorktreeMessage(`Removed worktree ${data.label}`);
      await loadWorktrees();
    } catch (error) {
      console.error('Failed to remove worktree:', error);
      setWorktreeMessage(error.message);
    } finally {
      setWorktreeLoading(false);
    }
  };

  const handleCleanupWorktrees = async (apply = false) => {
    if (apply && !window.confirm('Remove all clean stale Forge-managed worktrees that are currently marked as cleanup candidates?')) {
      return;
    }
    setWorktreeLoading(true);
    setWorktreeMessage('');
    try {
      const response = await fetch(`${API_URL}/api/worktrees/cleanup`, { method: apply ? 'POST' : 'GET' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to review cleanup candidates');
      if (apply) {
        setWorktreeMessage(`Cleanup removed ${data.removed_count || 0} worktrees and skipped ${data.failed_count || 0}.`);
      } else {
        setWorktreeMessage(`Cleanup preview found ${data.candidate_count || 0} clean stale worktree candidates.`);
      }
      await loadWorktrees();
    } catch (error) {
      console.error('Failed to run cleanup workflow:', error);
      setWorktreeMessage(error.message);
    } finally {
      setWorktreeLoading(false);
    }
  };

  const handleAssignHandoff = async (label) => {
    const owner = handoffOwner.trim();
    if (!label || !owner) return;
    setWorktreeLoading(true);
    setWorktreeMessage('');
    try {
      const params = new URLSearchParams({
        owner,
        purpose: 'bounded handoff',
        session_id: currentSessionId || '',
      });
      const response = await fetch(`${API_URL}/api/worktrees/${encodeURIComponent(label)}/handoff?${params.toString()}`, {
        method: 'POST',
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to assign worktree handoff');
      setWorktreeMessage(`Assigned ${label} to ${data.handoff.owner}.`);
      await loadWorktrees();
    } catch (error) {
      console.error('Failed to assign worktree handoff:', error);
      setWorktreeMessage(error.message);
    } finally {
      setWorktreeLoading(false);
    }
  };

  const handleReleaseHandoff = async (label) => {
    if (!label) return;
    setWorktreeLoading(true);
    setWorktreeMessage('');
    try {
      const response = await fetch(`${API_URL}/api/worktrees/${encodeURIComponent(label)}/handoff`, {
        method: 'DELETE',
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to release worktree handoff');
      setWorktreeMessage(`Released handoff for ${label}.`);
      await loadWorktrees();
    } catch (error) {
      console.error('Failed to release worktree handoff:', error);
      setWorktreeMessage(error.message);
    } finally {
      setWorktreeLoading(false);
    }
  };

  const formatDate = (timestamp) => {
    return new Date(timestamp).toLocaleString();
  };

  const formatHours = (hours) => {
    if (hours === null || hours === undefined || Number.isNaN(Number(hours))) {
      return 'n/a';
    }
    if (hours < 1) {
      return '<1h';
    }
    if (hours < 24) {
      return `${Math.round(hours)}h`;
    }
    return `${Math.round(hours / 24)}d`;
  };

  const canDeepPlanSelectedSession = Boolean(
    selectedSession &&
    selectedSession.session_id === currentSessionId &&
    selectedSession.active_goal &&
    onRunCommand
  );

  if (loading) {
    return <div className="session-loading">Loading sessions...</div>;
  }

  return (
    <div className="session-management">
      <div className="session-list">
        <div className="session-header">
          <h3>Active Sessions ({sessions.length})</h3>
          <div className="session-runtime-controls">
            <button type="button" onClick={() => handleRuntimeCommand('/doctor')} disabled={sessionActionState.loading || !onRunCommand}>
              <Wrench size={14} /> Run Doctor
            </button>
            <button type="button" onClick={() => handleRuntimeCommand('/memory maintain')} disabled={sessionActionState.loading || !onRunCommand}>
              <RefreshCw size={14} /> Maintain Memory
            </button>
            <button type="button" onClick={() => handleRuntimeCommand('/worktree')} disabled={sessionActionState.loading || !onRunCommand}>
              <GitBranch size={14} /> Check Worktrees
            </button>
          </div>
        </div>

        {sessions.length === 0 ? (
          <div className="session-empty">No active sessions</div>
        ) : (
          <div className="session-items">
            {sessions.map(session => (
              <div
                key={session.session_id}
                className={`session-item ${selectedSession?.session_id === session.session_id ? 'selected' : ''}`}
                onClick={() => handleViewSession(session)}
              >
                <div className="session-item-header">
                  <User size={16} />
                  <span className="session-id">{session.session_id.slice(0, 8)}...</span>
                  {session.session_id === currentSessionId && <span className="session-badge">live</span>}
                </div>
                <div className="session-item-stats">
                  <span><MessageSquare size={14} /> {session.message_count} messages</span>
                  <span><Clock size={14} /> {formatDate(session.updated_at)}</span>
                </div>
                {session.active_goal && (
                  <div className="session-goal">Goal: {session.active_goal}</div>
                )}
                <button
                  className="session-delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteSession(session.session_id);
                  }}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="worktree-panel">
          <div className="worktree-panel-header">
            <h4>Isolated Worktrees</h4>
            <div className="worktree-panel-actions">
              <button type="button" onClick={() => handleCleanupWorktrees(false)} disabled={worktreeLoading}>
                Review Cleanup
              </button>
              <button type="button" onClick={() => handleCleanupWorktrees(true)} disabled={worktreeLoading}>
                Apply Cleanup
              </button>
              <button type="button" onClick={loadWorktrees} disabled={worktreeLoading}>
                <RefreshCw size={14} /> Refresh
              </button>
            </div>
          </div>
          <div className="worktree-readiness">
            {worktreeData.readiness ? (
              <>
                <strong>{worktreeData.readiness.ready ? 'Ready' : 'Needs attention'}</strong>
                <span>{worktreeData.readiness.reason}</span>
              </>
            ) : (
              <span>Worktree readiness will appear here once loaded.</span>
            )}
          </div>
          <div className="worktree-create-row">
            <input
              type="text"
              value={worktreeLabel}
              onChange={(e) => setWorktreeLabel(e.target.value)}
              placeholder="new worktree label"
              disabled={worktreeLoading}
            />
            <button type="button" onClick={handleCreateWorktree} disabled={worktreeLoading || !worktreeLabel.trim()}>
              Create
            </button>
          </div>
          <div className="worktree-create-row handoff-owner-row">
            <input
              type="text"
              value={handoffOwner}
              onChange={(e) => setHandoffOwner(e.target.value)}
              placeholder="handoff owner"
              disabled={worktreeLoading}
            />
          </div>
          {worktreeMessage && <div className="session-action-message">{worktreeMessage}</div>}
          <div className="worktree-items">
            {(worktreeData.worktrees || []).filter(item => item.managed).map(worktree => (
              <div key={worktree.path} className={`worktree-item ${worktree.dirty ? 'dirty' : ''}`}>
                <div className="worktree-item-main">
                  <span className="worktree-label">{worktree.label || 'unnamed'}</span>
                  <span className="worktree-branch">{worktree.branch || 'detached'}</span>
                </div>
                <div className="worktree-item-sub">
                  <span>{worktree.path}</span>
                  <span>{worktree.dirty ? 'dirty' : 'clean'}</span>
                </div>
                <div className="worktree-lifecycle-row">
                  <span>Age {formatHours(worktree.age_hours)}</span>
                  <span>Idle {formatHours(worktree.idle_hours)}</span>
                  {worktree.last_activity_at && <span>Last activity {formatDate(worktree.last_activity_at)}</span>}
                </div>
                {worktree.cleanup_recommendation && (
                  <div className={`worktree-cleanup-note level-${worktree.cleanup_recommendation.level || 'keep'}`}>
                    <strong>{worktree.cleanup_recommendation.action}</strong>
                    <span>{worktree.cleanup_recommendation.reason}</span>
                  </div>
                )}
                {worktree.handoff?.status === 'active' && (
                  <div className="worktree-handoff-note">
                    <strong>Handoff: {worktree.handoff.owner}</strong>
                    <span>{worktree.handoff.purpose}</span>
                    <span>Cleanup: {worktree.handoff.cleanup_expectation}</span>
                  </div>
                )}
                <div className="worktree-item-actions">
                  {worktree.handoff?.status === 'active' ? (
                    <button type="button" onClick={() => handleReleaseHandoff(worktree.label)} disabled={worktreeLoading}>
                      Release Handoff
                    </button>
                  ) : (
                    <button type="button" onClick={() => handleAssignHandoff(worktree.label)} disabled={worktreeLoading || !handoffOwner.trim()}>
                      Assign Handoff
                    </button>
                  )}
                  <button type="button" onClick={() => handleRemoveWorktree(worktree.label, worktree.dirty)} disabled={worktreeLoading}>
                    {worktree.cleanup_recommendation?.action === 'remove_now' ? 'Clean Up' : 'Remove'}
                  </button>
                </div>
              </div>
            ))}
            {!worktreeLoading && ((worktreeData.worktrees || []).filter(item => item.managed).length === 0) && (
              <div className="session-empty worktree-empty">No Forge-managed worktrees yet.</div>
            )}
          </div>
        </div>
      </div>

      {selectedSession && (
        <div className="session-details">
          <div className="session-details-header">
            <h3>Session Details</h3>
            <button onClick={() => setSelectedSession(null)}>x</button>
          </div>

          <div className="session-info">
            <div className="info-row">
              <span className="info-label">Session ID:</span>
              <span className="info-value">{selectedSession.session_id}</span>
            </div>
            <div className="info-row">
              <span className="info-label">Created:</span>
              <span className="info-value">{formatDate(selectedSession.created_at)}</span>
            </div>
            <div className="info-row">
              <span className="info-label">Last Updated:</span>
              <span className="info-value">{formatDate(selectedSession.updated_at)}</span>
            </div>
            {selectedSession.active_goal && (
              <div className="info-row">
                <span className="info-label">Active Goal:</span>
                <span className="info-value">{selectedSession.active_goal}</span>
              </div>
            )}
          </div>

          <div className="session-actions">
            <button type="button" onClick={() => handleSessionAction('summary')} disabled={sessionActionState.loading}>
              Summary
            </button>
            <button type="button" onClick={() => handleSessionAction('resume')} disabled={sessionActionState.loading}>
              Resume
            </button>
            <button type="button" onClick={() => handleSessionAction('compact')} disabled={sessionActionState.loading}>
              Compact
            </button>
            <button type="button" onClick={() => handleSessionAction('export')} disabled={sessionActionState.loading}>
              Export
            </button>
            <button
              type="button"
              onClick={() => handleRuntimeCommand(`/plan ${selectedSession.active_goal}`)}
              disabled={!canDeepPlanSelectedSession || sessionActionState.loading}
            >
              Deep Plan Goal
            </button>
          </div>

          {sessionActionState.message && (
            <div className="session-action-message">{sessionActionState.message}</div>
          )}

          {sessionSummary && (
            <div className="session-summary-card">
              <h4>Session Summary</h4>
              <pre>{sessionSummary}</pre>
            </div>
          )}

          <div className="session-messages">
            <h4>Messages ({selectedSession.messages?.length || 0})</h4>
            <div className="messages-list">
              {selectedSession.messages?.map((msg, idx) => (
                <div key={idx} className={`message message-${msg.role}`}>
                  <div className="message-header">
                    <span className="message-role">{msg.role}</span>
                    <span className="message-time">{formatDate(msg.timestamp)}</span>
                  </div>
                  <div className="message-content">{msg.content}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SessionManagement;
