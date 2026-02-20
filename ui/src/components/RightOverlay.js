import React from 'react';
import { X } from 'lucide-react';
import './RightOverlay.css';

function RightOverlay({ isOpen, onClose, title, children, width = '50%' }) {
  if (!isOpen) return null;

  return (
    <>
      <div className="overlay-backdrop" onClick={onClose} />
      <div className="right-overlay" style={{ width }}>
        <div className="overlay-header">
          <h3>{title}</h3>
          <button className="overlay-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        <div className="overlay-content">
          {children}
        </div>
      </div>
    </>
  );
}

export default RightOverlay;
