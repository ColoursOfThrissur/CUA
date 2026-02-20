"""
Evolution Controller - Autonomous Capability Engine
Integrates all evolution components with safety backbone
"""
import logging
import ast
import hashlib
import json
from typing import Optional, List
from pathlib import Path
from core.proposal_types import EvolutionProposal, ProposalType
from core.capability_graph import CapabilityGraph
from core.growth_budget import GrowthBudget
from core.self_reflector import SelfReflector
from core.expansion_mode import ExpansionMode
from core.refactoring_permissions import RefactoringPermissions
from core.risk_weighted_decision import RiskWeightedDecision
from core.tool_creation.flow import ToolCreationOrchestrator

# Preserve security backbone
from core.baseline_health_checker import BaselineHealthChecker
from core.failure_classifier import FailureClassifier
from core.interface_protector import InterfaceProtector
from core.staleness_guard import StalenessGuard
from core.idempotency_checker import IdempotencyChecker

logger = logging.getLogger(__name__)

class EvolutionController:
    """
    Autonomous Capability Engine with controlled freedom
    
    Capabilities:
    - Propose improvements (LLM freedom)
    - Validate safety (Controller governance)
    - Create new tools (Sandboxed expansion)
    - Refactor intelligently (Internal improvements)
    - Self-reflect strategically (Gap analysis)
    """
    
    def __init__(self, llm_client, orchestrator=None, registry=None):
        # Evolution components
        self.capability_graph = CapabilityGraph()
        self.growth_budget = GrowthBudget()
        self.self_reflector = SelfReflector()
        self.expansion_mode = ExpansionMode()
        self.refactoring_perms = RefactoringPermissions()
        self.risk_decision = RiskWeightedDecision()
        
        # Store orchestrator and registry for tool creation
        self.orchestrator = orchestrator
        self.registry = registry
        
        self.tool_creation = ToolCreationOrchestrator(
            self.capability_graph,
            self.expansion_mode
        )
        
        # Security backbone (preserved)
        self.baseline_checker = BaselineHealthChecker()
        self.failure_classifier = FailureClassifier()
        self.interface_protector = InterfaceProtector()
        self.staleness_guard = StalenessGuard()
        self.idempotency_checker = IdempotencyChecker()
        
        self.llm_client = llm_client
        self.modified_files_this_cycle = set()  # Track files modified in current cycle
        self._history_file = Path("data/evolution_history.json")
        self._history = self._load_history()
        self._last_failure: Optional[dict] = None

    def _set_last_failure(self, stage: str, reason: str, message: str):
        self._last_failure = {
            "stage": stage,
            "reason": reason,
            "message": message
        }

    def _clear_last_failure(self):
        self._last_failure = None
    
    def run_evolution_cycle(self) -> dict:
        """Run one evolution cycle with full freedom and safety"""
        self._clear_last_failure()
        
        # Reset modified files tracker at start of cycle
        self.modified_files_this_cycle.clear()
        
        # Step 1: Baseline gate (security backbone)
        baseline_ok, msg = self.baseline_checker.check()
        if not baseline_ok:
            logger.error(f"Baseline failed: {msg}")
            return {"status": "stopped", "reason": "baseline_failure"}
        
        # Step 2: Self-reflection (strategic analysis)
        insights = self.self_reflector.analyze_system()
        if not insights:
            logger.info("No strategic improvements identified")
            return {"status": "idle", "reason": "no_insights"}
        
        top_insight = None
        for insight in insights:
            file_hint = insight.affected_files[0] if insight.affected_files else ""
            if file_hint and self._is_file_in_recent_cooldown(file_hint):
                logger.info(f"Skipping insight for recently modified file: {file_hint}")
                continue
            top_insight = insight
            break
        
        if not top_insight:
            logger.info("All insights currently in cooldown")
            return {"status": "idle", "reason": "insight_cooldown"}
        
        logger.info(f"Top insight: {top_insight.description}")
        
        # Step 3: LLM proposes evolution (freedom of proposal)
        proposal = self._generate_proposal(top_insight)
        if not proposal:
            failure = self._last_failure or {
                "stage": "proposal_generation",
                "reason": "no_proposal",
                "message": "No proposal generated"
            }
            return {
                "status": "failed",
                "reason": failure["reason"],
                "message": failure["message"],
                "stage": failure["stage"]
            }
        
        if self._is_duplicate_proposal(proposal):
            logger.info("Skipping duplicate proposal recently attempted")
            return {"status": "skipped", "reason": "duplicate_recent_proposal"}
        
        # Step 3.5: Check if file already modified this cycle
        if proposal.target_file in self.modified_files_this_cycle:
            logger.warning(f"File {proposal.target_file} already modified this cycle - skipping to prevent duplicate helpers")
            return {"status": "skipped", "reason": "file_already_modified_this_cycle"}
        
        # Step 4: Controller validates (controlled execution)
        permitted, reason = proposal.is_permitted(self.growth_budget)
        if not permitted:
            logger.info(f"Proposal rejected: {reason}")
            return {"status": "rejected", "reason": reason}
        
        # Step 5: Execute based on proposal type
        result = self._execute_proposal(proposal)
        
        # Step 5.5: Track modified file
        if result.get("status") == "success":
            self.modified_files_this_cycle.add(proposal.target_file)
            self._record_success(proposal)
            logger.info(f"Marked {proposal.target_file} as modified this cycle")
        else:
            self._record_attempt(proposal, result.get("status", "failed"))
        
        # Step 6: Increment cycle
        self.growth_budget.increment_cycle()
        
        return result

    def _normalize_file(self, file_path: str) -> str:
        return file_path.replace("\\", "/")

    def _proposal_fingerprint(self, proposal: EvolutionProposal) -> str:
        basis = f"{self._normalize_file(proposal.target_file)}|{proposal.proposal_type.value}|{proposal.description.strip().lower()}|{','.join(sorted(proposal.methods_affected))}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()

    def _load_history(self) -> dict:
        if self._history_file.exists():
            try:
                with open(self._history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data.setdefault("recent_successes", [])
                        data.setdefault("recent_attempts", [])
                        return data
            except Exception:
                pass
        return {"recent_successes": [], "recent_attempts": []}

    def _save_history(self):
        self._history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._history_file, "w", encoding="utf-8") as f:
            json.dump(self._history, f, indent=2)

    def _trim_history(self):
        self._history["recent_successes"] = self._history["recent_successes"][-100:]
        self._history["recent_attempts"] = self._history["recent_attempts"][-200:]

    def _is_file_in_recent_cooldown(self, file_path: str, cycles: int = 3) -> bool:
        normalized = self._normalize_file(file_path)
        for entry in reversed(self._history.get("recent_successes", [])):
            if self._normalize_file(entry.get("file", "")) == normalized:
                last_cycle = int(entry.get("cycle", -999))
                return (self.growth_budget.current_cycle - last_cycle) < cycles
        return False

    def _is_duplicate_proposal(self, proposal: EvolutionProposal, cycles: int = 3) -> bool:
        fingerprint = self._proposal_fingerprint(proposal)
        for entry in reversed(self._history.get("recent_attempts", [])):
            if entry.get("fingerprint") == fingerprint:
                last_cycle = int(entry.get("cycle", -999))
                if (self.growth_budget.current_cycle - last_cycle) < cycles:
                    return True
        return False

    def _record_success(self, proposal: EvolutionProposal):
        self._history["recent_successes"].append({
            "cycle": self.growth_budget.current_cycle,
            "file": self._normalize_file(proposal.target_file),
            "type": proposal.proposal_type.value,
            "fingerprint": self._proposal_fingerprint(proposal),
        })
        self._record_attempt(proposal, "success", save=False)
        self._trim_history()
        self._save_history()

    def _record_attempt(self, proposal: EvolutionProposal, status: str, save: bool = True):
        self._history["recent_attempts"].append({
            "cycle": self.growth_budget.current_cycle,
            "status": status,
            "file": self._normalize_file(proposal.target_file),
            "type": proposal.proposal_type.value,
            "fingerprint": self._proposal_fingerprint(proposal),
        })
        self._trim_history()
        if save:
            self._save_history()
    
    def _generate_proposal(self, insight) -> Optional[EvolutionProposal]:
        """LLM generates evolution proposal"""
        
        # Build enriched context
        enriched_context = ""
        if insight.enriched_data:
            data = insight.enriched_data
            
            # ALWAYS show available methods first
            if "all_methods" in data and data["all_methods"]:
                enriched_context += f"\n\nAvailable methods in file: {', '.join(data['all_methods'])}\n"
            
            if "duplicate_blocks" in data:
                if data["duplicate_blocks"]:
                    enriched_context += "\nTop duplicate clusters:\n"
                    for i, block in enumerate(data["duplicate_blocks"][:2], 1):
                        enriched_context += f"{i}. Repeated {block.get('pattern_type', 'logic')} in:\n"
                        for method in block['methods'][:3]:
                            enriched_context += f"   - {method}\n"
                        enriched_context += f"   Pattern: {block['pattern'][:60]}...\n"
                    enriched_context += f"\nMethods with duplication: {', '.join(data['methods_with_duplication'][:3])}\n"
            elif "long_methods" in data:
                enriched_context += "\nLong methods:\n"
                for method in data["long_methods"]:
                    enriched_context += f"- {method['name']}: {method['lines']} lines\n"
        
        prompt = f"""Based on this insight, propose an evolution:

Insight: {insight.description}
Category: {insight.category}
Severity: {insight.severity}
Affected files: {insight.affected_files}{enriched_context}

Propose ONE of:
- micro_patch: Small improvement to existing method
- structural_upgrade: Refactor within file
- tool_extension: Add capability to existing tool
- new_tool: Create new tool for capability gap

CONSTRAINTS:
- Must remain within single file
- No new files unless proposal_type = new_tool
- No method signature changes
- Max 3 methods affected
- No interface changes
- No cross-file refactoring
- No splitting into modules
- Helper name must be SPECIFIC (not generic like _send_request, _handle_request)
- Description must mention CONCRETE pattern (header, payload, error, response, etc.)
- methods_affected MUST be ACTUAL method names from "Available methods in file" list above

Structural upgrade means:
- Extract private helper method with SPECIFIC name
- Extract internal helper class
- Reduce duplication within file
- Encapsulate repeated logic
- NOT splitting file into modules
- NOT moving methods to new files
- NOT using generic helper names

CRITICAL: For methods_affected field:
- ONLY use method names from the "Available methods in file" list shown above
- Do NOT invent or hallucinate method names
- Do NOT use generic names like "send_request" or "handle_request"
- Use EXACT names from the available methods list

Return JSON with:
- proposal_type
- target_file
- description (MUST mention specific pattern like "header building" or "error handling", NOT just "repeated logic")
- justification
- estimated_risk (0.0-1.0)
- methods_affected (list ACTUAL method names from "Available methods in file" above, max 3)
"""
        
        # Log the full prompt for debugging
        logger.info(f"=== PROPOSAL GENERATION PROMPT ===")
        logger.info(f"Prompt length: {len(prompt)} chars")
        logger.info(f"Enriched context: {enriched_context}")
        logger.info(f"Full prompt:\n{prompt}")
        logger.info(f"=== END PROMPT ===")
        
        try:
            response = self.llm_client._call_llm(prompt, temperature=0.3, expect_json=True)
            
            # Log LLM response
            logger.info(f"=== LLM RESPONSE ===")
            logger.info(f"Response: {response}")
            logger.info(f"=== END RESPONSE ===")
            
            if not response:
                self._set_last_failure("proposal_generation", "empty_llm_response", "LLM returned empty response")
                return None
            response = self.llm_client._extract_json(response)
            
            # Log extracted JSON
            logger.info(f"=== EXTRACTED JSON ===")
            logger.info(f"JSON: {response}")
            logger.info(f"=== END JSON ===")
            
            if not response:
                self._set_last_failure("proposal_generation", "invalid_json_response", "Failed to parse LLM response as JSON")
                return None
            
            # Validate proposal structure
            if not self._validate_proposal_structure(response):
                logger.error(f"Proposal validation failed: {response}")
                self._set_last_failure("proposal_validation", "proposal_structure_invalid", "Proposal failed structural validation")
                # Record rejected attempts (best-effort) to avoid immediate re-proposal loops.
                try:
                    target_file = response.get('target_file', '')
                    proposal_type_raw = response.get('proposal_type', 'micro_patch')
                    proposal_type = ProposalType(proposal_type_raw)
                    methods_affected = response.get('methods_affected', []) or []
                    temp_proposal = EvolutionProposal(
                        proposal_type=proposal_type,
                        target_file=target_file,
                        description=response.get('description', ''),
                        justification=response.get('justification', ''),
                        estimated_risk=0.5,
                        requires_expansion_mode=proposal_type == ProposalType.NEW_TOOL,
                        methods_affected=methods_affected if isinstance(methods_affected, list) else []
                    )
                    self._record_attempt(temp_proposal, "rejected_validation")
                except Exception:
                    pass
                return None
            
            # AST validation
            from core.ast_validator import ASTValidator
            ast_validator = ASTValidator()
            valid, msg = ast_validator.validate_proposal(response, insight.enriched_data)
            if not valid:
                logger.error(f"AST validation failed: {msg}")
                self._set_last_failure("proposal_validation", "ast_validation_failed", f"AST validation failed: {msg}")
                return None
            
            # Override risk if needed
            estimated_risk = response['estimated_risk']
            methods_affected = response.get('methods_affected', [])
            
            # Risk recalibration - NEVER trust LLM risk blindly
            try:
                estimated_risk = float(response['estimated_risk'])
            except (TypeError, ValueError):
                logger.warning("Invalid estimated_risk format, defaulting to 0.3")
                estimated_risk = 0.3
            methods_affected = response.get('methods_affected', [])
            proposal_type = response['proposal_type']
            
            # Minimum risk thresholds by type
            if proposal_type == 'structural_upgrade':
                # Structural changes are never low risk
                estimated_risk = max(estimated_risk, 0.3)
                
                # High duplication + multiple methods = higher risk
                dup_score = insight.enriched_data.get('duplication_score') if insight.enriched_data else None
                if dup_score and float(dup_score) > 0.4 and len(methods_affected) >= 2:
                    estimated_risk = max(estimated_risk, 0.4)
                    logger.info(f"Risk adjusted to {estimated_risk} (high duplication + structural change)")
            
            elif proposal_type == 'tool_extension':
                estimated_risk = max(estimated_risk, 0.25)
            
            # Multiple methods always increases risk
            if len(methods_affected) > 2:
                estimated_risk = max(estimated_risk, 0.5)
                logger.warning(f"Risk adjusted to {estimated_risk} (affects {len(methods_affected)} methods)")
            
            return EvolutionProposal(
                proposal_type=ProposalType(response['proposal_type']),
                target_file=response['target_file'],
                description=response['description'],
                justification=response['justification'],
                estimated_risk=estimated_risk,
                requires_expansion_mode=response['proposal_type'] == 'new_tool',
                methods_affected=methods_affected
            )
        except Exception as e:
            logger.error(f"Failed to generate proposal: {e}")
            self._set_last_failure("proposal_generation", "proposal_exception", str(e))
            return None
    
    def _validate_proposal_structure(self, proposal: dict) -> bool:
        """Validate proposal doesn't violate structural constraints"""
        methods = proposal.get('methods_affected', [])
        description = proposal.get('description', '').lower()
        
        # Reject if affects "All" methods
        if any('all' in str(m).lower() for m in methods):
            logger.error("Rejected: affects 'All' methods")
            return False
        
        # Reject placeholder method names
        placeholder_patterns = ['method1', 'method2', 'method3', 'methodx', 'function1']
        if any(any(p in str(m).lower() for p in placeholder_patterns) for m in methods):
            logger.error("Rejected: contains placeholder method names")
            return False
        
        # Reject if too many methods
        if len(methods) > 3:
            logger.error(f"Rejected: affects {len(methods)} methods (max 3)")
            return False
        
        # Reject generic helper names
        generic_helpers = ['_send_request', '_handle_request', '_process_request', '_do_request']
        for generic in generic_helpers:
            if generic in description:
                logger.error(f"Rejected: generic helper name '{generic}' - must be specific")
                return False
        
        # Reject if description lacks concrete pattern reference
        concrete_patterns = [
            'header', 'payload', 'error', 'response', 'timeout', 'retry', 'validation',
            'toolresult', 'tool result', 'serialization', 'deserialization', 'json',
            'parsing', 'stringify', 'query', 'url', 'request', 'cache'
        ]
        if 'repeated logic' in description and not any(p in description for p in concrete_patterns):
            logger.error("Rejected: description too vague - must mention specific pattern")
            return False
        
        # Reject cross-file refactoring language
        forbidden_phrases = [
            'smaller modules',
            'separate files',
            'break into modules',
            'split into',
            'move to',
            'extract into new file',
            'create new module'
        ]
        
        for phrase in forbidden_phrases:
            if phrase in description:
                logger.error(f"Rejected: contains forbidden phrase '{phrase}'")
                return False
        
        return True
    
    def _execute_proposal(self, proposal: EvolutionProposal) -> dict:
        """Execute proposal with appropriate flow"""
        
        if proposal.proposal_type == ProposalType.NEW_TOOL:
            return self._execute_new_tool(proposal)
        
        elif proposal.proposal_type == ProposalType.STRUCTURAL_UPGRADE:
            return self._execute_refactoring(proposal)
        
        elif proposal.proposal_type == ProposalType.TOOL_EXTENSION:
            return self._execute_extension(proposal)
        
        else:  # MICRO_PATCH
            return self._execute_patch(proposal)
    
    def _execute_new_tool(self, proposal: EvolutionProposal) -> dict:
        """Create new tool via controlled flow"""
        success, msg = self.tool_creation.create_new_tool(
            proposal.description, self.llm_client
        )
        return {
            "status": "success" if success else "failed",
            "type": "new_tool",
            "message": msg
        }
    
    def _execute_refactoring(self, proposal: EvolutionProposal) -> dict:
        """Execute internal refactoring using standard improvement system"""
        try:
            # Read actual method code to provide context
            method_code = self._extract_method_code(proposal.target_file, proposal.methods_affected)
            
            # Convert EvolutionProposal to standard task format with actual code
            task = {
                'suggestion': f"{proposal.description}\n\nCurrent code:\n{method_code}",
                'files_affected': [proposal.target_file],
                'category': 'refactoring',
                'methods_to_modify': proposal.methods_affected,
                'justification': proposal.justification
            }
            
            # Use proposal_generator from standard system
            from core.proposal_generator import ProposalGenerator
            from core.system_analyzer import SystemAnalyzer
            from core.patch_generator import PatchGenerator
            
            analyzer = SystemAnalyzer()
            patch_gen = PatchGenerator()
            
            # Import orchestrator - need it for proposal generator
            from updater.orchestrator import UpdateOrchestrator
            orchestrator = UpdateOrchestrator(repo_path=".")
            
            proposal_gen = ProposalGenerator(self.llm_client, analyzer, patch_gen, orchestrator)
            
            # Generate proposal using step-by-step approach
            standard_proposal = proposal_gen.generate_proposal(task)
            
            if not standard_proposal:
                return {"status": "failed", "type": "refactoring", "message": "Proposal generation failed"}
            
            # Apply using atomic applier
            from updater.atomic_applier import AtomicApplier
            from datetime import datetime
            
            applier = AtomicApplier(repo_path=".")
            update_id = f"evolution_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            success, error = applier.apply_update(standard_proposal['patch'], update_id)
            
            if success:
                logger.info(f"Refactoring applied: {proposal.target_file}")
                return {"status": "success", "type": "refactoring", "message": f"Applied to {proposal.target_file}"}
            else:
                logger.error(f"Apply failed: {error}")
                return {"status": "failed", "type": "refactoring", "message": error}
                
        except Exception as e:
            logger.error(f"Refactoring execution failed: {e}")
            return {"status": "failed", "type": "refactoring", "message": str(e)}
    
    def _execute_extension(self, proposal: EvolutionProposal) -> dict:
        """Extend existing tool using standard improvement system"""
        try:
            # Read actual method code to provide context
            method_code = self._extract_method_code(proposal.target_file, proposal.methods_affected)
            
            task = {
                'suggestion': f"{proposal.description}\n\nCurrent code:\n{method_code}",
                'files_affected': [proposal.target_file],
                'category': 'tool_extension',
                'methods_to_modify': proposal.methods_affected,
                'justification': proposal.justification
            }
            
            from core.proposal_generator import ProposalGenerator
            from core.system_analyzer import SystemAnalyzer
            from core.patch_generator import PatchGenerator
            from updater.orchestrator import UpdateOrchestrator
            
            analyzer = SystemAnalyzer()
            patch_gen = PatchGenerator()
            orchestrator = UpdateOrchestrator(repo_path=".")
            proposal_gen = ProposalGenerator(self.llm_client, analyzer, patch_gen, orchestrator)
            
            standard_proposal = proposal_gen.generate_proposal(task)
            
            if not standard_proposal:
                return {"status": "failed", "type": "extension", "message": "Proposal generation failed"}
            
            from updater.atomic_applier import AtomicApplier
            from datetime import datetime
            
            applier = AtomicApplier(repo_path=".")
            update_id = f"evolution_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            success, error = applier.apply_update(standard_proposal['patch'], update_id)
            
            if success:
                logger.info(f"Extension applied: {proposal.target_file}")
                return {"status": "success", "type": "extension", "message": f"Extended {proposal.target_file}"}
            else:
                logger.error(f"Apply failed: {error}")
                return {"status": "failed", "type": "extension", "message": error}
                
        except Exception as e:
            logger.error(f"Extension execution failed: {e}")
            return {"status": "failed", "type": "extension", "message": str(e)}
    
    def _execute_patch(self, proposal: EvolutionProposal) -> dict:
        """Apply micro patch using standard improvement system"""
        try:
            # Read actual method code to provide context
            method_code = self._extract_method_code(proposal.target_file, proposal.methods_affected)
            
            task = {
                'suggestion': f"{proposal.description}\n\nCurrent code:\n{method_code}",
                'files_affected': [proposal.target_file],
                'category': 'micro_patch',
                'methods_to_modify': proposal.methods_affected,
                'justification': proposal.justification
            }
            
            from core.proposal_generator import ProposalGenerator
            from core.system_analyzer import SystemAnalyzer
            from core.patch_generator import PatchGenerator
            from updater.orchestrator import UpdateOrchestrator
            
            analyzer = SystemAnalyzer()
            patch_gen = PatchGenerator()
            orchestrator = UpdateOrchestrator(repo_path=".")
            proposal_gen = ProposalGenerator(self.llm_client, analyzer, patch_gen, orchestrator)
            
            standard_proposal = proposal_gen.generate_proposal(task)
            
            if not standard_proposal:
                return {"status": "failed", "type": "patch", "message": "Proposal generation failed"}
            
            from updater.atomic_applier import AtomicApplier
            from datetime import datetime
            
            applier = AtomicApplier(repo_path=".")
            update_id = f"evolution_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            success, error = applier.apply_update(standard_proposal['patch'], update_id)
            
            if success:
                logger.info(f"Patch applied: {proposal.target_file}")
                return {"status": "success", "type": "patch", "message": f"Patched {proposal.target_file}"}
            else:
                logger.error(f"Apply failed: {error}")
                return {"status": "failed", "type": "patch", "message": error}
                
        except Exception as e:
            logger.error(f"Patch execution failed: {e}")
            return {"status": "failed", "type": "patch", "message": str(e)}
    
    def _extract_method_code(self, file_path: str, method_names: List[str]) -> str:
        """Extract actual code of specified methods"""
        try:
            with open(file_path) as f:
                content = f.read()
                tree = ast.parse(content)
            
            lines = content.split('\n')
            method_codes = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in method_names:
                    start = node.lineno - 1
                    end = node.end_lineno
                    method_code = '\n'.join(lines[start:end])
                    method_codes.append(f"# Method: {node.name}\n{method_code}")
            
            return '\n\n'.join(method_codes) if method_codes else "# No methods found"
        except Exception as e:
            logger.error(f"Failed to extract method code: {e}")
            return "# Failed to extract code"
