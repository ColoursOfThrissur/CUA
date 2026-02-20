"""
Tests for experimental LocalRunNoteTool
"""
import pytest
from tools.experimental.LocalRunNoteTool import LocalRunNoteTool

def test_LocalRunNoteTool_basic():
    """Basic functionality test"""
    tool = LocalRunNoteTool()
    assert tool is not None

def test_LocalRunNoteTool_capabilities():
    """Test capability registration"""
    tool = LocalRunNoteTool()
    caps = tool.get_capabilities()
    assert len(caps) > 0
