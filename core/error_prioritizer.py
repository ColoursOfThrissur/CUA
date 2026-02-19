"""
Error-Based Prioritization - Analyzes logs to prioritize files for improvement
"""
import re
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Tuple
import json

class ErrorPrioritizer:
    def __init__(self, logs_dir: str = "logs"):
        self.logs_dir = Path(logs_dir)
        self.error_patterns = {
            'exception': r'(Exception|Error):\s*(.+)',
            'traceback': r'File "(.+?)", line (\d+)',
            'failed_test': r'FAILED\s+(.+?)::',
            'import_error': r'ImportError:\s*(.+)',
            'syntax_error': r'SyntaxError:\s*(.+)'
        }
    
    def analyze_logs(self, days: int = 7) -> Dict[str, Dict]:
        """Analyze recent logs and extract error patterns"""
        errors_by_file = defaultdict(lambda: {
            'count': 0,
            'error_types': Counter(),
            'recent_errors': []
        })
        
        # Scan log files
        for log_file in self.logs_dir.rglob("*.log"):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self._extract_errors(content, errors_by_file)
            except Exception as e:
                print(f"Error reading {log_file}: {e}")
        
        # Scan LLM logs
        llm_logs_dir = self.logs_dir / "llm"
        if llm_logs_dir.exists():
            for log_file in llm_logs_dir.glob("errors_*.jsonl"):
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip():
                                error_data = json.loads(line)
                                self._process_llm_error(error_data, errors_by_file)
                except Exception as e:
                    print(f"Error reading {log_file}: {e}")
        
        return dict(errors_by_file)
    
    def _extract_errors(self, content: str, errors_by_file: dict):
        """Extract errors from log content"""
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            # Check for traceback
            traceback_match = re.search(self.error_patterns['traceback'], line)
            if traceback_match:
                file_path = traceback_match.group(1)
                line_num = traceback_match.group(2)
                
                # Look ahead for error type
                error_type = "Unknown"
                for j in range(i, min(i + 5, len(lines))):
                    error_match = re.search(self.error_patterns['exception'], lines[j])
                    if error_match:
                        error_type = error_match.group(1)
                        break
                
                errors_by_file[file_path]['count'] += 1
                errors_by_file[file_path]['error_types'][error_type] += 1
                errors_by_file[file_path]['recent_errors'].append({
                    'line': line_num,
                    'type': error_type
                })
    
    def _process_llm_error(self, error_data: dict, errors_by_file: dict):
        """Process LLM error log entry"""
        if 'error' in error_data:
            # Extract file info if available
            error_msg = error_data.get('error', '')
            file_match = re.search(r'File "(.+?)"', error_msg)
            if file_match:
                file_path = file_match.group(1)
                errors_by_file[file_path]['count'] += 1
                errors_by_file[file_path]['error_types']['LLM Error'] += 1
    
    def get_priority_files(self, max_files: int = 5) -> List[Tuple[str, int]]:
        """Get prioritized list of files to improve"""
        errors = self.analyze_logs()
        
        # Sort by error count
        sorted_files = sorted(
            errors.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )
        
        # Filter to actual project files
        priority_files = []
        for file_path, data in sorted_files[:max_files * 2]:
            # Skip external libraries
            if 'site-packages' in file_path or 'venv' in file_path:
                continue
            
            # Convert to relative path if possible
            try:
                rel_path = Path(file_path).relative_to(Path.cwd())
                priority_files.append((str(rel_path), data['count']))
            except ValueError:
                priority_files.append((file_path, data['count']))
            
            if len(priority_files) >= max_files:
                break
        
        return priority_files
    
    def get_error_context(self, file_path: str) -> Dict:
        """Get detailed error context for a specific file"""
        errors = self.analyze_logs()
        return errors.get(file_path, {
            'count': 0,
            'error_types': Counter(),
            'recent_errors': []
        })
