import unittest
from unittest.mock import MagicMock, patch
from tools.enhanced_filesystem_tool import FilesystemTool

class TestEnhancedFilesystemTool(unittest.TestCase):
    def setUp(self):
        self.tool = FilesystemTool()

    @patch('os.path.abspath')
    @patch('os.path.normpath')
    @patch('os.listdir')
    def test_read_file(self, mock_listdir, mock_normpath, mock_abspath):
        # Arrange
        mock_abspath.side_effect = ["./test_data", "./test_data"]
        mock_listdir.return_value = ["test_file.txt"]
        with open("./test_data/test_file.txt", "r") as f:
            content = f.read()

        params = {"path": "./test_data/test_file.txt"}

        # Act
        result = self.tool.execute("read_file", params)

        # Assert
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.data, content)

    @patch('os.path.abspath')
    @patch('os.path.normpath')
    def test_read_file_outside_allowed_roots(self, mock_normpath, mock_abspath):
        # Arrange
        mock_abspath.side_effect = ["/root/test_data", "./test_data"]

        params = {"path": "/root/test_file.txt"}

        # Act and Assert
        with self.assertRaises(ValueError):
            self.tool.execute("read_file", params)

    @patch('os.path.abspath')
    @patch('os.path.normpath')
    @patch('os.listdir')
    def test_write_file(self, mock_listdir, mock_normpath, mock_abspath):
        # Arrange
        mock_abspath.side_effect = ["./test_output", "./test_output"]
        mock_listdir.return_value = []

        params = {"path": "./test_output/test_file.txt", "content": "Test content"}

        # Act
        result = self.tool.execute("write_file", params)

        # Assert
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIn("Successfully wrote", result.data)
        self.assertTrue(os.path.exists("./test_output/test_file.txt"))

    @patch('os.path.abspath')
    @patch('os.path.normpath')
    @patch('os.listdir')
    def test_write_file_outside_allowed_roots(self, mock_listdir, mock_normpath, mock_abspath):
        # Arrange
        mock_abspath.side_effect = ["/root/test_output", "./test_data"]

        params = {"path": "/root/test_file.txt", "content": "Test content"}

        # Act and Assert
        with self.assertRaises(ValueError):
            self.tool.execute("write_file", params)

    @patch('os.path.abspath')
    @patch('os.path.normpath')
    @patch('os.listdir')
    def test_list_directory(self, mock_listdir, mock_normpath, mock_abspath):
        # Arrange
        mock_abspath.side_effect = ["./test_data", "./test_data"]
        mock_listdir.return_value = ["test_file.txt", "subdir", "empty_folder"]

        params = {"path": "./test_data"}

        # Act
        result = self.tool.execute("list_directory", params)

        # Assert
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        expected_output = ["test_file.txt", "subdir/", "empty_folder/"]
        self.assertListEqual(result.data, sorted(expected_output))

    @patch('os.path.abspath')
    @patch('os.path.normpath')
    @patch('os.listdir')
    def test_list_directory_outside_allowed_roots(self, mock_listdir, mock_normpath, mock_abspath):
        # Arrange
        mock_abspath.side_effect = ["/root/test_data", "./test_data"]

        params = {"path": "/root"}

        # Act and Assert
        with self.assertRaises(ValueError):
            self.tool.execute("list_directory", params)