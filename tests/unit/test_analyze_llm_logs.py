import sys
import pytest
from pathlib import Path
import json
from collections import Counter

from tools.analyze_llm_logs import analyze_session

# Sample data for testing
SAMPLE_DATA_DIR = Path(__file__).parent / "sample_data"
SAMPLE_SESSION_FILE = SAMPLE_DATA_DIR / "sample_session.jsonl"

def test_analyze_session():
    analyze_session(str(SAMPLE_SESSION_FILE))

    expected_output = """
=== Session Analysis: sample_session.jsonl ===
Total interactions: 5

Phases:
  interaction: 3
  validation: 2
Validation Failures: 2
  LLMException: 1
  InvalidInputError: 1
Temperature: avg=0.7, min=0.6, max=0.8
Target files:
  target_file_1: 3
  target_file_2: 2
"""

    with open(SAMPLE_SESSION_FILE, 'r', encoding='utf-8') as f:
        lines = [line for line in f]
        assert len(lines) == 5

    with open("output.txt", "w", encoding="utf-8") as output_file:
        analyze_session(str(SAMPLE_SESSION_FILE))
        with open("expected_output.txt", "r", encoding="utf-8") as expected_file:
            assert output_file.read() == expected_file.read()

def test_no_session_logs():
    logs_dir = Path("non_existent_logs_directory")
    with pytest.raises(FileNotFoundError):
        analyze_session(str(logs_dir))

if __name__ == "__main__":
    pytest.main([__file__])