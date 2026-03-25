import React, { useState, useEffect, useCallback } from 'react';
import {
  Server, Plus, RefreshCw, Trash2, Wifi, WifiOff,
  ChevronDown, ChevronRight, Loader2, Copy, Check,
  Key, Terminal, ToggleLeft, ToggleRight, Play, Square
} from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from './Toast';
import './MCPPanel.css';

function MCPPanel() {
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState({});
  const [credInputs, setCredInputs] = useState({});
  const [actionLoading, setActionLoading] = useState({});
  const [copied, setCopied] = useState({});
  const [showCustom, setShowCustom] = useState(false);
  const [customForm, setCustomForm] = useState({ name: '', transport: 'stdio', command: '', url: '', rpc_path: '/rpc' });
  const toast = useToast();

  const fetchServers = useCallback(async () => {
    setLoading(true);
    try {
      const [cfgRes, procRes] = await Promise.all([
        fetch(`${API_URL}/mcp/configured`),
        fetch(`${API_URL}/mcp/processes`),
      ]);
      const cfg = await cfgRes.json();
      const proc = await procRes.json();
      const processes = proc.processes || {};
      // Merge process running state into server list
      const merged = (cfg.servers || []).map(s => ({
        ...s,
        process_running: processes[s.name]?.running || false,
      }));
      setServers(merged);
    } catch {
      toast.error('Failed to load MCP servers');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { fetchServers(); }, [fetchServers]);

  const setAction = (name, val) => setActionLoading(p => ({ ...p, [name]: val }));

  const handleStart = async (name) => {
    setAction(name, 'start');
    try {
      const res = await fetch(`${API_URL}/mcp/start/${encodeURIComponent(name)}`, { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        const cr = data.connect_result;
        if (cr?.connected || cr?.action === 'connected') toast.success(`${name} started — ${cr?.tools || 0} tools`);
        else toast.success(data.message);
        fetchServers();
      } else {
        toast.error(data.message || 'Start failed');
      }
    } catch (e) { toast.error(e.message); }
    finally { setAction(name, null); }
  };

  const handleStop = async (name) => {
    setAction(name, 'stop');
    try {
      const res = await fetch(`${API_URL}/mcp/stop/${encodeURIComponent(name)}`, { method: 'POST' });
      const data = await res.json();
      if (data.success) { toast.success(`${name} stopped`); fetchServers(); }
      else toast.error('Stop failed');
    } catch (e) { toast.error(e.message); }
    finally { setAction(name, null); }
  };

  const handleConfigure = async (server, enabled) => {
    setAction(server.name, 'configure');
    const credVal = credInputs[server.name] || '';
    try {
      const res = await fetch(`${API_URL}/mcp/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: server.name,
          enabled,
          credential_value: credVal || null,
        }),
      });
      const data = await res.json();
      if (data.success) {
        const cr = data.connect_result;
        if (cr?.connected) toast.success(`${server.name} enabled and connected — ${cr.tools} tools`);
        else if (cr?.action === 'not_reachable') toast.info(`${server.name} enabled. Start the server process to connect.`);
        else if (!enabled) toast.success(`${server.name} disabled`);
        else toast.success(`${server.name} configured`);
        // Clear credential input after save
        setCredInputs(p => ({ ...p, [server.name]: '' }));
        fetchServers();
      } else {
        toast.error(data.detail || 'Configure failed');
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setAction(server.name, null);
    }
  };

  const handleReconnect = async (name) => {
    setAction(name, 'reconnect');
    try {
      const res = await fetch(`${API_URL}/mcp/reconnect/${encodeURIComponent(name)}`, { method: 'POST' });
      const data = await res.json();
      if (data.success) { toast.success(data.message); fetchServers(); }
      else toast.error(data.message || 'Reconnect failed');
    } catch (e) {
      toast.error(e.message);
    } finally {
      setAction(name, null);
    }
  };

  const handleDisconnect = async (name) => {
    setAction(name, 'disconnect');
    try {
      const res = await fetch(`${API_URL}/mcp/disconnect/${encodeURIComponent(name)}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) { toast.success(data.message); fetchServers(); }
      else toast.error(data.detail || 'Disconnect failed');
    } catch (e) {
      toast.error(e.message);
    } finally {
      setAction(name, null);
    }
  };

  const handleCustomConnect = async () => {
    if (!customForm.name) { toast.error('Name required'); return; }
    if (customForm.transport === 'stdio' && !customForm.command) { toast.error('Command required for stdio transport'); return; }
    if (customForm.transport === 'http' && !customForm.url) { toast.error('URL required for http transport'); return; }
    setAction('__custom', true);
    try {
      const res = await fetch(`${API_URL}/mcp/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(customForm),
      });
      const data = await res.json();
      if (data.success) {
        toast.success(data.message);
        setShowCustom(false);
        setCustomForm({ name: '', url: '', rpc_path: '/rpc' });
        fetchServers();
      } else {
        toast.error(data.message || data.detail || 'Connect failed');
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setAction('__custom', false);
    }
  };

  const copyInstall = (server) => {
    const envPrefix = server.env_key ? `${server.env_key}=<your-key> ` : '';
    const cmd = `${envPrefix}npx -y ${server.package} --port ${server.port}`;
    navigator.clipboard.writeText(cmd).then(() => {
      setCopied(p => ({ ...p, [server.name]: true }));
      setTimeout(() => setCopied(p => ({ ...p, [server.name]: false })), 2000);
    });
  };

  const toggleExpand = (name) => setExpanded(p => ({ ...p, [name]: !p[name] }));

  const connected = servers.filter(s => s.connected).length;
  const enabled = servers.filter(s => s.enabled).length;

  return (
    <div className="mcp-panel">
      <div className="mcp-header">
        <div className="mcp-title">
          <Server size={18} />
          <h2>MCP Servers</h2>
          <span className="mcp-badge mcp-badge-connected">{connected} connected</span>
          <span className="mcp-badge mcp-badge-enabled">{enabled} enabled</span>
        </div>
        <div className="mcp-header-actions">
          <button className="mcp-icon-btn" onClick={fetchServers} disabled={loading} title="Refresh">
            <RefreshCw size={15} className={loading ? 'spin' : ''} />
          </button>
          <button className="mcp-connect-btn" onClick={() => setShowCustom(v => !v)}>
            <Plus size={15} /> Custom Server
          </button>
        </div>
      </div>

      {/* Custom server form */}
      {showCustom && (
        <div className="mcp-connect-form">
          <p className="mcp-form-hint">Connect any MCP server not in the list above</p>
          <div className="mcp-form-row">
            <input className="mcp-input" placeholder="Name (e.g. my-server)" value={customForm.name}
              onChange={e => setCustomForm(p => ({ ...p, name: e.target.value }))} />
            <select className="mcp-input mcp-input-sm" value={customForm.transport}
              onChange={e => setCustomForm(p => ({ ...p, transport: e.target.value }))}>
              <option value="stdio">stdio</option>
              <option value="http">http</option>
            </select>
          </div>
          <div className="mcp-form-row">
            {customForm.transport === 'stdio'
              ? <input className="mcp-input" placeholder="Command (e.g. npx -y @modelcontextprotocol/server-memory)" value={customForm.command}
                  onChange={e => setCustomForm(p => ({ ...p, command: e.target.value }))} />
              : <>
                  <input className="mcp-input" placeholder="URL (e.g. http://localhost:3200)" value={customForm.url}
                    onChange={e => setCustomForm(p => ({ ...p, url: e.target.value }))} />
                  <input className="mcp-input mcp-input-sm" placeholder="RPC path (/rpc)" value={customForm.rpc_path}
                    onChange={e => setCustomForm(p => ({ ...p, rpc_path: e.target.value }))} />
                </>
            }
          </div>
          <div className="mcp-form-actions">
            <button className="mcp-btn-secondary" onClick={() => setShowCustom(false)}>Cancel</button>
            <button className="mcp-btn-primary" onClick={handleCustomConnect} disabled={actionLoading['__custom']}>
              {actionLoading['__custom'] ? <Loader2 size={14} className="spin" /> : <Plus size={14} />} Connect
            </button>
          </div>
        </div>
      )}

      {/* Server list */}
      <div className="mcp-list">
        {servers.map(server => {
          const busy = actionLoading[server.name];
          const isExpanded = expanded[server.name];
          const needsKey = !!server.env_key;
          const keyReady = server.credential_set;

          return (
            <div key={server.name} className={`mcp-card ${server.connected ? 'mcp-connected' : server.enabled ? 'mcp-enabled' : 'mcp-disabled'}`}>
              {/* Card header */}
              <div className="mcp-card-header" onClick={() => toggleExpand(server.name)}>
                <div className="mcp-card-left">
                  {server.connected
                    ? <Wifi size={15} className="mcp-icon-connected" />
                    : <WifiOff size={15} className="mcp-icon-disconnected" />}
                  <span className="mcp-server-name">{server.name}</span>
                  <span className="mcp-server-url">{server.url}</span>
                  {server.connected && <span className="mcp-pill mcp-pill-green">{server.tool_count} tools</span>}
                  {server.process_running && !server.connected && <span className="mcp-pill mcp-pill-orange">starting…</span>}
                  {server.enabled && !server.process_running && !server.connected && <span className="mcp-pill mcp-pill-orange">not running</span>}
                  {needsKey && !keyReady && <span className="mcp-pill mcp-pill-red"><Key size={10} /> key needed</span>}
                  {needsKey && keyReady && <span className="mcp-pill mcp-pill-green"><Key size={10} /> key set</span>}
                </div>
                <div className="mcp-card-actions" onClick={e => e.stopPropagation()}>
                  {/* Start / Stop process buttons */}
                  {server.enabled && !server.process_running && (
                    <button className="mcp-icon-btn mcp-icon-start" onClick={() => handleStart(server.name)}
                      disabled={!!busy} title="Start server process">
                      {busy === 'start' ? <Loader2 size={13} className="spin" /> : <Play size={13} />}
                    </button>
                  )}
                  {server.process_running && (
                    <button className="mcp-icon-btn mcp-icon-danger" onClick={() => handleStop(server.name)}
                      disabled={!!busy} title="Stop server process">
                      {busy === 'stop' ? <Loader2 size={13} className="spin" /> : <Square size={13} />}
                    </button>
                  )}
                  {server.loaded && (
                    <button className="mcp-icon-btn" onClick={() => handleReconnect(server.name)}
                      disabled={!!busy} title="Reconnect adapter">
                      {busy === 'reconnect' ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />}
                    </button>
                  )}
                  {/* Enable / Disable toggle */}
                  <button
                    className={`mcp-toggle-btn ${server.enabled ? 'mcp-toggle-on' : ''}`}
                    onClick={() => handleConfigure(server, !server.enabled)}
                    disabled={!!busy}
                    title={server.enabled ? 'Disable' : 'Enable'}
                  >
                    {busy === 'configure'
                      ? <Loader2 size={14} className="spin" />
                      : server.enabled ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
                  </button>
                  {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                </div>
              </div>

              {/* Expanded body */}
              {isExpanded && (
                <div className="mcp-card-body">
                  {/* Error */}
                  {server.init_error && (
                    <div className="mcp-error-msg">{server.init_error}</div>
                  )}

                  {/* Install / command info */}
                  <div className="mcp-install-row">
                    <Terminal size={13} />
                    <code className="mcp-install-cmd">
                      {server.transport === 'stdio'
                        ? (server.env_key ? `${server.env_key}=<key> ${server.command}` : server.command)
                        : `${server.url}`
                      }
                    </code>
                    <button className="mcp-icon-btn mcp-copy-btn" onClick={() => {
                      const txt = server.transport === 'stdio'
                        ? (server.env_key ? `${server.env_key}=<key> ${server.command}` : server.command)
                        : server.url;
                      navigator.clipboard.writeText(txt).then(() => {
                        setCopied(p => ({ ...p, [server.name]: true }));
                        setTimeout(() => setCopied(p => ({ ...p, [server.name]: false })), 2000);
                      });
                    }} title="Copy">
                      {copied[server.name] ? <Check size={13} className="mcp-copied" /> : <Copy size={13} />}
                    </button>
                  </div>

                  {/* Credential input — only for servers that need a key */}
                  {needsKey && (
                    <div className="mcp-cred-row">
                      <Key size={13} className="mcp-cred-icon" />
                      <input
                        className="mcp-input mcp-cred-input"
                        type="password"
                        placeholder={keyReady ? `${server.env_key} already set — paste new to update` : `Paste ${server.env_key} here`}
                        value={credInputs[server.name] || ''}
                        onChange={e => setCredInputs(p => ({ ...p, [server.name]: e.target.value }))}
                      />
                      <button
                        className="mcp-btn-primary mcp-save-btn"
                        disabled={!credInputs[server.name] || !!busy}
                        onClick={() => handleConfigure(server, server.enabled)}
                      >
                        {busy === 'configure' ? <Loader2 size={13} className="spin" /> : 'Save Key'}
                      </button>
                    </div>
                  )}

                  {/* Tool list */}
                  {server.connected && server.tool_count > 0 && (
                    <div className="mcp-tools-section">
                      <span className="mcp-tools-label">Discovered tools</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {servers.length === 0 && !loading && (
        <div className="mcp-empty">
          <WifiOff size={32} />
          <p>No servers configured</p>
          <span>Add mcp_servers entries to config.yaml</span>
        </div>
      )}
    </div>
  );
}

export default MCPPanel;
