import React, { useState, useEffect } from 'react';
import { Trash2, MessageSquare, Clock, User } from 'lucide-react';
import { API_URL } from '../config';
import './SessionManagement.css';

function SessionManagement({ onClose }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSession, setSelectedSession] = useState(null);

  useEffect(() => {
    loadSessions();
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

  const handleDeleteSession = async (sessionId) => {
    if (!window.confirm('Delete this session and all its messages?')) return;

    try {
      await fetch(`${API_URL}/sessions/${sessionId}`, { method: 'DELETE' });
      setSessions(sessions.filter(s => s.session_id !== sessionId));
      if (selectedSession?.session_id === sessionId) {
        setSelectedSession(null);
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
    } catch (error) {
      console.error('Failed to load session details:', error);
    }
  };

  const formatDate = (timestamp) => {
    return new Date(timestamp).toLocaleString();
  };

  if (loading) {
    return <div className="session-loading">Loading sessions...</div>;
  }

  return (
    <div className="session-management">
      <div className="session-list">
        <div className="session-header">
          <h3>Active Sessions ({sessions.length})</h3>
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
      </div>

      {selectedSession && (
        <div className="session-details">
          <div className="session-details-header">
            <h3>Session Details</h3>
            <button onClick={() => setSelectedSession(null)}>×</button>
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
