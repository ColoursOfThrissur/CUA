import json
from pathlib import Path

from core.baseline_health_checker import BaselineHealthChecker


def test_baseline_syntax_skips_pending_files(tmp_path: Path):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tools" / "experimental").mkdir(parents=True, exist_ok=True)

    broken_tool = tmp_path / "tools" / "experimental" / "BrokenPendingTool.py"
    broken_tool.write_text("```python\ninvalid", encoding="utf-8")

    pending_payload = {
        "pending": {
            "tool_1": {
                "tool_file": "tools/experimental/BrokenPendingTool.py",
                "test_file": None,
            }
        },
        "history": [],
    }
    (tmp_path / "data" / "pending_tools.json").write_text(
        json.dumps(pending_payload), encoding="utf-8"
    )

    checker = BaselineHealthChecker(repo_path=str(tmp_path))
    ok, errors = checker._check_syntax()

    assert ok is True
    assert errors == []
