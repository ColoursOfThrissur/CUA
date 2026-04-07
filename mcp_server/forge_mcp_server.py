"""Read-only Forge MCP server exposed over stdio JSON-RPC."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class ForgeMCPServer:
    """Minimal MCP server that exposes Forge inspection tools."""

    PROTOCOL_VERSION = "2024-11-05"

    def __init__(self) -> None:
        self._tool_handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
            "forge_health": self._tool_forge_health,
            "forge_sessions": self._tool_forge_sessions,
            "forge_tasks": self._tool_forge_tasks,
            "forge_skills": self._tool_forge_skills,
            "forge_recent_executions": self._tool_forge_recent_executions,
            "forge_observability_summary": self._tool_forge_observability_summary,
            "forge_mcp_configured": self._tool_forge_mcp_configured,
        }

    def initialize(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "forge-mcp-server", "version": "1.0.0"},
        }

    def list_tools(self) -> Dict[str, Any]:
        return {
            "tools": [
                {
                    "name": "forge_health",
                    "description": "Read-only summary of Forge runtime health inferred from local state.",
                    "inputSchema": {"type": "object", "properties": {}},
                },
                {
                    "name": "forge_sessions",
                    "description": "List recent Forge sessions from cua.db.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Maximum sessions to return", "default": 10}
                        },
                    },
                },
                {
                    "name": "forge_tasks",
                    "description": "List recent persistent task artifacts from cua.db.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Maximum tasks to return", "default": 10},
                            "session_id": {"type": "string", "description": "Optional session filter"},
                        },
                    },
                },
                {
                    "name": "forge_skills",
                    "description": "List currently loadable Forge skills from the local skill registry.",
                    "inputSchema": {"type": "object", "properties": {}},
                },
                {
                    "name": "forge_recent_executions",
                    "description": "List recent tool executions recorded in cua.db.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Maximum executions to return", "default": 10}
                        },
                    },
                },
                {
                    "name": "forge_observability_summary",
                    "description": "Return high-level counts from core observability tables in cua.db.",
                    "inputSchema": {"type": "object", "properties": {}},
                },
                {
                    "name": "forge_mcp_configured",
                    "description": "List MCP servers configured for Forge from config.yaml.",
                    "inputSchema": {"type": "object", "properties": {}},
                },
            ]
        }

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        handler = self._tool_handlers.get(name)
        if handler is None:
            return self._tool_error(f"Unknown tool '{name}'")
        try:
            payload = handler(arguments or {})
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(payload, indent=2, ensure_ascii=True),
                    }
                ],
                "isError": False,
            }
        except Exception as exc:
            return self._tool_error(str(exc))

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        method = request.get("method")
        params = request.get("params") or {}
        request_id = request.get("id")

        if method == "initialize":
            result = self.initialize(params)
        elif method == "tools/list":
            result = self.list_tools()
        elif method == "tools/call":
            result = self.call_tool(params.get("name", ""), params.get("arguments") or {})
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def serve_stdio(self) -> None:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
            except Exception as exc:
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse or execution error: {exc}"},
                }
            sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
            sys.stdout.flush()

    def _tool_forge_health(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from infrastructure.persistence.credential_store import get_credential_store
        from infrastructure.persistence.sqlite.cua_database import DB_PATH, get_conn

        db_reachable = False
        session_count = 0
        conversation_count = 0
        task_count = 0
        with get_conn() as conn:
            db_reachable = True
            session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            conversation_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            task_count = conn.execute("SELECT COUNT(*) FROM task_artifacts").fetchone()[0]

        credential_store = get_credential_store()
        skills = self._tool_forge_skills({})
        configured_mcp = self._tool_forge_mcp_configured({})
        return {
            "status": "healthy" if db_reachable else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "db_path": str(DB_PATH),
            "db_exists": DB_PATH.exists(),
            "db_reachable": db_reachable,
            "session_count": session_count,
            "conversation_count": conversation_count,
            "task_count": task_count,
            "skill_count": skills["count"],
            "configured_mcp_servers": configured_mcp["total"],
            "credential_count": len(credential_store.list_keys()),
        }

    def _tool_forge_sessions(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from infrastructure.persistence.sqlite.cua_database import get_conn

        limit = max(1, int(arguments.get("limit", 10) or 10))
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT s.session_id, s.active_goal, s.created_at, s.updated_at,
                       COUNT(c.id) as message_count
                FROM sessions s
                LEFT JOIN conversations c ON s.session_id = c.session_id
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        sessions = [
            {
                "session_id": row["session_id"],
                "active_goal": row["active_goal"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "message_count": row["message_count"],
            }
            for row in rows
        ]
        return {"sessions": sessions, "count": len(sessions)}

    def _tool_forge_tasks(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from infrastructure.persistence.sqlite.cua_database import get_conn

        limit = max(1, int(arguments.get("limit", 10) or 10))
        session_id = (arguments.get("session_id") or "").strip()
        query = "SELECT * FROM task_artifacts"
        params: List[Any] = []
        if session_id:
            query += " WHERE session_id = ?"
            params.append(session_id)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with get_conn() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        tasks = [
            {
                "task_id": row["task_id"],
                "session_id": row["session_id"],
                "execution_id": row["execution_id"],
                "status": row["status"],
                "description": row["description"],
                "goal": row["goal"],
                "priority": row["priority"],
                "total_subtasks": row["total_subtasks"],
                "completed_subtasks": row["completed_subtasks"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
        return {"tasks": tasks, "count": len(tasks)}

    def _tool_forge_skills(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from application.services.skill_registry import SkillRegistry

        registry = SkillRegistry()
        registry.load_all()
        skills = registry.list_all()
        serialized = [
            {
                "name": skill.name,
                "category": skill.category,
                "description": skill.description,
                "preferred_tools": list(skill.preferred_tools or []),
                "verification_mode": skill.verification_mode,
            }
            for skill in skills
        ]
        return {"skills": serialized, "count": len(serialized)}

    def _tool_forge_recent_executions(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from infrastructure.persistence.sqlite.cua_database import get_conn

        limit = max(1, int(arguments.get("limit", 10) or 10))
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT tool_name, operation, success, error, execution_time_ms, timestamp
                FROM executions
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        executions = [
            {
                "tool_name": row["tool_name"],
                "operation": row["operation"],
                "success": bool(row["success"]),
                "error": row["error"],
                "execution_time_ms": row["execution_time_ms"],
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]
        return {"executions": executions, "count": len(executions)}

    def _tool_forge_observability_summary(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from infrastructure.persistence.sqlite.cua_database import get_conn

        tables = [
            "executions",
            "conversations",
            "sessions",
            "task_artifacts",
            "worktree_events",
            "tool_creations",
            "evolution_runs",
            "resolved_gaps",
        ]
        counts: Dict[str, int] = {}
        with get_conn() as conn:
            for table in tables:
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return {"counts": counts}

    def _tool_forge_mcp_configured(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from shared.config.config_manager import get_config

            servers = get_config().mcp_servers or []
        except Exception:
            servers = []
        payload = [
            {
                "name": server.name,
                "enabled": getattr(server, "enabled", False),
                "transport": getattr(server, "transport", "stdio"),
                "command": getattr(server, "command", ""),
                "url": getattr(server, "url", ""),
                "env_key": getattr(server, "env_key", "") or None,
            }
            for server in servers
        ]
        return {"servers": payload, "total": len(payload)}

    def _tool_error(self, message: str) -> Dict[str, Any]:
        return {"content": [{"type": "text", "text": message}], "isError": True}


def main() -> None:
    ForgeMCPServer().serve_stdio()


if __name__ == "__main__":
    main()
