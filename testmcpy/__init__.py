"""
testmcpy - MCP Testing Framework

A comprehensive testing framework for validating LLM tool calling
capabilities with MCP (Model Context Protocol) services.
"""

try:
    from importlib.metadata import version

    __version__ = version("testmcpy")
except Exception:
    # Fallback for development or when package not installed
    __version__ = "0.2.12"

__author__ = "testmcpy Contributors"
