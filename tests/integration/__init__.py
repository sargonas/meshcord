"""
Integration tests for Meshcord

These tests verify that different components work together correctly,
including Discord integration, HTTP polling, and serial communication.
"""

# Integration test specific imports
import pytest
import asyncio

# Mark all tests in this package as integration tests
pytestmark = pytest.mark.integration