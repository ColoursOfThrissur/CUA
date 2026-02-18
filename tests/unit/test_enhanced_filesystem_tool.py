import unittest
import os
import tempfile
from pathlib import Path
from tools.enhanced_filesystem_tool import FilesystemTool
from tools.tool_result import ToolResult, ResultStatus

class TestEnhancedFilesystemTool(unittest.TestCase):
    def setUp(self):
        self.tool = FilesystemTool()
        # Use workspace dir which is in allowed_roots
        self.test_dir = Path("./workspace/test_data")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.test_file = self.test_dir / "test.txt"
        self.test_file.write_text("test content")
    
    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_read_file(self):
        result = self.tool.execute("read_file", {"path": str(self.test_file)})
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.data, "test content")

    def test_read_file_outside_allowed_roots(self):
        result = self.tool.execute("read_file", {"path": "/etc/passwd"})
        self.assertEqual(result.status, ResultStatus.FAILURE)
        self.assertIn("outside allowed", result.error_message.lower())

    def test_write_file(self):
        new_file = self.test_dir / "new.txt"
        result = self.tool.execute("write_file", {"path": str(new_file), "content": "new content"})
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertTrue(new_file.exists())
        self.assertEqual(new_file.read_text(), "new content")

    def test_write_file_outside_allowed_roots(self):
        result = self.tool.execute("write_file", {"path": "/etc/test.txt", "content": "bad"})
        self.assertEqual(result.status, ResultStatus.FAILURE)
        self.assertIn("outside allowed", result.error_message.lower())

    def test_list_directory(self):
        result = self.tool.execute("list_directory", {"path": str(self.test_dir)})
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIn("test.txt", result.data)

    def test_list_directory_outside_allowed_roots(self):
        result = self.tool.execute("list_directory", {"path": "/etc"})
        self.assertEqual(result.status, ResultStatus.FAILURE)
        self.assertIn("outside allowed", result.error_message.lower())