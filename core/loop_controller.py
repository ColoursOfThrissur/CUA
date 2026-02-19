"""
Loop Controller - Main self-improvement loop orchestration
"""
import asyncio
import time
from datetime import datetime
from typing import Optional, Dict
from dataclasses import dataclass
from enum import Enum

class LoopStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"

@dataclass
class LoopState:
    status: LoopStatus
    current_iteration: int
    max_iterations: int
    stop_requested: bool
    emergency_stop: bool

class LoopController:
    def __init__(
        self, 
        llm_client,
        update_orchestrator,
        task_analyzer,
        proposal_generator,
        sandbox_tester,
        plan_history,
        analytics,
        max_iterations=None
    ):
        from core.config_manager import get_config
        from core.event_bus import get_event_bus
        from core.evolution_bridge import EvolutionBridge
        config = get_config()
        
        self.llm_client = llm_client
        self.update_orchestrator = update_orchestrator
        self.task_analyzer = task_analyzer
        self.proposal_generator = proposal_generator
        self.sandbox_tester = sandbox_tester
        self.plan_history = plan_history
        self.analytics = analytics
        self.max_iterations = max_iterations or config.improvement.max_iterations
        self.max_retries = 3  # Max 3 retries per stage
        self.config = config
        self.event_bus = get_event_bus()
        
        self.state = LoopState(
            status=LoopStatus.IDLE,
            current_iteration=0,
            max_iterations=max_iterations,
            stop_requested=False,
            emergency_stop=False
        )
        
        self.logs = []
        self.pending_approvals = {}
        self.approval_lock = asyncio.Lock()  # Prevent concurrent approval conflicts
        self.custom_focus = None
        self.dry_run = False
        self.preview_proposals = []
        self.failed_suggestions = []
        self.retry_count = {}
        self.iteration_history = []
        self.task_queue = []  # Queue of tasks from LLM
        self.task_attempts = {}  # Track attempts per task
        self.file_cooldown = {}  # Track recently failed files: {file: iteration}
        self.continuous_mode = False  # Continuous improvement mode
        self.in_critical_section = False  # Track if in critical operation
        
        # Retry coordinator for sandbox failures
        from core.retry_coordinator import RetryCoordinator
        self.retry_coordinator = RetryCoordinator(max_retries=3)
        
        # Evolution system integration
        self.evolution_bridge = EvolutionBridge(llm_client)
    
    def add_log(self, log_type: str, message: str, proposal_id: Optional[str] = None):
        """Add log entry with automatic truncation"""
        log_entry = {
            "type": log_type,
            "message": message,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "proposalId": proposal_id
        }
        self.logs.append(log_entry)
        
        # Truncate to prevent memory leak
        max_logs = self.config.improvement.max_logs_display * 2
        if len(self.logs) > max_logs:
            self.logs = self.logs[-max_logs:]
        
        print(f"[LOOP] {log_type}: {message}")
        
        # Emit log event for real-time UI updates
        asyncio.create_task(self.event_bus.emit('log_added', log_entry))
        
        return log_entry
    
    async def start_loop(self):
        """Start improvement loop with baseline gate"""
        if self.state.status == LoopStatus.RUNNING:
            return {"error": "Loop already running"}
        
        # CRITICAL: Baseline health check
        from core.baseline_health_checker import BaselineHealthChecker
        health_checker = BaselineHealthChecker()
        
        self.add_log("info", "Running baseline health check...")
        baseline_ok, message, failures = health_checker.check_baseline()
        
        if not baseline_ok:
            self.add_log("error", f"BASELINE FAILURE: {message}")
            for failure in failures[:5]:
                self.add_log("error", f"  - {failure}")
            self.add_log("error", "Loop cannot start - fix baseline first")
            return {"error": f"Baseline check failed: {message}", "failures": failures}
        
        self.add_log("success", "Baseline healthy - starting loop")
        
        # Validate config
        if self.max_iterations <= 0:
            return {"error": "max_iterations must be > 0"}
        if self.config.improvement.sandbox_timeout <= 0:
            return {"error": "sandbox_timeout must be > 0"}
        if self.config.improvement.approval_timeout <= 0:
            return {"error": "approval_timeout must be > 0"}
        
        # Unload model to free memory if enabled
        if self.config.improvement.warmup_enabled:
            try:
                self.llm_client._unload_model()
            except Exception as e:
                self.add_log("warning", f"Model unload failed: {e}")
        
        self.state.status = LoopStatus.RUNNING
        self.state.current_iteration = 0
        self.state.stop_requested = False
        self.state.emergency_stop = False
        self.logs = []
        self.preview_proposals = []
        # Start with fresh in-memory iteration context for this run.
        self.iteration_history = []
        # Keep feature tracker history across starts to avoid repeatedly
        # targeting files that were recently improved.
        # DON'T clear custom_focus - it was set by API before start_loop()
        
        self.add_log("start", f"Loop started (max {self.max_iterations} iterations)")
        asyncio.create_task(self.event_bus.emit('loop_started', {'max_iterations': self.max_iterations}))
        asyncio.create_task(self._run_loop())
        
        return {"status": "started", "max_iterations": self.max_iterations}
    
    async def stop_loop(self, mode: str = "graceful"):
        """Stop loop"""
        if mode == "immediate":
            # Check critical section
            if self.in_critical_section:
                self.add_log("warning", "In critical section - waiting for safe stop...")
                self.state.stop_requested = True
                self.state.status = LoopStatus.STOPPING
                return {"status": "stopping", "mode": "deferred", "reason": "critical_section"}
            
            self.state.emergency_stop = True
            self.state.status = LoopStatus.STOPPED
            self.continuous_mode = False
            self.add_log("stop", "Emergency stop")
            return {"status": "stopped", "mode": "immediate"}
        else:
            self.state.stop_requested = True
            self.state.status = LoopStatus.STOPPING
            self.continuous_mode = False
            self.add_log("stop", "Stop requested")
            return {"status": "stopping", "mode": "graceful"}
    
    async def _run_loop(self):
        """Main loop execution"""
        try:
            while True:  # Continuous mode support
                # Check stop at start of each iteration
                if self.state.stop_requested or self.state.emergency_stop:
                    break
                
                # Check if should continue
                if not self.continuous_mode and self.state.current_iteration >= self.max_iterations:
                    break
                
                self.state.current_iteration += 1
                self.add_log("iteration", f"Iteration {self.state.current_iteration}: Analyzing...")
                asyncio.create_task(self.event_bus.emit('iteration_started', {'iteration': self.state.current_iteration}))
                
                # Update feature tracker iteration
                self.task_analyzer.feature_tracker.set_iteration(self.state.current_iteration)
                
                iteration_start = time.time()
                
                # Check if should use evolution mode
                if self.evolution_bridge.should_use_evolution():
                    self.add_log("info", "Running evolution cycle...")
                    result = self.evolution_bridge.run_evolution_cycle()
                    
                    if result.get('stop_loop'):
                        self.add_log("error", result['message'])
                        break
                    
                    if result['success']:
                        self.add_log("success", result['message'])
                    else:
                        reason = result.get('reason', '')
                        stage = result.get('stage', '')
                        message = result.get('message', 'Evolution cycle failed')
                        if reason in {'no_insights', 'insight_cooldown', 'duplicate_recent_proposal', 'file_already_modified_this_cycle'}:
                            self.add_log("info", f"{message}")
                        else:
                            if stage:
                                self.add_log("error", f"{message} (stage={stage}, reason={reason})")
                            else:
                                self.add_log("error", f"{message} (reason={reason})")
                    
                    continue  # Skip normal flow
                
                # Get task from queue or analyze for new batch
                if not self.task_queue:
                    # Switch to analysis model (Mistral for reasoning)
                    original_model = self.llm_client.model
                    try:
                        analysis_model = self.config.llm.analysis_model
                        self.llm_client.set_model(analysis_model)
                        self.add_log("info", f"Using {analysis_model} for analysis")
                    except Exception:
                        pass
                    
                    self.add_log("info", "Analyzing for new task batch...")
                    # Get files on cooldown to exclude
                    excluded_files = [
                        f for f, iter_num in self.file_cooldown.items()
                        if self.state.current_iteration - iter_num < 3
                    ]
                    tasks = self.task_analyzer.analyze_and_propose_tasks(
                        focus=self.custom_focus,
                        failed_suggestions=self.failed_suggestions,
                        iteration_history=self.iteration_history.copy(),
                        excluded_files=excluded_files
                    )
                    
                    if not tasks:
                        self.add_log("info", "No improvements needed - all tools complete")
                        # Restore original model
                        try:
                            self.llm_client.set_model(original_model)
                        except Exception:
                            pass
                        # Stop loop - nothing left to improve
                        break
                    
                    self.task_queue = tasks[:1]  # SINGLE-SHOT: Only 1 task
                    self.add_log("info", f"Selected 1 task: {tasks[0].get('suggestion', '')[:60]}")
                    
                    # Restore model after analysis
                    try:
                        self.llm_client.set_model(original_model)
                    except Exception:
                        pass
                
                # Pop next task
                if not self.task_queue:  # Safety check
                    continue
                    
                analysis = self.task_queue.pop(0)
                
                # CRITICAL: Clear previous errors when starting new task
                self.proposal_generator.clear_errors()
                
                # Check file cooldown (skip if failed in last 3 iterations)
                files_affected = analysis.get('files_affected', [])
                target_file = files_affected[0] if files_affected else None
                if target_file and target_file in self.file_cooldown:
                    cooldown_iter = self.file_cooldown[target_file]
                    if self.state.current_iteration - cooldown_iter < 3:
                        self.add_log("info", f"Skipping {target_file} (cooldown) - getting new task")
                        # Clear queue and add to excluded files for next analysis
                        self.task_queue = []
                        self.state.current_iteration -= 1
                        continue
                
                # Check if task failed too many times
                task_id = hash(f"{analysis.get('files_affected', [])}::{analysis.get('suggestion', '')[:50]}")
                if self.task_attempts.get(task_id, 0) >= 3:
                    self.add_log("info", f"Skipping task (3 attempts): {analysis.get('suggestion', '')[:50]}")
                    # Don't count as iteration - try next task
                    self.state.current_iteration -= 1
                    continue
                
                self.task_attempts[task_id] = self.task_attempts.get(task_id, 0) + 1
                
                # Switch to code model (Qwen for code generation)
                original_model = self.llm_client.model
                try:
                    code_model = self.config.llm.code_model
                    self.llm_client.set_model(code_model)
                    self.add_log("info", f"Using {code_model} for code generation")
                except Exception:
                    pass
                
                # RETRY LOOP: Code generation + validation (max 3 attempts)
                self.retry_coordinator.start_retry_cycle('code_generation')
                proposal = None
                
                # Log multi-method tasks
                methods_to_modify = analysis.get('methods_to_modify', [])
                if len(methods_to_modify) > 1:
                    self.add_log("info", f"Multi-method task: {len(methods_to_modify)} methods")
                
                for attempt in range(1, self.max_retries + 1):
                    if self.state.stop_requested or self.state.emergency_stop:
                        break
                    
                    self.add_log("info", f"Code generation attempt {attempt}/{self.max_retries}...")
                    
                    # Modify analysis on retry to give LLM different context
                    if attempt > 1:
                        # Add attempt number to force different approach
                        analysis_copy = analysis.copy()
                        analysis_copy['suggestion'] = f"{analysis['suggestion']} (Attempt {attempt}: Try different approach)"
                        proposal = self.proposal_generator.generate_proposal(analysis_copy)
                    else:
                        proposal = self.proposal_generator.generate_proposal(analysis)
                    
                    if proposal and self._validate_proposal_structure(proposal):
                        self.add_log("success", f"Valid proposal generated on attempt {attempt}")
                        break
                    else:
                        error_msg = "Invalid proposal structure" if proposal else "Proposal generation failed"
                        self.add_log("error", f"Validation failed (attempt {attempt}/{self.max_retries}): {error_msg}")
                        
                        if attempt < self.max_retries:
                            # Feed error back to LLM with specific guidance
                            formatted_error = self.retry_coordinator.format_error_for_llm(error_msg, {})
                            self.proposal_generator.add_error(formatted_error)
                        else:
                            self.add_log("error", "Max retries exhausted for code generation")
                            proposal = None
                
                self.retry_coordinator.reset()
                
                if not proposal:
                    self.add_log("error", "Failed to generate valid proposal")
                    # Restore original model
                    try:
                        self.llm_client.set_model(original_model)
                    except Exception:
                        pass
                    # Add to history even on validation failure
                    self.iteration_history.append({
                        "iter": self.state.current_iteration,
                        "task": analysis.get('suggestion', 'Unknown')[:80],
                        "file": analysis.get('files_affected', ['unknown'])[0],
                        "result": "validation_fail",
                        "error": "Invalid proposal structure",
                        "category": analysis.get('category', 'core'),
                        "methods_modified": analysis.get('methods_to_modify', [])
                    })
                    
                    # Track validation failure
                    self.task_analyzer.feature_tracker.add_feature(
                        file=analysis.get('files_affected', ['unknown'])[0],
                        feature=analysis.get('suggestion', 'Unknown')[:80],
                        category=analysis.get('category', 'core'),
                        iteration=self.state.current_iteration,
                        result="failure",
                        methods=analysis.get('methods_to_modify', [])
                    )
                    continue
                
                # Restore original model after code generation
                try:
                    self.llm_client.set_model(original_model)
                except Exception:
                    pass
                
                # Calculate risk
                risk_score = self.update_orchestrator.risk_scorer.score_update(
                    proposal['files_changed'],
                    proposal['diff_lines']
                )
                
                self.add_log("proposal", f"Proposal: {proposal['description']}")
                self.add_log("info", f"Risk: {risk_score.level.value.upper()}")
                
                # Check approval if needed
                if risk_score.requires_approval:
                    approved = await self._handle_approval(proposal, risk_score)
                    if not approved:
                        continue
                
                # Test in sandbox with retry (max 3 attempts)
                self.retry_coordinator.start_retry_cycle('sandbox_test')
                sandbox_result = None
                
                for attempt in range(1, self.max_retries + 1):
                    if self.state.stop_requested or self.state.emergency_stop:
                        break
                    
                    self.add_log("testing", f"Sandbox test attempt {attempt}/{self.max_retries}...")
                    sandbox_result = self.sandbox_tester.test_proposal(proposal, timeout=self.config.improvement.sandbox_timeout)
                    
                    if sandbox_result['success']:
                        self.add_log("success", f"Tests passed on attempt {attempt}")
                        break
                    else:
                        error_msg = sandbox_result.get('output', 'Unknown error')[:500]
                        
                        # CLASSIFY FAILURE
                        from core.failure_classifier import FailureClassifier, FailureAction
                        context = {
                            'baseline_passed': sandbox_result.get('baseline_passed', 0),
                            'tests_passed': sandbox_result.get('tests_passed', 0)
                        }
                        failure_type, action = FailureClassifier.classify(error_msg, context)
                        
                        self.add_log("error", f"Sandbox failed (attempt {attempt}/{self.max_retries}): {failure_type.value}")
                        
                        # BASELINE FAILURE - STOP IMMEDIATELY
                        if action == FailureAction.STOP_LOOP:
                            self.add_log("error", "CRITICAL: Baseline failure detected - stopping loop")
                            self.state.stop_requested = True
                            break
                        
                        # REJECT - NO RETRY
                        if action == FailureAction.REJECT:
                            self.add_log("error", "Failure classified as non-recoverable - rejecting")
                            break
                        
                        if attempt < self.max_retries:
                            # Regenerate based on action
                            if action == FailureAction.REGENERATE:
                                formatted_error = self.retry_coordinator.format_error_for_llm(error_msg, context)
                                self.proposal_generator.add_error(formatted_error)
                                self.add_log("info", f"Regenerating proposal with error feedback...")
                                proposal = self.proposal_generator.generate_proposal(analysis)
                                
                                if not proposal or not self._validate_proposal_structure(proposal):
                                    self.add_log("error", "Proposal regeneration failed")
                                    break
                        else:
                            self.add_log("error", "Max retries exhausted")
                
                self.retry_coordinator.reset()
                
                if not sandbox_result or not sandbox_result['success']:
                    error_msg = sandbox_result.get('output', 'Unknown error')
                    self.add_log("error", f"Sandbox failed: {error_msg}")
                    
                    # Add file to cooldown
                    self.file_cooldown[target_file] = self.state.current_iteration
                    
                    # Pass error to proposal generator with limit
                    self.proposal_generator.add_error(f"Sandbox: {error_msg}")
                    
                    # Track failures (keep for backward compatibility)
                    suggestion_key = str(analysis.get('files_affected', []))
                    self.retry_count[suggestion_key] = self.retry_count.get(suggestion_key, 0) + 1
                    
                    # Add to history BEFORE next iteration
                    self.iteration_history.append({
                        "iter": self.state.current_iteration,
                        "task": proposal['description'][:80],
                        "file": proposal['files_changed'][0],
                        "result": "sandbox_fail",
                        "error": error_msg[:100],
                        "category": analysis.get('category', 'core'),
                        "methods_modified": analysis.get('methods_to_modify', [])
                    })
                    
                    # Track failure in feature tracker
                    self.task_analyzer.feature_tracker.add_feature(
                        file=proposal['files_changed'][0],
                        feature=proposal['description'][:80],
                        category=analysis.get('category', 'core'),
                        iteration=self.state.current_iteration,
                        result="failure",
                        methods=analysis.get('methods_to_modify', [])
                    )
                    
                    # Record analytics
                    duration = time.time() - iteration_start
                    self.analytics.record_attempt(
                        self.state.current_iteration,
                        proposal['description'],
                        risk_score.level.value,
                        False, False, duration, "sandbox_failure"
                    )
                    continue
                
                self.add_log("success", f"Tests passed ({sandbox_result['tests_passed']}/{sandbox_result['tests_total']})")
                
                # Apply or preview
                if self.dry_run:
                    self._handle_dry_run(proposal, risk_score, sandbox_result)
                else:
                    # CRITICAL SECTION: File write operation
                    self.in_critical_section = True
                    try:
                        self.add_log("info", "Applying changes...")
                        # Check idempotency before applying
                        from core.idempotency_checker import IdempotencyChecker
                        idem_checker = IdempotencyChecker()
                        is_dup, reason = idem_checker.is_duplicate(
                            proposal['files_changed'][0],
                            proposal['description']
                        )
                        if is_dup:
                            self.add_log("error", f"Duplicate change: {reason}")
                            continue
                        
                        apply_result = await self._apply_changes(proposal)
                        
                        # Record change if successful
                        if apply_result['success']:
                            idem_checker.record_change(
                                proposal['files_changed'][0],
                                proposal['description'],
                                f"improvement_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                            )
                    finally:
                        self.in_critical_section = False
                    
                    # Save to history
                    plan_id = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.state.current_iteration}"
                    self.plan_history.save_plan(
                        plan_id,
                        self.state.current_iteration,
                        proposal,
                        risk_score.level.value,
                        sandbox_result,
                        apply_result
                    )
                    
                    if apply_result['success']:
                        verified, verify_error = self._verify_applied_change(proposal, analysis)
                        if not verified:
                            apply_result = {"success": False, "error": f"Apply verification failed: {verify_error}"}
                            self.add_log("error", apply_result["error"])
                    
                    if apply_result['success']:
                        self.add_log("success", "Changes applied successfully")
                        self.add_log("info", f"Backup: {apply_result['backup_id']}")
                        result_status = "success"
                        error_msg = ""
                    else:
                        error_msg = apply_result.get('error', 'Unknown error')
                        self.add_log("error", f"Failed to apply: {error_msg}")
                        result_status = "apply_fail"
                    
                    # Add to history BEFORE next iteration
                    self.iteration_history.append({
                        "iter": self.state.current_iteration,
                        "task": proposal['description'][:80],
                        "file": proposal['files_changed'][0],
                        "result": result_status,
                        "error": error_msg[:100] if error_msg else "",
                        "stage": "applied" if result_status == "success" else "apply_failed",
                        "category": analysis.get('category', 'core'),
                        "methods_modified": analysis.get('methods_to_modify', [])
                    })
                    self._record_attempt_terminal_state(
                        proposal=proposal,
                        analysis=analysis,
                        sandbox_result=sandbox_result,
                        apply_result=apply_result,
                        result_status=result_status
                    )
                    
                    # Track feature in task_analyzer's feature tracker
                    if result_status == "success":
                        self.task_analyzer.feature_tracker.add_feature(
                            file=proposal['files_changed'][0],
                            feature=proposal['description'][:80],
                            category=analysis.get('category', 'core'),
                            iteration=self.state.current_iteration,
                            result="success",
                            methods=analysis.get('methods_to_modify', [])
                        )
                    
                    # Record analytics
                    duration = time.time() - iteration_start
                    self.analytics.record_attempt(
                        self.state.current_iteration,
                        proposal['description'],
                        risk_score.level.value,
                        True,
                        apply_result['success'],
                        duration,
                        None if apply_result['success'] else "apply_failure"
                    )
                    
                    # Emit task completion event
                    asyncio.create_task(self.event_bus.emit('task_completed', {
                        'iteration': self.state.current_iteration,
                        'success': apply_result['success'],
                        'description': proposal['description'][:80]
                    }))
                
                if self.state.stop_requested:
                    self.add_log("stop", "Loop stopped gracefully")
                    break
                
                # Circuit breaker - stop if too many consecutive failures
                recent_failures = sum(1 for h in self.iteration_history[-5:] if h.get('result') != 'success')
                if recent_failures >= 5:
                    self.add_log("error", "Circuit breaker: 5 consecutive failures - stopping loop")
                    break
                
                # In continuous mode, reset iteration counter after max_iterations
                if self.continuous_mode and self.state.current_iteration >= self.max_iterations:
                    self.add_log("info", f"Continuous mode: Starting new cycle")
                    self.state.current_iteration = 0
                
                # Rate limiting
                await asyncio.sleep(self.config.improvement.rate_limit_delay)
            
            self._finalize_loop()
            
        except Exception as e:
            self.add_log("error", f"Loop error: {str(e)}")
            self.state.status = LoopStatus.STOPPED
    
    def _validate_proposal_structure(self, proposal: Dict) -> bool:
        """Validate proposal has required fields"""
        required = ['description', 'files_changed', 'patch', 'raw_code']
        return all(field in proposal for field in required)
    
    async def _handle_approval(self, proposal: Dict, risk_score) -> bool:
        """Handle approval workflow with lock"""
        async with self.approval_lock:  # Prevent race conditions
            proposal_id = f"proposal_{self.state.current_iteration:03d}"
            
            # Check if already exists (shouldn't happen but safety check)
            if proposal_id in self.pending_approvals:
                return False
            
            self.pending_approvals[proposal_id] = {
                "proposal": proposal,
                "risk_score": risk_score,
                "approved": None
            }
        
        self.add_log("approval_needed", 
                    f"Risk: {risk_score.level.value.upper()} - Waiting for approval...",
                    proposal_id)
        
        approved = await self._wait_for_approval(proposal_id)
        
        if approved:
            self.add_log("approved", f"Proposal {proposal_id} approved")
        else:
            self.add_log("rejected", f"Proposal {proposal_id} rejected")
        
        return approved
    
    async def _wait_for_approval(self, proposal_id: str, timeout: int = None) -> bool:
        """Wait for user approval"""
        timeout = timeout or self.config.improvement.approval_timeout
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            if self.state.emergency_stop:
                return False
            
            approval = self.pending_approvals.get(proposal_id, {}).get('approved')
            if approval is not None:
                return approval
            
            await asyncio.sleep(0.5)
        
        self.add_log("error", f"Approval timeout for {proposal_id}")
        return False
    
    def _handle_dry_run(self, proposal: Dict, risk_score, sandbox_result: Dict):
        """Handle dry-run mode"""
        self.preview_proposals.append({
            "iteration": self.state.current_iteration,
            "proposal": proposal,
            "risk_score": risk_score,
            "test_result": sandbox_result
        })
        self.add_log("info", "[DRY-RUN] Preview saved - changes NOT applied")
    
    async def _apply_changes(self, proposal: Dict) -> Dict:
        """Apply changes using AtomicApplier or direct write"""
        try:
            from updater.atomic_applier import AtomicApplier
            
            applier = AtomicApplier(repo_path=".")
            update_id = f"improvement_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            try:
                success, error = applier.apply_update(proposal['patch'], update_id)
                
                if success:
                    return {"success": True, "backup_id": f"backup_{update_id}"}
                else:
                    return {"success": False, "error": error}
            except FileNotFoundError:
                return await self._apply_without_git(proposal, update_id)
        except Exception as e:
            self.add_log("error", f"Apply failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _apply_without_git(self, proposal: Dict, update_id: str) -> Dict:
        """Apply changes directly when git unavailable"""
        import shutil
        from pathlib import Path
        
        backup_path = None
        file_path = None
        
        try:
            files_changed = proposal.get('files_changed', [])
            if not files_changed:
                return {"success": False, "error": "No files to change"}
            
            target_file = files_changed[0]
            file_path = Path(target_file)
            raw_code = proposal.get('raw_code')
            
            if not raw_code:
                return {"success": False, "error": "No raw code"}
            
            # Backup if exists
            if file_path.exists():
                backup_dir = Path("backups")
                backup_dir.mkdir(exist_ok=True)
                backup_path = backup_dir / f"{file_path.name}.{update_id}.bak"
                shutil.copy2(file_path, backup_path)
            
            # Write new content
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(raw_code, encoding='utf-8')
            
            # Validate written file
            try:
                import ast
                if file_path.suffix == '.py':
                    ast.parse(raw_code)
            except SyntaxError as e:
                # Rollback on syntax error
                if backup_path and backup_path.exists():
                    shutil.copy2(backup_path, file_path)
                    self.add_log("error", "Syntax error detected - rolled back")
                return {"success": False, "error": f"Syntax error: {e}"}
            
            return {"success": True, "backup_id": f"manual_backup_{update_id}"}
        except Exception as e:
            # Attempt rollback
            if backup_path and backup_path.exists() and file_path:
                try:
                    shutil.copy2(backup_path, file_path)
                    self.add_log("error", f"Apply failed, rolled back: {e}")
                except Exception:
                    pass
            return {"success": False, "error": f"Direct apply failed: {str(e)}"}
    
    def _finalize_loop(self):
        """Finalize loop execution"""
        if not self.state.emergency_stop:
            if self.dry_run:
                self.add_log("stop", f"[DRY-RUN] Preview complete: {len(self.preview_proposals)} proposals")
            else:
                self.add_log("stop", f"Loop completed {self.state.current_iteration} iterations")
        
        self.state.status = LoopStatus.STOPPED
        asyncio.create_task(self.event_bus.emit('loop_stopped', {'iterations': self.state.current_iteration}))

    def _verify_applied_change(self, proposal: Dict, analysis: Dict) -> tuple[bool, str]:
        """Verify that applied change is reflected in target file and syntax remains valid."""
        try:
            files_changed = proposal.get('files_changed', [])
            if not files_changed:
                return False, "No target file in proposal"
            target_file = files_changed[0]
            from pathlib import Path
            p = Path(target_file)
            if not p.exists():
                return False, f"Target file missing after apply: {target_file}"
            content = p.read_text(encoding="utf-8")
            if target_file.endswith(".py"):
                import ast
                ast.parse(content)
            expected_methods = analysis.get('methods_to_modify', []) or []
            for method in expected_methods:
                if method and f"def {method}(" not in content:
                    return False, f"Expected method not found after apply: {method}"
            return True, ""
        except Exception as e:
            return False, str(e)

    def _record_attempt_terminal_state(self, proposal: Dict, analysis: Dict, sandbox_result: Dict, apply_result: Dict, result_status: str):
        """Emit normalized terminal state for observability."""
        terminal_state = {
            "iteration": self.state.current_iteration,
            "file": (proposal.get("files_changed") or ["unknown"])[0],
            "description": proposal.get("description", "")[:160],
            "methods": analysis.get("methods_to_modify", []),
            "generated": True,
            "sandbox_passed": bool(sandbox_result.get("success", False)),
            "applied": bool(apply_result.get("success", False)),
            "status": result_status,
        }
        self.add_log("info", f"Terminal state: {terminal_state['status']} | file={terminal_state['file']} | applied={terminal_state['applied']}")
        try:
            self.analytics.record_terminal_state(
                iteration=terminal_state["iteration"],
                file_path=terminal_state["file"],
                status=terminal_state["status"],
                generated=terminal_state["generated"],
                sandbox_passed=terminal_state["sandbox_passed"],
                applied=terminal_state["applied"],
            )
        except Exception:
            pass
        asyncio.create_task(self.event_bus.emit('attempt_terminal_state', terminal_state))
    
    def approve_proposal(self, proposal_id: str) -> bool:
        """Approve pending proposal with locking"""
        if proposal_id in self.pending_approvals:
            # Check if already approved/rejected
            current = self.pending_approvals[proposal_id].get('approved')
            if current is not None:
                return False  # Already processed
            self.pending_approvals[proposal_id]['approved'] = True
            return True
        return False
    
    def reject_proposal(self, proposal_id: str) -> bool:
        """Reject pending proposal with locking"""
        if proposal_id in self.pending_approvals:
            # Check if already approved/rejected
            current = self.pending_approvals[proposal_id].get('approved')
            if current is not None:
                return False  # Already processed
            self.pending_approvals[proposal_id]['approved'] = False
            return True
        return False
    
    def get_status(self) -> Dict:
        """Get current loop status"""
        max_logs = self.config.improvement.max_logs_display
        return {
            "status": self.state.status.value,
            "running": self.state.status == LoopStatus.RUNNING,
            "iteration": self.state.current_iteration,
            "maxIterations": self.max_iterations,
            "logs": self.logs[-max_logs:],
            "dry_run": self.dry_run,
            "preview_count": len(self.preview_proposals)
        }
    
    def set_evolution_mode(self, enabled: bool):
        """Toggle between deterministic and evolution mode"""
        if enabled:
            self.evolution_bridge.enable_evolution_mode()
            self.add_log("info", "Evolution mode ENABLED - LLM can propose freely")
        else:
            self.evolution_bridge.disable_evolution_mode()
            self.add_log("info", "Evolution mode DISABLED - deterministic mode")
