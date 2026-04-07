from __future__ import annotations

from typing import Dict, Iterable, Optional

from application.commands.command_models import CommandDefinition


class CommandRegistry:
    """Registry of user-facing slash commands."""

    def __init__(self) -> None:
        self._commands: Dict[str, CommandDefinition] = {}

    def register(self, command: CommandDefinition) -> None:
        self._commands[command.name] = command
        for alias in command.aliases:
            self._commands[alias] = command

    def get(self, name: str) -> Optional[CommandDefinition]:
        return self._commands.get((name or "").strip().lower())

    def list_unique(self) -> Iterable[CommandDefinition]:
        seen = set()
        for command in self._commands.values():
            if command.name in seen:
                continue
            seen.add(command.name)
            yield command
