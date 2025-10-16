#!/usr/bin/env python3
"""
Detailed Claude Agent SDK exploration to understand the API structure.
"""

import inspect
import claude_agent_sdk


def explore_module():
    """Explore the SDK module in detail."""
    print("="*80)
    print("CLAUDE AGENT SDK - Detailed API Exploration")
    print("="*80 + "\n")

    # 1. Explore ClaudeSDKClient
    print("1. ClaudeSDKClient Class")
    print("-" * 80)
    client_class = claude_agent_sdk.ClaudeSDKClient

    # Get init signature
    try:
        sig = inspect.signature(client_class.__init__)
        print(f"__init__ signature: {sig}")
        print(f"Parameters:")
        for param_name, param in sig.parameters.items():
            if param_name != 'self':
                print(f"  - {param_name}: {param.annotation if param.annotation != inspect.Parameter.empty else 'Any'}")
                if param.default != inspect.Parameter.empty:
                    print(f"    default = {param.default}")
    except Exception as e:
        print(f"Could not get init signature: {e}")

    # Get docstring
    if client_class.__doc__:
        print(f"\nDocstring:\n{client_class.__doc__}")

    # Get methods
    print("\nMethods:")
    for name in dir(client_class):
        if not name.startswith('_'):
            attr = getattr(client_class, name)
            if callable(attr):
                try:
                    sig = inspect.signature(attr)
                    print(f"  - {name}{sig}")
                    if attr.__doc__:
                        doc = attr.__doc__.strip().split('\n')[0]  # First line only
                        print(f"    {doc}")
                except:
                    print(f"  - {name}()")

    # 2. Explore query function
    print("\n" + "="*80)
    print("2. query() Function")
    print("-" * 80)
    if hasattr(claude_agent_sdk, 'query'):
        query_func = claude_agent_sdk.query
        try:
            sig = inspect.signature(query_func)
            print(f"Signature: query{sig}")
            if query_func.__doc__:
                print(f"\nDocstring:\n{query_func.__doc__}")
        except Exception as e:
            print(f"Could not get query signature: {e}")
    else:
        print("query function not found")

    # 3. Explore tool decorator
    print("\n" + "="*80)
    print("3. tool Decorator")
    print("-" * 80)
    if hasattr(claude_agent_sdk, 'tool'):
        tool_func = claude_agent_sdk.tool
        try:
            sig = inspect.signature(tool_func)
            print(f"Signature: tool{sig}")
            if tool_func.__doc__:
                print(f"\nDocstring:\n{tool_func.__doc__}")
        except Exception as e:
            print(f"Could not get tool signature: {e}")
    else:
        print("tool decorator not found")

    # 4. Explore MCP server configs
    print("\n" + "="*80)
    print("4. MCP Configuration Classes")
    print("-" * 80)

    for name in ['McpServerConfig', 'McpSdkServerConfig']:
        if hasattr(claude_agent_sdk, name):
            config_class = getattr(claude_agent_sdk, name)
            print(f"\n{name}:")
            try:
                sig = inspect.signature(config_class.__init__)
                print(f"  __init__ signature: {sig}")
                if config_class.__doc__:
                    print(f"  Docstring: {config_class.__doc__}")
            except Exception as e:
                print(f"  Could not inspect: {e}")

    # 5. Explore ClaudeAgentOptions
    print("\n" + "="*80)
    print("5. ClaudeAgentOptions")
    print("-" * 80)
    if hasattr(claude_agent_sdk, 'ClaudeAgentOptions'):
        options_class = claude_agent_sdk.ClaudeAgentOptions
        try:
            sig = inspect.signature(options_class.__init__)
            print(f"__init__ signature: {sig}")
            if options_class.__doc__:
                print(f"\nDocstring:\n{options_class.__doc__}")
        except Exception as e:
            print(f"Could not inspect: {e}")

    # 6. Look for example usage in module
    print("\n" + "="*80)
    print("6. Type Hints and Imports")
    print("-" * 80)
    print(f"Module file: {claude_agent_sdk.__file__}")
    print(f"Module version: {getattr(claude_agent_sdk, '__version__', 'unknown')}")

    # 7. Permission modes
    print("\n" + "="*80)
    print("7. PermissionMode Enum")
    print("-" * 80)
    if hasattr(claude_agent_sdk, 'PermissionMode'):
        perm_mode = claude_agent_sdk.PermissionMode
        print(f"Available permission modes:")
        for item in dir(perm_mode):
            if not item.startswith('_'):
                print(f"  - {item}")


if __name__ == "__main__":
    explore_module()