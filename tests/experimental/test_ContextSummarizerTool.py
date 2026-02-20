"""
Tests for experimental ContextSummarizerTool
"""
import pytest
from tools.experimental.ContextSummarizerTool import ContextSummarizerTool

def test_ContextSummarizerTool_basic():
    """Basic functionality test"""
    tool = ContextSummarizerTool()
    assert tool is not None

def test_ContextSummarizerTool_capabilities():
    """Test capability registration"""
    tool = ContextSummarizerTool()
    caps = tool.get_capabilities()
    assert len(caps) > 0
