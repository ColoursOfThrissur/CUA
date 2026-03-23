import React, { useEffect, useRef } from 'react';
import { User, Bot, Mic, Send } from 'lucide-react';
import OutputRenderer from './output/OutputRenderer';
import './ChatPanel.css';

function ChatPanel({ messages, onSendMessage, isProcessing, mode, skills = [] }) {
  const [input, setInput] = React.useState('');
  const messagesEndRef = useRef(null);

  const getPlaceholder = () => {
    switch (mode) {
      case 'tools':
        return 'Describe the tool you want to create...';
      case 'evolution':
        return 'Request tool improvements or start self-improvement...';
      default:
        return 'Type a command or question... (Ctrl+Enter to send)';
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isProcessing) {
      onSendMessage(input);
      setInput('');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      handleSubmit(e);
    }
  };

  const startVoiceInput = () => {
    if ('webkitSpeechRecognition' in window) {
      const recognition = new window.webkitSpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      
      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setInput(transcript);
      };
      
      recognition.start();
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>Task Execution</h3>
      </div>
      
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-welcome">
            <h2>Welcome to CUA Agent</h2>
            <p>Try these commands:</p>
            <div className="example-commands">
              <button onClick={() => setInput('list files in current directory')}>
                List files
              </button>
              <button onClick={() => setInput('create a test file')}>
                Create file
              </button>
              <button onClick={() => setInput('what can you do?')}>
                What can you do?
              </button>
            </div>
            {skills.length > 0 && (
              <div style={{ marginTop: '24px', textAlign: 'left' }}>
                <h4 style={{ marginBottom: '10px' }}>Loaded Skills</h4>
                <div style={{ display: 'grid', gap: '10px' }}>
                  {skills.map((skill) => (
                    <button
                      key={skill.name}
                      type="button"
                      onClick={() => setInput(skill.trigger_examples?.[0] || skill.description)}
                      style={{
                        textAlign: 'left',
                        padding: '12px',
                        borderRadius: '12px',
                        border: '1px solid rgba(255,255,255,0.12)',
                        background: 'rgba(255,255,255,0.03)',
                        color: 'inherit',
                        cursor: 'pointer'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap' }}>
                        <strong>{skill.name}</strong>
                        <span style={{ opacity: 0.75, fontSize: '12px', textTransform: 'uppercase' }}>{skill.category}</span>
                      </div>
                      <div style={{ marginTop: '6px', opacity: 0.85 }}>{skill.description}</div>
                      {skill.ui_renderer && (
                        <div style={{ marginTop: '8px', fontSize: '12px', opacity: 0.7 }}>
                          Renderer: {skill.ui_renderer}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          messages.map((msg, index) => (
            <div key={index} className={`message ${msg.role} ${msg.metadata?.type === 'progress' ? 'progress-message' : ''}`}>
              <div className="message-avatar">
                {msg.role === 'user' ? <User size={20} /> : <Bot size={20} />}
              </div>
              <div className="message-content">
                {(msg.skill || msg.category) && (
                  <div style={{
                    display: 'flex',
                    gap: '8px',
                    flexWrap: 'wrap',
                    marginBottom: '8px'
                  }}>
                    {msg.skill && (
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        padding: '4px 8px',
                        borderRadius: '999px',
                        background: 'rgba(34, 197, 94, 0.12)',
                        border: '1px solid rgba(34, 197, 94, 0.3)',
                        color: '#86efac',
                        fontSize: '11px',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.04em'
                      }}>
                        Skill: {msg.skill}
                      </span>
                    )}
                    {msg.category && (
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        padding: '4px 8px',
                        borderRadius: '999px',
                        background: 'rgba(96, 165, 250, 0.12)',
                        border: '1px solid rgba(96, 165, 250, 0.3)',
                        color: '#93c5fd',
                        fontSize: '11px',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.04em'
                      }}>
                        Category: {msg.category}
                      </span>
                    )}
                  </div>
                )}
                <div className="message-text">
                  {msg.metadata?.type === 'progress' && (
                    <span className="progress-indicator">⏳ </span>
                  )}
                  {msg.content}
                </div>
                {msg.role === 'assistant' && msg.execution_result?.status === 'awaiting_approval' && msg.execution_result?.plan && (
                  <div style={{
                    marginTop: '10px',
                    padding: '12px',
                    border: '1px solid rgba(255,255,255,0.12)',
                    borderRadius: '10px',
                    background: 'rgba(255,255,255,0.04)'
                  }}>
                    <div style={{ fontWeight: 700, marginBottom: '6px' }}>Plan approval required</div>
                    {Array.isArray(msg.execution_result.plan.steps) && (
                      <div style={{ fontSize: '13px', opacity: 0.9, marginBottom: '10px' }}>
                        {msg.execution_result.plan.steps.slice(0, 8).map((s) => (
                          <div key={s.step_id} style={{ marginBottom: '4px' }}>
                            <span style={{ opacity: 0.8 }}>{s.step_id}:</span> {s.description}{' '}
                            <span style={{ opacity: 0.8 }}>({s.tool_name}.{s.operation})</span>
                          </div>
                        ))}
                        {msg.execution_result.plan.steps.length > 8 && (
                          <div style={{ opacity: 0.7 }}>…and {msg.execution_result.plan.steps.length - 8} more steps</div>
                        )}
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '10px' }}>
                      <button
                        disabled={isProcessing}
                        onClick={() => onSendMessage('go ahead')}
                        style={{
                          padding: '8px 12px',
                          borderRadius: '8px',
                          border: 'none',
                          background: '#22c55e',
                          color: '#fff',
                          fontWeight: 700,
                          cursor: 'pointer'
                        }}
                      >
                        Approve & Run
                      </button>
                      <button
                        disabled={isProcessing}
                        onClick={() => onSendMessage('cancel')}
                        style={{
                          padding: '8px 12px',
                          borderRadius: '8px',
                          border: '1px solid rgba(255,255,255,0.2)',
                          background: 'transparent',
                          color: 'inherit',
                          fontWeight: 700,
                          cursor: 'pointer'
                        }}
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                )}
                {msg.components && <OutputRenderer components={msg.components} />}
                {msg.timestamp && (
                  <div className="message-time">{msg.timestamp}</div>
                )}
              </div>
            </div>
          ))
        )}
        {isProcessing && (
          <div className="message assistant">
            <div className="message-avatar"><Bot size={20} /></div>
            <div className="message-content">
              <div className="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      
      <form className="chat-input-form" onSubmit={handleSubmit}>
        <input
          type="text"
          className="chat-input"
          placeholder={getPlaceholder()}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isProcessing}
        />
        <button 
          type="button" 
          className="btn-voice" 
          onClick={startVoiceInput}
          disabled={isProcessing}
        >
          <Mic size={18} />
        </button>
        <button 
          type="submit" 
          className="btn-send" 
          disabled={isProcessing || !input.trim()}
        >
          <Send size={16} />
          Send
        </button>
      </form>
    </div>
  );
}

export default ChatPanel;
