"""
Tests for http_tool
"""
import unittest
from unittest.mock import patch
from tools.http_tool import HTTPTool, ToolResult, ResultStatus

class TestHTTPTool(unittest.TestCase):
    def setUp(self):
        self.tool = HTTPTool()

    @patch('requests.get')
    @patch('requests.post')
    def test_get_success(self, mock_post, mock_get):
        # Arrange
        url = "http://localhost:8000/health"
        params = {"url": url}
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "Test response body"

        # Act
        result = self.tool.execute("get", params)

        # Assert
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIn("status", result.data)
        self.assertIn("body", result.data)
        mock_get.assert_called_once_with(url, timeout=10)

    @patch('requests.get')
    def test_get_failure(self, mock_get):
        # Arrange
        url = "http://notallowed.com"
        params = {"url": url}

        # Act
        result = self.tool.execute("get", params)

        # Assert
        self.assertEqual(result.status, ResultStatus.FAILURE)
        self.assertIn("URL not allowed", result.error_message)
        mock_get.assert_called_once_with(url, timeout=10)

    @patch('requests.post')
    def test_post_success(self, mock_post):
        # Arrange
        url = "http://localhost:8000/api"
        params = {"url": url, "data": {}}
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = "Test response body"

        # Act
        result = self.tool.execute("post", params)

        # Assert
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIn("status", result.data)
        self.assertIn("body", result.data)
        mock_post.assert_called_once_with(url, json={}, timeout=10)

    @patch('requests.post')
    def test_post_failure(self, mock_post):
        # Arrange
        url = "http://localhost:8000/api"
        params = {"url": url, "data": {}}

        # Act
        result = self.tool.execute("post", params)

        # Assert
        self.assertEqual(result.status, ResultStatus.FAILURE)
        mock_post.assert_called_once_with(url, json={}, timeout=10)

if __name__ == "__main__":
    unittest.main()