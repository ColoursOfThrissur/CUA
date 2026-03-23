import React from 'react';
import ChatPanel from './ChatPanel';
import FloatingActionBar from './FloatingActionBar';
import EvolutionMode from './EvolutionMode';
import ToolModeChat from './ToolModeChat';
import './MainCanvas.css';

function MainCanvas({ mode, messages, onSendMessage, isProcessing, onFloatingAction, onModeChange, skills, backendConnected, agentPlan }) {
  const renderContent = () => {
    if (mode === 'tools') {
      return <ToolModeChat key="tools" onModeChange={onModeChange} />;
    }
    
    if (mode === 'evolution') {
      return <EvolutionMode key="evolution" />;
    }
    
    return (
      <ChatPanel 
        key="chat"
        messages={messages}
        onSendMessage={onSendMessage}
        isProcessing={isProcessing}
        mode={mode}
        skills={skills}
        backendConnected={backendConnected}
        agentPlan={agentPlan}
      />
    );
  };

  return (
    <div className="main-canvas">
      <FloatingActionBar mode={mode} onAction={onFloatingAction} />
      <div className="canvas-content">
        {renderContent()}
      </div>
    </div>
  );
}

export default MainCanvas;
