"""
Task Analyzer - Two-stage analysis for feature-focused improvements
"""
import json
import re
from typing import Optional, Dict, List
from pathlib import Path

class TaskAnalyzer:
    def __init__(self, llm_client, system_analyzer, llm_logger):
        self.llm_client = llm_client
        self.analyzer = system_analyzer
        self.llm_logger = llm_logger
        self.static_analyzer = None
        
        # Feature tracking and gap analysis
        from core.feature_tracker import FeatureTracker
        from core.feature_gap_analyzer import FeatureGapAnalyzer
        self.feature_tracker = FeatureTracker()
        self.gap_analyzer = FeatureGapAnalyzer()
        
        try:
            from tools.static_analyzer import StaticAnalyzer
            self.static_analyzer = StaticAnalyzer()
        except ImportError:
            pass
    
    def analyze_and_propose_tasks(
        self, 
        focus: Optional[str] = None,
        failed_suggestions: List[str] = None,
        iteration_history: List[Dict] = None,
        excluded_files: List[str] = None
    ) -> List[Dict]:
        """Two-stage analysis with retry on rejection"""
        # User focus is used as guidance but LLM still selects file
        from core.logging_system import get_logger
        logger = get_logger("task_analyzer")
        if focus:
            logger.info(f"User focus provided: {focus[:60]}")
        
        context = self.analyzer.get_codebase_context()
        test_files = context['test_coverage']['test_files']
        
        tools_info = self._get_tools_info(test_files)
        
        if not tools_info:
            from core.logging_system import get_logger
            logger = get_logger("task_analyzer")
            logger.warning("No tools found for analysis")
            return []
        
        static_issues = []
        if self.static_analyzer:
            try:
                static_issues = self.static_analyzer.get_top_issues(max_issues=3)
            except Exception:
                pass
        
        repeated_count = self._count_repeated_tasks(iteration_history or [])
        blocked_tasks = self._extract_blocked_tasks(iteration_history or [])
        
        # Add excluded files to blocked tasks
        if excluded_files:
            blocked_tasks.extend(excluded_files)
        
        # RETRY LOOP: Try up to 3 times to find valid task
        for attempt in range(3):
            # STAGE 1: Discovery (always run to select file)
            selected_tool = self._analyze_stage1_discovery(
                tools_info, focus, blocked_tasks, static_issues, repeated_count
            )
            
            if not selected_tool:
                if static_issues:
                    return self._fallback_to_static_issues(static_issues, blocked_tasks)
                return []
            
            # STAGE 2: Implementation
            task = self._analyze_stage2_implementation(
                selected_tool, tools_info, test_files, focus, blocked_tasks
            )
            
            if task:
                return [task]
            
            # Stage 2 rejected - add to blocked for next retry
            rejected_file = selected_tool['target_file']
            blocked_tasks.append(rejected_file)
            
            from core.logging_system import get_logger
            logger = get_logger("task_analyzer")
            logger.info(f"Attempt {attempt+1}: Rejected {rejected_file}, blocked_tasks now: {len(blocked_tasks)}")
        
        # All 3 attempts failed
        from core.logging_system import get_logger
        logger = get_logger("task_analyzer")
        logger.info(f"All 3 attempts exhausted, no valid tasks found")
        return []
    
    def _analyze_stage1_discovery(
        self, tools_info, focus, blocked_tasks, static_issues, repeated_count
    ) -> Optional[Dict]:
        """Stage 1: Score tools and let LLM pick from top candidates"""
        from core.logging_system import get_logger
        logger = get_logger("task_analyzer")
        
        # Score and filter tools
        scored_tools = self._score_tools(tools_info, blocked_tasks)
        if not scored_tools:
            return None
        
        # Get top 3 candidates
        top_candidates = scored_tools[:3]
        
        # Build prompt with only top candidates
        tool_list = []
        for tool, score in top_candidates:
            tool_list.append(f"- {tool['file']} (score: {score}, has_test: {tool['has_test']})")
        
        tools_text = '\n'.join(tool_list)
        focus_section = f"\n\n## USER REQUEST:\n{focus}\n" if focus else ""
        
        if focus:
            prompt_text = f"""Pick ONE tool file that matches the user's request:
{focus_section}
## Top Candidates (pre-filtered):
{tools_text}

CRITICAL: Prioritize the file that best matches the USER REQUEST above.
If user mentions "file tool" or "filesystem", pick enhanced_filesystem_tool.py
If user mentions "http" or "web", pick http_tool.py
If user mentions "shell" or "command", pick shell_tool.py

Output JSON:
{{
  "target_file": "tools/xxx.py",
  "reasoning": "This matches the user's request because..."
}}"""
        else:
            prompt_text = f"""Pick ONE tool file from these top candidates:

## Top Candidates (pre-filtered):
{tools_text}

These are the best candidates based on:
- Missing tests
- Low feature count
- Need for improvement

Pick the one that would benefit most from a new feature.

Output JSON:
{{
  "target_file": "tools/xxx.py",
  "reasoning": "This tool needs improvement because..."
}}"""
        
        prompt = self.llm_client._format_prompt(prompt_text, expect_json=True)
        temperature = 0.7 if repeated_count >= 3 else 0.4
        
        try:
            response = self.llm_client._call_llm(prompt, temperature=temperature, expect_json=True)
            self.llm_logger.log_interaction(prompt=prompt, response=response or "<empty>",
                metadata={"phase": "stage1_discovery", "temperature": temperature})
            
            if not response:
                return None
            
            selection = self.llm_client._extract_json(response)
            if not selection or 'target_file' not in selection:
                return None
            
            target_file = selection['target_file']
            if self._is_blocked(target_file, blocked_tasks) or self._is_protected(target_file):
                return None
            
            logger.info(f"Stage 1: Selected {target_file}")
            return selection
        except Exception as e:
            logger.error(f"Stage 1 failed: {e}")
            return None
    
    def _analyze_stage2_implementation(
        self, selected_tool, tools_info, test_files, focus, blocked_tasks
    ) -> Optional[Dict]:
        """Stage 2: Analyze gaps and suggest specific feature from highest priority category"""
        from core.logging_system import get_logger
        logger = get_logger("task_analyzer")
        
        target_file = selected_tool['target_file']
        
        # Get FULL file content
        full_content = self.analyzer.get_file_content(target_file)
        if not full_content:
            return None
        
        # Get covered categories and analyze gaps
        covered_categories = self.feature_tracker.get_covered_categories(target_file)
        priority_category, suggestions = self.gap_analyzer.get_priority_gap(
            target_file, full_content, covered_categories
        )
        
        if not priority_category:
            logger.info(f"{target_file} is feature-complete (all categories covered)")
            return None
        
        logger.info(f"{target_file}: Priority gap = {priority_category}, suggestions = {len(suggestions)}")
        
        # EARLY FILTER: Remove suggestions that are already implemented
        from core.feature_deduplicator import FeatureDeduplicator
        dedup = FeatureDeduplicator()
        
        filtered_suggestions = []
        for suggestion in suggestions:
            is_dup, reason = dedup.is_duplicate(target_file, suggestion, [])
            if not is_dup:
                filtered_suggestions.append(suggestion)
            else:
                logger.info(f"Pre-filtered duplicate: {suggestion[:60]} - {reason}")
        
        if not filtered_suggestions:
            logger.info(f"All suggestions in {priority_category} already implemented")
            return None
        
        suggestions = filtered_suggestions
        
        # Get test file for reference
        import os
        file_basename = os.path.basename(target_file)
        test_file_name = f"test_{file_basename}"
        test_content = ""
        for tf in test_files:
            if test_file_name in tf:
                test_path = f"tests/unit/{tf}"
                test_content = self.analyzer.get_file_content(test_path) or ""
                break
        
        # Get already added features
        added_features = self.feature_tracker.get_added_features(target_file)
        added_features_text = "\n".join([f"- {f}" for f in added_features]) if added_features else "None"
        
        # Build prompt with gap analysis
        suggestions_text = "\n".join([f"- {s}" for s in suggestions])
        
        # Build user focus section
        focus_section = ""
        if focus:
            focus_section = f"\n\n## USER REQUEST:\n{focus}\n\nCRITICAL: Your suggestion MUST align with the user's request above. Interpret their intent and pick the most relevant feature.\n"
        
        prompt_text = f"""Analyze this tool and suggest ONE specific feature to add.

File: {target_file}
Maturity: {selected_tool.get('maturity', 'unknown')}
{focus_section}
COMPLETE CODE:
```python
{full_content}
```

Tests:
```python
{test_content[:1000] if test_content else "No tests yet"}
```

FEATURES ALREADY ADDED:
{added_features_text}

PRIORITY GAP: {priority_category}
SUGGESTED FEATURES (pre-filtered, NOT already implemented):
{suggestions_text}

CRITICAL:
1. Pick ONE feature from the suggested list above
2. These suggestions are already verified as NOT implemented
3. Provide specific implementation details
4. If you believe ALL suggestions are already implemented despite filtering, set already_implemented=true

JSON output:
{{
  "task_type": "add_feature",
  "target_file": "{target_file}",
  "test_file": "tests/unit/{test_file_name}",
  "description": "Add timeout parameter to all HTTP methods",
  "category": "{priority_category}",
  "methods_to_modify": ["_get", "_post"],
  "priority": "high",
  "already_implemented": false
}}
"""
        
        prompt = self.llm_client._format_prompt(prompt_text, expect_json=True)
        
        try:
            response = self.llm_client._call_llm(prompt, temperature=0.3, expect_json=True)
            self.llm_logger.log_interaction(prompt=prompt, response=response or "<empty>",
                metadata={"phase": "stage2_implementation"})
            
            if not response:
                return None
            
            task_data = self.llm_client._extract_json(response)
            if not task_data or 'description' not in task_data:
                return None
            
            # Check if already implemented
            if task_data.get('already_implemented', False):
                logger.info(f"All features in {priority_category} category already implemented")
                return None
            
            # Double-check with deduplicator
            from core.feature_deduplicator import FeatureDeduplicator
            dedup = FeatureDeduplicator()
            is_dup, reason = dedup.is_duplicate(
                target_file,
                task_data.get('description', ''),
                task_data.get('methods_to_modify', [])
            )
            if is_dup:
                logger.info(f"Duplicate feature detected: {reason}")
                return None
            
            # SANITY CHECK: Does feature make sense for this tool?
            if not self._sanity_check_feature(target_file, task_data.get('description', ''), full_content):
                logger.info(f"Feature doesn't make sense for {target_file}")
                return None
            
            # Ensure required fields
            if 'methods_to_modify' not in task_data:
                task_data['methods_to_modify'] = []
            if 'category' not in task_data:
                task_data['category'] = priority_category
            
            logger.info(f"Stage 2: Created task for {target_file} - {task_data['description'][:60]}")
            return self._interpret_task(task_data, focus)
        except Exception as e:
            logger.error(f"Stage 2 failed: {e}")
            return None
    
    def _get_tool_signatures(self, tools_info: List[Dict]) -> str:
        """Extract method signatures with docstrings"""
        from core.method_extractor import MethodExtractor
        extractor = MethodExtractor()
        
        signatures = []
        for tool in tools_info:
            content = self.analyzer.get_file_content(tool['file'])
            if not content:
                continue
            
            methods = extractor.extract_methods(content)
            class_name = tool['class']
            
            sig_lines = [f"### {tool['file']}", f"class {class_name}:"]
            for method_name, method_info in methods.items():
                # Extract docstring if exists
                code = method_info['code']
                docstring = ""
                if '"""' in code:
                    start = code.find('"""') + 3
                    end = code.find('"""', start)
                    if end != -1:
                        docstring = code[start:end].strip().split('\n')[0][:60]
                
                if docstring:
                    sig_lines.append(f"    def {method_name}(...):  # {docstring}")
                else:
                    sig_lines.append(f"    def {method_name}(...)")
            
            signatures.append("\n".join(sig_lines))
        
        return "\n\n".join(signatures)
    
    def _is_blocked(self, target_file: str, blocked_tasks: List[str]) -> bool:
        for blocked in blocked_tasks:
            blocked_file = blocked.split('(')[0].strip() if '(' in blocked else blocked.strip()
            if target_file == blocked_file:
                return True
        return False
    
    def _is_protected(self, target_file: str) -> bool:
        from core.config_manager import get_config
        protected_files = get_config().improvement.protected_files
        normalized = target_file.replace('\\', '/')
        return any(p in normalized for p in protected_files)
    
    def _get_tools_info(self, test_files: List[str]) -> List[Dict]:
        tools_info = []
        tools_dir = self.analyzer.repo_path / "tools"
        
        if not tools_dir.exists():
            return tools_info
        
        for tool_file in tools_dir.glob("*.py"):
            if tool_file.name.startswith("_"):
                continue
            
            content = self.analyzer.get_file_content(f"tools/{tool_file.name}")
            if not content or 'class ' not in content:
                continue
            
            class_match = re.search(r'class (\w+)', content)
            class_name = class_match.group(1) if class_match else "Unknown"
            
            # Count methods
            method_count = len(re.findall(r'\n    def ', content))
            
            tools_info.append({
                "file": f"tools/{tool_file.name}",
                "class": class_name,
                "has_test": f"test_{tool_file.stem}.py" in test_files,
                "method_count": method_count
            })
        
        return tools_info
    
    def _score_tools(self, tools_info: List[Dict], blocked_tasks: List[str]) -> List[tuple]:
        """Score tools by maturity and cooldown - focus on immature tools"""
        from core.logging_system import get_logger
        logger = get_logger("task_analyzer")
        
        scored = []
        current_iteration = self.feature_tracker.current_iteration
        
        for tool in tools_info:
            file = tool['file']
            
            # Skip blocked
            if self._is_blocked(file, blocked_tasks):
                continue
            if self._is_protected(file):
                continue
            
            # Check cooldown with category awareness
            in_cooldown, cooldown_until = self.feature_tracker.is_in_cooldown(file, current_iteration, None)
            if in_cooldown:
                logger.info(f"Skipping {file} (cooldown until iteration {cooldown_until})")
                continue
            
            # Calculate maturity score
            maturity_level, priority_score = self.feature_tracker.get_file_maturity(
                file, tool['method_count']
            )
            
            # Bonus for missing tests
            if not tool['has_test']:
                priority_score += 10
            
            tool['maturity'] = maturity_level
            scored.append((tool, priority_score))
            
            logger.info(f"{file}: maturity={maturity_level}, score={priority_score}")
        
        # Sort by score descending (higher score = higher priority)
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    
    def _count_repeated_tasks(self, iteration_history: List[Dict]) -> int:
        if len(iteration_history) < 2:
            return 0
        recent_files = [h.get('file', '') for h in iteration_history[-5:]]
        if not recent_files:
            return 0
        from collections import Counter
        counts = Counter(recent_files)
        return max(counts.values()) if counts else 0
    
    def _extract_blocked_tasks(self, iteration_history: List[Dict]) -> List[str]:
        """Block files only in current session (last 5 iterations)"""
        blocked = []
        
        # Only look at recent history (last 5 iterations)
        recent = iteration_history[-5:] if len(iteration_history) > 5 else iteration_history
        
        file_attempts = {}
        for h in recent:
            file = h.get('file', '')
            if not file:
                continue
            
            file_attempts[file] = file_attempts.get(file, 0) + 1
        
        # Block files attempted 2+ times in recent history
        for file, count in file_attempts.items():
            if count >= 2:
                blocked.append(file)
        
        return blocked
    
    def _interpret_task(self, analysis: Dict, focus: Optional[str]) -> Optional[Dict]:
        target = analysis.get('target_file')
        if not target:
            return None
        
        import os
        target = target.replace('/', os.sep).replace('\\', os.sep)
        
        if not (self.analyzer.repo_path / target).exists():
            return None
        
        return {
            "issue": focus if focus else analysis.get('description', 'Feature improvement'),
            "suggestion": focus if focus else analysis.get('description', 'Feature improvement'),
            "priority": analysis.get('priority', 'high' if focus else 'medium'),
            "user_override": bool(focus),
            "files_affected": [target],
            "methods_to_modify": analysis.get('methods_to_modify', []),
            "test_file": analysis.get('test_file', ''),
            "task_type": analysis.get('task_type', 'improve_code'),
            "category": analysis.get('category', 'core')  # Add category for tracking
        }
    
    def _fallback_to_static_issues(self, static_issues: List[Dict], blocked_tasks: List[str]) -> List[Dict]:
        """Fallback: use static analyzer issues if two-stage fails"""
        from core.logging_system import get_logger
        logger = get_logger("task_analyzer")
        
        from core.config_manager import get_config
        protected_files = get_config().improvement.protected_files
        
        for issue in static_issues:
            file_path = issue['file']
            issue_key = f"{file_path}::{issue['code']}::{issue['line']}"
            
            # Skip protected and blocked
            if any(p in file_path.replace('\\', '/') for p in protected_files):
                continue
            if self._is_blocked(file_path, blocked_tasks):
                continue
            # Skip if this exact issue was blocked
            if any(issue_key in blocked for blocked in blocked_tasks):
                continue
            
            logger.info(f"Fallback: Using static issue in {file_path}")
            return [{
                "issue": issue['message'],
                "suggestion": f"Fix {issue['code']} at line {issue['line']}: {issue['message']}",
                "priority": "medium",
                "user_override": False,
                "files_affected": [file_path]
            }]
        
        return []
    
    def _sanity_check_feature(self, target_file: str, description: str, file_content: str) -> bool:
        """Check if feature makes sense for this tool"""
        desc_lower = description.lower()
        
        # Shell tool specific checks
        if 'shell_tool' in target_file:
            # Shell commands are stateless - caching doesn't make sense
            if 'caching' in desc_lower or 'cache' in desc_lower:
                if 'subprocess.run' in file_content and 'pwd' in file_content:
                    return False
            # Shell tool uses subprocess.run which is synchronous - async doesn't help
            if 'async' in desc_lower or 'await' in desc_lower:
                return False
        
        # HTTP tool specific checks
        if 'http_tool' in target_file:
            # Don't add features that already exist
            if 'timeout' in desc_lower and 'timeout=' in file_content:
                return False
        
        # File tool specific checks
        if 'file' in target_file and 'tool' in target_file:
            # Don't add path validation if it already exists
            if 'path validation' in desc_lower and '_validate_path' in file_content:
                return False
        
        return True
