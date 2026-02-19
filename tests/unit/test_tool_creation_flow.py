from dataclasses import dataclass
from pathlib import Path

from core.tool_creation_flow import ToolCreationFlow


class FakeLLM:
    def __init__(self, code_responses, model="mistral:latest"):
        self.code_responses = list(code_responses)
        self.calls = 0
        self.model = model

    def _call_llm(self, prompt, temperature=0.3, expect_json=False):
        if expect_json:
            return '{"name":"DriftedTool","domain":"general","inputs":[],"outputs":[],"dependencies":[],"risk_level":0.1}'
        self.calls += 1
        if self.code_responses:
            return self.code_responses.pop(0)
        return None

    def _extract_json(self, _response):
        return {
            "name": "DriftedTool",
            "domain": "general",
            "inputs": [],
            "outputs": ["snapshot"],
            "dependencies": [],
            "risk_level": 0.1,
        }


@dataclass
class FakeCapabilityGraph:
    registered_name: str | None = None

    def register_tool(self, node):
        self.registered_name = node.tool_name
        return True, "ok"


class FakeBudget:
    def can_create_tool(self):
        return True

    def record_tool_creation(self):
        return None


@dataclass
class FakeExpansion:
    enabled: bool = True
    created_name: str | None = None
    created_code: str | None = None
    experimental_dir: str = "tools/experimental"

    def create_experimental_tool(self, tool_name, template):
        self.created_name = tool_name
        self.created_code = template
        exp_dir = Path(self.experimental_dir)
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / f"{tool_name}.py").write_text(template, encoding="utf-8")
        return True, f"Experimental tool created: {tool_name}"


def _valid_code(tool_name: str) -> str:
    class_name = "".join((part[:1].upper() + part[1:]) for part in tool_name.split("_"))
    return f'''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus

class {class_name}(BaseTool):
    def __init__(self):
        self.name = "{tool_name}"
        self.description = "desc"
        super().__init__()

    def register_capabilities(self):
        cap = ToolCapability(
            name="read",
            description="read",
            parameters=[],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._read)
        return list(self.get_capabilities().values())

    def execute(self, operation: str, **kwargs) -> ToolResult:
        return self.execute_capability(operation, **kwargs)

    def _read(self, **kwargs):
        return {{"ok": True}}
'''


def test_create_new_tool_honors_preferred_tool_name():
    tool_name = "TaskSnapshotTool"
    llm = FakeLLM([_valid_code(tool_name)])
    graph = FakeCapabilityGraph()
    expansion = FakeExpansion(experimental_dir="tests/tmp_tools")
    flow = ToolCreationFlow(graph, expansion, FakeBudget())

    success, msg = flow.create_new_tool(
        "build a snapshot tool",
        llm,
        bypass_budget=True,
        preferred_tool_name=tool_name,
    )

    assert success is True
    assert tool_name in msg
    assert graph.registered_name == tool_name
    assert expansion.created_name == tool_name
    (Path(expansion.experimental_dir) / f"{tool_name}.py").unlink(missing_ok=True)


def test_run_sandbox_fails_for_missing_file():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(experimental_dir="tests/missing_tools"), FakeBudget())
    assert flow._run_sandbox("NoSuchTool") is False


def test_run_sandbox_passes_for_valid_generated_tool(tmp_path):
    tool_name = "TaskSnapshotTool"
    tool_dir = tmp_path / "experimental"
    tool_dir.mkdir(parents=True, exist_ok=True)
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(experimental_dir=str(tool_dir)), FakeBudget())
    (tool_dir / f"{tool_name}.py").write_text(_valid_code(tool_name), encoding="utf-8")
    assert flow._run_sandbox(tool_name) is True


def test_validate_generated_tool_contract_rejects_self_capabilities_assignment():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        self.capabilities = []
    def execute(self, operation: str, **kwargs) -> ToolResult:
        return self.execute_capability(operation, **kwargs)
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "must not assign self.capabilities directly" in error


def test_fill_logic_retries_after_validation_failure():
    tool_name = "TaskSnapshotTool"
    bad = '''from tools.tool_interface import BaseTool
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        self.capabilities = []
    def execute(self, operation: str, **kwargs):
        return None
'''
    llm = FakeLLM([bad, _valid_code(tool_name)])
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    template = flow._scaffold_template({"name": tool_name, "description": "d"})

    output = flow._fill_logic(template, {"name": tool_name}, llm)

    assert output is not None
    assert llm.calls == 2


def test_validate_generated_tool_contract_rejects_parameter_without_description():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.tool_result import ToolResult
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        cap = ToolCapability(
            name="read",
            description="read",
            parameters=[Parameter(name="task_id", type=ParameterType.STRING, required=True)],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._read)
    def execute(self, operation: str, **kwargs) -> ToolResult:
        return self.execute_capability(operation, **kwargs)
    def _read(self, **kwargs):
        return {"ok": True}
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "must include description" in error


