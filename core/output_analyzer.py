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

        if preferred_renderer or summary or skill_name:
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
            # Check for web research outputs
            if 'url' in data and ('content' in data or 'summary' in data or 'text' in data):
                components.append({
                    'type': 'web_content',
                    'renderer': 'web_content',
                    'url': data['url'],
                    'title': data.get('title', 'Web Content'),
                    'content': data.get('content') or data.get('summary') or data.get('text', ''),
                    'summary': data.get('summary', ''),
                })
            
            # Check for summarized text content
            if 'summary' in data or 'text' in data:
                content = data.get('summary') or data.get('text')
                if isinstance(content, str) and len(content) > 50:
                    components.append({
                        'type': 'text_content',
                        'renderer': 'text_content',
                        'content': content,
                        'title': data.get('title', 'Summary'),
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
            if 'image' in data or 'image_url' in data:
                components.append({
                    'type': 'image',
                    'renderer': 'image',
                    'url': data.get('image_url') or data.get('image'),
                    'alt': data.get('image_alt', 'Generated image')
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
        
        # Always add raw JSON as collapsible fallback
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
            "summary": summary or "Task completed.",
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
