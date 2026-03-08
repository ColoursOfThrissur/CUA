"""Test memory system SQLite persistence."""
import sys
sys.path.insert(0, '.')

from core.memory_system import MemorySystem
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_memory_persistence():
    """Test that memory system persists data correctly."""
    
    # Create memory system
    memory = MemorySystem()
    
    # Test 1: Create session
    logger.info("Test 1: Create session")
    session_id = "test_session_123"
    context = memory.create_session(session_id, {"theme": "dark", "language": "en"})
    assert context.session_id == session_id
    assert context.user_preferences["theme"] == "dark"
    logger.info("✓ Session created")
    
    # Test 2: Add messages
    logger.info("Test 2: Add messages")
    memory.add_message(session_id, "user", "Hello")
    memory.add_message(session_id, "assistant", "Hi there!")
    messages = memory.get_recent_messages(session_id, limit=10)
    assert len(messages) == 2
    assert messages[0].content == "Hello"
    logger.info("✓ Messages added")
    
    # Test 3: Set active goal
    logger.info("Test 3: Set active goal")
    memory.set_active_goal(session_id, "Test goal achievement")
    context = memory.get_session(session_id)
    assert context.active_goal == "Test goal achievement"
    logger.info("✓ Active goal set")
    
    # Test 4: Add execution
    logger.info("Test 4: Add execution")
    memory.add_execution(session_id, "exec_001")
    memory.add_execution(session_id, "exec_002")
    context = memory.get_session(session_id)
    assert len(context.execution_history) == 2
    logger.info("✓ Executions added")
    
    # Test 5: Update preference
    logger.info("Test 5: Update preference")
    memory.update_preference(session_id, "theme", "light")
    context = memory.get_session(session_id)
    assert context.user_preferences["theme"] == "light"
    logger.info("✓ Preference updated")
    
    # Test 6: Learn pattern
    logger.info("Test 6: Learn pattern")
    memory.learn_pattern("test_pattern", {"key": "value", "score": 0.95})
    patterns = memory.get_patterns("test_pattern", limit=5)
    assert len(patterns) > 0
    assert patterns[0]["key"] == "value"
    logger.info("✓ Pattern learned")
    
    # Test 7: Clear cache and reload from DB
    logger.info("Test 7: Persistence test (clear cache and reload)")
    memory.active_sessions.clear()  # Clear in-memory cache
    context = memory.get_session(session_id)  # Should load from DB
    assert context is not None
    assert context.session_id == session_id
    assert len(context.messages) == 2
    assert context.active_goal == "Test goal achievement"
    assert len(context.execution_history) == 2
    assert context.user_preferences["theme"] == "light"
    logger.info("✓ Data persisted and reloaded from SQLite")
    
    # Test 8: Clear session
    logger.info("Test 8: Clear session")
    memory.clear_session(session_id)
    context = memory.get_session(session_id)
    assert context is None
    logger.info("✓ Session cleared")
    
    logger.info("\n✅ All tests passed! Memory system SQLite persistence working correctly.")


if __name__ == "__main__":
    test_memory_persistence()
