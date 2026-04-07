from __future__ import annotations

from typing import Optional

from application.commands.command_models import CommandContext, CommandResult
from application.commands.command_registry import CommandRegistry
from application.commands.builtin.system_commands import builtin_commands

_registry: Optional[CommandRegistry] = None


def get_command_registry() -> CommandRegistry:
    global _registry
    if _registry is None:
        _registry = CommandRegistry()
        for command in builtin_commands():
            _registry.register(command)
    return _registry


def try_execute_command(context: CommandContext) -> Optional[CommandResult]:
    message = (context.request_message or "").strip()
    if not message.startswith("/"):
        return None

    body = message[1:].strip()
    if not body:
        registry = get_command_registry()
        names = ", ".join(f"/{cmd.name}" for cmd in registry.list_unique())
        return CommandResult(
            response_text=f"Available commands: {names}",
            execution_result={"success": True, "mode": "command", "command": "help"},
        )

    name, _, args = body.partition(" ")
    command = get_command_registry().get(name.lower())
    if command is None:
        names = ", ".join(f"/{cmd.name}" for cmd in get_command_registry().list_unique())
        return CommandResult(
            response_text=f"Unknown command '/{name}'. Available commands: {names}",
            success=False,
            execution_result={
                "success": False,
                "mode": "command",
                "command": name.lower(),
                "error": "unknown_command",
            },
        )

    permission_gate = getattr(context.runtime, "permission_gate", None)
    if permission_gate and hasattr(permission_gate, "check_command_permission"):
        permission = permission_gate.check_command_permission(
            context.session_id,
            command.name,
            allowed_tools=command.allowed_tools,
        )
        if not permission.is_valid:
            return CommandResult(
                response_text=f"Command '/{command.name}' blocked: {permission.reason}",
                success=False,
                execution_result={
                    "success": False,
                    "mode": "command",
                    "command": command.name,
                    "error": "permission_denied",
                    "reason": permission.reason,
                    "risk_level": getattr(permission.risk_level, "value", str(permission.risk_level)),
                },
            )

    result = command.handler(context, args.strip())
    result.execution_result.setdefault("success", result.success)
    result.execution_result.setdefault("mode", "command")
    result.execution_result.setdefault("command", command.name)
    if permission_gate and hasattr(permission_gate, "record_command"):
        permission_gate.record_command(context.session_id, command.name, result.success)
    return result
