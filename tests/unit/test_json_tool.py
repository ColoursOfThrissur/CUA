import unittest
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

    @patch("tools.json_tool.json")
    def test_parse_failure(self, mock_json):
        mock_json.loads.side_effect = json.JSONDecodeError("Invalid JSON", '{"invalid": 1}', 2)
        params = {"text": '{"invalid": 1}'}
        result = self.tool.execute("parse", params)
        self.assertEqual(result.status, ResultStatus.FAILURE)
        self.assertIsInstance(result.error_message, str)
        self.assertEqual(result.error_message, "Invalid JSON: Invalid syntax (2): line 1 column 6 - line 1 column 9 (char 5): expected separator ',' or '}'")

    @patch("tools.json_tool.json")
    def test_stringify_success(self, mock_json):
        mock_json.dumps.return_value = '{"key": "value"}'
        params = {"data": {"key": "value"}}
        result = self.tool.execute("stringify", params)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIsInstance(result.data, str)
        self.assertEqual(result.data, '{"key": "value"}')

    @patch("tools.json_tool.json")
    def test_stringify_failure(self, mock_json):
        mock_json.dumps.side_effect = Exception("Unexpected error")
        params = {"data": None}
        result = self.tool.execute("stringify", params)
        self.assertEqual(result.status, ResultStatus.FAILURE)
        self.assertIsInstance(result.error_message, str)
        self.assertEqual(result.error_message, "Unexpected error")

    @patch("tools.json_tool.json")
    def test_query_success(self, mock_json):
        mock_data = {"user": {"name": "Alice"}}
        mock_json.loads.return_value = mock_data
        params = {"data": '{"user": {"name": "Alice"}}', "path": "user.name"}
        result = self.tool.execute("query", params)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIsInstance(result.data, str)
        self.assertEqual(result.data, "Alice")

    @patch("tools.json_tool.json")
    def test_query_failure(self, mock_json):
        mock_data = {"user": {"name": "Alice"}}
        mock_json.loads.return_value = mock_data
        params = {"data": '{"user": {"name": "Alice"}}', "path": "non-existent"}
        result = self.tool.execute("query", params)
        self.assertEqual(result.status, ResultStatus.FAILURE)
        self.assertIsInstance(result.error_message, str)
        self.assertEqual(result.error_message, "Query failed: KeyError('non-existent')")

if __name__ == "__main__":
    unittest.main()