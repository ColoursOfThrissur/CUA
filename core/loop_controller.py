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
        config = get_config()
        
        self.llm_client = llm_client
        self.update_orchestrator = update_orchestrator
        self.task_analyzer = task_analyzer
        self.proposal_generator = proposal_generator
        self.sandbox_tester = sandbox_tester
        self.plan_history = plan_history
        self.analytics = analytics
        self.max_iterations = max_iterations or config.improvement.max_iterations
        self.config = config
        
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
        max_logs = self.config.improvement.max_logs_display * 2  # Keep 2x for history
        if len(self.logs) > max_logs:
            self.logs = self.logs[-max_logs:]
        
        print(f"[LOOP] {log_type}: {message}")
        return log_entry
    
    async def start_loop(self):
        """Start improvement loop"""
        if self.state.status == LoopStatus.RUNNING:
            return {"error": "Loop already running"}
        
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
        
        self.add_log("start", f"Loop started (max {self.max_iterations} iterations)")
        asyncio.create_task(self._run_loop())
        
        return {"status": "started", "max_iterations": self.max_iterations}
    
    async def stop_loop(self, mode: str = "graceful"):
        """Stop loop"""
        if mode == "immediate":
            self.state.emergency_stop = True
            self.state.status = LoopStatus.STOPPED
            self.add_log("stop", "Emergency stop")
            return {"status": "stopped", "mode": "immediate"}
        else:
            self.state.stop_requested = True
            self.state.status = LoopStatus.STOPPING
            self.add_log("stop", "Stop requested")
            return {"status": "stopping", "mode": "graceful"}
    
    async def _run_loop(self):
        """Main loop execution"""
        try:
            while self.state.current_iteration < self.max_iterations:
                if self.state.emergency_stop:
                    break
                
                self.state.current_iteration += 1
                self.add_log("iteration", f"Iteration {self.state.current_iteration}: Analyzing...")
                
                iteration_start = time.time()
                
                # Analyze system (pass history BEFORE adding current iteration)
                analysis = self.task_analyzer.analyze_and_propose_task(
                    focus=self.custom_focus,
                    failed_suggestions=self.failed_suggestions,
                    iteration_history=self.iteration_history.copy()
                )
                
                if not analysis:
                    self.add_log("info", "No improvements needed")
                    await asyncio.sleep(2)
                    continue
                
                # Generate proposal
                proposal = self.proposal_generator.generate_proposal(analysis)
                
                if not proposal or not self._validate_proposal_structure(proposal):
                    self.add_log("error", "Failed to generate valid proposal")
                    # Add to history even on validation failure
                    self.iteration_history.append({
                        "iter": self.state.current_iteration,
                        "task": analysis.get('suggestion', 'Unknown')[:80],
                        "file": analysis.get('files_affected', ['unknown'])[0],
                        "result": "validation_fail",
                        "error": "Invalid proposal structure"
                    })
                    continue
                
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
                
                # Test in sandbox
                self.add_log("testing", "Running in sandbox...")
                sandbox_result = self.sandbox_tester.test_proposal(proposal, timeout=self.config.improvement.sandbox_timeout)
                
                if not sandbox_result['success']:
                    error_msg = sandbox_result.get('output', 'Unknown error')
                    self.add_log("error", f"Sandbox failed: {error_msg}")
                    
                    # Pass error to proposal generator with limit
                    self.proposal_generator.add_error(f"Sandbox: {error_msg}")
                    
                    # Track failures
                    suggestion_key = str(analysis.get('files_affected', []))
                    self.retry_count[suggestion_key] = self.retry_count.get(suggestion_key, 0) + 1
                    
                    if self.retry_count[suggestion_key] >= self.config.improvement.max_retries:
                        self.failed_suggestions.append(suggestion_key)
                        self.add_log("info", f"Marking as failed after {self.config.improvement.max_retries} attempts")
                        self.proposal_generator.clear_errors()
                    
                    # Add to history BEFORE next iteration
                    self.iteration_history.append({
                        "iter": self.state.current_iteration,
                        "task": proposal['description'][:80],
                        "file": proposal['files_changed'][0],
                        "result": "sandbox_fail",
                        "error": error_msg[:100]
                    })
                    
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
                    self.add_log("info", "Applying changes...")
                    apply_result = await self._apply_changes(proposal)
                    
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
                        "error": error_msg[:100] if error_msg else ""
                    })
                    
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
                
                if self.state.stop_requested:
                    self.add_log("stop", "Loop stopped gracefully")
                    break
                
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
        """Handle approval workflow"""
        proposal_id = f"proposal_{self.state.current_iteration:03d}"
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
            backup_path = None
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
            if 'backup_path' in locals() and backup_path and backup_path.exists():
                try:
                    shutil.copy2(backup_path, file_path)
                    self.add_log("error", f"Apply failed, rolled back: {e}")
                except:
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
    
    def approve_proposal(self, proposal_id: str) -> bool:
        """Approve pending proposal with locking"""
        if proposal_id in self.pending_approvals:
            # Check if already approved/rejected
            if self.pending_approvals[proposal_id].get('approved') is not None:
                return False  # Already processed
            self.pending_approvals[proposal_id]['approved'] = True
            return True
        return False
    
    def reject_proposal(self, proposal_id: str) -> bool:
        """Reject pending proposal with locking"""
        if proposal_id in self.pending_approvals:
            # Check if already approved/rejected
            if self.pending_approvals[proposal_id].get('approved') is not None:
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
