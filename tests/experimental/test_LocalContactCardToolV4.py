"""
Tests for experimental LocalContactCardToolV4
"""
import pytest
from tools.experimental.LocalContactCardToolV4 import LocalContactCardToolV4

def test_LocalContactCardToolV4_basic():
    """Basic functionality test"""
    tool = LocalContactCardToolV4()
    assert tool is not None

def test_LocalContactCardToolV4_capabilities():
    """Test capability registration"""
    tool = LocalContactCardToolV4()
    caps = tool.get_capabilities()
    assert len(caps) > 0
