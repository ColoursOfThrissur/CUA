import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import './CollapsibleSection.css';

function CollapsibleSection({ title, children, defaultOpen = true }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="collapsible-section">
      <button 
        className="collapsible-header" 
        onClick={() => setIsOpen(!isOpen)}
      >
        <h3 className="section-title">{title}</h3>
        {isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>
      <div className={`collapsible-content ${isOpen ? 'open' : 'closed'}`}>
        {children}
      </div>
    </div>
  );
}

export default CollapsibleSection;
