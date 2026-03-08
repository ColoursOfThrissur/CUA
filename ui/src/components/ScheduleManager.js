import React, { useState, useEffect } from 'react';
import { API_URL } from '../config';
import './ScheduleManager.css';

function ScheduleManager() {
  const [schedules, setSchedules] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newSchedule, setNewSchedule] = useState({
    schedule_id: '',
    cron: 'daily:02:00',
    max_iterations: 5,
    dry_run: false
  });

  useEffect(() => {
    fetchSchedules();
  }, []);

  const fetchSchedules = async () => {
    try {
      const response = await fetch(`${API_URL}/schedule/list`);
      const data = await response.json();
      setSchedules(data.schedules || []);
    } catch (error) {
      console.error('Failed to fetch schedules:', error);
    }
  };

  const handleCreate = async () => {
    if (!newSchedule.schedule_id) {
      alert('Schedule ID is required');
      return;
    }

    try {
      const response = await fetch(`${API_URL}/schedule/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newSchedule)
      });

      if (response.ok) {
        setShowCreate(false);
        setNewSchedule({ schedule_id: '', cron: 'daily:02:00', max_iterations: 5, dry_run: false });
        fetchSchedules();
      }
    } catch (error) {
      alert('Failed to create schedule: ' + error.message);
    }
  };

  const handleDelete = async (scheduleId) => {
    if (!window.confirm(`Delete schedule "${scheduleId}"?`)) return;

    try {
      const response = await fetch(`${API_URL}/schedule/${scheduleId}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        fetchSchedules();
      }
    } catch (error) {
      alert('Failed to delete schedule: ' + error.message);
    }
  };

  const handleToggle = async (scheduleId, enabled) => {
    try {
      const response = await fetch(`${API_URL}/schedule/${scheduleId}/enable?enabled=${!enabled}`, {
        method: 'POST'
      });

      if (response.ok) {
        fetchSchedules();
      }
    } catch (error) {
      alert('Failed to toggle schedule: ' + error.message);
    }
  };

  return (
    <div className="schedule-manager">
      <div className="schedule-header">
        <h3>Scheduled Improvements</h3>
        <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? 'Cancel' : '+ New Schedule'}
        </button>
      </div>

      {showCreate && (
        <div className="schedule-form">
          <input
            type="text"
            placeholder="Schedule ID (e.g., daily_improvement)"
            value={newSchedule.schedule_id}
            onChange={(e) => setNewSchedule({...newSchedule, schedule_id: e.target.value})}
          />
          
          <select 
            value={newSchedule.cron}
            onChange={(e) => setNewSchedule({...newSchedule, cron: e.target.value})}
          >
            <option value="hourly">Every Hour</option>
            <option value="daily:02:00">Daily at 2:00 AM</option>
            <option value="daily:03:00">Daily at 3:00 AM</option>
            <option value="weekly:monday:02:00">Weekly Monday 2:00 AM</option>
            <option value="weekly:sunday:03:00">Weekly Sunday 3:00 AM</option>
          </select>

          <input
            type="number"
            placeholder="Max Iterations"
            value={newSchedule.max_iterations}
            onChange={(e) => setNewSchedule({...newSchedule, max_iterations: Number(e.target.value)})}
            min="1"
            max="20"
          />

          <label>
            <input
              type="checkbox"
              checked={newSchedule.dry_run}
              onChange={(e) => setNewSchedule({...newSchedule, dry_run: e.target.checked})}
            />
            Dry-run (preview only)
          </label>

          <button className="btn btn-success" onClick={handleCreate}>Create Schedule</button>
        </div>
      )}

      <div className="schedule-list">
        {schedules.length === 0 ? (
          <div className="schedule-empty">No schedules configured</div>
        ) : (
          schedules.map((schedule) => (
            <div key={schedule.schedule_id} className={`schedule-item ${!schedule.enabled ? 'disabled' : ''}`}>
              <div className="schedule-info">
                <div className="schedule-id">{schedule.schedule_id}</div>
                <div className="schedule-details">
                  <span className="schedule-cron">{schedule.cron}</span>
                  <span className="schedule-iterations">{schedule.max_iterations} iterations</span>
                  {schedule.dry_run && <span className="schedule-badge">DRY-RUN</span>}
                </div>
                {schedule.last_run && (
                  <div className="schedule-last-run">Last run: {new Date(schedule.last_run).toLocaleString()}</div>
                )}
              </div>
              <div className="schedule-actions">
                <button 
                  className={`btn-icon ${schedule.enabled ? 'btn-warning' : 'btn-success'}`}
                  onClick={() => handleToggle(schedule.schedule_id, schedule.enabled)}
                  title={schedule.enabled ? 'Disable' : 'Enable'}
                >
                  {schedule.enabled ? '⏸' : '▶'}
                </button>
                <button 
                  className="btn-icon btn-danger"
                  onClick={() => handleDelete(schedule.schedule_id)}
                  title="Delete"
                >
                  🗑️
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default ScheduleManager;
