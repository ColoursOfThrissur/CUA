import React, { useEffect, useRef, useState } from 'react';
import { User, Bot, Mic, Send, Square, ChevronDown, ChevronUp } from 'lucide-react';
import OutputRenderer from './output/OutputRenderer';
import ToolExecutionSteps from './ToolExecutionSteps';
import { useTraceWebSocket } from '../hooks/useTraceWebSocket';
import './ChatPanel.css';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const DOMAIN_OPTIONS = [
  { value: 'auto', label: 'Auto', hint: 'Let Forge route and narrow context automatically.' },
  { value: 'computer', label: 'Computer', hint: 'Desktop apps, local files, shell, and system control.' },
  { value: 'web', label: 'Web', hint: 'Browser work and web-facing automation.' },
  { value: 'code', label: 'Code', hint: 'Repository work, editing, tests, and implementation.' },
  { value: 'research', label: 'Research', hint: 'Search, summarize, compare, and gather information.' },
  { value: 'finance', label: 'Finance', hint: 'Markets, portfolios, reports, and investing workflows.' },
];
const COMMAND_SHORTCUTS = [
  { label: '/doctor', action: 'send', value: '/doctor' },
  { label: '/memory maintain', action: 'send', value: '/memory maintain' },
  { label: '/worktree', action: 'send', value: '/worktree' },
  { label: '/worktree list', action: 'send', value: '/worktree list' },
  { label: '/plan', action: 'draft', value: '/plan ' },
  { label: '/plan isolated', action: 'draft', value: '/plan isolated ' },
];

