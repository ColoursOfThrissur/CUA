"""
Tests for experimental LocalCodeSnippetLibraryTool
"""
import pytest
from tools.experimental.LocalCodeSnippetLibraryTool import LocalCodeSnippetLibraryTool

def test_LocalCodeSnippetLibraryTool_basic():
    """Basic functionality test"""
    tool = LocalCodeSnippetLibraryTool()
    assert tool is not None

def test_LocalCodeSnippetLibraryTool_capabilities():
    """Test capability registration"""
    tool = LocalCodeSnippetLibraryTool()
    caps = tool.get_capabilities()
    assert len(caps) > 0
