"""
Tests for experimental SyntaxGuardRetryAfterSanitization
"""
import pytest
from tools.experimental.SyntaxGuardRetryAfterSanitization import Syntaxguardretryaftersanitization

def test_SyntaxGuardRetryAfterSanitization_basic():
    """Basic functionality test"""
    tool = Syntaxguardretryaftersanitization()
    assert tool is not None

def test_SyntaxGuardRetryAfterSanitization_capabilities():
    """Test capability registration"""
    tool = Syntaxguardretryaftersanitization()
    caps = tool.register_capabilities()
    assert len(caps) > 0
