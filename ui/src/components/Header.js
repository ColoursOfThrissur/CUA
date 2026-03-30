import React, { useState, useEffect } from 'react';
import { Settings, Database, MessageSquare, Wrench, Zap, Sun, Moon, Activity, Bot, Trash2, Key, Plus, Check, ChevronDown } from 'lucide-react';
import { API_URL } from '../config';
import './Header.css';

const PROVIDERS = [
  { value: 'ollama', label: 'Ollama (Local)' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'gemini', label: 'Google Gemini' },
];

function LLMSettingsPanel({ onClose, onToast, onSaved }) {
  const [cfg, setCfg] = useState(null);
  const [provider, setProvider] = useState('ollama');
  const [modelKey, setModelKey] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [saving, setSaving] = useState(false);
  // add-model form
  const [showAddModel, setShowAddModel] = useState(false);
  const [newModelKey, setNewModelKey] = useState('');
  const [newModelName, setNewModelName] = useState('');
  const [newModelDesc, setNewModelDesc] = useState('');

  useEffect(() => {
    fetch(`${API_URL}/settings/config`)
      .then(r => r.json())
      .then(data => {
        setCfg(data);
        setProvider(data.provider || 'ollama');
        const currentKey = Object.keys(data.available_models || {}).find(
          k => data.available_models[k].name === data.model
        ) || '';
        setModelKey(currentKey);
        setBaseUrl(data.base_url || '');
      })
      .catch(() => {});
  }, []);

  const handleSave = async () => {
    if (!modelKey) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/settings/provider`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model: modelKey, api_key: apiKey, base_url: baseUrl }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        onToast && onToast('success', `Switched to ${data.provider} / ${data.model}`);
        onSaved && onSaved(data.model);
        onClose();
      } else {
        onToast && onToast('error', data.detail || 'Failed to save');
      }
    } catch (e) {
      onToast && onToast('error', e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleAddModel = async () => {
    if (!newModelKey || !newModelName) return;
    try {
      const res = await fetch(`${API_URL}/settings/add-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: newModelKey, name: newModelName, description: newModelDesc }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        onToast && onToast('success', `Model "${newModelKey}" added`);
        // refresh config
        const r2 = await fetch(`${API_URL}/settings/config`);
        const d2 = await r2.json();
        setCfg(d2);
        setNewModelKey(''); setNewModelName(''); setNewModelDesc('');
        setShowAddModel(false);
      }
    } catch (e) {
      onToast && onToast('error', e.message);
    }
  };

  const models = cfg?.available_models || {};
  const needsApiKey = provider === 'openai' || provider === 'gemini';
  const needsBaseUrl = provider === 'openai';

  // Filter models to those relevant to the selected provider
  const OLLAMA_KEYS = new Set(['qwen', 'mistral', 'phi']);
  const GEMINI_KEYS = new Set(['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-2.5-flash']);
  const OPENAI_KEYS = new Set(['gpt-4o', 'gpt-4-turbo', 'gpt-3.5-turbo', 'chatgpt']);
  const filteredModels = Object.fromEntries(
    Object.entries(models).filter(([k]) => {
      if (provider === 'ollama') return OLLAMA_KEYS.has(k) || (!GEMINI_KEYS.has(k) && !OPENAI_KEYS.has(k));
      if (provider === 'gemini') return GEMINI_KEYS.has(k) || k.startsWith('gemini');
      if (provider === 'openai') return OPENAI_KEYS.has(k) || k.startsWith('gpt') || k.startsWith('chatgpt');
      return true;
    })
  );

  return (
    <div className="llm-settings-panel">
      <div className="llm-settings-header">
        <span>LLM Settings</span>
      </div>

      <div className="llm-settings-body">
        {/* Provider */}
        <div className="llm-field">
          <label className="llm-label">Provider</label>
          <div className="llm-select-wrap">
            <select className="llm-select" value={provider} onChange={e => { setProvider(e.target.value); setModelKey(''); }}>
              {PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
            <ChevronDown size={14} className="llm-select-icon" />
          </div>
        </div>

        {/* Model */}
        <div className="llm-field">
          <label className="llm-label">Model</label>
          <div className="llm-select-wrap">
            <select className="llm-select" value={modelKey} onChange={e => setModelKey(e.target.value)}>
              <option value="">-- select --</option>
              {Object.entries(filteredModels).map(([k, m]) => (
                <option key={k} value={k}>{m.description || m.name}</option>
              ))}
            </select>
            <ChevronDown size={14} className="llm-select-icon" />
          </div>
        </div>

        {/* API Key */}
        {needsApiKey && (
          <div className="llm-field">
            <label className="llm-label">
              <Key size={12} /> API Key
              {cfg?.api_key_set && <span className="llm-badge-set">set</span>}
            </label>
            <div className="llm-input-wrap">
              <input
                className="llm-input"
                type={showApiKey ? 'text' : 'password'}
                placeholder={cfg?.api_key_masked || 'sk-...'}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
              />
              <button className="llm-eye" onClick={() => setShowApiKey(v => !v)}>
                {showApiKey ? '🙈' : '👁'}
              </button>
            </div>
          </div>
        )}

        {/* Base URL (OpenAI-compatible override) */}
        {needsBaseUrl && (
          <div className="llm-field">
            <label className="llm-label">Base URL <span className="llm-optional">(optional)</span></label>
            <input
              className="llm-input"
              type="text"
              placeholder="https://api.openai.com"
              value={baseUrl}
              onChange={e => setBaseUrl(e.target.value)}
            />
          </div>
        )}

        {/* Ollama URL info */}
        {provider === 'ollama' && cfg?.ollama_url && (
          <div className="llm-info-row">
            <span className="llm-info-label">Ollama URL</span>
            <span className="llm-info-val">{cfg.ollama_url}</span>
          </div>
        )}

        <div className="settings-divider" />

        {/* Add custom model */}
        <button className="llm-add-toggle" onClick={() => setShowAddModel(v => !v)}>
          <Plus size={13} /> Add custom model
        </button>

        {showAddModel && (
          <div className="llm-add-model">
            <input className="llm-input" placeholder="Key (e.g. my-gpt4)" value={newModelKey} onChange={e => setNewModelKey(e.target.value)} />
            <input className="llm-input" placeholder="Model name (e.g. gpt-4o)" value={newModelName} onChange={e => setNewModelName(e.target.value)} />
            <input className="llm-input" placeholder="Description (optional)" value={newModelDesc} onChange={e => setNewModelDesc(e.target.value)} />
            <button className="llm-btn-add" onClick={handleAddModel} disabled={!newModelKey || !newModelName}>
              <Check size={13} /> Save model
            </button>
          </div>
        )}
      </div>

      <div className="llm-settings-footer">
        <button className="llm-btn-cancel" onClick={onClose}>Cancel</button>
        <button className="llm-btn-save" onClick={handleSave} disabled={saving || !modelKey}>
          {saving ? 'Saving…' : 'Apply & Save'}
        </button>
      </div>
    </div>
  );
}

