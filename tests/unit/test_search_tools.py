from pathlib import Path

from tools.glob_tool import GlobTool
from tools.grep_tool import GrepTool


def test_glob_tool_finds_matching_files(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")

    tool = GlobTool(allowed_roots=[str(tmp_path)])
    result = tool.execute("glob", {"root": str(tmp_path), "pattern": "**/*.py"})

    assert result.is_success()
    assert result.data["matches"] == ["src/main.py"]
    assert result.data["truncated"] is False


def test_glob_tool_rejects_paths_outside_allowed_roots(tmp_path):
    tool = GlobTool(allowed_roots=[str(tmp_path)])
    outside = Path(tmp_path).parent

    result = tool.execute("glob", {"root": str(outside), "pattern": "*.py"})

    assert result.is_failure()
    assert "outside allowed roots" in result.error_message


def test_grep_tool_finds_matching_lines(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "service.py").write_text(
        "def handler():\n    # TODO: tighten validation\n    return True\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "ignore.txt").write_text("TODO but not in python filter\n", encoding="utf-8")

    tool = GrepTool(allowed_roots=[str(tmp_path)])
    result = tool.execute(
        "grep",
        {
            "root": str(tmp_path),
            "query": "TODO",
            "file_pattern": "**/*.py",
        },
    )

    assert result.is_success()
    assert result.data["match_count"] == 1
    assert result.data["matches"][0]["path"] == "pkg/service.py"
    assert result.data["matches"][0]["line_number"] == 2


def test_grep_tool_supports_case_sensitive_regex(tmp_path):
    (tmp_path / "app.py").write_text("ValueError\nvalueerror\n", encoding="utf-8")

    tool = GrepTool(allowed_roots=[str(tmp_path)])
    result = tool.execute(
        "grep",
        {
            "root": str(tmp_path),
            "query": "^ValueError$",
            "regex": True,
            "case_sensitive": True,
            "file_pattern": "*.py",
        },
    )

    assert result.is_success()
    assert result.data["match_count"] == 1
    assert result.data["matches"][0]["line_text"] == "ValueError"
