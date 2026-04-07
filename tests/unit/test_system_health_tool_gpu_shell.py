from types import SimpleNamespace


def test_system_health_tool_uses_shell_service_for_gpu_stats():
    from tools.experimental.SystemHealthTool import SystemHealthTool

    class FakeShell:
        def __init__(self):
            self.commands = []

        def execute(self, command):
            self.commands.append(command)
            return {
                "success": True,
                "stdout": "RTX 4090, 1024, 24576, 12\n",
                "stderr": "",
                "exit_code": 0,
            }

    shell = FakeShell()
    tool = SystemHealthTool(orchestrator=None)
    tool.services = SimpleNamespace(shell=shell)

    gpu = tool._get_gpu_stats()

    assert shell.commands == [
        "nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits"
    ]
    assert gpu == {
        "name": "RTX 4090",
        "memory_used_mb": 1024,
        "memory_total_mb": 24576,
        "utilization_pct": 12,
    }
