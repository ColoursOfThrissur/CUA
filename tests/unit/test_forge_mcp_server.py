import json
from uuid import uuid4

from mcp_server.forge_mcp_server import ForgeMCPServer
from infrastructure.persistence.sqlite.cua_database import get_conn


def test_forge_mcp_server_lists_tools():
    server = ForgeMCPServer()

    result = server.list_tools()

    names = {tool["name"] for tool in result["tools"]}
    assert "forge_health" in names
    assert "forge_sessions" in names
    assert "forge_mcp_configured" in names


def test_forge_mcp_server_can_return_sessions_and_tasks():
    session_id = f"mcp-server-{uuid4().hex[:8]}"
    session_created_at = "9999-04-04T00:00:00"
    session_updated_at = "9999-04-04T00:00:01"
    task_created_at = "9999-04-04T00:00:02"
    task_updated_at = "9999-04-04T00:00:03"
    with get_conn() as conn:
        conn.execute("DELETE FROM task_artifacts WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.execute(
            "INSERT INTO sessions (session_id, user_preferences, active_goal, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, "{}", "inspect forge", session_created_at, session_updated_at),
        )
        conn.execute(
            "INSERT INTO conversations (session_id, timestamp, role, content, metadata) VALUES (?, ?, ?, ?, ?)",
            (session_id, 1.0, "user", "hello forge", None),
        )
        conn.execute(
            """
            INSERT INTO task_artifacts (
                task_id, session_id, execution_id, status, description, goal, priority, source,
                target_file, total_subtasks, completed_subtasks, plan_json, step_results_json,
                created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"task-{session_id}",
                session_id,
                None,
                "awaiting_approval",
                "Inspect Forge",
                "Inspect Forge",
                "normal",
                "unit_test",
                "",
                1,
                0,
                "{}",
                "[]",
                task_created_at,
                task_updated_at,
                None,
            ),
        )

    server = ForgeMCPServer()
    sessions_result = server.call_tool("forge_sessions", {"limit": 250})
    tasks_result = server.call_tool("forge_tasks", {"session_id": session_id, "limit": 5})

    sessions_payload = json.loads(sessions_result["content"][0]["text"])
    tasks_payload = json.loads(tasks_result["content"][0]["text"])

    assert sessions_result["isError"] is False
    assert any(item["session_id"] == session_id for item in sessions_payload["sessions"])
    assert tasks_result["isError"] is False
    assert tasks_payload["tasks"][0]["session_id"] == session_id


def test_forge_mcp_server_handles_rpc_request():
    server = ForgeMCPServer()

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "forge_observability_summary", "arguments": {}},
        }
    )

    assert response["id"] == 7
    payload = response["result"]
    assert payload["isError"] is False
