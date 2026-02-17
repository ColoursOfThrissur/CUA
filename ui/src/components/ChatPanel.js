import React, { useEffect, useRef } from 'react';
import './ChatPanel.css';

function ChatPanel({ messages, onSendMessage, isProcessing }) {
  const [input, setInput] = React.useState('');
  const messagesEndRef = useRef(null);

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
          </div>
        ) : (
          messages.map((msg, index) => (
            <div key={index} className={`message ${msg.role}`}>
              <div className="message-avatar">
                {msg.role === 'user' ? '👤' : '🤖'}
              </div>
              <div className="message-content">
                <div className="message-text">{msg.content}</div>
                {msg.timestamp && (
                  <div className="message-time">{msg.timestamp}</div>
                )}
              </div>
            </div>
          ))
        )}
        {isProcessing && (
          <div className="message assistant">
            <div className="message-avatar">🤖</div>
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
          placeholder="Type a command or question..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isProcessing}
        />
        <button 
          type="button" 
          className="btn-voice" 
          onClick={startVoiceInput}
          disabled={isProcessing}
        >
          🎤
        </button>
        <button 
          type="submit" 
          className="btn-send" 
          disabled={isProcessing || !input.trim()}
        >
          Send
        </button>
      </form>
    </div>
  );
}

export default ChatPanel;
