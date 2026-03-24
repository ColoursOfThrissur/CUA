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
