import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import './RightOverlay.css';

function RightOverlay({ isOpen, onClose, title, children, width = '50%' }) {
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setMounted(true);
      requestAnimationFrame(() => setVisible(true));
    } else {
      setVisible(false);
      const t = setTimeout(() => setMounted(false), 300);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

  if (!mounted) return null;

  return (
    <>
      <div className={`overlay-backdrop ${visible ? 'visible' : ''}`} onClick={onClose} />
      <div className={`right-overlay ${visible ? 'visible' : ''}`} style={{ width }}>
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
