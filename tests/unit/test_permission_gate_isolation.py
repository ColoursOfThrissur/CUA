"""
Unit tests for PermissionGate session isolation
"""
import pytest
from core.session_permissions import PermissionGate, SessionPermissions, PermissionLevel

@pytest.mark.unit
class TestSessionPermissions:
    
    def test_session_creation(self):
        """Test session is created with correct defaults"""
        session = SessionPermissions("test_session", max_file_writes=5)
        assert session.session_id == "test_session"
        assert session.max_file_writes == 5
        assert session.files_written == 0
    
    def test_record_write_operation(self):
        """Test recording write operations increments counter"""
        session = SessionPermissions("test_session")
        
        session.record_operation("filesystem_tool", "write_file", True)
        assert session.files_written == 1
        
        session.record_operation("filesystem_tool", "write_file", True)
        assert session.files_written == 2
    
    def test_record_non_write_operation(self):
        """Test non-write operations don't increment counter"""
        session = SessionPermissions("test_session")
        
        session.record_operation("filesystem_tool", "read_file", True)
        assert session.files_written == 0
    
    def test_can_write_file_within_limit(self):
        """Test can write when within limit"""
        session = SessionPermissions("test_session", max_file_writes=5)
        session.files_written = 3
        
        can_write, reason = session.can_write_file()
        assert can_write
        assert reason == "OK"
    
    def test_can_write_file_at_limit(self):
        """Test cannot write when at limit"""
        session = SessionPermissions("test_session", max_file_writes=5)
        session.files_written = 5
        
        can_write, reason = session.can_write_file()
        assert not can_write
        assert "limit exceeded" in reason
    
    def test_can_write_file_size_check(self):
        """Test file size limit is enforced"""
        session = SessionPermissions("test_session", max_file_size=100)
        
        can_write, reason = session.can_write_file(content_size=150)
        assert not can_write
        assert "exceeds limit" in reason
    
    def test_reset_session(self):
        """Test session reset clears counters"""
        session = SessionPermissions("test_session")
        session.files_written = 5
        session.operations_log = [{"op": "test"}]
        
        session.reset()
        
        assert session.files_written == 0
        assert len(session.operations_log) == 0

@pytest.mark.unit
class TestPermissionGate:
    
    def test_get_or_create_session(self):
        """Test session is created on first access"""
        gate = PermissionGate()
        
        session1 = gate.get_session("session_1")
        session2 = gate.get_session("session_1")
        
        assert session1 is session2
        assert session1.session_id == "session_1"
    
    def test_session_isolation(self):
        """Test sessions are isolated from each other"""
        gate = PermissionGate()
        
        session1 = gate.get_session("session_1")
        session2 = gate.get_session("session_2")
        
        session1.files_written = 5
        session2.files_written = 2
        
        assert session1.files_written == 5
        assert session2.files_written == 2
    
    def test_check_permission_valid_operation(self):
        """Test permission check for valid operation"""
        gate = PermissionGate()
        
        result = gate.check_permission(
            "session_1",
            "filesystem_tool",
            "read_file",
            {"path": "./test.txt"}
        )
        
        assert result.is_valid
    
    def test_check_permission_write_limit(self):
        """Test permission check enforces write limit"""
        gate = PermissionGate()
        
        session = gate.get_session("session_1")
        session.files_written = 10  # At limit
        
        result = gate.check_permission(
            "session_1",
            "filesystem_tool",
            "write_file",
            {"path": "./test.txt", "content": "test"}
        )
        
        assert not result.is_valid
        assert "limit exceeded" in result.reason
    
    def test_check_permission_undefined_operation(self):
        """Test permission check for undefined operation"""
        gate = PermissionGate()
        
        result = gate.check_permission(
            "session_1",
            "unknown_tool",
            "unknown_operation",
            {}
        )
        
        assert not result.is_valid
    
    def test_record_operation_updates_session(self):
        """Test recording operation updates session state"""
        gate = PermissionGate()
        
        gate.record_operation("session_1", "filesystem_tool", "write_file", True)
        
        session = gate.get_session("session_1")
        assert session.files_written == 1
        assert len(session.operations_log) == 1
    
    def test_reset_session(self):
        """Test resetting specific session"""
        gate = PermissionGate()
        
        gate.record_operation("session_1", "filesystem_tool", "write_file", True)
        gate.reset_session("session_1")
        
        session = gate.get_session("session_1")
        assert session.files_written == 0
    
    def test_delete_session(self):
        """Test deleting session removes it"""
        gate = PermissionGate()
        
        gate.get_session("session_1")
        assert "session_1" in gate.sessions
        
        gate.delete_session("session_1")
        assert "session_1" not in gate.sessions
    
    def test_concurrent_sessions(self):
        """Test multiple concurrent sessions work independently"""
        gate = PermissionGate()
        
        # Session 1 writes 3 files
        for _ in range(3):
            gate.record_operation("session_1", "filesystem_tool", "write_file", True)
        
        # Session 2 writes 5 files
        for _ in range(5):
            gate.record_operation("session_2", "filesystem_tool", "write_file", True)
        
        session1 = gate.get_session("session_1")
        session2 = gate.get_session("session_2")
        
        assert session1.files_written == 3
        assert session2.files_written == 5
