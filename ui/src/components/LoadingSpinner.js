import React from 'react';
import './LoadingSpinner.css';

const LoadingSpinner = ({ message = 'Processing...' }) => {
  return (
    <div className="loading-spinner-overlay">
      <div className="loading-spinner-content">
        <div className="spinner"></div>
        <p>{message}</p>
      </div>
    </div>
  );
};

export default LoadingSpinner;
