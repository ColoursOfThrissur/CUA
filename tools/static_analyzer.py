"""
Static Analysis Tool - Find concrete issues for LLM to fix
Uses pylint, flake8, and custom patterns
"""
import subprocess
import re
from pathlib import Path
from typing import List, Dict, Optional

class StaticAnalyzer:
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path)
    
    def analyze_file(self, file_path: str) -> List[Dict]:
        """Analyze single file and return concrete issues"""
        issues = []
        
        # Run flake8 (lightweight, fast)
        issues.extend(self._run_flake8(file_path))
        
        # Custom pattern detection
        issues.extend(self._detect_patterns(file_path))
        
        return issues
    
    def _run_flake8(self, file_path: str) -> List[Dict]:
        """Run flake8 for code quality issues"""
        issues = []
        
        try:
            result = subprocess.run(
                ["flake8", file_path, "--max-line-length=120", "--ignore=E501,W503"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Parse flake8 output: file.py:line:col: CODE message
            for line in result.stdout.split('\n'):
                if not line.strip():
                    continue
                
                match = re.match(r'(.+):(\d+):(\d+): (\w+) (.+)', line)
                if match:
                    _, line_num, col, code, message = match.groups()
                    issues.append({
                        "file": file_path,
                        "line": int(line_num),
                        "column": int(col),
                        "code": code,
                        "message": message,
                        "severity": "medium" if code.startswith('E') else "low",
                        "tool": "flake8"
                    })
        except FileNotFoundError:
            # flake8 not installed - skip
            pass
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass
        
        return issues
    
    def _detect_patterns(self, file_path: str) -> List[Dict]:
        """Detect common code issues with pattern matching"""
        issues = []
        
        try:
            content = Path(file_path).read_text(encoding='utf-8')
            lines = content.split('\n')
            
            for i, line in enumerate(lines, 1):
                # Hardcoded paths
                if re.search(r'["\'](?:/|C:\\\\)[^"\']+["\']', line) and 'test' not in file_path.lower():
                    if not any(x in line for x in ['__file__', 'Path(', 'os.path']):
                        issues.append({
                            "file": file_path,
                            "line": i,
                            "code": "HARDCODED_PATH",
                            "message": "Hardcoded file path - should use config or Path",
                            "severity": "medium",
                            "tool": "pattern"
                        })
                
                # Print statements (should use logger)
                if re.search(r'\bprint\s*\(', line) and 'logger' not in content[:content.find(line)]:
                    if 'core/' in file_path or 'updater/' in file_path:
                        issues.append({
                            "file": file_path,
                            "line": i,
                            "code": "PRINT_STATEMENT",
                            "message": "Use logger instead of print in core modules",
                            "severity": "low",
                            "tool": "pattern"
                        })
                
                # Missing error handling
                if 'open(' in line and 'with' not in line:
                    issues.append({
                        "file": file_path,
                        "line": i,
                        "code": "MISSING_CONTEXT_MANAGER",
                        "message": "Use 'with open()' for automatic file closing",
                        "severity": "medium",
                        "tool": "pattern"
                    })
                
                # Bare except
                if re.match(r'\s*except\s*:', line):
                    issues.append({
                        "file": file_path,
                        "line": i,
                        "code": "BARE_EXCEPT",
                        "message": "Bare except catches all exceptions - specify exception type",
                        "severity": "high",
                        "tool": "pattern"
                    })
                
                # SQL injection risk
                if 'execute(' in line and ('+' in line or 'f"' in line or "f'" in line):
                    if 'sql' in line.lower() or 'query' in line.lower():
                        issues.append({
                            "file": file_path,
                            "line": i,
                            "code": "SQL_INJECTION",
                            "message": "Potential SQL injection - use parameterized queries",
                            "severity": "critical",
                            "tool": "pattern"
                        })
        
        except Exception:
            pass
        
        return issues
    
    def get_top_issues(self, max_issues: int = 5) -> List[Dict]:
        """Get top priority issues across codebase"""
        all_issues = []
        
        # Scan core and tools directories
        for directory in ['core', 'tools', 'updater']:
            dir_path = self.repo_path / directory
            if not dir_path.exists():
                continue
            
            for py_file in dir_path.glob('*.py'):
                if py_file.name.startswith('_'):
                    continue
                issues = self.analyze_file(str(py_file))
                all_issues.extend(issues)
        
        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_issues.sort(key=lambda x: severity_order.get(x['severity'], 4))
        
        return all_issues[:max_issues]
    
    def format_for_llm(self, issues: List[Dict]) -> str:
        """Format issues for LLM prompt"""
        if not issues:
            return "No issues found"
        
        formatted = "## Concrete Issues Found:\n\n"
        for i, issue in enumerate(issues, 1):
            formatted += f"{i}. **{issue['file']}:{issue['line']}** [{issue['severity'].upper()}]\n"
            formatted += f"   - Code: {issue['code']}\n"
            formatted += f"   - Issue: {issue['message']}\n\n"
        
        return formatted
