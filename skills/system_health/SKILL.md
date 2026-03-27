# system_health skill

Routes system and agent health queries to `SystemHealthTool`.

## What it handles

- System metrics: CPU, RAM, disk, GPU
- LLM runtime: Ollama process stats, p50/p95/p99 latency, LLM call rate
- Agent behavior: tool success rates, circuit breakers, loop detection, planning trend
- CUA internals: pending queues, DB size, WAL pressure, last autonomy cycle
- Full health report: all layers + LLM advisor diagnosis with specific fixes

## Example queries

- "Why is CUA slow?" → `get_health_report`
- "Is Ollama running?" → `get_llm_runtime`
- "What tools are failing?" → `get_agent_behavior`
- "Check system status" → `get_system_metrics`
- "Are there pending evolutions?" → `get_cua_internals`
