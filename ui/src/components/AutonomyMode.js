import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Play, Square, RefreshCw, AlertTriangle, CheckCircle, XCircle,
  Zap, Shield, ChevronDown, ChevronUp, Brain, GitBranch,
  Activity, Clock, SkipForward, Layers, Package
} from 'lucide-react';
import { API_URL, WS_URL } from '../config';
import { useToast } from './Toast';
import './AutonomyMode.css';

const POLL_MS = 5000;
const MAX_THOUGHTS = 80;

// ── Cycle pipeline stages ────────────────────────────────────────────────────
const STAGES = [
  { id: 'baseline',      label: 'Baseline',      icon: Shield },
  { id: 'gap_review',    label: 'Gap Review',     icon: GitBranch },
  { id: 'gap_resolution',label: 'Resolver Pass',  icon: Zap },
  { id: 'auto_evolution',label: 'Evolution Queue',icon: Layers },
  { id: 'improvement_loop', label: 'Improvement', icon: Brain },
  { id: 'quality_gate',  label: 'Quality Gate',   icon: CheckCircle },
  { id: 'sleeping',      label: 'Waiting',        icon: Clock },
];

function stageStatus(stageId, activeStage, cycleResult) {
  if (!activeStage && !cycleResult) return 'idle';
  // sleeping = between cycles, show all prior stages as done
  if (activeStage === 'sleeping') {
    return stageId === 'sleeping' ? 'running' : 'done';
  }
  if (cycleResult) {
    if (cycleResult.baseline_ok === false && stageId !== 'baseline') return 'idle';
    if (stageId === 'baseline') return cycleResult.baseline_ok ? 'done' : 'failed';
    if (stageId === 'quality_gate') return cycleResult.quality_gate?.low_value ? 'warn' : 'done';
    if (stageId === 'sleeping') return 'idle';
    return 'done';
  }
  const order = STAGES.map(s => s.id);
  const active = order.indexOf(activeStage);
  const mine = order.indexOf(stageId);
  if (mine < active) return 'done';
  if (mine === active) return 'running';
  return 'idle';
}