function AgentPlanStatus({ agentPlan }) {
  const [collapsed, setCollapsed] = useState(false);
  const completedCount = agentPlan.steps.filter(s => s.status === 'completed').length;
  const failedCount = agentPlan.steps.filter(s => s.status === 'failed').length;
  const total = agentPlan.steps.length;
  const progress = total > 0 ? Math.round((completedCount / total) * 100) : 0;

  return (
    <div className="agent-plan-status">
      <div className="agent-plan-header" onClick={() => setCollapsed(c => !c)}>
        <div className="agent-plan-header-left">
          <span className="agent-plan-spinner" />
          <span className="agent-plan-title">Executing Plan</span>
          <span className="agent-plan-iter">iter {agentPlan.iteration}/{agentPlan.max_iterations}</span>
        </div>
        <div className="agent-plan-header-right">
          <span className="agent-plan-counts">
            <span className="apc-done">{completedCount}✓</span>
            {failedCount > 0 && <span className="apc-fail">{failedCount}✗</span>}
            <span className="apc-total">/{total}</span>
          </span>
          <div className="agent-plan-progress-bar">
            <div className="agent-plan-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          {collapsed ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
        </div>
      </div>
      {!collapsed && (
        <div className="agent-plan-steps">
          {agentPlan.steps.map(step => (
            <div key={step.step_id} className={`agent-plan-step status-${step.status}`}>
              <span className="step-icon">
                {step.status === 'completed' ? '✓'
                  : step.status === 'failed' ? '✗'
                  : step.status === 'running' ? '⟳'
                  : '·'}
              </span>
              <span className="step-desc">{step.description}</span>
              <span className="step-tool">{step.tool_name}.{step.operation}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ChatPanel({
  messages,
  onSendMessage,
  isProcessing,
  mode,
  skills = [],
  backendConnected = true,
  agentPlan = null,
  domainHint = 'auto',
  onDomainHintChange,
}) {
  const [input, setInput] = React.useState('');
  const messagesEndRef = useRef(null);
  const traces = useTraceWebSocket({ limit: 3, persist: false, ttlMs: 5000 });
  const selectedDomain = DOMAIN_OPTIONS.find(option => option.value === domainHint) || DOMAIN_OPTIONS[0];

  const getPlaceholder = () => {
    return 'Ask anything or give a task... (Ctrl+Enter to send)';
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

  const handleStop = async () => {
    try {
      await fetch(`${API_URL}/chat/stop`, { method: 'POST' });
    } catch (e) {
      console.error('Stop failed:', e);
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
        <div className="chat-scope-panel">
          <div className="chat-scope-copy">
            <span className="chat-scope-kicker">Planning Scope</span>
            <h3>{selectedDomain.label}</h3>
            <p>{selectedDomain.hint}</p>
          </div>
          <div className="chat-scope-options" role="tablist" aria-label="Planning scope">
            {DOMAIN_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`chat-scope-chip ${domainHint === option.value ? 'is-active' : ''}`}
                onClick={() => onDomainHintChange?.(option.value)}
                aria-pressed={domainHint === option.value}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-welcome">
            {!backendConnected && (
              <div className="welcome-offline">
                Backend offline — responses unavailable
              </div>
            )}
            <h2>Forge Assistant</h2>
            <p>What would you like to do?</p>
            <div className="example-commands">
              <button onClick={() => setInput('list files in current directory')}>List files</button>
              <button onClick={() => setInput('search the web for latest AI news')}>Web search</button>
              <button onClick={() => setInput('what can you do?')}>What can you do?</button>
            </div>
            <div className="command-shortcuts">
              <h4>Operational Shortcuts</h4>
              <div className="command-shortcut-list">
                {COMMAND_SHORTCUTS.map((shortcut) => (
                  <button
                    key={shortcut.label}
                    type="button"
                    className="command-shortcut"
                    onClick={() => {
                      if (shortcut.action === 'send') {
                        onSendMessage(shortcut.value);
                        return;
                      }
                      setInput(shortcut.value);
                    }}
                    disabled={isProcessing}
                  >
                    <span>{shortcut.label}</span>
                    <small>{shortcut.action === 'send' ? 'run now' : 'draft'}</small>
                  </button>
                ))}
              </div>
            </div>
            {skills.length > 0 && (
              <div className="skills-grid">
                <h4>Available Skills</h4>
                <div className="skills-list">
                  {skills.map((skill) => (
                    <button
                      key={skill.name}
                      type="button"
                      className="skill-card"
                      onClick={() => setInput(skill.trigger_examples?.[0] || skill.description)}
                    >
                      <div className="skill-card-header">
                        <strong>{skill.name}</strong>
                        <span className="skill-category">{skill.category}</span>
                      </div>
                      <div className="skill-card-desc">{skill.description}</div>
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
                  <div className="message-skill-tags">
                    {msg.role === 'user' && msg.domain_hint && (
                      <span className="skill-tag skill-tag--scope">{msg.domain_hint}</span>
                    )}
                    {msg.skill && <span className="skill-tag skill-tag--green">skill: {msg.skill}</span>}
                    {msg.category && <span className="skill-tag skill-tag--blue">{msg.category}</span>}
                    {msg.execution_result?.decision?.strategy && msg.execution_result.decision.strategy !== 'conversation' && (
                      <span className="skill-tag skill-tag--strategy">{msg.execution_result.decision.strategy.replace('_', ' ')}</span>
                    )}
                    {msg.execution_result?.decision?.confidence != null && msg.execution_result.decision.confidence > 0 && (
                      <span className={`skill-tag skill-tag--confidence ${
                        msg.execution_result.decision.confidence >= 0.7 ? 'conf-high'
                        : msg.execution_result.decision.confidence >= 0.45 ? 'conf-mid'
                        : 'conf-low'
                      }`}>
                        {Math.round(msg.execution_result.decision.confidence * 100)}%
                      </span>
                    )}
                    {msg.execution_result?.rounds_used > 1 && (
                      <span className="skill-tag skill-tag--rounds">{msg.execution_result.rounds_used} rounds</span>
                    )}
                  </div>
                )}
                <div className="message-text">
                  {msg.metadata?.type === 'progress' && (
                    <span className="progress-indicator">⏳ </span>
                  )}
                  {msg.content}
                </div>
                {/* Verification warnings */}
                {msg.role === 'assistant' && msg.execution_result?.verification_warnings?.length > 0 && (
                  <div className="msg-verify-warnings">
                    {msg.execution_result.verification_warnings.map((w, i) => (
                      <div key={i} className="msg-verify-item">⚠ {w}</div>
                    ))}
                  </div>
                )}
                {/* Capability gap detected */}
                {msg.role === 'assistant' && msg.execution_result?.gap_detected && (
                  <div className="msg-gap-notice">
                    <span>⚡ Capability gap detected</span>
                    {msg.execution_result.gap_action && (
                      <span className="msg-gap-action"> → {msg.execution_result.gap_action}</span>
                    )}
                  </div>
                )}
                {msg.role === 'assistant' && msg.execution_result?.status === 'awaiting_approval' && msg.execution_result?.plan && (
                  <div style={{
                    marginTop: '10px',
                    padding: '12px',
                    border: '1px solid rgba(255,255,255,0.12)',
                    borderRadius: '10px',
                    background: 'rgba(255,255,255,0.04)'
                  }}>
                    <div style={{ fontWeight: 700, marginBottom: '6px' }}>Plan approval required</div>
                    {msg.execution_result.plan.workflow_metadata?.worktree?.worktree_path && (
                      <div style={{ fontSize: '13px', opacity: 0.9, marginBottom: '10px' }}>
                        Isolated worktree: {msg.execution_result.plan.workflow_metadata.worktree.label}
                        <br />
                        <span style={{ opacity: 0.75 }}>{msg.execution_result.plan.workflow_metadata.worktree.worktree_path}</span>
                      </div>
                    )}
                    {msg.execution_result.plan.workflow_metadata?.isolation_policy?.level && (
                      <div style={{ fontSize: '13px', opacity: 0.9, marginBottom: '10px' }}>
                        Isolation policy: {msg.execution_result.plan.workflow_metadata.isolation_policy.level}
                        <br />
                        <span style={{ opacity: 0.75 }}>{msg.execution_result.plan.workflow_metadata.isolation_policy.reason}</span>
                      </div>
                    )}
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
                {/* Tool execution steps */}
                {msg.role === 'assistant' && msg.execution_result?.tool_history && (
                  <ToolExecutionSteps toolHistory={msg.execution_result.tool_history} />
                )}
                {msg.components && <OutputRenderer components={msg.components} rawData={msg.execution_result?.primary_result} />}
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
              {agentPlan ? (
                <AgentPlanStatus agentPlan={agentPlan} />
              ) : (
                <>
                  {traces.length > 0 && traces[0].type === 'thinking' && (
                    <div className="thinking-trace">
                      <div className="thinking-label">💭 Thinking...</div>
                      <div className="thinking-content">{traces[0].message}</div>
                    </div>
                  )}
                  {traces.length === 0 && (
                    <div className="typing-indicator">
                      <span></span><span></span><span></span>
                    </div>
                  )}
                </>
              )}
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
        {isProcessing ? (
          <button
            type="button"
            className="btn-stop"
            onClick={handleStop}
            title="Stop execution"
          >
            <Square size={16} />
            Stop
          </button>
        ) : (
          <button 
            type="submit" 
            className="btn-send" 
            disabled={!input.trim()}
          >
            <Send size={16} />
            Send
          </button>
        )}
      </form>
    </div>
  );
}
