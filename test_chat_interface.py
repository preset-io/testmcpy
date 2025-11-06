#!/usr/bin/env python3
"""
Test script for the chat interface.

This script validates that the chat interface components work correctly.
"""

import asyncio
import sys


async def test_chat_session():
    """Test the ChatSession class."""
    print("Testing ChatSession...")

    from testmcpy.core.chat_session import ChatSession

    # Create a chat session (use default config)
    session = ChatSession()

    print(f"  ✓ ChatSession created")
    print(f"    Provider: {session.provider_name}")
    print(f"    Model: {session.model}")
    print(f"    MCP URL: {session.mcp_url}")

    # Test basic functionality without actually initializing
    # (to avoid requiring MCP service to be running)
    print(f"  ✓ Message count: {session.get_message_count()}")
    print(f"  ✓ Total cost: ${session.total_cost:.4f}")

    # Test export conversation (empty conversation)
    json_export = session.export_conversation("json")
    print(f"  ✓ JSON export works (length: {len(json_export)})")

    yaml_export = session.export_conversation("yaml")
    print(f"  ✓ YAML export works (length: {len(yaml_export)})")

    print("✓ ChatSession tests passed\n")


def test_tui_imports():
    """Test that TUI components can be imported."""
    print("Testing TUI imports...")

    try:
        from testmcpy.tui.app import TestMCPyApp, launch_chat
        from testmcpy.tui.screens.chat import ChatScreen, MessageWidget, ToolCallWidget

        print("  ✓ TUI app imported")
        print("  ✓ ChatScreen imported")
        print("  ✓ MessageWidget imported")
        print("  ✓ ToolCallWidget imported")
        print("✓ TUI import tests passed\n")

    except Exception as e:
        print(f"✗ TUI import failed: {e}")
        return False

    return True


def test_cli_command():
    """Test that the CLI command is registered."""
    print("Testing CLI command...")

    try:
        from testmcpy.cli import app

        # Check if chat command is in the app
        commands = [cmd.name for cmd in app.registered_commands]
        if "chat" in commands:
            print("  ✓ chat command registered")
            print("✓ CLI command tests passed\n")
            return True
        else:
            print(f"✗ chat command not found. Available: {commands}")
            return False

    except Exception as e:
        print(f"✗ CLI command test failed: {e}")
        return False


def test_tool_call_execution():
    """Test ToolCallExecution dataclass."""
    print("Testing ToolCallExecution...")

    from testmcpy.core.chat_session import ToolCallExecution

    # Create a test tool call execution
    tool_call = ToolCallExecution(
        tool_name="test_tool", arguments={"param": "value"}, start_time=0.0
    )

    print(f"  ✓ ToolCallExecution created")
    print(f"    Tool: {tool_call.tool_name}")
    print(f"    Status emoji: {tool_call.status_emoji}")

    # Complete the execution
    tool_call.end_time = 2.5
    tool_call.success = True
    tool_call.result = "Success!"

    print(f"  ✓ Duration: {tool_call.duration}s")
    print(f"  ✓ Status emoji: {tool_call.status_emoji}")

    print("✓ ToolCallExecution tests passed\n")


def test_chat_message():
    """Test ChatMessage dataclass."""
    print("Testing ChatMessage...")

    from testmcpy.core.chat_session import ChatMessage

    # Create a test message
    msg = ChatMessage(role="user", content="Hello, world!")

    print(f"  ✓ ChatMessage created")
    print(f"    Role: {msg.role}")
    print(f"    Content: {msg.content}")
    print(f"    Cost: ${msg.cost:.4f}")

    print("✓ ChatMessage tests passed\n")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("testmcpy Chat Interface Tests")
    print("=" * 60 + "\n")

    all_passed = True

    try:
        # Test core components
        test_chat_message()
        test_tool_call_execution()
        await test_chat_session()

        # Test TUI components
        if not test_tui_imports():
            all_passed = False

        # Test CLI integration
        if not test_cli_command():
            all_passed = False

    except Exception as e:
        print(f"\n✗ Test suite failed with error: {e}")
        import traceback

        traceback.print_exc()
        all_passed = False

    print("=" * 60)
    if all_passed:
        print("✓ All tests passed!")
        print("\nYou can now launch the chat interface with:")
        print("  testmcpy chat")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
