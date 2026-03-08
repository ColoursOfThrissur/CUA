from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class UserApprovalGateTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "Automation and Security"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        self._cache = {}
        super().__init__()

    def register_capabilities(self):
        request_approval_capability = ToolCapability(
            name="request_approval",
            description="Operation: request_approval",
            parameters=[
                Parameter(name="action_description", type=ParameterType.STRING, description="Description of the autonomous/automated action requiring approval.", required=True),
                Parameter(name="user_id", type=ParameterType.STRING, description="ID of the user who needs to approve the action.", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.ids", "self.services.time", "self.services.logging"],
        )
        self.add_capability(request_approval_capability, self._handle_request_approval)

        log_approval_capability = ToolCapability(
            name="log_approval",
            description="Operation: log_approval",
            parameters=[
                Parameter(name="approval_id", type=ParameterType.STRING, description="Unique ID for the approval request.", required=True),
                Parameter(name="status", type=ParameterType.STRING, description="Status of the approval (e.g., approved, denied).", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.time", "self.services.logging"],
        )
        self.add_capability(log_approval_capability, self._handle_log_approval)

        configure_policy_capability = ToolCapability(
            name="configure_policy",
            description="Operation: configure_policy",
            parameters=[
                Parameter(name="policy_name", type=ParameterType.STRING, description="Name of the policy to configure.", required=True),
                Parameter(name="rules", type=ParameterType.DICT, description="JSON object defining the rules for the policy.", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.time", "self.services.logging"],
        )
        self.add_capability(configure_policy_capability, self._handle_configure_policy)

        check_policy_capability = ToolCapability(
            name="check_policy",
            description="Operation: check_policy",
            parameters=[
                Parameter(name="action_description", type=ParameterType.STRING, description="Description of the autonomous/automated action to check against policies.", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.MEDIUM,
            examples=[{}],
            dependencies=["self.services.storage", "self.services.time", "self.services.logging"],
        )
        self.add_capability(check_policy_capability, self._handle_check_policy)

    def execute(self, operation: str, **kwargs):
        return self.execute_capability(operation, **kwargs)

    def _handle_request_approval(self, **kwargs):
        action_description = (kwargs.get("action_description") or "").strip()
        user_id = (kwargs.get("user_id") or "").strip()

        if not action_description:
            return {"success": False, "error": "action_description is required", "data": None}
        if not user_id:
            return {"success": False, "error": "user_id is required", "data": None}

        approval_id = self.services.ids.generate("approval")
        now = self.services.time.now_utc_iso()

        policy_check = self._evaluate_policies(action_description)

        record = {
            "record_type": "approval_request",
            "approval_id": approval_id,
            "action_description": action_description,
            "user_id": user_id,
            "status": "pending",
            "requested_at_utc": now,
            "policy_check": policy_check,
        }

        saved = self.services.storage.save(approval_id, record)
        self.services.logging.info("Approval requested", approval_id=approval_id, user_id=user_id)

        return {"success": True, "data": {"approval_id": approval_id, "request": saved}, "error": None}

    def _handle_log_approval(self, **kwargs):
        approval_id = (kwargs.get("approval_id") or "").strip()
        status = (kwargs.get("status") or "").strip().lower()

        if not approval_id:
            return {"success": False, "error": "approval_id is required", "data": None}
        if not status:
            return {"success": False, "error": "status is required", "data": None}

        allowed = {"approved", "denied", "pending", "cancelled"}
        if status not in allowed:
            return {"success": False, "error": f"Unsupported status '{status}'. Allowed: {sorted(allowed)}", "data": None}

        if not self.services.storage.exists(approval_id):
            return {"success": False, "error": f"Approval request not found: {approval_id}", "data": None}

        updated = self.services.storage.update(
            approval_id,
            {
                "status": status,
                "resolved_at_utc": self.services.time.now_utc_iso(),
            },
        )

        # Add a small immutable audit event record.
        event_id = self.services.ids.generate("approval_event")
        self.services.storage.save(
            event_id,
            {
                "record_type": "approval_event",
                "approval_id": approval_id,
                "status": status,
                "event_at_utc": self.services.time.now_utc_iso(),
            },
        )

        self.services.logging.info("Approval status updated", approval_id=approval_id, status=status)
        return {"success": True, "data": {"approval_id": approval_id, "updated": updated}, "error": None}

    def _handle_configure_policy(self, **kwargs):
        policy_name = (kwargs.get("policy_name") or "").strip()
        rules = kwargs.get("rules")

        if not policy_name:
            return {"success": False, "error": "policy_name is required", "data": None}
        if not isinstance(rules, dict):
            return {"success": False, "error": "rules must be a dict", "data": None}

        policy_id = f"policy_{self._safe_key(policy_name)}"
        now = self.services.time.now_utc_iso()

        record = {
            "record_type": "policy",
            "policy_id": policy_id,
            "policy_name": policy_name,
            "rules": rules,
            "configured_at_utc": now,
        }

        # Upsert (save overwrites path by id).
        saved = self.services.storage.save(policy_id, record)
        self.services.logging.info("Policy configured", policy_id=policy_id, policy_name=policy_name)
        return {"success": True, "data": {"policy_id": policy_id, "policy": saved}, "error": None}

    def _handle_check_policy(self, **kwargs):
        action_description = (kwargs.get("action_description") or "").strip()
        if not action_description:
            return {"success": False, "error": "action_description is required", "data": None}

        evaluation = self._evaluate_policies(action_description)
        return {"success": True, "data": evaluation, "error": None}

    def _evaluate_policies(self, action_description: str) -> dict:
        """Evaluate policies deterministically using simple keyword matching rules."""
        desc = (action_description or "").lower()

        # Load all stored policies for this tool.
        policies = self.services.storage.find(lambda r: isinstance(r, dict) and r.get("record_type") == "policy", limit=200)

        matched = []
        requires_approval = False

        for policy in policies:
            rules = policy.get("rules") if isinstance(policy, dict) else None
            if not isinstance(rules, dict):
                continue

            keywords = rules.get("keywords", [])
            if isinstance(keywords, str):
                keywords = [keywords]
            if not isinstance(keywords, list):
                keywords = []

            keywords_norm = [str(k).strip().lower() for k in keywords if str(k).strip()]
            match_mode = str(rules.get("match", "any")).strip().lower()
            if match_mode not in {"any", "all"}:
                match_mode = "any"

            if not keywords_norm:
                is_match = bool(rules.get("requires_approval", False))
            else:
                if match_mode == "all":
                    is_match = all(k in desc for k in keywords_norm)
                else:
                    is_match = any(k in desc for k in keywords_norm)

            if not is_match:
                continue

            matched.append(
                {
                    "policy_id": policy.get("policy_id"),
                    "policy_name": policy.get("policy_name"),
                    "rules": rules,
                }
            )
            if bool(rules.get("requires_approval", True)):
                requires_approval = True

        return {
            "action_description": action_description,
            "policies_evaluated": len(policies),
            "matched_policies": matched,
            "requires_approval": requires_approval,
            "evaluated_at_utc": self.services.time.now_utc_iso(),
        }

    @staticmethod
    def _safe_key(value: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in (value or ""))
        cleaned = cleaned.strip("_") or "policy"
        return cleaned[:120]