function Header({ loopStatus, availableModels, currentModel, onModelChange, onOpenObservability, activeMode, onModeChange, theme, onThemeToggle, onOpenAutoEvolution, onClearCache, onToast, onProviderSaved }) {
  const [showSettings, setShowSettings] = useState(false);
  const [showLLMSettings, setShowLLMSettings] = useState(false);

  const modes = [
    { id: 'chat', label: 'Forge', icon: MessageSquare },
    { id: 'tools', label: 'Tools', icon: Wrench },
    { id: 'evolution', label: 'Evolution', icon: Zap },
    { id: 'autonomy', label: 'Autonomy', icon: Bot }
  ];

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Tab' && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey) {
        const activeElement = document.activeElement;
        if (activeElement.tagName !== 'INPUT' && activeElement.tagName !== 'TEXTAREA') {
          e.preventDefault();
          const currentIndex = modes.findIndex(m => m.id === activeMode);
          const nextIndex = (currentIndex + 1) % modes.length;
          onModeChange(modes[nextIndex].id);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeMode, onModeChange]);

  return (
    <header className="header">
      <div className="header-left">
        <h1 className="logo">Forge</h1>
        <span className="status-badge">
          <span className={`status-dot ${loopStatus.running ? 'running' : 'stopped'}`}></span>
          {loopStatus.running ? `Running (${loopStatus.iteration}/${loopStatus.maxIterations})` : 'Idle'}
        </span>
      </div>

      <div className="header-center">
        {modes.map(mode => {
          const Icon = mode.icon;
          return (
            <button
              key={mode.id}
              className={`mode-tab ${activeMode === mode.id ? 'active' : ''} mode-${mode.id}`}
              onClick={() => onModeChange(mode.id)}
            >
              <Icon size={18} />
              <span>{mode.label}</span>
            </button>
          );
        })}
      </div>

      <div className="header-right">
        <button className="btn btn-auto-evolution" onClick={onOpenAutoEvolution} title="Auto-Evolution">
          <Bot size={18} />
          <span className="btn-label">Auto-Evolve</span>
        </button>
        <button className="btn btn-theme" onClick={onThemeToggle} title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        <button className="btn btn-settings" onClick={() => onModeChange('tools-management')} title="Tools Management">
          <Activity size={18} />
          <span className="btn-label">Tools</span>
        </button>
        <button className="btn btn-settings" onClick={onOpenObservability} title="Observability">
          <Database size={18} />
          <span className="btn-label">Data</span>
        </button>
        <button className="btn btn-settings" onClick={() => { setShowSettings(v => !v); setShowLLMSettings(false); }} title="Settings">
          <Settings size={18} />
        </button>
      </div>

      {showSettings && (
        <div className="settings-dropdown">
          <div className="settings-item">
            <label>Model:</label>
            <select
              value={Object.keys(availableModels).find(key => availableModels[key].name === currentModel) || 'mistral'}
              onChange={(e) => onModelChange(e.target.value)}
            >
              {Object.entries(availableModels).map(([key, model]) => (
                <option key={key} value={key}>{model.description || model.name}</option>
              ))}
            </select>
          </div>
          <div className="settings-divider" />
          <button
            className="settings-menu-item"
            onClick={() => { setShowLLMSettings(true); setShowSettings(false); }}
          >
            <Key size={16} />
            LLM Provider & Keys
          </button>
          <button className="settings-menu-item" onClick={() => { setShowSettings(false); window.dispatchEvent(new CustomEvent('openOverlay', { detail: 'sessions' })); }}>
            <MessageSquare size={16} />
            Sessions
          </button>
          <button className="settings-menu-item settings-menu-item--danger" onClick={() => { setShowSettings(false); onClearCache && onClearCache(); }}>
            <Trash2 size={16} />
            Clear Cache
          </button>
        </div>
      )}

      {showLLMSettings && (
        <LLMSettingsPanel
          onClose={() => setShowLLMSettings(false)}
          onToast={onToast}
          onSaved={onProviderSaved}
        />
      )}
    </header>
  );
}

export default Header;
