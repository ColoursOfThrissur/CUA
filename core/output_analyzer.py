"""Output Analyzer - Analyzes tool outputs and suggests UI components"""
from typing import Dict, List, Any, Optional


class OutputAnalyzer:
    """Analyzes tool output and generates UI component specifications"""
    
    @staticmethod
    def analyze(data: Any, tool_name: str = "", operation: str = "") -> List[Dict]:
        """
        Analyze output and return list of UI components to render
        
        Returns:
            List of component specs: [{"type": "table", "data": [...], ...}]
        """
        components = []
        
        if not data:
            return components
        
        # Handle dict outputs
        if isinstance(data, dict):
            # Check for table data (list of dicts with consistent keys)
            if 'executions' in data and isinstance(data['executions'], list):
                components.append({
                    'type': 'table',
                    'data': data['executions'],
                    'title': f'{tool_name} Executions',
                    'columns': OutputAnalyzer._extract_columns(data['executions'])
                })
            
            if 'performance' in data and isinstance(data['performance'], list):
                components.append({
                    'type': 'table',
                    'data': data['performance'],
                    'title': 'Performance Metrics',
                    'columns': OutputAnalyzer._extract_columns(data['performance'])
                })
            
            if 'logs' in data and isinstance(data['logs'], list):
                components.append({
                    'type': 'logs',
                    'data': data['logs'],
                    'title': 'System Logs'
                })
            
            # Check for metrics/stats
            metrics = OutputAnalyzer._extract_metrics(data)
            if metrics:
                components.append({
                    'type': 'stats',
                    'metrics': metrics
                })
            
            # Check for code/patches
            if 'code' in data or 'patch' in data:
                components.append({
                    'type': 'code',
                    'content': data.get('code') or data.get('patch'),
                    'language': OutputAnalyzer._detect_language(data)
                })
            
            # Check for images
            if 'image' in data or 'image_url' in data:
                components.append({
                    'type': 'image',
                    'url': data.get('image_url') or data.get('image'),
                    'alt': data.get('image_alt', 'Generated image')
                })
            
            # Check for markdown
            if 'markdown' in data:
                components.append({
                    'type': 'markdown',
                    'content': data['markdown']
                })
            
            # Check for errors/warnings
            if 'error' in data and data['error']:
                components.append({
                    'type': 'alert',
                    'level': 'error',
                    'message': data['error']
                })
        
        # Handle list outputs
        elif isinstance(data, list) and data:
            # Check if list of dicts (table data)
            if isinstance(data[0], dict):
                components.append({
                    'type': 'table',
                    'data': data,
                    'columns': OutputAnalyzer._extract_columns(data)
                })
            else:
                # Simple list
                components.append({
                    'type': 'list',
                    'items': data
                })
        
        # Always add raw JSON as collapsible fallback
        components.append({
            'type': 'json',
            'data': data,
            'collapsed': True,
            'title': 'Raw Data'
        })
        
        return components
    
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
