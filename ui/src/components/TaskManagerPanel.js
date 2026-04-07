import React, { useEffect, useState } from 'react';
import { API_URL } from '../config';
import './TaskManagerPanel.css';

function TaskManagerPanel({ taskStatus, onAbortTask, onViewStaging }) {
  const [history, setHistory] = useState([]);

  useEffect(() => {
    const loadHistory = async () => {
      try {
        const response = await fetch(`${API_URL}/tasks/history?limit=5`);
        const data = await response.json();
        setHistory(data.history || []);
      } catch (error) {
        console.error('Failed to load task history:', error);
        setHistory([]);
      }
    };

    loadHistory();
  }, [taskStatus?.parent_task?.parent_id, taskStatus?.active]);

  const formatTimestamp = (value) => {
    if (!value) {
      return 'n/a';
    }
    return new Date(value).toLocaleString();
  };

  const renderHistory = () => (
    <div className="task-history-card">
      <div className="task-history-header">
        <h4>Recent Task History</h4>
      </div>
      {history.length === 0 ? (
        <div className="task-history-empty">No completed task history yet.</div>
      ) : (
        <div className="task-history-list">
          {history.map((item) => {
            const metadata = item.workflow_metadata || {};
            const worktree = metadata.worktree || {};
            const policy = metadata.isolation_policy || {};
            return (
              <div key={item.parent_id} className="task-history-item">
                <div className="task-history-topline">
                  <strong>{item.description}</strong>
                  <span className={`task-history-status status-${item.status}`}>{item.status}</span>
                </div>
                <div className="task-history-meta">
                  <span>{formatTimestamp(item.updated_at || item.created_at)}</span>
                  {metadata.execution_mode && <span>{metadata.execution_mode}</span>}
                  {worktree.label && <span>worktree: {worktree.label}</span>}
                  {policy.level && <span>policy: {policy.level}</span>}
                </div>
                {worktree.worktree_path && (
                  <div className="task-history-path">{worktree.worktree_path}</div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  if (!taskStatus || !taskStatus.active) {
    return (
      <div className="task-manager-panel">
        <div className="task-empty">
          <p>No active parent task. Complex tasks (&gt;3 methods) will appear here.</p>
        </div>
        {renderHistory()}
      </div>
    );
  }

  const { parent_task } = taskStatus;
  const progress = (parent_task.completed_subtasks / parent_task.total_subtasks) * 100;
  const workflowMetadata = parent_task.workflow_metadata || {};
  const isolatedWorktree = workflowMetadata.worktree || null;
  const isolationPolicy = workflowMetadata.isolation_policy || null;

  const getStatusIcon = (status) => {
    const icons = {
      completed: 'OK',
      in_progress: '...',
      pending: '--',
      failed: 'X',
    };
    return icons[status] || '*';
  };

  const getStatusClass = (status) => {
    return `subtask-status-${status}`;
  };

  return (
    <div className="task-manager-panel">
      <div className="parent-task-card">
        <div className="parent-task-header">
          <div className="parent-task-info">
            <h3>{parent_task.description}</h3>
            <div className="parent-task-meta">
              <span className="task-file">Path: {parent_task.target_file || 'not set'}</span>
              <span className={`task-priority priority-${parent_task.priority}`}>
                {parent_task.priority.toUpperCase()}
              </span>
            </div>
            {(workflowMetadata.execution_mode || isolationPolicy?.level) && (
              <div className="task-workflow-meta">
                {workflowMetadata.execution_mode && (
                  <span className="task-mode-chip">{workflowMetadata.execution_mode}</span>
                )}
                {isolatedWorktree?.label && (
                  <span className="task-worktree-chip">worktree: {isolatedWorktree.label}</span>
                )}
                {isolatedWorktree?.worktree_path && (
                  <div className="task-worktree-path">{isolatedWorktree.worktree_path}</div>
                )}
                {isolationPolicy?.level && (
                  <div className="task-policy-note">
                    Isolation policy: {isolationPolicy.level} - {isolationPolicy.reason}
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="parent-task-actions">
            <button
              className="btn-secondary btn-small"
              onClick={() => onViewStaging(parent_task.parent_id)}
              title="Preview staged changes"
            >
              View Staging
            </button>
            <button
              className="btn-danger btn-small"
              onClick={() => onAbortTask(parent_task.parent_id)}
              title="Abort and rollback"
            >
              Abort Task
            </button>
          </div>
        </div>

        <div className="progress-section">
          <div className="progress-bar-container">
            <div
              className="progress-bar-fill"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="progress-text">
            {parent_task.completed_subtasks} / {parent_task.total_subtasks} subtasks completed ({progress.toFixed(0)}%)
          </div>
        </div>

        <div className="subtasks-list">
          {parent_task.subtasks.map((subtask, idx) => (
            <div
              key={subtask.subtask_id}
              className={`subtask-item ${getStatusClass(subtask.status)}`}
            >
              <span className="subtask-icon">{getStatusIcon(subtask.status)}</span>
              <div className="subtask-content">
                <div className="subtask-title">
                  Subtask {idx + 1}: {subtask.methods.join(', ')}
                </div>
                {subtask.status === 'in_progress' && (
                  <div className="subtask-progress">
                    Attempt {subtask.attempts}/{subtask.max_attempts}
                  </div>
                )}
                {subtask.error && (
                  <div className="subtask-error">
                    Warning: {subtask.error}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
      {renderHistory()}
    </div>
  );
}

export default TaskManagerPanel;
