from application.services.context_compactor import ContextCompactor
from application.services.diff_payload import build_diff_payload


def test_context_compactor_summarizes_older_messages():
    messages = [
        {"role": "user", "content": "first request"},
        {"role": "assistant", "content": "first response"},
        {"role": "user", "content": "second request"},
        {"role": "assistant", "content": "second response"},
        {"role": "user", "content": "latest request"},
        {"role": "assistant", "content": "latest response"},
    ]

    result = ContextCompactor().compact_messages(messages, active_goal="ship phase 5", keep_recent=2)

    assert result["compacted"] is True
    assert result["removed_count"] == 4
    assert len(result["retained_messages"]) == 2
    assert "Active goal: ship phase 5" in result["summary_text"]
    assert "Earlier user requests:" in result["summary_text"]


def test_build_diff_payload_extracts_files_and_stats():
    patch = "\n".join(
        [
            "diff --git a/api/server.py b/api/server.py",
            "--- a/api/server.py",
            "+++ b/api/server.py",
            "@@ -1,2 +1,3 @@",
            " import os",
            "+print('debug')",
            "-return False",
        ]
    )

    payload = build_diff_payload(patch)

    assert payload["stats"]["files_changed"] == 1
    assert payload["stats"]["additions"] == 1
    assert payload["stats"]["deletions"] == 1
    assert payload["files"][0]["path"] == "api/server.py"
    assert any(line["type"] == "add" for line in payload["lines"])
