import asyncio, sys, json
sys.stdout.reconfigure(encoding='utf-8')

async def test():
    from core.config_manager import get_config
    from planner.llm_client import LLMClient
    
    cfg = get_config()
    llm = LLMClient(model=cfg.llm.default_model)
    
    # Simulate covered_caps from loaded tools
    covered_caps = {
        'navigate', 'screenshot', 'click', 'fill_input', 'summarize_text',
        'extract_key_points', 'sentiment_analysis', 'save_snippet', 'get_snippet',
        'search', 'list_popular', 'run_benchmark_suite', 'add_benchmark_case',
        'compare_text_files', 'compare_json_data', 'query_logs', 'analyze_failures',
        'read', 'write', 'list', 'get', 'post', 'parse', 'stringify',
        'execute', 'fetch', 'crawl', 'classify_intent', 'suggest_tool',
        'request_approval', 'log_approval', 'define_workflow', 'execute_workflow',
        'evaluate', 'evaluate_plan', 'analyze_task',
    }
    
    from pathlib import Path
    import json as _json
    
    skills_snapshot = []
    for skill_dir in sorted(Path('skills').iterdir()):
        skill_json = skill_dir / 'skill.json'
        if not skill_json.exists():
            continue
        try:
            sd = _json.loads(skill_json.read_text())
            skills_snapshot.append({
                'name': sd.get('name', skill_dir.name),
                'description': sd.get('description', ''),
            })
        except Exception:
            pass
    
    existing_tools = [
        f.stem for base in [Path('tools'), Path('tools/experimental')]
        if base.exists()
        for f in base.glob('*.py')
        if not f.name.startswith('__')
    ]
    
    prompt = (
        "You are analysing the CUA autonomous agent system to find missing tool capabilities.\n"
        "CUA is a local autonomous agent: plans tasks, routes via skills, calls tools, creates/evolves tools.\n\n"
        f"SKILLS: {', '.join(s['name'] for s in skills_snapshot)}\n"
        f"SKILL DESCRIPTIONS: {'; '.join(s['description'] for s in skills_snapshot if s['description'])}\n"
        f"EXISTING TOOLS: {', '.join(existing_tools)}\n"
        f"COVERED CAPABILITIES (sample): {', '.join(sorted(covered_caps)[:40])}\n\n"
        "Identify up to 2 tool capabilities that are CLEARLY missing for a general-purpose autonomous agent.\n"
        "Think about: scheduling, notifications, email, calendar, code execution, file watching, "
        "image processing, PDF handling, API key management, caching, rate limiting, "
        "data validation, report generation, template rendering.\n"
        "Pick the 2 most impactful gaps that no existing tool covers.\n\n"
        "Return JSON array (max 2 items):\n"
        '[{"capability": "snake_case_name", "confidence": 0.0-1.0, '
        '"reason": "one sentence why this is needed", '
        '"suggested_tool_name": "ToolNameTool"}]\n'
        "Confidence >= 0.6 is sufficient. Return [] only if the system is truly complete."
    )
    
    print('Calling LLM for proactive gap analysis...')
    raw = llm._call_llm(prompt, 0.1, 600, True)
    print(f'Raw response: {raw[:500]}')
    
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        print(f'\nParsed: {json.dumps(data, indent=2)}')
    except Exception as e:
        print(f'Parse error: {e}')

asyncio.run(test())
