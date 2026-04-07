import React, { useState, useEffect } from 'react';
import { API_URL } from '../config';
import './StagingPreviewModal.css';
import DiffViewer from './output/DiffViewer';

function StagingPreviewModal({ parentId, onClose }) {
  const [staging, setStaging] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStaging();
  }, [parentId]);

  const fetchStaging = async () => {
    try {
      const response = await fetch(`${API_URL}/tasks/${parentId}/staging`);
      const data = await response.json();
      setStaging(data);
    } catch (error) {
      console.error('Failed to fetch staging:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>Staging Preview</h2>
            <button className="close-btn" onClick={onClose}>x</button>
          </div>
          <div className="modal-body">
            <p>Loading...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content staging-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Staging Preview</h2>
          <button className="close-btn" onClick={onClose}>x</button>
        </div>

        <div className="modal-body">
          {staging?.available === false ? (
            <div className="staging-note">
              <strong>Staging preview unavailable:</strong> {staging?.message || 'No staged diff is available.'}
            </div>
          ) : (
            <>
              <div className="staging-info">
                <p><strong>Target File:</strong> {staging?.target_file}</p>
                <p><strong>Staged Changes:</strong> {staging?.staged_count} subtasks</p>
                <p><strong>Status:</strong> {staging?.has_merged ? 'Merged' : 'Staging'}</p>
              </div>

              <div className="staged-changes-list">
                <h3>Staged Subtasks:</h3>
                {staging?.changes?.map((change, idx) => (
                  <div key={idx} className="staged-change-item">
                    <div className="change-header">
                      <span className="change-number">#{idx + 1}</span>
                      <span className="change-methods">{(change.methods || []).join(', ')}</span>
                      <span className="change-time">{new Date(change.timestamp).toLocaleTimeString()}</span>
                    </div>
                  </div>
                ))}
              </div>

              {(staging?.diff_payload || staging?.patch) && (
                <DiffViewer payload={staging?.diff_payload} patch={staging?.patch} title="Staged Diff" compact />
              )}

              <div className="staging-note">
                <strong>Note:</strong> Changes are staged but not committed yet.
                They will be committed only after all subtasks pass and integration test succeeds.
              </div>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

export default StagingPreviewModal;
