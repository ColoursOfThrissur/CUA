import unittest
import json
from unittest.mock import MagicMock, patch
from tools.json_tool import JSONTool, ToolResult, ResultStatus

class TestJSONTool(unittest.TestCase):
    def setUp(self):
        self.tool = JSONTool()

    @patch("tools.json_tool.json")
    def test_parse_success(self, mock_json):
        mock_json.loads.return_value = {"key": "value"}
        params = {"text": '{"key": "value"}'}
        result = self.tool.execute("parse", params)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIsInstance(result.data, dict)
        self.assertEqual(result.data, {"key": "value"})

    def test_parse_failure(self):
        params = {"text": '{invalid json}'}
        result = self.tool.execute("parse", params)
        self.assertEqual(result.status, ResultStatus.FAILURE)
        self.assertIn("Invalid JSON", result.error_message)

    @patch("tools.json_tool.json")
    def test_stringify_success(self, mock_json):
        mock_json.dumps.return_value = '{"key": "value"}'
        params = {"data": {"key": "value"}}
        result = self.tool.execute("stringify", params)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIsInstance(result.data, str)
        self.assertEqual(result.data, '{"key": "value"}')

    def test_stringify_failure(self):
        params = {}
        result = self.tool.execute("stringify", params)
        self.assertEqual(result.status, ResultStatus.FAILURE)
        self.assertIn("Data required", result.error_message)

    def test_query_success(self):
        params = {"data": {"user": {"name": "Alice"}}, "path": "user.name"}
        result = self.tool.execute("query", params)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.data, "Alice")

    def test_query_failure(self):
        params = {"data": {"user": {"name": "Alice"}}, "path": "non-existent"}
        result = self.tool.execute("query", params)
        self.assertEqual(result.status, ResultStatus.FAILURE)
        self.assertIn("Query failed", result.error_message)

if __name__ == "__main__":
    unittest.main()