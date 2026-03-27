"""Output Analyzer - Analyzes tool outputs and suggests UI components."""
from typing import Dict, List, Any, Optional


class OutputAnalyzer:
    """Analyzes tool output and generates UI component specifications."""
    
    @staticmethod
    def analyze(
        data: Any,
        tool_name: str = "",
        operation: str = "",
        preferred_renderer: Optional[str] = None,
        summary: str = "",
        skill_name: str = "",
        category: str = "",
        output_types: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Analyze output and return list of UI components to render
        
        Returns:
            List of component specs: [{"type": "table", "data": [...], ...}]
        """
        components = []
        
        if not data:
            return components

        has_overview = bool(preferred_renderer or summary or skill_name)
        if has_overview:
            components.append(
                OutputAnalyzer._build_result_overview(
                    data=data,
                    tool_name=tool_name,
                    operation=operation,
                    preferred_renderer=preferred_renderer,
                    summary=summary,
                    skill_name=skill_name,
                    category=category,
                    output_types=output_types or [],
                )
            )
        
        # Handle dict outputs
        if isinstance(data, dict):
            # CodeAnalysisTool outputs
            if operation in ("get_code_review", "get_file_metrics", "detect_issues", "get_dependencies", "get_change_impact") or tool_name == "CodeAnalysisTool":
                components.extend(OutputAnalyzer._build_code_analysis_components(data, operation))
                return components

            # SystemHealthTool outputs
            if operation in ("get_health_report", "get_system_metrics", "get_agent_behavior", "get_llm_runtime", "get_cua_internals") or tool_name == "SystemHealthTool":
                components.extend(OutputAnalyzer._build_health_components(data, operation))
                return components

            # FinancialAnalysisTool outputs
            if operation in ("get_advisor_insight", "get_price_data", "get_technicals", "get_portfolio_analysis", "get_sentiment", "generate_morning_note", "generate_full_report", "save_portfolio") or tool_name == "FinancialAnalysisTool":
                components.extend(OutputAnalyzer._build_finance_components(data, operation))
                return components

            # File write/read result
            if 'path' in data and ('bytes_written' in data or 'content' in data or 'size' in data):
                content = data.get('content', '')
                components.append({
                    'type': 'file_result',
                    'renderer': 'file_result',
                    'path': data['path'],
                    'bytes_written': data.get('bytes_written') or data.get('size'),
                    'content': content[:3000] if isinstance(content, str) else None,
                    'operation': operation,
                })

            # Tool/capability list (e.g. list_tools, status responses)
            if 'tools' in data and isinstance(data['tools'], (list, dict)):
                tools_raw = data['tools']
                if isinstance(tools_raw, dict):
                    tools_raw = [{'name': k, **v} if isinstance(v, dict) else {'name': k, 'info': str(v)} for k, v in tools_raw.items()]
                components.append({
                    'type': 'tool_list',
                    'renderer': 'tool_list',
                    'tools': tools_raw,
                    'title': data.get('title', 'Tools'),
                })

            # Shell/command output
            if 'output' in data and ('command' in data or 'exit_code' in data or operation in ('execute', 'run_script')):
                components.append({
                    'type': 'terminal_output',
                    'renderer': 'terminal_output',
                    'command': data.get('command', ''),
                    'output': str(data['output'])[:4000],
                    'exit_code': data.get('exit_code', 0),
                    'error': data.get('error', ''),
                })

            # Check for web research outputs — skip if overview card already covers it
            if not has_overview and 'url' in data and ('content' in data or 'summary' in data or 'text' in data):
                components.append({
                    'type': 'web_content',
                    'renderer': 'web_content',
                    'url': data['url'],
                    'title': data.get('title', 'Web Content'),
                    'content': data.get('content') or data.get('summary') or data.get('text', ''),
                    'summary': data.get('summary', ''),
                })
            
            # Check for summarized text content — skip if overview card already covers it
            if not has_overview and ('summary' in data or 'text' in data):
                content = data.get('summary') or data.get('text')
                if isinstance(content, str) and len(content) > 50:
                    components.append({
                        'type': 'text_content',
                        'renderer': 'text_content',
                        'content': content,
                        'title': data.get('title', 'Summary'),
                        'source_url': data.get('url', ''),
                    })
            
            # Structured browser content (get_structured_content)
            if 'tables' in data and isinstance(data['tables'], list):
                for tbl in data['tables'][:5]:
                    if tbl.get('rows'):
                        components.append({
                            'type': 'table',
                            'renderer': 'table',
                            'data': tbl['rows'],
                            'title': tbl.get('caption') or 'Table',
                            'columns': tbl.get('headers') or OutputAnalyzer._extract_columns(tbl['rows']),
                        })

            # extract_links — render as table
            if 'links' not in data and 'count' in data and isinstance(data.get('links'), list):
                pass  # handled below
            if isinstance(data.get('links'), list) and data['links'] and isinstance(data['links'][0], dict) and 'href' in data['links'][0]:
                components.append({
                    'type': 'table', 'renderer': 'table',
                    'data': data['links'],
                    'title': 'Links',
                    'columns': ['text', 'href', 'title'],
                })

            # extract_lists — render each as a list component
            if isinstance(data.get('lists'), list):
                for lst in data['lists'][:5]:
                    if lst.get('items'):
                        components.append({
                            'type': 'list', 'renderer': 'list',
                            'items': lst['items'],
                        })

            # extract_article — render body as text_content
            if 'body' in data and isinstance(data.get('body'), str) and len(data['body']) > 100:
                components.append({
                    'type': 'text_content', 'renderer': 'text_content',
                    'content': data['body'],
                    'title': data.get('title') or 'Article',
                    'source_url': data.get('url', ''),
                })

            if 'sources' in data and isinstance(data['sources'], list):
                components.append({
                    'type': 'table',
                    'renderer': 'table',
                    'data': data['sources'],
                    'title': 'Sources',
                    'columns': OutputAnalyzer._extract_columns(data['sources'])
                })

            if 'links' in data and isinstance(data['links'], list):
                components.append({
                    'type': 'table',
                    'renderer': 'table',
                    'data': data['links'],
                    'title': 'Links',
                    'columns': OutputAnalyzer._extract_columns(data['links'])
                })

            if 'results' in data and isinstance(data['results'], list) and data['results'] and isinstance(data['results'][0], dict):
                components.append({
                    'type': 'table',
                    'renderer': 'table',
                    'data': data['results'],
                    'title': 'Results',
                    'columns': OutputAnalyzer._extract_columns(data['results'])
                })

            # Check for table data (list of dicts with consistent keys)
            if 'executions' in data and isinstance(data['executions'], list):
                components.append({
                    'type': 'table',
                    'renderer': 'table',
                    'data': data['executions'],
                    'title': f'{tool_name} Executions',
                    'columns': OutputAnalyzer._extract_columns(data['executions'])
                })
            
            if 'performance' in data and isinstance(data['performance'], list):
                components.append({
                    'type': 'table',
                    'renderer': 'table',
                    'data': data['performance'],
                    'title': 'Performance Metrics',
                    'columns': OutputAnalyzer._extract_columns(data['performance'])
                })
            
            if 'logs' in data and isinstance(data['logs'], list):
                components.append({
                    'type': 'logs',
                    'renderer': 'logs',
                    'data': data['logs'],
                    'title': 'System Logs'
                })
            
            # Check for metrics/stats
            metrics = OutputAnalyzer._extract_metrics(data)
            if metrics:
                components.append({
                    'type': 'stats',
                    'renderer': 'stats',
                    'metrics': metrics
                })
            
            # Check for code/patches
            if 'code' in data or 'patch' in data:
                components.append({
                    'type': 'code',
                    'renderer': 'code',
                    'content': data.get('code') or data.get('patch'),
                    'language': OutputAnalyzer._detect_language(data)
                })
            
            # Check for images
            if 'image' in data or 'image_url' in data or 'screenshot_b64' in data:
                b64 = data.get('screenshot_b64')
                components.append({
                    'type': 'screenshot',
                    'renderer': 'screenshot',
                    'src': f'data:image/png;base64,{b64}' if b64 else None,
                    'url': data.get('image_url') or data.get('image'),
                    'filepath': data.get('filepath', ''),
                    'alt': data.get('image_alt', 'Screenshot'),
                })
            
            # Check for markdown
            if 'markdown' in data:
                components.append({
                    'type': 'markdown',
                    'renderer': 'markdown',
                    'content': data['markdown']
                })
            
            # Check for errors/warnings
            if 'error' in data and data['error']:
                components.append({
                    'type': 'alert',
                    'renderer': 'alert',
                    'level': 'error',
                    'message': data['error']
                })
        
        # Handle string outputs (like summaries)
        elif isinstance(data, str) and len(data) > 20:
            components.append({
                'type': 'text_content',
                'renderer': 'text_content',
                'content': data,
                'title': 'Content',
            })
        
        # Handle list outputs
        elif isinstance(data, list) and data:
            # Check if list of dicts (table data)
            if isinstance(data[0], dict):
                components.append({
                    'type': 'table',
                    'renderer': 'table',
                    'data': data,
                    'columns': OutputAnalyzer._extract_columns(data)
                })
            else:
                # Simple list
                components.append({
                    'type': 'list',
                    'renderer': 'list',
                    'items': data
                })
        
        # Add raw JSON only when no overview card (avoids clutter for agent results)
        if not has_overview:
            components.append({
                'type': 'json',
                'renderer': 'json',
                'data': data,
                'collapsed': True,
                'title': 'Raw Data'
            })
        
        return components

    @staticmethod
    def _build_code_analysis_components(data: dict, operation: str) -> list:
        components = []
        if not isinstance(data, dict):
            return components

        # Header stats — include by_severity breakdown
        stats = []
        if data.get("by_severity") and isinstance(data["by_severity"], dict):
            for sev, count in data["by_severity"].items():
                if count > 0:
                    stats.append({"label": sev.upper(), "value": count, "format": "number"})
        if data.get("maintainability"):
            m = data["maintainability"]
            stats.append({"label": "Maintainability", "value": f"{m['score']}/100 ({m['grade']})", "format": "text"})
        if data.get("complexity"):
            c = data["complexity"]
            stats.append({"label": "Avg Complexity", "value": c["avg"], "format": "number"})
            stats.append({"label": "Max Complexity", "value": c["max"], "format": "number"})
        if data.get("lines"):
            stats.append({"label": "Lines of Code", "value": data["lines"]["code"], "format": "number"})
        if data.get("issue_count") is not None:
            stats.append({"label": "Total Issues", "value": data["issue_count"], "format": "number"})
        if data.get("evolution_priority"):
            stats.append({"label": "Evolution Priority", "value": data["evolution_priority"].upper(), "format": "text"})
        if stats:
            components.append({"type": "stats", "renderer": "stats", "metrics": stats, "title": data.get("file", "Code Analysis")})

        # Summary
        if data.get("summary"):
            components.append({"type": "text_content", "renderer": "text_content", "content": data["summary"], "title": "Summary"})

        # Issues table
        if data.get("issues") and isinstance(data["issues"], list):
            components.append({"type": "table", "renderer": "table", "data": data["issues"],
                                "title": f"Issues ({data.get('issue_count', len(data['issues']))})",
                                "columns": ["severity", "type", "message", "location"]})

        # Refactor candidates
        if data.get("refactor_candidates") and isinstance(data["refactor_candidates"], list):
            components.append({"type": "table", "renderer": "table", "data": data["refactor_candidates"],
                                "title": "Refactor Candidates", "columns": ["function", "reason", "suggestion"]})

        # Quick wins as list
        if data.get("quick_wins") and isinstance(data["quick_wins"], list):
            components.append({"type": "list", "renderer": "list", "items": data["quick_wins"], "title": "Quick Wins"})

        # High-complexity functions
        layers = data.get("layers", {})
        metrics = layers.get("metrics", data)
        if metrics.get("complexity", {}).get("high_complexity"):
            chart_data = [{"label": f["name"], "value": f["complexity"]}
                          for f in metrics["complexity"]["high_complexity"]]
            components.append({"type": "chart", "renderer": "chart_bar",
                                "data": chart_data, "title": "Function Complexity"})
            components.append({"type": "table", "renderer": "table",
                                "data": metrics["complexity"]["high_complexity"],
                                "title": "High Complexity Functions",
                                "columns": ["name", "complexity", "rank", "lineno"]})

        # Dependencies
        deps = layers.get("dependencies", data)
        if deps.get("external_packages"):
            components.append({"type": "list", "renderer": "list",
                                "items": deps["external_packages"], "title": "External Packages"})
        if deps.get("unused_imports"):
            components.append({"type": "list", "renderer": "list",
                                "items": deps["unused_imports"], "title": "Unused Imports"})

        # Risks
        if data.get("risks") and isinstance(data["risks"], list):
            components.append({"type": "list", "renderer": "list", "items": data["risks"], "title": "Risks"})

        return components

    @staticmethod
    def _build_health_components(data: dict, operation: str) -> list:
        components = []
        if not isinstance(data, dict):
            return components

        # Status badge + summary
        stats = []
        if data.get("status"):
            stats.append({"label": "Status", "value": data["status"].upper(), "format": "text"})
        layers = data.get("layers", {})
        system = layers.get("system", data)
        if system.get("cpu_percent") is not None:
            stats.append({"label": "CPU", "value": f"{system['cpu_percent']}%", "format": "text"})
        if system.get("memory"):
            m = system["memory"]
            stats.append({"label": "RAM", "value": f"{m['used_gb']}GB / {m['total_gb']}GB ({m['percent']}%)", "format": "text"})
        if system.get("gpu"):
            g = system["gpu"]
            stats.append({"label": "GPU", "value": f"{g['name']} {g['memory_used_mb']}MB/{g['memory_total_mb']}MB", "format": "text"})
        llm_rt = layers.get("llm_runtime", data)
        if llm_rt.get("ollama"):
            o = llm_rt["ollama"]
            stats.append({"label": "Ollama", "value": "Running" if o.get("running") else "NOT RUNNING", "format": "text"})
            if o.get("memory_gb"):
                stats.append({"label": "Ollama RAM", "value": f"{o['memory_gb']}GB", "format": "text"})
        if stats:
            components.append({"type": "stats", "renderer": "stats", "metrics": stats, "title": "System Health"})

        if data.get("summary"):
            components.append({"type": "text_content", "renderer": "text_content", "content": data["summary"], "title": "Diagnosis"})

        if data.get("bottlenecks") and isinstance(data["bottlenecks"], list):
            components.append({"type": "list", "renderer": "list", "items": data["bottlenecks"], "title": "Bottlenecks"})

        if data.get("actions") and isinstance(data["actions"], list):
            components.append({"type": "list", "renderer": "list", "items": data["actions"], "title": "Recommended Actions"})

        if data.get("warnings") and isinstance(data["warnings"], list):
            components.append({"type": "list", "renderer": "list", "items": data["warnings"], "title": "Warnings"})

        # Top processes table
        if system.get("top_processes"):
            components.append({"type": "table", "renderer": "table", "data": system["top_processes"],
                                "title": "Top Processes", "columns": ["name", "memory_mb", "cpu_pct", "pid"]})

        # Tool success rates
        agent = layers.get("agent_behavior", data)
        if agent.get("tool_success_rates"):
            chart_data = [{"label": k.split(".")[0], "value": round(v["success_rate"] * 100, 1)}
                          for k, v in agent["tool_success_rates"].items()]
            components.append({"type": "chart", "renderer": "chart_horizontal",
                                "data": chart_data, "title": "Tool Success Rates", "unit": "%"})
            rows = [{"tool": k, **v} for k, v in agent["tool_success_rates"].items()]
            components.append({"type": "table", "renderer": "table", "data": rows,
                                "title": "Tool Success Rates", "columns": ["tool", "total", "success_rate", "avg_ms"]})

        if agent.get("loop_detection"):
            components.append({"type": "table", "renderer": "table", "data": agent["loop_detection"],
                                "title": "Loop Detection", "columns": ["call", "count"]})

        # Pending queues
        internals = layers.get("cua_internals", data)
        if internals.get("pending_queues"):
            rows = [{"queue": k, "count": v} for k, v in internals["pending_queues"].items()]
            components.append({"type": "table", "renderer": "table", "data": rows,
                                "title": "Pending Queues", "columns": ["queue", "count"]})

        return components

    @staticmethod
    def _build_finance_components(data: dict, operation: str) -> list:
        components = []
        if not isinstance(data, dict):
            return components

        layers = data.get("layers", {})

        # Morning note specific fields
        if data.get("one_liner"):
            components.append({"type": "text_content", "renderer": "text_content",
                                "content": data["one_liner"], "title": f"Morning Note — {data.get('date', '')}"})
        if data.get("market_mood"):
            components.append({"type": "text_content", "renderer": "text_content",
                                "content": data["market_mood"], "title": "Market Mood"})
        if data.get("portfolio_snapshot"):
            components.append({"type": "text_content", "renderer": "text_content",
                                "content": data["portfolio_snapshot"], "title": "Portfolio Snapshot"})
        if data.get("watchlist") and isinstance(data["watchlist"], list):
            components.append({"type": "list", "renderer": "list",
                                "items": data["watchlist"], "title": "Watchlist"})
        if data.get("earnings_this_week") and isinstance(data["earnings_this_week"], dict) and data["earnings_this_week"]:
            rows = [{"ticker": t, **v} for t, v in data["earnings_this_week"].items()]
            components.append({"type": "table", "renderer": "table", "data": rows,
                                "title": "⚠ Earnings This Week", "columns": ["ticker", "earnings_date", "days_away"]})

        # Full report specific fields
        if data.get("executive_summary"):
            components.append({"type": "text_content", "renderer": "text_content",
                                "content": data["executive_summary"], "title": "Executive Summary"})
        if data.get("performance_vs_benchmark"):
            components.append({"type": "text_content", "renderer": "text_content",
                                "content": data["performance_vs_benchmark"], "title": "Performance vs Benchmark"})
        if data.get("holding_analysis") and isinstance(data["holding_analysis"], dict):
            rows = [{"ticker": t, **{k: v for k, v in d.items()}} for t, d in data["holding_analysis"].items() if isinstance(d, dict)]
            if rows:
                components.append({"type": "table", "renderer": "table", "data": rows,
                                    "title": "Holding Analysis", "columns": ["ticker", "trend", "valuation", "recommendation"]})
        if data.get("risk_assessment"):
            components.append({"type": "text_content", "renderer": "text_content",
                                "content": data["risk_assessment"], "title": "Risk Assessment"})
        if data.get("outlook"):
            components.append({"type": "text_content", "renderer": "text_content",
                                "content": data["outlook"], "title": "Outlook"})
        if data.get("markdown_report"):
            components.append({"type": "code", "renderer": "code",
                                "content": data["markdown_report"], "language": "markdown", "title": "Full Report (Markdown)"})

        # Rating badge for full report
        if data.get("rating"):
            components.append({"type": "stats", "renderer": "stats",
                                "metrics": [{"label": "Overall Rating", "value": data["rating"].upper(), "format": "text"}],
                                "title": "Report Rating"})

        # Macro snapshot
        macro = layers.get("macro", {})
        if macro:
            macro_stats = []
            for label, v in macro.items():
                if isinstance(v, dict) and v.get("value") is not None:
                    change_str = f" ({'+' if (v.get('change_pct') or 0) >= 0 else ''}{v.get('change_pct')}%)" if v.get('change_pct') is not None else ""
                    macro_stats.append({"label": label, "value": f"{v['value']}{change_str}", "format": "text"})
            if macro_stats:
                components.append({"type": "stats", "renderer": "stats",
                                    "metrics": macro_stats, "title": "Macro Snapshot"})

        # Insights, actions, risks, risk_flags — top level lists
        if data.get("insights") and isinstance(data["insights"], list):
            components.append({"type": "list", "renderer": "list", "items": data["insights"], "title": "Insights"})
        if data.get("actions") and isinstance(data["actions"], list):
            components.append({"type": "list", "renderer": "list", "items": data["actions"], "title": "Recommended Actions"})
        if data.get("recommendations") and isinstance(data["recommendations"], list):
            components.append({"type": "list", "renderer": "list", "items": data["recommendations"], "title": "Recommendations"})
        if data.get("risks") and isinstance(data["risks"], list):
            components.append({"type": "list", "renderer": "list", "items": data["risks"], "title": "Risks"})
        if data.get("risk_flags") and isinstance(data["risk_flags"], list):
            components.append({"type": "list", "renderer": "list", "items": data["risk_flags"], "title": "Risk Flags"})

        # Price data table
        price = layers.get("price_data", data.get("data", {}))
        if isinstance(price, dict):
            rows = []
            ohlcv_rows = []
            for ticker, info in price.items():
                if not isinstance(info, dict) or info.get("error"):
                    continue
                rows.append({
                    "ticker": ticker,
                    "price": info.get("current_price"),
                    "change_%": info.get("price_change_pct"),
                    "52w_high": info.get("high_52w"),
                    "52w_low": info.get("low_52w"),
                    "avg_volume": info.get("avg_volume"),
                    "pe_ratio": info.get("pe_ratio"),
                    "beta": info.get("beta"),
                    "sector": info.get("sector"),
                })
                # OHLCV tail as its own table
                if info.get("ohlcv_tail") and isinstance(info["ohlcv_tail"], list):
                    for row in info["ohlcv_tail"]:
                        ohlcv_rows.append({"ticker": ticker, **row})
            if rows:
                components.append({"type": "table", "renderer": "table", "data": rows,
                                    "title": "Price Overview",
                                    "columns": ["ticker", "price", "change_%", "52w_high", "52w_low", "avg_volume", "pe_ratio", "beta", "sector"]})
            if ohlcv_rows:
                components.append({"type": "table", "renderer": "table", "data": ohlcv_rows,
                                    "title": "Recent OHLCV",
                                    "columns": ["ticker", "Open", "High", "Low", "Close", "Volume"]})

        # Technicals table
        tech = layers.get("technicals", {})
        if tech:
            rows = []
            for t, d in tech.items():
                if isinstance(d, dict):
                    rows.append({
                        "ticker": t,
                        "price": d.get("current_price"),
                        "rsi": d.get("rsi"),
                        "rsi_signal": d.get("rsi_signal"),
                        "macd": d.get("macd"),
                        "macd_crossover": d.get("macd_crossover"),
                        "ma20": d.get("ma20"),
                        "ma50": d.get("ma50"),
                        "trend": d.get("trend"),
                        "bb_upper": d.get("bollinger_upper"),
                        "bb_lower": d.get("bollinger_lower"),
                        "bb_position": d.get("bollinger_position"),
                    })
            if rows:
                components.append({"type": "table", "renderer": "table", "data": rows,
                                    "title": "Technical Indicators",
                                    "columns": ["ticker", "price", "rsi", "rsi_signal", "macd", "macd_crossover", "trend", "bb_position"]})

        # Sentiment
        sentiment = layers.get("sentiment", {})
        if sentiment:
            for ticker, s in sentiment.items():
                if not isinstance(s, dict):
                    continue
                stats = [
                    {"label": "Sentiment", "value": s.get("sentiment", "").upper(), "format": "text"},
                    {"label": "Score", "value": s.get("score"), "format": "number"},
                ]
                components.append({"type": "stats", "renderer": "stats", "metrics": stats, "title": f"Sentiment — {ticker}"})
                if s.get("summary"):
                    components.append({"type": "text_content", "renderer": "text_content",
                                        "content": s["summary"], "title": "Sentiment Summary"})
                if s.get("headlines") and isinstance(s["headlines"], list):
                    components.append({"type": "list", "renderer": "list",
                                        "items": s["headlines"], "title": "Headlines"})

        # Portfolio metrics
        portfolio = layers.get("portfolio", {})
        if portfolio.get("sector_exposure_pct"):
            pie_data = [{"label": k, "value": v} for k, v in portfolio["sector_exposure_pct"].items()]
            components.append({"type": "chart", "renderer": "chart_donut",
                                "data": pie_data, "title": "Sector Exposure", "chartType": "donut", "unit": "%"})
            rows = [{"sector": k, "weight_%": v} for k, v in portfolio["sector_exposure_pct"].items()]
            components.append({"type": "table", "renderer": "table", "data": rows,
                                "title": "Sector Exposure", "columns": ["sector", "weight_%"]})
        stats = []
        if portfolio.get("sharpe_ratio") is not None:
            stats.append({"label": "Sharpe Ratio", "value": portfolio["sharpe_ratio"], "format": "number"})
        if portfolio.get("max_drawdown_pct") is not None:
            stats.append({"label": "Max Drawdown", "value": f"{portfolio['max_drawdown_pct']}%", "format": "text"})
        if portfolio.get("concentration_risk"):
            stats.append({"label": "Concentration Risk", "value": portfolio["concentration_risk"].upper(), "format": "text"})
        if stats:
            components.append({"type": "stats", "renderer": "stats", "metrics": stats, "title": "Portfolio Metrics"})

        return components

    @staticmethod
    def _build_result_overview(
        data: Any,
        tool_name: str,
        operation: str,
        preferred_renderer: Optional[str],
        summary: str,
        skill_name: str,
        category: str,
        output_types: List[str],
    ) -> Dict[str, Any]:
        title = skill_name.replace("_", " ").title() if skill_name else "Agent Result"
        highlights = []

        if isinstance(data, dict):
            if isinstance(data.get("sources"), list):
                highlights.append({"label": "Sources", "value": len(data["sources"])})
            if isinstance(data.get("links"), list):
                highlights.append({"label": "Links", "value": len(data["links"])})
            if isinstance(data.get("results"), list):
                highlights.append({"label": "Results", "value": len(data["results"])})
            if isinstance(data.get("logs"), list):
                highlights.append({"label": "Logs", "value": len(data["logs"])})
            if isinstance(data.get("executions"), list):
                highlights.append({"label": "Executions", "value": len(data["executions"])})
            if isinstance(data.get("performance"), list):
                highlights.append({"label": "Performance Rows", "value": len(data["performance"])})
            highlights.extend(OutputAnalyzer._extract_metrics(data)[:4])
        elif isinstance(data, list):
            highlights.append({"label": "Items", "value": len(data)})

        return {
            "type": "agent_result",
            "renderer": preferred_renderer or "agent_result",
            "title": title,
            "summary": "",  # already shown in message bubble
            "skill": skill_name,
            "category": category,
            "tool_name": tool_name,
            "operation": operation,
            "output_types": output_types,
            "highlights": highlights[:4],
        }
    
    @staticmethod
    def _extract_columns(data: List[Dict]) -> List[str]:
        """Extract column names from list of dicts"""
        if not data or not isinstance(data[0], dict):
            return []
        
        # Get all unique keys from first few items
        keys = set()
        for item in data[:5]:
            keys.update(item.keys())
        
        # Prioritize common columns
        priority = ['id', 'name', 'tool_name', 'operation', 'status', 'success', 'timestamp', 'error']
        ordered = [k for k in priority if k in keys]
        ordered.extend([k for k in sorted(keys) if k not in ordered])
        
        return ordered
    
    @staticmethod
    def _extract_metrics(data: Dict) -> List[Dict]:
        """Extract numeric metrics from data"""
        metrics = []
        
        # Look for common metric patterns
        metric_keys = ['count', 'total', 'success_rate', 'avg', 'min', 'max', 'duration']
        
        for key, value in data.items():
            if any(mk in key.lower() for mk in metric_keys):
                if isinstance(value, (int, float)):
                    metrics.append({
                        'label': key.replace('_', ' ').title(),
                        'value': value,
                        'format': 'percent' if 'rate' in key.lower() or 'percent' in key.lower() else 'number'
                    })
        
        return metrics
    
    @staticmethod
    def _detect_language(data: Dict) -> str:
        """Detect programming language from data"""
        if 'language' in data:
            return data['language']
        
        content = data.get('code') or data.get('patch', '')
        
        # Simple detection
        if 'def ' in content or 'import ' in content:
            return 'python'
        elif 'function ' in content or 'const ' in content:
            return 'javascript'
        elif '<?php' in content:
            return 'php'
        
        return 'text'