def test_validate_generated_tool_contract_rejects_tool_capability_operation_field():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.tool_result import ToolResult
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        cap = ToolCapability(
            operation="read",
            description="read",
            parameters=[Parameter(name="task_id", type=ParameterType.STRING, description="id")],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._read)
    def execute(self, operation: str, **kwargs) -> ToolResult:
        return self.execute_capability(operation, **kwargs)
    def _read(self, **kwargs):
        return {"ok": True}
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "must use name" in error


def test_validate_generated_tool_contract_rejects_tool_result_shortcut_fields():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, SafetyLevel
from tools.tool_result import ToolResult
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        cap = ToolCapability(
            name="read",
            description="read",
            parameters=[],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._read)
    def execute(self, operation: str, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={})
    def _read(self, **kwargs):
        return {"ok": True}
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "unsupported fields" in error


def test_qwen_flow_uses_staged_generation():
    tool_name = "TaskSnapshotTool"
    llm = FakeLLM(
        [_valid_code(tool_name), _valid_code(tool_name), _valid_code(tool_name)],
        model="qwen2.5-coder:14b",
    )
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    template = flow._scaffold_template({"name": tool_name, "description": "d"})

    output = flow._fill_logic(template, {"name": tool_name}, llm)

    assert output is not None
    assert llm.calls >= 2


def test_validate_generated_tool_contract_rejects_result_status_error():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        cap = ToolCapability(
            name="read",
            description="read",
            parameters=[],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._read)
    def execute(self, operation: str, **kwargs) -> ToolResult:
        return ToolResult(tool_name=self.name, capability_name=operation, status=ResultStatus.ERROR)
    def _read(self, **kwargs):
        return {"ok": True}
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "Unsupported ResultStatus.ERROR" in error


def test_validate_generated_tool_contract_rejects_mutable_defaults_and_relative_dir():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        self.output_dir = "./tmp"
        super().__init__()
    def register_capabilities(self):
        cap = ToolCapability(
            name="read",
            description="read",
            parameters=[],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._read)
    def execute(self, operation: str, **kwargs) -> ToolResult:
        return self.execute_capability(operation, **kwargs)
    def _read(self, tags=[]):
        return {"ok": True}
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert (
        "deterministic data/" in error
        or "mutable default argument" in error
    )


def test_extract_operations_respects_required_false_and_optional_true():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    prompt_spec = {
        "inputs": [
            {
                "operation": "create",
                "parameters": [
                    {"name": "contact_id", "type": "string", "required": True},
                    {"name": "phone", "type": "string", "required": False},
                    {"name": "tags", "type": "list", "optional": True},
                    {"name": "limit", "type": "integer", "default": 10},
                ],
            }
        ]
    }

    ops = flow._extract_operations_from_prompt_spec(prompt_spec)
    assert len(ops) == 1
    params = {p["name"]: p for p in ops[0]["parameters"]}
    assert params["contact_id"]["required"] is True
    assert params["phone"]["required"] is False
    assert params["tags"]["required"] is False
    assert params["limit"]["required"] is False
    assert params["limit"]["default"] == 10


def test_build_deterministic_scaffold_uses_normalized_required_flags():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    prompt_spec = {
        "inputs": [
            {
                "operation": "create",
                "parameters": [
                    {"name": "contact_id", "type": "string", "required": True},
                    {"name": "notes", "type": "string", "required": False},
                    {"name": "tags", "type": "list", "optional": True},
                ],
            }
        ]
    }
    code = flow._build_deterministic_stage1_scaffold(prompt_spec, {"name": "LocalContactCardTool"})

    assert "Parameter(name='contact_id'" in code and "required=True" in code
    assert "Parameter(name='notes'" in code and "required=False" in code
    assert "Parameter(name='tags'" in code and "required=False" in code
    assert "required_params = ['contact_id']" in code


def test_validate_generated_tool_contract_rejects_required_with_default():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.tool_result import ToolResult
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        cap = ToolCapability(
            name="list",
            description="list",
            parameters=[Parameter(name="limit", type=ParameterType.INTEGER, description="limit", required=True, default=10)],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._list)
    def execute(self, operation: str, **kwargs) -> ToolResult:
        return self.execute_capability(operation, **kwargs)
    def _list(self, **kwargs):
        return {"ok": True}
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "required=True when default is set" in error


def test_deterministic_stage1_scaffold_passes_validation_for_required_param_alignment():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    prompt_spec = {
        "inputs": [
            {
                "operation": "create",
                "parameters": [
                    {"name": "note_id", "type": "string", "required": True},
                    {"name": "text", "type": "string", "required": True},
                    {"name": "tags", "type": "list", "required": False},
                ],
            }
        ]
    }
    code = flow._build_deterministic_stage1_scaffold(prompt_spec, {"name": "LocalRunNoteTool"})
    ok, error = flow._validate_generated_tool_contract(code, {"name": "LocalRunNoteTool"})
    assert ok is True, error


