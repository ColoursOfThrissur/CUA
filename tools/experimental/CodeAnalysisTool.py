"""
CodeAnalysisTool — structural code analysis for Python files and modules.

5 layers (Sourcery + CodeRabbit + Radon inspired):
  1. File metrics    — complexity, maintainability index, lines, comment ratio (radon)
  2. Issue detection — dead code, long functions, bare excepts, too many params (AST)
  3. Dependencies    — imports graph, unused imports, circular deps, external ratio
  4. Change impact   — what else in CUA depends on this file, test coverage exists?
  5. LLM advisor     — structured numbers → specific refactor candidates + rewrites
"""
import ast
import os
import re
from pathlib import Path
from typing import Optional
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel


class CodeAnalysisTool(BaseTool):
    """Structural code analysis: complexity, issues, dependencies, change impact, LLM advisor."""

    def __init__(self, orchestrator=None):
        self.description = "Analyse Python code for complexity, issues, dependencies, and change impact. Feeds the evolution pipeline with structured metrics."
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        self.add_capability(ToolCapability(
            name="get_file_metrics",
            description="Cyclomatic complexity, maintainability index (0-100), lines of code, comment ratio, and function-level breakdown for a Python file.",
            parameters=[
                Parameter("file_path", ParameterType.STRING, "Path to Python file", required=True),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["radon"]
        ), self._handle_get_file_metrics)

        self.add_capability(ToolCapability(
            name="detect_issues",
            description="AST-based issue detection: dead code, long functions (>50 lines), too many params (>5), bare excepts, missing return types, duplicate logic patterns.",
            parameters=[
                Parameter("file_path", ParameterType.STRING, "Path to Python file", required=True),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=[]
        ), self._handle_detect_issues)

        self.add_capability(ToolCapability(
            name="get_dependencies",
            description="Import graph for a file: what it imports, unused imports, external vs internal ratio, circular dependency check within CUA.",
            parameters=[
                Parameter("file_path", ParameterType.STRING, "Path to Python file", required=True),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=[]
        ), self._handle_get_dependencies)

        self.add_capability(ToolCapability(
            name="get_change_impact",
            description="What other CUA files import this module, whether a test file exists, and which tool registry entries reference it.",
            parameters=[
                Parameter("file_path", ParameterType.STRING, "Path to Python file", required=True),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=[]
        ), self._handle_get_change_impact)

        self.add_capability(ToolCapability(
            name="get_code_review",
            description="Full code review: runs all 4 layers then LLM advisor gives refactor candidates, specific rewrites, and evolution priority score.",
            parameters=[
                Parameter("file_path", ParameterType.STRING, "Path to Python file", required=True),
                Parameter("context", ParameterType.STRING, "Optional context e.g. 'this tool keeps failing on get_price_data'", required=False, default=""),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["radon"]
        ), self._handle_get_code_review)

    def execute(self, operation: str, **kwargs) -> ToolResult:
        return self.execute_capability(operation, **kwargs)

    # ── Layer 1: File Metrics ─────────────────────────────────────────────────

    def _handle_get_file_metrics(self, **kwargs) -> dict:
        file_path = kwargs.get("file_path", "")
        path = self._resolve_path(file_path)
        if not path:
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            source = path.read_text(encoding="utf-8")
        except Exception as e:
            return {"success": False, "error": str(e)}

        try:
            from radon.complexity import cc_visit, cc_rank
            from radon.metrics import mi_visit
            from radon.raw import analyze
        except ImportError:
            return {"success": False, "error": "radon not installed. Run: pip install radon"}

        try:
            raw = analyze(source)
            mi = mi_visit(source, multi=True)
            cc_results = cc_visit(source)

            # Per-function complexity
            functions = []
            for block in sorted(cc_results, key=lambda b: b.complexity, reverse=True):
                functions.append({
                    "name": block.name,
                    "type": block.type,
                    "complexity": block.complexity,
                    "rank": cc_rank(block.complexity),
                    "lines": block.endline - block.lineno + 1 if hasattr(block, "endline") else None,
                    "lineno": block.lineno,
                })

            avg_complexity = round(sum(f["complexity"] for f in functions) / len(functions), 2) if functions else 0
            max_complexity = functions[0]["complexity"] if functions else 0

            # Maintainability grade
            mi_score = round(mi, 1)
            if mi_score >= 85:
                mi_grade = "A"
            elif mi_score >= 65:
                mi_grade = "B"
            elif mi_score >= 45:
                mi_grade = "C"
            else:
                mi_grade = "D"

            return {
                "success": True,
                "file": str(path),
                "lines": {
                    "total": raw.loc + raw.comments + raw.blank,
                    "code": raw.loc,
                    "comments": raw.comments,
                    "blank": raw.blank,
                    "comment_ratio": round(raw.comments / max(raw.loc, 1), 2),
                },
                "maintainability": {
                    "score": mi_score,
                    "grade": mi_grade,
                    "interpretation": {"A": "highly maintainable", "B": "maintainable",
                                       "C": "moderate debt", "D": "high debt"}[mi_grade],
                },
                "complexity": {
                    "avg": avg_complexity,
                    "max": max_complexity,
                    "total_functions": len(functions),
                    "high_complexity": [f for f in functions if f["complexity"] >= 10],
                },
                "functions": functions[:20],  # top 20 by complexity
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Layer 2: Issue Detection ──────────────────────────────────────────────

    def _handle_detect_issues(self, **kwargs) -> dict:
        file_path = kwargs.get("file_path", "")
        path = self._resolve_path(file_path)
        if not path:
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception as e:
            return {"success": False, "error": str(e)}

        issues = []
        lines = source.splitlines()

        # Walk all function/method definitions
        defined_names = set()
        called_names = set()

        for node in ast.walk(tree):
            # Collect defined function names
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined_names.add(node.name)
                func_lines = (node.end_lineno - node.lineno + 1) if hasattr(node, "end_lineno") else 0
                params = [a.arg for a in node.args.args if a.arg != "self"]

                # Long function
                if func_lines > 50:
                    issues.append({
                        "type": "long_function",
                        "severity": "medium",
                        "location": f"line {node.lineno}",
                        "message": f"`{node.name}` is {func_lines} lines — consider splitting",
                    })

                # Too many parameters
                if len(params) > 5:
                    issues.append({
                        "type": "too_many_params",
                        "severity": "low",
                        "location": f"line {node.lineno}",
                        "message": f"`{node.name}` has {len(params)} params ({', '.join(params[:5])}...) — consider a config dict",
                    })

                # Missing return annotation on non-private functions
                if not node.name.startswith("_") and node.returns is None and node.name not in ("__init__",):
                    issues.append({
                        "type": "missing_return_type",
                        "severity": "low",
                        "location": f"line {node.lineno}",
                        "message": f"`{node.name}` has no return type annotation",
                    })

            # Collect called names
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_names.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called_names.add(node.func.attr)

            # Bare except
            elif isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    issues.append({
                        "type": "bare_except",
                        "severity": "high",
                        "location": f"line {node.lineno}",
                        "message": "Bare `except:` catches everything including KeyboardInterrupt — use `except Exception:`",
                    })

            # TODO/FIXME/HACK comments
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                val = str(node.value.value)
                for marker in ("TODO", "FIXME", "HACK", "XXX"):
                    if marker in val:
                        issues.append({
                            "type": "tech_debt_marker",
                            "severity": "low",
                            "location": f"line {node.lineno}",
                            "message": f"{marker} comment found",
                        })

        # Dead code — defined but never called (skip private/dunder)
        public_defined = {n for n in defined_names if not n.startswith("_")}
        dead = public_defined - called_names - {"execute", "register_capabilities", "call_tool"}
        for name in sorted(dead)[:5]:  # cap at 5
            issues.append({
                "type": "dead_code",
                "severity": "low",
                "message": f"`{name}` is defined but never called within this file",
            })

        # Inline TODO/FIXME in comments
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                for marker in ("TODO", "FIXME", "HACK"):
                    if marker in stripped:
                        issues.append({
                            "type": "tech_debt_marker",
                            "severity": "low",
                            "location": f"line {i}",
                            "message": f"{marker}: {stripped[:80]}",
                        })

        # Sort by severity
        sev_order = {"high": 0, "medium": 1, "low": 2}
        issues.sort(key=lambda x: sev_order.get(x["severity"], 3))

        return {
            "success": True,
            "file": str(path),
            "issue_count": len(issues),
            "by_severity": {
                "high": len([i for i in issues if i["severity"] == "high"]),
                "medium": len([i for i in issues if i["severity"] == "medium"]),
                "low": len([i for i in issues if i["severity"] == "low"]),
            },
            "issues": issues[:30],
        }

    # ── Layer 3: Dependencies ─────────────────────────────────────────────────

    def _handle_get_dependencies(self, **kwargs) -> dict:
        file_path = kwargs.get("file_path", "")
        path = self._resolve_path(file_path)
        if not path:
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception as e:
            return {"success": False, "error": str(e)}

        imports = []
        imported_names = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"module": alias.name, "alias": alias.asname, "type": "import"})
                    imported_names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append({"module": module, "name": alias.name, "alias": alias.asname, "type": "from"})
                    imported_names.add(alias.asname or alias.name)

        # Classify internal vs external
        cua_modules = {"core", "tools", "api", "planner", "updater", "skills"}
        stdlib_modules = set(["os", "sys", "re", "json", "ast", "time", "datetime", "pathlib",
                               "typing", "dataclasses", "collections", "itertools", "functools",
                               "threading", "subprocess", "hashlib", "math", "random", "copy",
                               "io", "abc", "enum", "logging", "inspect", "importlib", "contextlib"])

        internal, external, stdlib = [], [], []
        for imp in imports:
            mod = imp["module"].split(".")[0]
            if mod in cua_modules:
                internal.append(imp)
            elif mod in stdlib_modules:
                stdlib.append(imp)
            else:
                external.append(imp)

        # Used names in code (to detect unused imports)
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    used_names.add(node.value.id)

        unused = [n for n in imported_names if n not in used_names and n != "*"]

        # Simple circular dep check within CUA
        circular = []
        module_name = str(path).replace("\\", "/").replace("/", ".").replace(".py", "")
        for imp in internal:
            dep_path = Path(imp["module"].replace(".", "/") + ".py")
            if dep_path.exists():
                try:
                    dep_source = dep_path.read_text(encoding="utf-8")
                    short_name = path.stem
                    if short_name in dep_source and f"import {short_name}" in dep_source:
                        circular.append(imp["module"])
                except Exception:
                    pass

        return {
            "success": True,
            "file": str(path),
            "total_imports": len(imports),
            "internal": len(internal),
            "external": len(external),
            "stdlib": len(stdlib),
            "external_ratio": round(len(external) / max(len(imports), 1), 2),
            "unused_imports": unused[:10],
            "circular_dependencies": circular,
            "external_packages": [i["module"].split(".")[0] for i in external],
            "internal_modules": [i["module"] for i in internal],
        }

    # ── Layer 4: Change Impact ────────────────────────────────────────────────

    def _handle_get_change_impact(self, **kwargs) -> dict:
        file_path = kwargs.get("file_path", "")
        path = self._resolve_path(file_path)
        if not path:
            return {"success": False, "error": f"File not found: {file_path}"}

        module_name = path.stem
        importers = []

        # Scan CUA source dirs for files that import this module
        scan_dirs = [Path("core"), Path("api"), Path("tools"), Path("planner"), Path("updater")]
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for py_file in scan_dir.rglob("*.py"):
                if py_file == path:
                    continue
                try:
                    content = py_file.read_text(encoding="utf-8")
                    if module_name in content and (
                        f"import {module_name}" in content or
                        f"from {module_name}" in content or
                        f"\"{module_name}\"" in content or
                        f"'{module_name}'" in content
                    ):
                        importers.append(str(py_file))
                except Exception:
                    pass

        # Test coverage — does a test file exist?
        test_candidates = [
            Path(f"tests/unit/test_{module_name.lower()}.py"),
            Path(f"tests/experimental/test_{module_name}.py"),
            Path(f"tests/integration/test_{module_name.lower()}.py"),
        ]
        test_file = next((str(p) for p in test_candidates if p.exists()), None)

        # Registry reference
        registry_entry = None
        try:
            import json
            reg = json.loads(Path("data/tool_registry.json").read_text())
            for name, data in reg.get("tools", {}).items():
                src = str(data.get("source_file", "")).replace("\\", "/")
                if module_name in src:
                    registry_entry = {"name": name, "version": data.get("version"), "status": data.get("status")}
                    break
        except Exception:
            pass

        return {
            "success": True,
            "file": str(path),
            "module_name": module_name,
            "imported_by": importers[:20],
            "importer_count": len(importers),
            "has_tests": test_file is not None,
            "test_file": test_file,
            "registry_entry": registry_entry,
            "change_risk": "high" if len(importers) > 5 else ("medium" if len(importers) > 2 else "low"),
        }

    # ── Layer 5: LLM Advisor ─────────────────────────────────────────────────

    def _handle_get_code_review(self, **kwargs) -> dict:
        file_path = kwargs.get("file_path", "")
        context = kwargs.get("context", "")
        path = self._resolve_path(file_path)
        if not path:
            return {"success": False, "error": f"File not found: {file_path}"}

        metrics = self._handle_get_file_metrics(file_path=file_path)
        issues = self._handle_detect_issues(file_path=file_path)
        deps = self._handle_get_dependencies(file_path=file_path)
        impact = self._handle_get_change_impact(file_path=file_path)

        # Build structured context — numbers first, not raw code
        parts = [f"FILE: {path.name}"]

        if metrics.get("success"):
            m = metrics
            parts.append(
                f"METRICS:\n"
                f"  Lines: {m['lines']['code']} code / {m['lines']['total']} total\n"
                f"  Maintainability: {m['maintainability']['score']}/100 (grade {m['maintainability']['grade']}) — {m['maintainability']['interpretation']}\n"
                f"  Avg complexity: {m['complexity']['avg']}  Max: {m['complexity']['max']}\n"
                f"  High-complexity functions: {[f['name'] for f in m['complexity']['high_complexity']]}"
            )

        if issues.get("success"):
            i = issues
            parts.append(
                f"ISSUES: {i['issue_count']} total "
                f"({i['by_severity']['high']} high, {i['by_severity']['medium']} medium, {i['by_severity']['low']} low)\n"
                + "\n".join(f"  [{x['severity'].upper()}] {x['message']}" for x in i['issues'][:8])
            )

        if deps.get("success"):
            d = deps
            parts.append(
                f"DEPENDENCIES: {d['total_imports']} imports "
                f"({d['internal']} internal, {d['external']} external, {d['stdlib']} stdlib)\n"
                f"  External packages: {d['external_packages']}\n"
                f"  Unused imports: {d['unused_imports']}\n"
                f"  Circular deps: {d['circular_dependencies']}"
            )

        if impact.get("success"):
            imp = impact
            parts.append(
                f"CHANGE IMPACT: {imp['importer_count']} files depend on this (risk: {imp['change_risk']})\n"
                f"  Has tests: {imp['has_tests']}\n"
                f"  Registry: {imp['registry_entry']}"
            )

        if context:
            parts.append(f"CONTEXT: {context}")

        prompt = (
            "You are a senior Python engineer reviewing code for an AI agent system.\n"
            "Based on the structured metrics below, give a concise actionable review.\n\n"
            + "\n\n".join(parts)
            + "\n\nReply with JSON:\n"
            '{"evolution_priority": "urgent|recommended|monitor|healthy", '
            '"summary": "2-3 sentence overview", '
            '"refactor_candidates": [{"function": "name", "reason": "why", "suggestion": "what to do"}], '
            '"quick_wins": ["specific small fix 1", ...], '
            '"risks": ["risk if changed without tests", ...]}'
        )

        try:
            raw = self.services.llm.generate(prompt, temperature=0.2, max_tokens=700)
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            parsed = __import__('json').loads(match.group()) if match else {}
        except Exception as e:
            parsed = {"error": str(e)}

        return {
            "success": True,
            "file": str(path),
            "evolution_priority": parsed.get("evolution_priority", "unknown"),
            "summary": parsed.get("summary", ""),
            "refactor_candidates": parsed.get("refactor_candidates", []),
            "quick_wins": parsed.get("quick_wins", []),
            "risks": parsed.get("risks", []),
            "layers": {
                "metrics": {k: v for k, v in metrics.items() if k != "success"},
                "issues": {k: v for k, v in issues.items() if k != "success"},
                "dependencies": {k: v for k, v in deps.items() if k != "success"},
                "change_impact": {k: v for k, v in impact.items() if k != "success"},
            },
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_path(self, file_path: str) -> Optional[Path]:
        """Resolve file path — absolute, relative to CWD, or tool name."""
        if not file_path:
            return None

        # Direct path
        p = Path(file_path)
        if p.exists():
            return p

        # Try relative to CWD
        rel = Path.cwd() / file_path
        if rel.exists():
            return rel

        # Try as tool name (e.g. "FinancialAnalysisTool")
        candidates = [
            Path(f"tools/experimental/{file_path}.py"),
            Path(f"tools/{file_path}.py"),
            Path(f"core/{file_path}.py"),
        ]
        for c in candidates:
            if c.exists():
                return c

        # Try registry
        try:
            from application.use_cases.tool_lifecycle.tool_registry_manager import ToolRegistryManager
            resolved = ToolRegistryManager().resolve_source_file(file_path)
            if resolved and resolved.exists():
                return resolved
        except Exception:
            pass

        return None
