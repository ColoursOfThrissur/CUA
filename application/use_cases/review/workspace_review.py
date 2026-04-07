"""Workspace review helpers for slash-command review flows."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from application.services.diff_payload import build_diff_payload


@dataclass
class ReviewFinding:
    severity: str
    summary: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None


class WorkspaceReviewUseCase:
    """Produce lightweight review findings from the current git workspace diff."""

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = repo_path

    def review(self, security: bool = False) -> Dict[str, object]:
        if not self._in_git_repo():
            return {
                "ok": False,
                "error": "not_a_git_repo",
                "summary": "Workspace review requires a git repository.",
                "findings": [],
                "changed_files": [],
            }

        status_lines = self._run_git(["status", "--short"]).splitlines()
        diff_text = self._run_git(["diff", "--no-ext-diff", "--unified=0"])
        cached_diff = self._run_git(["diff", "--cached", "--no-ext-diff", "--unified=0"])
        combined_diff = "\n".join(part for part in (diff_text, cached_diff) if part.strip())

        changed_files = self._parse_changed_files(status_lines)
        if not changed_files:
            return {
                "ok": True,
                "summary": "No workspace changes to review.",
                "findings": [],
                "changed_files": [],
                "status_lines": [],
            }

        findings = self._build_findings(changed_files, combined_diff, security=security)
        findings.sort(key=lambda item: (self._severity_rank(item.severity), item.file_path or "", item.line_number or 0))
        return {
            "ok": True,
            "summary": self._build_summary(changed_files, findings, security=security),
            "findings": findings,
            "changed_files": changed_files,
            "status_lines": status_lines,
            "diff": build_diff_payload(combined_diff),
        }

    def _in_git_repo(self) -> bool:
        try:
            output = self._run_git(["rev-parse", "--is-inside-work-tree"])
            return output.strip().lower() == "true"
        except Exception:
            return False

    def _run_git(self, args: List[str]) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "git command failed").strip())
        return completed.stdout

    def _parse_changed_files(self, status_lines: List[str]) -> List[Dict[str, str]]:
        files: List[Dict[str, str]] = []
        for raw in status_lines:
            line = raw.rstrip()
            if not line:
                continue
            status = line[:2]
            path = line[3:].strip()
            if "->" in path:
                path = path.split("->", 1)[1].strip()
            files.append({"status": status, "path": path})
        return files

    def _build_findings(self, changed_files: List[Dict[str, str]], diff_text: str, security: bool) -> List[ReviewFinding]:
        findings: List[ReviewFinding] = []
        added_lines = self._parse_added_lines(diff_text)

        if not security:
            findings.extend(self._general_findings(changed_files, added_lines))
        else:
            findings.extend(self._security_findings(added_lines))

        if not security and self._needs_tests_warning(changed_files):
            findings.append(
                ReviewFinding(
                    severity="medium",
                    summary="Source changes are present without matching test updates.",
                )
            )

        if security and not findings:
            findings.append(
                ReviewFinding(
                    severity="info",
                    summary="No obvious security-sensitive additions were detected in the current diff.",
                )
            )
        elif not security and not findings:
            findings.append(
                ReviewFinding(
                    severity="info",
                    summary="No obvious review findings were detected from the current diff heuristics.",
                )
            )
        return findings

    def _general_findings(self, changed_files: List[Dict[str, str]], added_lines: List[Dict[str, object]]) -> List[ReviewFinding]:
        findings: List[ReviewFinding] = []
        for line in added_lines:
            text = str(line["text"])
            normalized = text.strip()
            if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", normalized):
                findings.append(
                    ReviewFinding(
                        severity="medium",
                        summary="New TODO/FIXME-style marker added to the diff.",
                        file_path=str(line["path"]),
                        line_number=int(line["line"]),
                    )
                )
            if re.search(r"\b(print\(|console\.log\(|debugger\b|pdb\.set_trace\(|breakpoint\()", normalized):
                findings.append(
                    ReviewFinding(
                        severity="medium",
                        summary="Debug-only output or breakpoint statement was added.",
                        file_path=str(line["path"]),
                        line_number=int(line["line"]),
                    )
                )
        large_changes = sum(1 for line in added_lines if self._is_source_file(str(line["path"])))
        if large_changes > 80:
            findings.append(
                ReviewFinding(
                    severity="low",
                    summary=f"Large source diff detected ({large_changes} added source lines); manual review depth should be higher.",
                )
            )
        return findings

    def _security_findings(self, added_lines: List[Dict[str, object]]) -> List[ReviewFinding]:
        findings: List[ReviewFinding] = []
        for line in added_lines:
            text = str(line["text"]).strip()
            path = str(line["path"])
            line_number = int(line["line"])
            if re.search(r"\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*[\"'][^\"']+[\"']", text, re.IGNORECASE):
                findings.append(ReviewFinding("high", "Possible hard-coded credential added.", path, line_number))
            if "verify=False" in text or "ssl=False" in text:
                findings.append(ReviewFinding("high", "TLS verification appears to be disabled.", path, line_number))
            if re.search(r"\bshell\s*=\s*True\b", text):
                findings.append(ReviewFinding("high", "Subprocess shell=True was added.", path, line_number))
            if re.search(r"\b(eval|exec)\s*\(", text):
                findings.append(ReviewFinding("high", "Dynamic code execution was added.", path, line_number))
            if "yaml.load(" in text and "safe_load" not in text:
                findings.append(ReviewFinding("medium", "Unsafe yaml.load usage was added.", path, line_number))
            if re.search(r"CORS.*\*", text) or "allow_origins=[\"*\"]" in text:
                findings.append(ReviewFinding("medium", "Wildcard CORS configuration was added.", path, line_number))
        return findings

    def _parse_added_lines(self, diff_text: str) -> List[Dict[str, object]]:
        current_file: Optional[str] = None
        new_line = 0
        added: List[Dict[str, object]] = []
        for raw in diff_text.splitlines():
            if raw.startswith("+++ b/"):
                current_file = raw[6:]
                continue
            if raw.startswith("@@"):
                match = re.search(r"\+(\d+)(?:,(\d+))?", raw)
                if match:
                    new_line = int(match.group(1))
                continue
            if raw.startswith("+") and not raw.startswith("+++"):
                if current_file is not None:
                    added.append({"path": current_file, "line": new_line, "text": raw[1:]})
                new_line += 1
                continue
            if raw.startswith("-") and not raw.startswith("---"):
                continue
            if raw.startswith(" "):
                new_line += 1
        return added

    def _needs_tests_warning(self, changed_files: List[Dict[str, str]]) -> bool:
        source_changed = any(self._is_source_file(item["path"]) for item in changed_files)
        tests_changed = any("test" in item["path"].lower() for item in changed_files)
        return source_changed and not tests_changed

    def _is_source_file(self, path: str) -> bool:
        return Path(path).suffix.lower() in {".py", ".js", ".ts", ".tsx", ".jsx"}

    def _build_summary(self, changed_files: List[Dict[str, str]], findings: List[ReviewFinding], security: bool) -> str:
        label = "Security review" if security else "Workspace review"
        return f"{label}: {len(changed_files)} changed files, {len(findings)} findings."

    def _severity_rank(self, severity: str) -> int:
        ranks = {"high": 0, "medium": 1, "low": 2, "info": 3}
        return ranks.get(severity, 4)
