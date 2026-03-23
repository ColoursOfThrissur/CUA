"""
Multi-Layer Verification Engine

Verifies tool output through 4 progressive layers:
  Layer 1 — Structural:    shape, required fields, type checks
  Layer 2 — Heuristic:     empty result, login page, error HTML, truncated JSON, rate-limit signals
  Layer 3 — Cross-source:  if multiple results exist, do they agree?
  Layer 4 — LLM reasoning: last resort for ambiguous cases

Returns a VerificationResult with verdict, confidence, issues found, and
a recommended action (accept / retry / fallback / escalate).
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

VERDICT_ACCEPT    = "accept"
VERDICT_RETRY     = "retry"
VERDICT_FALLBACK  = "fallback"
VERDICT_ESCALATE  = "escalate"   # human review needed


@dataclass
class VerificationIssue:
    layer: str          # structural | heuristic | cross_source | llm
    severity: str       # warning | error
    message: str


@dataclass
class VerificationResult:
    verdict: str                                    # accept | retry | fallback | escalate
    confidence: float                               # 0-1
    issues: List[VerificationIssue] = field(default_factory=list)
    layer_reached: str = "structural"
    notes: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == VERDICT_ACCEPT


# ---------------------------------------------------------------------------
# Heuristic patterns
# ---------------------------------------------------------------------------

_LOGIN_SIGNALS = [
    "sign in", "log in", "login", "please sign in", "authentication required",
    "access denied", "403 forbidden", "401 unauthorized", "session expired",
    "captcha", "verify you are human", "robot check",
]

_ERROR_HTML_SIGNALS = [
    "<title>error</title>", "404 not found", "500 internal server error",
    "502 bad gateway", "503 service unavailable", "page not found",
    "something went wrong", "an error occurred",
]

_RATE_LIMIT_SIGNALS = [
    "rate limit", "too many requests", "429", "quota exceeded",
    "throttled", "slow down", "try again later",
]

_TRUNCATION_SIGNALS = [
    "...[truncated]", "[truncated]", "... (truncated)", "output truncated",
]


def _text_of(data: Any) -> str:
    """Flatten data to a lowercase string for heuristic scanning."""
    if isinstance(data, str):
        return data.lower()
    if isinstance(data, dict):
        return json.dumps(data, default=str).lower()
    if isinstance(data, list):
        return json.dumps(data[:20], default=str).lower()
    return str(data).lower()


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class VerificationEngine:
    """
    Runs up to 4 verification layers on a tool result.
    Stops as soon as a definitive verdict is reached.
    """

    def __init__(self, llm_client=None):
        self._llm = llm_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(
        self,
        data: Any,
        tool_name: str,
        operation: str,
        expected_shape: Optional[Dict] = None,
        peer_results: Optional[List[Any]] = None,
        skill_context: Optional[Any] = None,
    ) -> VerificationResult:
        """
        Verify a single tool result.

        Args:
            data:           The result data to verify.
            tool_name:      Name of the tool that produced the result.
            operation:      Operation that was called.
            expected_shape: Optional dict of {field: type_str} for structural check.
            peer_results:   Other results from the same wave (for cross-source check).
            skill_context:  SkillExecutionContext if available.
        """
        issues: List[VerificationIssue] = []

        # Layer 1 — Structural
        layer1_issues = self._layer_structural(data, tool_name, operation, expected_shape)
        issues.extend(layer1_issues)
        errors = [i for i in layer1_issues if i.severity == "error"]
        if errors:
            return VerificationResult(
                verdict=VERDICT_RETRY,
                confidence=0.9,
                issues=issues,
                layer_reached="structural",
                notes=f"Structural errors: {'; '.join(e.message for e in errors)}",
            )

        # Layer 2 — Heuristic
        layer2_issues = self._layer_heuristic(data, tool_name, operation)
        issues.extend(layer2_issues)
        heuristic_errors = [i for i in layer2_issues if i.severity == "error"]
        if heuristic_errors:
            # Distinguish retry vs fallback based on signal type
            verdict = VERDICT_FALLBACK if any(
                "login" in i.message or "captcha" in i.message or "auth" in i.message
                for i in heuristic_errors
            ) else VERDICT_RETRY
            return VerificationResult(
                verdict=verdict,
                confidence=0.85,
                issues=issues,
                layer_reached="heuristic",
                notes=f"Heuristic errors: {'; '.join(e.message for e in heuristic_errors)}",
            )

        # Layer 3 — Cross-source (only if peers provided)
        if peer_results:
            layer3_issues = self._layer_cross_source(data, peer_results, tool_name)
            issues.extend(layer3_issues)
            cross_errors = [i for i in layer3_issues if i.severity == "error"]
            if cross_errors:
                return VerificationResult(
                    verdict=VERDICT_ESCALATE,
                    confidence=0.75,
                    issues=issues,
                    layer_reached="cross_source",
                    notes=f"Cross-source disagreement: {'; '.join(e.message for e in cross_errors)}",
                )

        # Layer 4 — LLM (only for ambiguous warnings, not clean results)
        warnings = [i for i in issues if i.severity == "warning"]
        if warnings and self._llm:
            layer4_result = self._layer_llm(data, tool_name, operation, warnings)
            if layer4_result:
                issues.extend(layer4_result.issues)
                if not layer4_result.passed:
                    return layer4_result

        # All layers passed
        confidence = max(0.5, 1.0 - 0.05 * len(warnings))
        return VerificationResult(
            verdict=VERDICT_ACCEPT,
            confidence=confidence,
            issues=issues,
            layer_reached="llm" if (warnings and self._llm) else ("cross_source" if peer_results else "heuristic"),
            notes="All verification layers passed." + (f" {len(warnings)} warning(s)." if warnings else ""),
        )

    def verify_wave(
        self,
        wave_results: Dict[str, Any],
        tool_names: Dict[str, str],
        operations: Dict[str, str],
        skill_context: Optional[Any] = None,
    ) -> Dict[str, VerificationResult]:
        """
        Verify all results from a parallel wave.
        Passes peer results for cross-source checking.
        Returns a dict of step_id → VerificationResult.
        """
        all_data = list(wave_results.values())
        results: Dict[str, VerificationResult] = {}

        for step_id, data in wave_results.items():
            peers = [d for sid, d in wave_results.items() if sid != step_id]
            results[step_id] = self.verify(
                data=data,
                tool_name=tool_names.get(step_id, "unknown"),
                operation=operations.get(step_id, "unknown"),
                peer_results=peers if peers else None,
                skill_context=skill_context,
            )

        return results

    # ------------------------------------------------------------------
    # Layer 1 — Structural
    # ------------------------------------------------------------------

    def _layer_structural(
        self,
        data: Any,
        tool_name: str,
        operation: str,
        expected_shape: Optional[Dict],
    ) -> List[VerificationIssue]:
        issues = []

        if data is None:
            issues.append(VerificationIssue(
                layer="structural", severity="error",
                message=f"{tool_name}.{operation} returned None",
            ))
            return issues

        # Empty container — only error for str/dict, not list (find_elements with no matches is valid)
        if isinstance(data, (dict, str)) and not data:
            issues.append(VerificationIssue(
                layer="structural", severity="error",
                message=f"{tool_name}.{operation} returned empty {type(data).__name__}",
            ))
            return issues
        if isinstance(data, list) and not data:
            issues.append(VerificationIssue(
                layer="structural", severity="warning",
                message=f"{tool_name}.{operation} returned empty list",
            ))
            return issues

        # Expected shape check
        if expected_shape and isinstance(data, dict):
            for field_name, expected_type in expected_shape.items():
                if field_name not in data:
                    issues.append(VerificationIssue(
                        layer="structural", severity="error",
                        message=f"Missing required field '{field_name}' in {tool_name}.{operation} output",
                    ))
                elif expected_type and not isinstance(data[field_name], self._resolve_type(expected_type)):
                    issues.append(VerificationIssue(
                        layer="structural", severity="warning",
                        message=f"Field '{field_name}' expected {expected_type}, got {type(data[field_name]).__name__}",
                    ))

        return issues

    # ------------------------------------------------------------------
    # Layer 2 — Heuristic
    # ------------------------------------------------------------------

    # Operations that are allowed to return login/auth pages (it's their job)
    _BROWSER_OPS = {
        "navigate", "open_page", "open_and_navigate", "wait_for_element",
        "click_element", "fill_input", "submit_form", "get_current_page",
        "take_screenshot", "get_page_content", "scroll_page",
    }
    # Web fetch ops — real pages commonly have "sign in" in nav/footer; treat as warning only
    _WEB_FETCH_OPS = {"fetch_url", "search_web", "crawl_site", "extract_links", "extract_search_results"}

    def _layer_heuristic(self, data: Any, tool_name: str, operation: str) -> List[VerificationIssue]:
        issues = []
        text = _text_of(data)
        is_browser_op = operation in self._BROWSER_OPS or "browser" in tool_name.lower()
        is_web_fetch = operation in self._WEB_FETCH_OPS

        # Login / auth wall — warning for browser ops and web fetches (nav menus contain "sign in")
        # Only error if the page is EXCLUSIVELY a login wall (no real content alongside it)
        if any(sig in text for sig in _LOGIN_SIGNALS):
            # Check if there's actual content beyond the login signal
            has_content = len(text) > 500  # real pages are much longer than a bare login wall
            severity = "warning" if (is_browser_op or is_web_fetch or has_content) else "error"
            issues.append(VerificationIssue(
                layer="heuristic",
                severity=severity,
                message=f"{tool_name}.{operation}: output contains login/auth wall signals — result is likely a login page, not content",
            ))

        # Error HTML
        if any(sig in text for sig in _ERROR_HTML_SIGNALS):
            issues.append(VerificationIssue(
                layer="heuristic", severity="error",
                message=f"{tool_name}.{operation}: output contains HTTP error page signals",
            ))

        # Rate limit — skip for browser ops (base64 screenshot data can contain "429")
        if not is_browser_op and not is_web_fetch and any(sig in text for sig in _RATE_LIMIT_SIGNALS):
            issues.append(VerificationIssue(
                layer="heuristic", severity="error",
                message=f"{tool_name}.{operation}: output contains rate-limit signals — data may be incomplete",
            ))

        # Truncation
        if any(sig in text for sig in _TRUNCATION_SIGNALS):
            issues.append(VerificationIssue(
                layer="heuristic", severity="warning",
                message=f"{tool_name}.{operation}: output appears truncated",
            ))

        # Suspiciously short content for web operations
        if "fetch" in operation or "scrape" in operation or "get_content" in operation:
            content = data.get("content", "") if isinstance(data, dict) else str(data)
            if isinstance(content, str) and 0 < len(content) < 100:
                issues.append(VerificationIssue(
                    layer="heuristic", severity="warning",
                    message=f"{tool_name}.{operation}: content is suspiciously short ({len(content)} chars) for a web fetch",
                ))

        # List result with zero items when items expected
        if isinstance(data, dict):
            for list_key in ("results", "items", "files", "messages", "orders", "issues", "repos"):
                val = data.get(list_key)
                if isinstance(val, list) and len(val) == 0:
                    issues.append(VerificationIssue(
                        layer="heuristic", severity="warning",
                        message=f"{tool_name}.{operation}: '{list_key}' list is empty — may indicate no data or a silent failure",
                    ))

        return issues

    # ------------------------------------------------------------------
    # Layer 3 — Cross-source
    # ------------------------------------------------------------------

    def _layer_cross_source(
        self, data: Any, peers: List[Any], tool_name: str
    ) -> List[VerificationIssue]:
        issues = []

        # Only compare numeric/boolean facts — skip if data is raw HTML/text
        if not isinstance(data, dict) or not peers:
            return issues

        # Check for key numeric fields that should agree across sources
        for key in ("count", "total", "price", "amount", "status"):
            val = data.get(key)
            if val is None:
                continue
            peer_vals = [
                p.get(key) for p in peers
                if isinstance(p, dict) and p.get(key) is not None
            ]
            if not peer_vals:
                continue
            # Flag if this result disagrees with majority of peers
            disagreements = [pv for pv in peer_vals if pv != val]
            if len(disagreements) >= len(peer_vals):
                issues.append(VerificationIssue(
                    layer="cross_source", severity="error",
                    message=(
                        f"{tool_name}: field '{key}' value {val!r} disagrees with "
                        f"peer result(s) {peer_vals} — possible data inconsistency"
                    ),
                ))

        return issues

    # ------------------------------------------------------------------
    # Layer 4 — LLM
    # ------------------------------------------------------------------

    def _layer_llm(
        self,
        data: Any,
        tool_name: str,
        operation: str,
        warnings: List[VerificationIssue],
    ) -> Optional[VerificationResult]:
        """Ask LLM to judge whether the result looks valid given the warnings."""
        if not self._llm:
            return None

        warning_text = "; ".join(w.message for w in warnings)
        data_preview = str(data)[:600]

        prompt = (
            f"A tool returned a result with warnings. Decide if the result is usable.\n\n"
            f"Tool: {tool_name}.{operation}\n"
            f"Warnings: {warning_text}\n"
            f"Result preview: {data_preview}\n\n"
            "Return JSON only: "
            '{"verdict": "accept|retry|fallback", "confidence": 0.0_to_1.0, "reason": "string"}'
        )
        try:
            raw = self._llm._call_llm(prompt, temperature=0.1, max_tokens=150, expect_json=True)
            parsed = self._llm._extract_json(raw) if raw else None
            if not isinstance(parsed, dict):
                return None
            verdict = str(parsed.get("verdict", VERDICT_ACCEPT)).lower()
            if verdict not in (VERDICT_ACCEPT, VERDICT_RETRY, VERDICT_FALLBACK, VERDICT_ESCALATE):
                verdict = VERDICT_ACCEPT
            confidence = float(parsed.get("confidence", 0.6))
            reason = str(parsed.get("reason", ""))
            return VerificationResult(
                verdict=verdict,
                confidence=confidence,
                issues=[VerificationIssue(layer="llm", severity="warning" if verdict == VERDICT_ACCEPT else "error", message=reason)],
                layer_reached="llm",
                notes=f"LLM verdict: {verdict} ({reason})",
            )
        except Exception as e:
            logger.warning(f"VerificationEngine LLM layer failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_type(self, type_str: str):
        return {"str": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict}.get(type_str, object)


# Singleton
_engine: Optional[VerificationEngine] = None


def get_verification_engine(llm_client=None) -> VerificationEngine:
    global _engine
    if _engine is None:
        _engine = VerificationEngine(llm_client=llm_client)
    elif llm_client and _engine._llm is None:
        _engine._llm = llm_client
    return _engine
