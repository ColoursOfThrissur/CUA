import React from 'react';
import './CodePreviewModal.css';
import DiffViewer from './output/DiffViewer';

const CodePreviewModal = ({ tool, onClose }) => {
  if (!tool) return null;
  const hasDiff = Boolean(tool.diff_payload || tool.patch);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Code Preview</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          <div className="code-info">
            <span className="info-label">File:</span>
            <code>{tool.tool_file}</code>
          </div>

          {hasDiff ? (
            <DiffViewer payload={tool.diff_payload} patch={tool.patch} title="Patch Preview" compact />
          ) : (
            <div className="code-container">
              <pre>
                <code>{tool.code || 'No code available'}</code>
              </pre>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn-close" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
};

export default CodePreviewModal;