function CyclePipeline({ activeStage, cycleResult, running }) {
  return (
    <div className="aut-pipeline">
      {STAGES.map((s, i) => {
        const Icon = s.icon;
        const st = stageStatus(s.id, running ? activeStage : null, !running ? cycleResult : null);
        return (
          <React.Fragment key={s.id}>
            <div className={`aut-pipeline-node aut-node-${st}`}>
              <div className="aut-node-icon"><Icon size={14} /></div>
              <div className="aut-node-label">{s.label}</div>
              {st === 'running' && <div className="aut-node-pulse" />}
            </div>
            {i < STAGES.length - 1 && (
              <div className={`aut-pipeline-edge ${st === 'done' ? 'edge-done' : ''}`} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ── Thought stream ───────────────────────────────────────────────────────────
function ThoughtStream({ thoughts }) {
  const bottomRef = useRef(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [thoughts]);

  const icon = (status) => {
    if (status === 'success') return <CheckCircle size={13} className="aut-t-ok" />;
    if (status === 'error')   return <XCircle size={13} className="aut-t-err" />;
    return <Activity size={13} className="aut-t-info" />;
  };

  return (
    <div className="aut-thoughts">
      {thoughts.length === 0
        ? <div className="aut-thoughts-empty">Waiting for agent activity…</div>
        : thoughts.map((t, i) => (
          <div key={i} className={`aut-thought aut-thought-${t.status}`}>
            <span className="aut-thought-icon">{icon(t.status)}</span>
            <span className="aut-thought-msg">{t.message}</span>
            <span className="aut-thought-ts">{t.ts}</span>
          </div>
        ))
      }
      <div ref={bottomRef} />
    </div>
  );
}

// ── Gap kanban ───────────────────────────────────────────────────────────────
const GAP_COLS = [
  { id: 'detected',   label: 'Detected',         color: 'var(--accent-orange)' },
  { id: 'resolving',  label: 'Resolver Pass',     color: 'var(--accent-blue)' },
  { id: 'queued',     label: 'Queued / Pending',  color: 'var(--accent-purple)' },
  { id: 'resolved',   label: 'Resolved',          color: 'var(--accent-green)' },
];

function gapColumn(gap) {
  if (gap.resolution_attempted && gap.resolution_action) return 'resolved';
  if (gap.resolution_action === 'create_tool') return 'queued';
  if (gap.resolution_attempted) return 'resolving';
  return 'detected';
}

function GapKanban({ gaps, resolvedGaps }) {
  const allGaps = [
    ...gaps.map(g => ({ ...g, _col: gapColumn(g) })),
    ...resolvedGaps.map(g => ({ capability: g.capability, resolution_action: g.resolution_action, _col: 'resolved', _db: true })),
  ];

  return (
    <div className="aut-kanban">
      {GAP_COLS.map(col => {
        const items = allGaps.filter(g => g._col === col.id);
        return (
          <div key={col.id} className="aut-kanban-col">
            <div className="aut-kanban-col-header" style={{ borderColor: col.color }}>
              <span style={{ color: col.color }}>{col.label}</span>
              <span className="aut-kanban-count">{items.length}</span>
            </div>
            <div className="aut-kanban-cards">
              {items.length === 0
                ? <div className="aut-kanban-empty">—</div>
                : items.map((g, i) => (
                  <div key={i} className="aut-kanban-card">
                    <div className="aut-kanban-cap">{g.capability}</div>
                    {g.confidence_avg != null && (
                      <div className="aut-kanban-meta">conf {(g.confidence_avg * 100).toFixed(0)}% · {g.occurrence_count}×</div>
                    )}
                    {g.resolution_action && (
                      <div className="aut-kanban-action">{g.resolution_action}</div>
                    )}
                  </div>
                ))
              }
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Cycle history ────────────────────────────────────────────────────────────
function CycleHistory({ cycles }) {
  const [expanded, setExpanded] = useState(null);
  if (!cycles.length) return <div className="aut-empty-block">No completed cycles yet</div>;

  return (
    <div className="aut-history">
      {cycles.map((c, i) => {
        const score = c.quality_gate?.score;
        const scoreColor = score >= 0.6 ? 'var(--accent-green)' : score >= 0.35 ? 'var(--accent-orange)' : 'var(--accent-red)';
        const isOpen = expanded === i;
        return (
          <div key={i} className="aut-history-row">
            <button className="aut-history-header" onClick={() => setExpanded(isOpen ? null : i)}>
              <span className="aut-history-num">#{c.cycle_count ?? i + 1}</span>
              <span className="aut-history-ts">{c.finished_at ? c.finished_at.slice(0, 19).replace('T', ' ') : '—'}</span>
              <span className="aut-history-gaps">{c.gap_summary?.count ?? 0} gaps</span>
              <span className="aut-history-evo">
                {(c.pending_summary?.delta?.pending_tools ?? 0) + (c.pending_summary?.delta?.pending_evolutions ?? 0)} queued
              </span>
              {score != null && <span className="aut-history-score" style={{ color: scoreColor }}>score {score.toFixed(2)}</span>}
              {c.quality_gate?.low_value && <span className="aut-badge-warn">low value</span>}
              {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {isOpen && (
              <div className="aut-history-detail">
                <div className="aut-detail-grid">
                  <div><span className="aut-dl">Baseline</span><span>{c.baseline_ok ? '✓ OK' : '✗ Failed'}</span></div>
                  <div><span className="aut-dl">Top gaps</span><span>{(c.gap_summary?.top_capabilities || []).join(', ') || '—'}</span></div>
                  <div><span className="aut-dl">Evolutions processed</span><span>{c.auto_evolution?.processed ?? '—'}</span></div>
                  <div><span className="aut-dl">Tools created</span><span>{c.tool_creation?.queued ?? 0}</span></div>
                  <div><span className="aut-dl">Improvement iterations</span><span>{c.improvement_loop?.iterations_completed ?? '—'}</span></div>
                  <div><span className="aut-dl">Quality reason</span><span>{c.quality_gate?.reason ?? '—'}</span></div>
                  <div><span className="aut-dl">Health Δ</span><span>{c.quality_gate?.avg_health_delta != null ? (c.quality_gate.avg_health_delta >= 0 ? '+' : '') + c.quality_gate.avg_health_delta.toFixed(3) : '—'}</span></div>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
export default function AutonomyMode() {
  const toast = useToast();
  const wsRef = useRef(null);

  const [coordinated, setCoordinated] = useState(null);
  const [gaps, setGaps]               = useState([]);
  const [resolvedGaps, setResolvedGaps] = useState([]);
  const [queue, setQueue]             = useState([]);
  const [pendingTools, setPendingTools]   = useState(0);
  const [pendingEvos, setPendingEvos]     = useState(0);
  const [thoughts, setThoughts]       = useState([]);
  const [cycles, setCycles]           = useState([]);
  const [activeStage, setActiveStage] = useState(null);
  const [loading, setLoading]         = useState(false);
  const [section, setSection]         = useState('stream');

  const addThought = useCallback((msg, status, ts) => {
    setThoughts(prev => {
      const next = [...prev, { message: msg, status, ts }];
      return next.length > MAX_THOUGHTS ? next.slice(-MAX_THOUGHTS) : next;
    });
  }, []);

  // WebSocket for live trace
  useEffect(() => {
    const connect = () => {
      try {
        const ws = new WebSocket(`${WS_URL}/trace`);
        wsRef.current = ws;
        ws.onmessage = (e) => {
          try {
            const ev = JSON.parse(e.data);
            const stage = ev.details?.stage;
            if (stage) setActiveStage(stage);
            const ts = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            addThought(ev.message, ev.status, ts);
          } catch (_) {}
        };
        ws.onclose = () => { setTimeout(connect, 3000); };
        ws.onerror = () => { ws.close(); };
      } catch (_) {}
    };
    connect();
    return () => { wsRef.current?.close(); };
  }, [addThought]);

  const fetchAll = useCallback(async () => {
    try {
      const [coordRes, gapRes, resolvedRes, queueRes, pendingToolsRes, pendingEvosRes, evoMetricsRes] = await Promise.allSettled([
        fetch(`${API_URL}/auto-evolution/coordinated/status`),
        fetch(`${API_URL}/improvement/evolution/capability-gaps`),
        fetch(`${API_URL}/observability/data/cua.db/resolved_gaps?limit=50`),
        fetch(`${API_URL}/auto-evolution/queue`),
        fetch(`${API_URL}/pending-tools/list`),
        fetch(`${API_URL}/evolution/pending`),
        fetch(`${API_URL}/observability/data/cua.db/auto_evolution_metrics?limit=20`),
      ]);

      if (coordRes.status === 'fulfilled' && coordRes.value.ok) {
        const d = await coordRes.value.json();
        setCoordinated(d);
        if (d.last_cycle?.cycle_count != null) {
          setCycles(prev => {
            const exists = prev.find(c => c.cycle_count === d.last_cycle.cycle_count);
            if (exists) return prev;
            return [d.last_cycle, ...prev].slice(0, 20);
          });
        }
        if (!d.running) setActiveStage(null);
      }
      if (gapRes.status === 'fulfilled' && gapRes.value.ok) {
        const d = await gapRes.value.json();
        const raw = d.gaps;
        setGaps(Array.isArray(raw) ? raw : Array.isArray(raw?.gaps) ? raw.gaps : []);
      }
      if (resolvedRes.status === 'fulfilled' && resolvedRes.value.ok) {
        const d = await resolvedRes.value.json();
        setResolvedGaps(Array.isArray(d.rows) ? d.rows : []);
      }
      if (queueRes.status === 'fulfilled' && queueRes.value.ok) {
        const d = await queueRes.value.json();
        setQueue(Array.isArray(d.queue) ? d.queue : []);
      }
      if (pendingToolsRes.status === 'fulfilled' && pendingToolsRes.value.ok) {
        const d = await pendingToolsRes.value.json();
        setPendingTools((d.pending_tools || []).length);
      }
      if (pendingEvosRes.status === 'fulfilled' && pendingEvosRes.value.ok) {
        const d = await pendingEvosRes.value.json();
        setPendingEvos(Array.isArray(d.pending_evolutions) ? d.pending_evolutions.length : 0);
      }
      // Seed cycle history from DB if in-memory list is empty
      if (evoMetricsRes.status === 'fulfilled' && evoMetricsRes.value.ok) {
        const d = await evoMetricsRes.value.json();
        setCycles(prev => {
          if (prev.length > 0) return prev;
          return (d.rows || []).map((r, i) => ({
            cycle_count: i + 1,
            finished_at: r.created_at || r.hour_timestamp,
            baseline_ok: true,
            gap_summary: { count: 0, top_capabilities: [] },
            auto_evolution: { processed: r.evolutions_triggered ?? 0, failures: r.evolutions_rejected ?? 0 },
            tool_creation: { queued: 0 },
            improvement_loop: { iterations_completed: 0 },
            pending_summary: {
              delta: {
                pending_tools: 0,
                pending_evolutions: r.evolutions_pending ?? 0,
              }
            },
            quality_gate: {
              score: null,
              low_value: false,
              avg_health_delta: r.avg_health_improvement ?? 0,
              reason: `${r.tools_analyzed ?? 0} tools analyzed, ${r.evolutions_triggered ?? 0} evolutions`,
            },
          })).reverse();
        });
      }
    } catch (_) {}
  }, []);

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, POLL_MS);
    return () => clearInterval(t);
  }, [fetchAll]);

  // Controls
  const coordRunning = coordinated?.running;
  const reloadBlocked = coordinated?.reload_blocked;
  const scanning = coordinated?.auto_evolution?.scanning;

  const act = async (url, method = 'POST', body = null) => {
    setLoading(true);
    try {
      const r = await fetch(`${API_URL}${url}`, {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      const d = await r.json();
      if (!r.ok) toast.error(d.detail || 'Request failed');
      else toast.success(d.message || 'Done');
      await fetchAll();
    } catch (e) { toast.error(e.message); }
    setLoading(false);
  };

  const qualityScore = coordinated?.last_cycle?.quality_gate?.score;
  const scoreColor = qualityScore >= 0.6 ? 'var(--accent-green)' : qualityScore >= 0.35 ? 'var(--accent-orange)' : 'var(--accent-red)';
  const totalPending = pendingTools + pendingEvos;

  return (
    <div className="aut-page">

      {/* Header */}
      <div className="aut-header">
        <div className="aut-header-left">
          <Brain size={20} className="aut-header-icon" />
          <span className="aut-header-title">Agent Cockpit</span>
          <span className={`aut-status-pill ${coordRunning ? 'pill-running' : 'pill-idle'}`}>
            {coordRunning ? 'Running' : 'Idle'}
          </span>
          {coordinated?.paused_reason && (
            <span className="aut-status-pill pill-warn">Paused: {coordinated.paused_reason}</span>
          )}
          {reloadBlocked && (
            <span className="aut-status-pill pill-warn">Reload Mode</span>
          )}
        </div>
        <div className="aut-header-right">
          <button className="aut-btn-icon" onClick={fetchAll} disabled={loading} title="Refresh">
            <RefreshCw size={15} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      {/* Cycle pipeline */}
      <CyclePipeline
        activeStage={activeStage}
        cycleResult={coordinated?.last_cycle}
        running={coordRunning}
      />

      {/* Controls row */}
      <div className="aut-controls-row">
        <div className="aut-controls-left">
          {!coordRunning
            ? <button className="aut-btn aut-btn-start" onClick={() => act('/auto-evolution/coordinated/start')} disabled={loading || reloadBlocked}>
                <Play size={14} /> Start Coordinated
              </button>
            : <button className="aut-btn aut-btn-stop" onClick={() => act('/auto-evolution/coordinated/stop')} disabled={loading}>
                <Square size={14} /> Stop
              </button>
          }
          <button className="aut-btn aut-btn-secondary" onClick={() => act('/auto-evolution/coordinated/run-cycle')} disabled={loading || reloadBlocked || coordRunning}>
            <SkipForward size={14} /> Run Cycle Now
          </button>
          <button className="aut-btn aut-btn-secondary" onClick={() => act('/auto-evolution/trigger-scan')} disabled={loading || scanning}>
            <RefreshCw size={14} className={scanning ? 'spin' : ''} />
            {scanning ? 'Scanning…' : 'Scan Tools'}
          </button>
        </div>

        {/* Last cycle summary */}
        {coordinated?.last_cycle && (
          <div className="aut-cycle-summary">
            <span className="aut-cs-label">Last cycle</span>
            <span className="aut-cs-val">#{coordinated.last_cycle.cycle_count}</span>
            {qualityScore != null && <span className="aut-cs-score" style={{ color: scoreColor }}>score {qualityScore.toFixed(2)}</span>}
            <span className="aut-cs-ts">{coordinated.last_cycle.finished_at?.slice(0, 19).replace('T', ' ')}</span>
          </div>
        )}

        {coordRunning && (
          <button className="aut-btn aut-btn-emergency" onClick={() => act('/auto-evolution/coordinated/stop')} disabled={loading}>
            <AlertTriangle size={14} /> Emergency Stop
          </button>
        )}
      </div>

      {/* Pending approvals banner */}
      {totalPending > 0 && (
        <div className="aut-pending-banner">
          <Package size={14} />
          <span>{totalPending} item{totalPending !== 1 ? 's' : ''} waiting for approval</span>
          {pendingTools > 0 && <span className="aut-pending-chip">{pendingTools} new tool{pendingTools !== 1 ? 's' : ''}</span>}
          {pendingEvos > 0 && <span className="aut-pending-chip">{pendingEvos} evolution{pendingEvos !== 1 ? 's' : ''}</span>}
          <span className="aut-pending-note">Approve or decline before tool creation runs</span>
          <button className="aut-pending-link" onClick={() => window.dispatchEvent(new CustomEvent('switchMode', { detail: 'evolution' }))}>
            Review in Evolution →
          </button>
        </div>
      )}
      {totalPending === 0 && coordinated?.last_cycle?.tool_creation?.queued > 0 && (
        <div className="aut-pending-banner aut-pending-creation">
          <Package size={14} />
          <span>{coordinated.last_cycle.tool_creation.queued} tool creation{coordinated.last_cycle.tool_creation.queued !== 1 ? 's' : ''} queued this cycle</span>
          <button className="aut-pending-link" onClick={() => window.dispatchEvent(new CustomEvent('switchMode', { detail: 'tools' }))}>
            Review in Tools →
          </button>
        </div>
      )}

      {/* Evolution queue */}
      {queue.length > 0 && (
        <div className="aut-queue">
          <div className="aut-queue-header">
            <Layers size={13} /> Queue ({queue.length})
          </div>
          <div className="aut-queue-items">
            {queue.map((item, i) => (
              <div key={i} className="aut-queue-item">
                <span className={`aut-queue-kind aut-kind-${(item.metadata?.kind || 'evolve').replace('_tool','')}`}>
                  {item.metadata?.kind === 'create_tool' ? 'CREATE' : 'EVOLVE'}
                </span>
                <span className="aut-queue-name">{item.tool_name?.replace('CREATE::', '')}</span>
                <span className="aut-queue-score">{(item.priority_score ?? 0).toFixed(0)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Section tabs */}
      <div className="aut-section-tabs">
        {[
          { id: 'stream',  label: 'Thought Stream', icon: Activity },
          { id: 'gaps',    label: `Gap Pipeline (${gaps.length + resolvedGaps.length})`, icon: GitBranch },
          { id: 'history', label: `Cycle History (${cycles.length})`, icon: Clock },
        ].map(({ id, label, icon: Icon }) => (
          <button key={id} className={`aut-tab ${section === id ? 'aut-tab-active' : ''}`} onClick={() => setSection(id)}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {/* Section content */}
      <div className="aut-section-body">
        {section === 'stream' && <ThoughtStream thoughts={thoughts} />}
        {section === 'gaps'   && <GapKanban gaps={gaps} resolvedGaps={resolvedGaps} />}
        {section === 'history'&& <CycleHistory cycles={cycles} />}
      </div>

    </div>
  );
}
