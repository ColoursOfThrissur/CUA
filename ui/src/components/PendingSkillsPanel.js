import React, { useState, useEffect } from 'react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './PendingSkillsPanel.css';

const PendingSkillsPanel = () => {
  const [pendingSkills, setPendingSkills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [processingSkillId, setProcessingSkillId] = useState(null);
  const [selectedSkill, setSelectedSkill] = useState(null);
  const toast = useToast();

  useEffect(() => {
    fetchPendingSkills();
  }, []);

  const fetchPendingSkills = async () => {
    try {
      const response = await fetch(`${API_URL}/api/skills/pending`);
      const data = await response.json();
      if (data.success) {
        setPendingSkills(data.pending_skills || []);
      }
    } catch (error) {
      console.error('Failed to fetch pending skills:', error);
      toast.error('Failed to load pending skills');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (skillId) => {
    if (processingSkillId) return;
    setProcessingSkillId(skillId);
    
    try {
      const response = await fetch(`${API_URL}/api/skills/pending/${skillId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Approved via UI' })
      });
      
      const data = await response.json();
      if (data.success) {
        toast.success(data.message);
        fetchPendingSkills();
      } else {
        toast.error(data.message || 'Failed to approve skill');
      }
    } catch (error) {
      toast.error('Error approving skill: ' + error.message);
    } finally {
      setProcessingSkillId(null);
    }
  };

  const handleReject = async (skillId) => {
    if (processingSkillId) return;
    setProcessingSkillId(skillId);
    
    try {
      const response = await fetch(`${API_URL}/api/skills/pending/${skillId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Rejected via UI' })
      });
      
      const data = await response.json();
      if (data.success) {
        toast.success('Skill rejected');
        fetchPendingSkills();
      } else {
        toast.error(data.message || 'Failed to reject skill');
      }
    } catch (error) {
      toast.error('Error rejecting skill: ' + error.message);
    } finally {
      setProcessingSkillId(null);
    }
  };

  const getCategoryColor = (category) => {
    const colors = {
      web: '#3b82f6',
      computer: '#10b981',
      development: '#8b5cf6',
      conversation: '#f59e0b',
      general: '#6b7280'
    };
    return colors[category?.toLowerCase()] || '#6b7280';
  };

  const getRiskColor = (risk) => {
    const colors = {
      low: '#10b981',
      medium: '#f59e0b',
      high: '#ef4444'
    };
    return colors[risk?.toLowerCase()] || '#6b7280';
  };

  if (loading) {
    return (
      <div className="pending-skills-panel">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading pending skills...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="pending-skills-panel">
      <div className="panel-header">
        <h2>Pending Skills ({pendingSkills.length})</h2>
        <p className="subtitle">Review and approve skills before activation</p>
      </div>

      {pendingSkills.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🎯</div>
          <p>No pending skills</p>
          <span className="empty-hint">Skills will appear here when detected by gap analysis</span>
        </div>
      ) : (
        <div className="skills-list">
          {pendingSkills.map((skill) => (
            <div
              key={skill.id}
              className="skill-card"
              style={{ borderLeft: `4px solid ${getCategoryColor(skill.skill_definition?.category)}` }}
            >
              <div className="skill-header">
                <div className="skill-title-row">
                  <span
                    className="category-badge"
                    style={{ backgroundColor: getCategoryColor(skill.skill_definition?.category) }}
                  >
                    {skill.skill_definition?.category?.toUpperCase() || 'GENERAL'}
                  </span>
                  <h3 className="skill-name">{skill.skill_name}</h3>
                </div>
                <span
                  className="risk-badge"
                  style={{ backgroundColor: getRiskColor(skill.skill_definition?.risk_level) }}
                >
                  {skill.skill_definition?.risk_level?.toUpperCase() || 'MEDIUM'} RISK
                </span>
              </div>

              <p className="skill-description">{skill.skill_definition?.description}</p>

              <div className="skill-details">
                <div className="detail-item">
                  <span className="detail-label">Requested by:</span>
                  <span className="detail-value">{skill.requested_by}</span>
                </div>

                <div className="detail-item">
                  <span className="detail-label">Trigger Examples:</span>
                  <div className="trigger-examples">
                    {skill.skill_definition?.trigger_examples?.map((example, idx) => (
                      <span key={idx} className="trigger-example">{example}</span>
                    )) || <span className="no-examples">None specified</span>}
                  </div>
                </div>

                {skill.skill_definition?.preferred_tools?.length > 0 && (
                  <div className="detail-item">
                    <span className="detail-label">Preferred Tools:</span>
                    <span className="detail-value">
                      {skill.skill_definition.preferred_tools.join(', ')}
                    </span>
                  </div>
                )}

                <div className="detail-item">
                  <span className="detail-label">Verification Mode:</span>
                  <span className="detail-value">{skill.skill_definition?.verification_mode || 'basic'}</span>
                </div>

                {skill.context && (
                  <div className="context-info">
                    <strong>Gap Context:</strong>
                    <pre className="context-text">{skill.context}</pre>
                  </div>
                )}

                <div className="detail-item">
                  <span className="detail-label">Created:</span>
                  <span className="detail-value">
                    {new Date(skill.created_at).toLocaleString()}
                  </span>
                </div>
              </div>

              <div className="skill-actions">
                <button
                  className="btn-view-details"
                  onClick={() => setSelectedSkill(selectedSkill === skill.id ? null : skill.id)}
                  disabled={processingSkillId === skill.id}
                >
                  {selectedSkill === skill.id ? 'Hide Details' : 'View Details'}
                </button>
                <button
                  className="btn-reject"
                  onClick={() => handleReject(skill.id)}
                  disabled={processingSkillId === skill.id}
                >
                  Reject
                </button>
                <button
                  className="btn-approve"
                  onClick={() => handleApprove(skill.id)}
                  disabled={processingSkillId === skill.id}
                >
                  {processingSkillId === skill.id ? 'Processing...' : 'Approve & Create'}
                </button>
              </div>

              {selectedSkill === skill.id && (
                <div className="skill-details-expanded">
                  <h4>Skill Definition (JSON)</h4>
                  <pre className="skill-json">
                    {JSON.stringify(skill.skill_definition, null, 2)}
                  </pre>
                  
                  {skill.instructions && (
                    <>
                      <h4>Instructions (SKILL.md)</h4>
                      <pre className="skill-instructions">{skill.instructions}</pre>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default PendingSkillsPanel;