def test_operation_contract_for_create_includes_exact_parameter_constraint():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    prompt_spec = {
        "inputs": [
            {
                "operation": "create",
                "parameters": [
                    {"name": "note_id", "type": "string", "required": True},
                    {"name": "text", "type": "string", "required": True},
                ],
            }
        ]
    }
    contract = flow._operation_contract_for_method(prompt_spec, "_handle_create")
    assert "Do not invent or rename parameter keys" in contract
    assert "\"note_id\"" in contract
    assert "\"text\"" in contract


def test_operation_contract_for_get_requires_persisted_storage_read():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    prompt_spec = {
        "inputs": [
            {"operation": "get", "parameters": [{"name": "note_id", "type": "string", "required": True}]}
        ]
    }
    contract = flow._operation_contract_for_method(prompt_spec, "_handle_get")
    assert "Read from persisted local storage under data/" in contract


def test_validate_generated_tool_contract_rejects_create_without_persistence_write():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        c = ToolCapability(
            name="create",
            description="c",
            parameters=[Parameter(name="id", type=ParameterType.STRING, description="id", required=True)],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(c, self._handle_create)
    def execute(self, operation: str, parameters: dict) -> ToolResult:
        return self._handle_create(**(parameters or {}))
    def _handle_create(self, **kwargs):
        if not kwargs.get("id"):
            return ToolResult(tool_name=self.name, capability_name="create", status=ResultStatus.FAILURE, data=None, error_message="missing")
        return ToolResult(tool_name=self.name, capability_name="create", status=ResultStatus.SUCCESS, data={"id": kwargs.get("id")})
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "must persist data to local storage" in error


def test_validate_generated_tool_contract_rejects_get_without_storage_read_when_create_exists():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from pathlib import Path
from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        c = ToolCapability(name="create", description="c", parameters=[Parameter(name="id", type=ParameterType.STRING, description="id", required=True)], returns="payload", safety_level=SafetyLevel.LOW, examples=[], dependencies=[])
        g = ToolCapability(name="get", description="g", parameters=[Parameter(name="id", type=ParameterType.STRING, description="id", required=True)], returns="payload", safety_level=SafetyLevel.LOW, examples=[], dependencies=[])
        self.add_capability(c, self._handle_create)
        self.add_capability(g, self._handle_get)
    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation == "create":
            return self._handle_create(**(parameters or {}))
        return self._handle_get(**(parameters or {}))
    def _handle_create(self, **kwargs):
        p = Path(f"data/contact_cards/{kwargs.get('id','x')}.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            f.write("{}")
        return ToolResult(tool_name=self.name, capability_name="create", status=ResultStatus.SUCCESS, data={})
    def _handle_get(self, **kwargs):
        records = {"x": {"id": "x"}}
        if kwargs.get("id") in records:
            return ToolResult(tool_name=self.name, capability_name="get", status=ResultStatus.SUCCESS, data=records[kwargs.get("id")])
        return ToolResult(tool_name=self.name, capability_name="get", status=ResultStatus.FAILURE, data=None, error_message="not found")
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "must read from persisted local storage" in error


def test_validate_generated_tool_contract_rejects_undefined_private_helper():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        cap = ToolCapability(
            name="list",
            description="list",
            parameters=[],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._handle_list)
    def execute(self, operation: str, parameters: dict) -> ToolResult:
        return self._handle_list(**(parameters or {}))
    def _handle_list(self, **kwargs):
        data = self._fetch_contacts(10, None)
        return ToolResult(tool_name=self.name, capability_name="list", status=ResultStatus.SUCCESS, data=data)
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "undefined helper '_fetch_contacts'" in error


def test_validate_generated_tool_contract_rejects_create_get_path_mismatch():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        c = ToolCapability(name="create", description="c", parameters=[], returns="payload", safety_level=SafetyLevel.LOW, examples=[], dependencies=[])
        g = ToolCapability(name="get", description="g", parameters=[], returns="payload", safety_level=SafetyLevel.LOW, examples=[], dependencies=[])
        self.add_capability(c, self._handle_create)
        self.add_capability(g, self._handle_get)
    def execute(self, operation: str, parameters: dict) -> ToolResult:
        if operation == "create":
            return self._handle_create(**(parameters or {}))
        return self._handle_get(**(parameters or {}))
    def _handle_create(self, **kwargs):
        with open(f"data/{kwargs.get('id','x')}.json", "w") as f:
            f.write("{}")
        return ToolResult(tool_name=self.name, capability_name="create", status=ResultStatus.SUCCESS, data={})
    def _handle_get(self, **kwargs):
        with open(f"data/contacts/{kwargs.get('id','x')}.json", "r") as f:
            data = f.read()
        return ToolResult(tool_name=self.name, capability_name="get", status=ResultStatus.SUCCESS, data=data)
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "Storage path mismatch" in error


def test_validate_generated_tool_contract_rejects_data_write_without_dir_prepare():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        c = ToolCapability(name="create", description="c", parameters=[], returns="payload", safety_level=SafetyLevel.LOW, examples=[], dependencies=[])
        self.add_capability(c, self._handle_create)
    def execute(self, operation: str, parameters: dict) -> ToolResult:
        return self._handle_create(**(parameters or {}))
    def _handle_create(self, **kwargs):
        with open(f"data/contact_cards/{kwargs.get('id','x')}.json", "w") as f:
            f.write("{}")
        return ToolResult(tool_name=self.name, capability_name="create", status=ResultStatus.SUCCESS, data={})
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "does not create directories first" in error


def test_validate_generated_tool_contract_accepts_data_write_with_dir_prepare():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from pathlib import Path
from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        c = ToolCapability(name="create", description="c", parameters=[], returns="payload", safety_level=SafetyLevel.LOW, examples=[], dependencies=[])
        self.add_capability(c, self._handle_create)
    def execute(self, operation: str, parameters: dict) -> ToolResult:
        return self._handle_create(**(parameters or {}))
    def _handle_create(self, **kwargs):
        p = Path(f"data/contact_cards/{kwargs.get('id','x')}.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            f.write("{}")
        return ToolResult(tool_name=self.name, capability_name="create", status=ResultStatus.SUCCESS, data={})
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is True


def test_validate_generated_tool_contract_rejects_isinstance_parametertype_usage():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        cap = ToolCapability(
            name="create",
            description="create",
            parameters=[Parameter(name="task_id", type=ParameterType.STRING, description="id", required=True)],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._handle_create)
    def execute(self, operation: str, parameters: dict) -> ToolResult:
        return self._handle_create(**(parameters or {}))
    def _handle_create(self, **kwargs):
        if not isinstance(kwargs.get("task_id"), ParameterType.STRING):
            return ToolResult(tool_name=self.name, capability_name="create", status=ResultStatus.FAILURE, data=None, error_message="bad")
        return ToolResult(tool_name=self.name, capability_name="create", status=ResultStatus.SUCCESS, data={})
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "isinstance(..., ParameterType." in error


def test_validate_generated_tool_contract_rejects_handler_required_param_drift():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        cap = ToolCapability(
            name="create",
            description="create",
            parameters=[
                Parameter(name="contact_id", type=ParameterType.STRING, description="id", required=True),
                Parameter(name="name", type=ParameterType.STRING, description="name", required=True),
                Parameter(name="email", type=ParameterType.STRING, description="email", required=True)
            ],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._handle_create)
    def execute(self, operation: str, parameters: dict) -> ToolResult:
        return self._handle_create(**(parameters or {}))
    def _handle_create(self, **kwargs):
        required_params = {"name": ParameterType.STRING, "phone_number": ParameterType.STRING, "email": ParameterType.STRING}
        for k in required_params:
            if not kwargs.get(k):
                return ToolResult(tool_name=self.name, capability_name="create", status=ResultStatus.FAILURE, data=None, error_message="bad")
        return ToolResult(tool_name=self.name, capability_name="create", status=ResultStatus.SUCCESS, data={})
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "unknown required keys" in error or "does not reference required capability parameters" in error


def test_validate_generated_tool_contract_rejects_static_mock_list_handler():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, SafetyLevel
from tools.tool_result import ToolResult, ResultStatus
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
    def register_capabilities(self):
        cap = ToolCapability(
            name="list",
            description="list",
            parameters=[],
            returns="payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(cap, self._handle_list)
    def execute(self, operation: str, parameters: dict) -> ToolResult:
        return self._handle_list(**(parameters or {}))
    def _handle_list(self, **kwargs):
        contacts = [{"name": "Alice"}, {"name": "Bob"}]
        return ToolResult(tool_name=self.name, capability_name="list", status=ResultStatus.SUCCESS, data=contacts)
'''
    ok, error = flow._validate_generated_tool_contract(code, {"name": "TaskSnapshotTool"})
    assert ok is False
    assert "hardcoded mock records" in error


def test_repair_missing_symbol_import_inserts_path_import():
    flow = ToolCreationFlow(FakeCapabilityGraph(), FakeExpansion(), FakeBudget())
    code = '''"""tool"""
from tools.tool_interface import BaseTool
class TaskSnapshotTool(BaseTool):
    def __init__(self):
        self.name = "TaskSnapshotTool"
        super().__init__()
'''
    repaired = flow._repair_missing_symbol_import(code, "Path")
    assert repaired is not None
    assert "from pathlib import Path" in repaired
