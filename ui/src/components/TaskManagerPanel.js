import React from 'react';
import './TaskManagerPanel.css';

function TaskManagerPanel({ taskStatus, onAbortTask, onViewStaging }) {
  if (!taskStatus || !taskStatus.active) {
    return (
      <div className="task-manager-panel">
        <div className="task-empty">
          <p>No active parent task. Complex tasks (>3 methods) will appear here.</p>
        </div>
      </div>
    );
  }

  const { parent_task } = taskStatus;
  const progress = (parent_task.completed_subtasks / parent_task.total_subtasks) * 100;

  const getStatusIcon = (status) => {
    const icons = {
      completed: '✅',
      in_progress: '⏳',
      pending: '⏸',
      failed: '❌'
    };
    return icons[status] || '•';
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
              <span className="task-file">📁 {parent_task.target_file}</span>
              <span className={`task-priority priority-${parent_task.priority}`}>
                {parent_task.priority.toUpperCase()}
              </span>
            </div>
          </div>
          <div className="parent-task-actions">
            <button 
              className="btn-secondary btn-small"
              onClick={() => onViewStaging(parent_task.parent_id)}
              title="Preview staged changes"
            >
              👁 View Staging
            </button>
            <button 
              className="btn-danger btn-small"
              onClick={() => onAbortTask(parent_task.parent_id)}
              title="Abort and rollback"
            >
              ⏹ Abort Task
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
                    ⚠ {subtask.error}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default TaskManagerPanel;
