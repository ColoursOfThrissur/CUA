"""
Unit tests for FilesystemTool path validation
"""
import pytest
import os
from tools.enhanced_filesystem_tool import FilesystemTool

@pytest.mark.unit
class TestFilesystemToolPathValidation:
    
    def test_validate_path_within_allowed_root(self):
        """Test path within allowed roots is accepted"""
        tool = FilesystemTool(allowed_roots=[".", "./output"])
        assert tool._validate_path("./output/test.txt")
    
    def test_validate_path_outside_allowed_root(self):
        """Test path outside allowed roots is rejected"""
        tool = FilesystemTool(allowed_roots=["./output"])
        assert not tool._validate_path("./workspace/test.txt")
    
    def test_validate_path_with_traversal(self):
        """Test path traversal is blocked"""
        tool = FilesystemTool(allowed_roots=["./output"])
        assert not tool._validate_path("./output/../../etc/passwd")
    
    def test_validate_path_different_drives_windows(self):
        """Test different drives on Windows are handled"""
        tool = FilesystemTool(allowed_roots=["C:\\workspace"])
        # D: drive should be rejected
        assert not tool._validate_path("D:\\test.txt")
    
    def test_validate_path_with_symlink_attempt(self):
        """Test symlink-like paths are validated"""
        tool = FilesystemTool(allowed_roots=["./output"])
        # Even if symlink, commonpath should validate correctly
        assert tool._validate_path("./output/link.txt")

@pytest.mark.unit
class TestFilesystemToolWriteFile:
    
    def test_write_file_in_current_directory(self, tmp_path):
        """Test writing file in current directory (no dirname)"""
        tool = FilesystemTool(allowed_roots=[str(tmp_path)])
        os.chdir(tmp_path)
        
        result = tool._handle_write_file("test.txt", "content")
        assert "Successfully wrote" in result
        assert (tmp_path / "test.txt").exists()
    
    def test_write_file_with_subdirectory(self, tmp_path):
        """Test writing file with subdirectory creation"""
        tool = FilesystemTool(allowed_roots=[str(tmp_path)])
        
        file_path = str(tmp_path / "subdir" / "test.txt")
        result = tool._handle_write_file(file_path, "content")
        
        assert "Successfully wrote" in result
        assert os.path.exists(file_path)
    
    def test_write_file_outside_allowed_root(self, tmp_path):
        """Test writing file outside allowed roots fails"""
        tool = FilesystemTool(allowed_roots=[str(tmp_path / "allowed")])
        
        with pytest.raises(ValueError, match="outside allowed roots"):
            tool._handle_write_file(str(tmp_path / "forbidden" / "test.txt"), "content")

@pytest.mark.unit
class TestFilesystemToolReadFile:
    
    def test_read_existing_file(self, tmp_path):
        """Test reading existing file"""
        tool = FilesystemTool(allowed_roots=[str(tmp_path)])
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        result = tool._handle_read_file(str(test_file))
        assert result == "test content"
    
    def test_read_nonexistent_file(self, tmp_path):
        """Test reading non-existent file raises error"""
        tool = FilesystemTool(allowed_roots=[str(tmp_path)])
        
        with pytest.raises(FileNotFoundError):
            tool._handle_read_file(str(tmp_path / "nonexistent.txt"))
    
    def test_read_file_outside_allowed_root(self, tmp_path):
        """Test reading file outside allowed roots fails"""
        tool = FilesystemTool(allowed_roots=[str(tmp_path / "allowed")])
        
        with pytest.raises(ValueError, match="outside allowed roots"):
            tool._handle_read_file(str(tmp_path / "forbidden" / "test.txt"))

@pytest.mark.unit
class TestFilesystemToolListDirectory:
    
    def test_list_directory(self, tmp_path):
        """Test listing directory contents"""
        tool = FilesystemTool(allowed_roots=[str(tmp_path)])
        
        # Create test files
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.txt").touch()
        (tmp_path / "subdir").mkdir()
        
        result = tool._handle_list_directory(str(tmp_path))
        
        assert "file1.txt" in result
        assert "file2.txt" in result
        assert "subdir/" in result
    
    def test_list_nonexistent_directory(self, tmp_path):
        """Test listing non-existent directory raises error"""
        tool = FilesystemTool(allowed_roots=[str(tmp_path)])
        
        with pytest.raises(FileNotFoundError):
            tool._handle_list_directory(str(tmp_path / "nonexistent"))
    
    def test_list_file_not_directory(self, tmp_path):
        """Test listing a file (not directory) raises error"""
        tool = FilesystemTool(allowed_roots=[str(tmp_path)])
        
        test_file = tmp_path / "test.txt"
        test_file.touch()
        
        with pytest.raises(ValueError, match="not a directory"):
            tool._handle_list_directory(str(test_file))
