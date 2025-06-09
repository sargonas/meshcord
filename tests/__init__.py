"""
Meshcord test suite

This package contains all unit tests, integration tests, and test utilities
for the Meshcord Discord bot.
"""

# Test configuration
import os
import sys

# Add the parent directory to the path so tests can import meshcord_bot
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Common test fixtures and utilities can be imported here
# from .fixtures import *  # If you create shared test fixtures