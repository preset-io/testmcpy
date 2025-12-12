# CLI Real-Time Token Usage Display Implementation Plan

**Status:** Planning Phase  
**Created:** 2025-10-31  
**Author:** Claude Code Assistant  
**Priority:** Medium  
**Estimated Effort:** 2-3 days  

---

## Executive Summary

This document outlines a comprehensive plan to enhance the testmcpy CLI chat interface with real-time token usage display, similar to how Claude Code displays token information during conversations. The implementation will provide users with immediate visibility into:
- Input tokens (user prompts + system/cache)
- Output tokens (assistant responses)
- Cache hits and creation
- Estimated costs
- Running totals

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Claude Code Token Display Analysis](#claude-code-token-display-analysis)
3. [Architecture Design](#architecture-design)
4. [Implementation Details](#implementation-details)
5. [UI/UX Design](#uiux-design)
6. [Testing Strategy](#testing-strategy)
7. [Rollout Plan](#rollout-plan)

---

## Current State Analysis

### Existing CLI Chat Implementation

**File:** `testmcpy/cli.py` (lines 648-767)

**Current Flow:**
```python
async def chat_session():
    # Initialize LLM provider
    llm = create_llm_provider(provider.value, model)
    await llm.initialize()
    
    # Chat loop
    while True:
        user_input = console.input("[bold blue]You:[/bold blue] ")
        
        # Show thinking indicator
        with console.status("[dim]Thinking...[/dim]"):
            response = await llm.generate_with_tools(user_input, tools_dict)
        
        # Display response
        console.print(f"[bold green]{model}:[/bold green] {response.response}")
        
        # Show basic tool call info
        if response.tool_calls:
            console.print(f"[dim]Used {len(response.tool_calls)} tool call(s)[/dim]")
```

**Current Token Tracking:**
- Token usage is captured in `LLMResult.token_usage` (dict)
- Available fields from Anthropic API:
  - `prompt` (or `input_tokens`)
  - `completion` (or `output_tokens`)
  - `total`
  - `cache_creation` (cache creation tokens)
  - `cache_read` (cache hit tokens - FREE!)
- Cost is calculated in `LLMResult.cost`
- **BUT:** Tokens are NOT displayed in the chat interface

### Token Tracking in Test Runner

**File:** `testmcpy/src/test_runner.py` (lines 329-358)

The test runner DOES display token usage:
```python
if self.verbose and not self.hide_tool_output:
    tokens = llm_result.token_usage
    if tokens:
        print(f"  Token Usage:")
        if "prompt" in tokens:
            print(f"    Input: {tokens['prompt']} tokens")
        if "completion" in tokens:
            print(f"    Output: {tokens['completion']} tokens")
        if tokens.get("cache_creation", 0) > 0:
            print(f"    Cache Creation: {tokens['cache_creation']} tokens")
        if tokens.get("cache_read", 0) > 0:
            print(f"    Cache Read: {tokens['cache_read']} tokens (FREE!)")
        if "total" in tokens:
            print(f"    Total: {tokens['total']} tokens")
    
    if llm_result.cost > 0:
        print(f"  Cost: ${llm_result.cost:.4f}")
```

**Insights:**
1. Token data is already available
2. Display logic exists in test runner
3. Need to adapt for chat interface
4. Rich console is already in use

### LLM Provider Token Tracking

**File:** `testmcpy/src/llm_integration.py`

**Anthropic Provider** (lines 751-762):
```python
usage = result.get("usage", {})
token_usage = {
    "prompt": usage.get("input_tokens", 0),
    "completion": usage.get("output_tokens", 0),
    "total": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
    "cache_creation": usage.get("cache_creation_input_tokens", 0),
    "cache_read": usage.get("cache_read_input_tokens", 0)
}

# Estimate cost (Claude pricing)
cost = (token_usage["prompt"] * 0.003 + token_usage["completion"] * 0.015) / 1000
```

**Key Observations:**
1. Token usage data is extracted from API response
2. Includes cache tokens (important for Anthropic)
3. Cost calculation is basic (needs model-specific pricing)
4. Available for ALL providers that return usage

---

## Claude Code Token Display Analysis

### Observable Behavior

Based on Claude Code's display patterns, the token usage is shown:

**Location:** Bottom-right status bar or in-line with response

**Format Examples:**
```
┌─────────────────────────────────────────────────┐
│ ● Input: 1,234 tokens                           │
│ ● Output: 567 tokens                            │
│ ● Cache: 45K tokens (hit)                       │
│ ● Total: 1,801 tokens                           │
│ ● Cost: $0.0234                                 │
└─────────────────────────────────────────────────┘
```

**Timing:**
- Appears AFTER response is complete
- Updates incrementally if streaming
- Shows cache hit status
- Running session totals

**Visual Elements:**
- Clear separation from chat content
- Muted colors for less distraction
- Formatted numbers with commas
- Cost in dollars with 4 decimal places
- Cache tokens highlighted (they're free!)

### Key Features to Replicate

1. **Real-time Updates:** Display tokens as they're counted
2. **Cache Visibility:** Clearly show cache creation vs hits
3. **Cost Transparency:** Show per-message and session costs
4. **Formatting:** Use Rich library for beautiful display
5. **Positioning:** Non-intrusive but visible
6. **Session Totals:** Track cumulative usage

---

## Architecture Design

### High-Level Data Flow

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│              │         │              │         │              │
│  User Input  │────────▶│  LLM Call    │────────▶│  API Response│
│              │         │              │         │              │
└──────────────┘         └──────────────┘         └──────┬───────┘
                                                         │
                                                         │ Extract
                                                         │ token_usage
                                                         │
                         ┌───────────────────────────────▼
                         │
                         │  TokenTracker
                         │  - Update running totals
                         │  - Calculate costs
                         │  - Format for display
                         │
                         └───────────────┬───────────────┘
                                         │
                                         │ Display
                                         │
                         ┌───────────────▼───────────────┐
                         │                               │
                         │  Rich Console Display         │
                         │  - Token breakdown            │
                         │  - Cache information          │
                         │  - Cost breakdown             │
                         │  - Session totals             │
                         │                               │
                         └───────────────────────────────┘
```

### Component Architecture

```python
# New Components

class TokenTracker:
    """Track token usage across chat session."""
    
    def __init__(self):
        self.session_total_input = 0
        self.session_total_output = 0
        self.session_total_cache_read = 0
        self.session_total_cache_creation = 0
        self.session_total_cost = 0.0
        self.message_count = 0
    
    def update(self, token_usage: Dict[str, int], cost: float):
        """Update running totals."""
        pass
    
    def get_summary(self) -> Dict[str, Any]:
        """Get current session summary."""
        pass


class TokenDisplay:
    """Format and display token information using Rich."""
    
    def __init__(self, console: Console):
        self.console = console
    
    def display_message_tokens(
        self, 
        token_usage: Dict[str, int], 
        cost: float,
        show_breakdown: bool = True
    ):
        """Display tokens for a single message."""
        pass
    
    def display_session_summary(
        self,
        tracker: TokenTracker,
        show_detailed: bool = False
    ):
        """Display session totals."""
        pass


class ModelPricing:
    """Model-specific pricing information."""
    
    PRICING = {
        "claude-sonnet-4-5": {
            "input": 0.003,   # per 1K tokens
            "output": 0.015,  # per 1K tokens
            "cache_write": 0.00375,
            "cache_read": 0.0003
        },
        "claude-haiku-4-5": {
            "input": 0.0008,
            "output": 0.004,
            "cache_write": 0.001,
            "cache_read": 0.00008
        },
        # ... more models
    }
    
    @staticmethod
    def calculate_cost(
        model: str,
        token_usage: Dict[str, int]
    ) -> float:
        """Calculate accurate cost for model."""
        pass
```

### Integration Points

**Modified File:** `testmcpy/cli.py`

```python
# In chat() command function
async def chat_session():
    # ... existing setup ...
    
    # NEW: Initialize token tracker
    token_tracker = TokenTracker()
    token_display = TokenDisplay(console)
    
    # Chat loop
    while True:
        user_input = console.input("[bold blue]You:[/bold blue] ")
        
        if user_input.lower() in ['exit', 'quit', 'bye']:
            # NEW: Show session summary before exit
            console.print("\n[bold cyan]Session Summary[/bold cyan]")
            token_display.display_session_summary(token_tracker)
            break
        
        # Generate response
        with console.status("[dim]Thinking...[/dim]"):
            response = await llm.generate_with_tools(user_input, tools_dict)
        
        # Display response
        console.print(f"[bold green]{model}:[/bold green] {response.response}")
        
        # Show tool calls
        if response.tool_calls:
            # ... existing tool call display ...
        
        # NEW: Display token usage
        if response.token_usage:
            token_tracker.update(response.token_usage, response.cost)
            token_display.display_message_tokens(
                response.token_usage,
                response.cost
            )
        
        console.print()  # Empty line for spacing
```

---

## Implementation Details

### Phase 1: Core Token Tracking

**File:** `testmcpy/token_tracking.py` (NEW)

```python
"""
Token tracking and cost calculation for CLI chat.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class MessageTokens:
    """Token usage for a single message."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0


class ModelPricing:
    """Model-specific pricing information.
    
    Pricing is per 1,000 tokens in USD.
    Source: https://www.anthropic.com/api#pricing
    """
    
    PRICING = {
        # Claude 4.5 models
        "claude-sonnet-4-5": {
            "input": 0.003,
            "output": 0.015,
            "cache_write": 0.00375,  # 1.25x input
            "cache_read": 0.0003     # 10% of input
        },
        "claude-haiku-4-5": {
            "input": 0.0008,
            "output": 0.004,
            "cache_write": 0.001,
            "cache_read": 0.00008
        },
        "claude-opus-4-1": {
            "input": 0.015,
            "output": 0.075,
            "cache_write": 0.01875,
            "cache_read": 0.0015
        },
        
        # GPT models (OpenAI)
        "gpt-4o": {
            "input": 0.0025,
            "output": 0.01
        },
        "gpt-4-turbo": {
            "input": 0.01,
            "output": 0.03
        },
        "gpt-3.5-turbo": {
            "input": 0.0005,
            "output": 0.0015
        },
        
        # Ollama models (free)
        "ollama": {
            "input": 0.0,
            "output": 0.0
        }
    }
    
    @classmethod
    def calculate_cost(
        cls,
        model: str,
        token_usage: Dict[str, int]
    ) -> float:
        """Calculate cost based on model and token usage.
        
        Args:
            model: Model name (e.g., "claude-haiku-4-5")
            token_usage: Dict with token counts
            
        Returns:
            Cost in USD
        """
        # Normalize model name
        model_key = model
        for known_model in cls.PRICING.keys():
            if known_model in model.lower():
                model_key = known_model
                break
        
        pricing = cls.PRICING.get(model_key, cls.PRICING["ollama"])
        
        input_tokens = token_usage.get("prompt", token_usage.get("input_tokens", 0))
        output_tokens = token_usage.get("completion", token_usage.get("output_tokens", 0))
        cache_creation = token_usage.get("cache_creation", 0)
        cache_read = token_usage.get("cache_read", 0)
        
        cost = 0.0
        cost += (input_tokens * pricing["input"]) / 1000
        cost += (output_tokens * pricing["output"]) / 1000
        
        if "cache_write" in pricing:
            cost += (cache_creation * pricing["cache_write"]) / 1000
        if "cache_read" in pricing:
            cost += (cache_read * pricing["cache_read"]) / 1000
        
        return cost


class TokenTracker:
    """Track token usage across a chat session."""
    
    def __init__(self):
        self.messages: list[MessageTokens] = []
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.session_cache_creation = 0
        self.session_cache_read = 0
        self.session_total_tokens = 0
        self.session_total_cost = 0.0
    
    def update(
        self,
        token_usage: Dict[str, int],
        cost: Optional[float] = None
    ) -> MessageTokens:
        """Update tracker with new message tokens.
        
        Args:
            token_usage: Token usage dict from LLM response
            cost: Pre-calculated cost (optional)
            
        Returns:
            MessageTokens object
        """
        # Extract token counts (handle different key formats)
        input_tokens = token_usage.get("prompt", token_usage.get("input_tokens", 0))
        output_tokens = token_usage.get("completion", token_usage.get("output_tokens", 0))
        cache_creation = token_usage.get("cache_creation", 0)
        cache_read = token_usage.get("cache_read", 0)
        total = token_usage.get("total", input_tokens + output_tokens)
        
        # Create message record
        message = MessageTokens(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_tokens=cache_creation,
            cache_read_tokens=cache_read,
            total_tokens=total,
            cost=cost or 0.0
        )
        
        # Update session totals
        self.session_input_tokens += input_tokens
        self.session_output_tokens += output_tokens
        self.session_cache_creation += cache_creation
        self.session_cache_read += cache_read
        self.session_total_tokens += total
        self.session_total_cost += message.cost
        
        self.messages.append(message)
        return message
    
    def get_summary(self) -> Dict[str, Any]:
        """Get current session summary."""
        return {
            "message_count": len(self.messages),
            "input_tokens": self.session_input_tokens,
            "output_tokens": self.session_output_tokens,
            "cache_creation": self.session_cache_creation,
            "cache_read": self.session_cache_read,
            "total_tokens": self.session_total_tokens,
            "total_cost": self.session_total_cost
        }
```

### Phase 2: Rich Display Components

**File:** `testmcpy/token_display.py` (NEW)

```python
"""
Rich console display for token usage.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from typing import Dict, Any, Optional

from .token_tracking import TokenTracker, MessageTokens


class TokenDisplay:
    """Display token information using Rich console."""
    
    def __init__(self, console: Console):
        self.console = console
    
    def format_number(self, num: int) -> str:
        """Format number with commas."""
        return f"{num:,}"
    
    def format_cost(self, cost: float) -> str:
        """Format cost in USD."""
        return f"${cost:.4f}"
    
    def display_message_tokens(
        self,
        token_usage: Dict[str, int],
        cost: float,
        compact: bool = False
    ):
        """Display token usage for a single message.
        
        Args:
            token_usage: Token usage dict
            cost: Cost in USD
            compact: If True, show inline; if False, show detailed
        """
        input_tokens = token_usage.get("prompt", token_usage.get("input_tokens", 0))
        output_tokens = token_usage.get("completion", token_usage.get("output_tokens", 0))
        cache_creation = token_usage.get("cache_creation", 0)
        cache_read = token_usage.get("cache_read", 0)
        total = token_usage.get("total", input_tokens + output_tokens)
        
        if compact:
            # Inline display
            parts = []
            parts.append(f"[cyan]{self.format_number(total)} tokens[/cyan]")
            
            if cache_read > 0:
                parts.append(f"[green]{self.format_number(cache_read)} cached[/green]")
            
            if cost > 0:
                parts.append(f"[yellow]{self.format_cost(cost)}[/yellow]")
            
            self.console.print(f"[dim]  {' | '.join(parts)}[/dim]")
        else:
            # Detailed panel display
            table = Table.grid(padding=(0, 2))
            table.add_column(style="dim", justify="right")
            table.add_column()
            
            # Input tokens
            table.add_row(
                "Input:",
                f"[cyan]{self.format_number(input_tokens)}[/cyan] tokens"
            )
            
            # Output tokens
            table.add_row(
                "Output:",
                f"[cyan]{self.format_number(output_tokens)}[/cyan] tokens"
            )
            
            # Cache information (if applicable)
            if cache_creation > 0:
                table.add_row(
                    "Cache created:",
                    f"[yellow]{self.format_number(cache_creation)}[/yellow] tokens"
                )
            
            if cache_read > 0:
                table.add_row(
                    "Cache read:",
                    f"[green]{self.format_number(cache_read)}[/green] tokens [dim](FREE!)[/dim]"
                )
            
            # Total
            table.add_row(
                "Total:",
                f"[bold cyan]{self.format_number(total)}[/bold cyan] tokens"
            )
            
            # Cost
            if cost > 0:
                table.add_row(
                    "Cost:",
                    f"[yellow]{self.format_cost(cost)}[/yellow]"
                )
            
            panel = Panel(
                table,
                title="[dim]Token Usage[/dim]",
                border_style="dim",
                padding=(0, 1)
            )
            
            self.console.print(panel)
    
    def display_session_summary(
        self,
        tracker: TokenTracker,
        show_message_breakdown: bool = False
    ):
        """Display session totals.
        
        Args:
            tracker: TokenTracker instance
            show_message_breakdown: Show per-message details
        """
        summary = tracker.get_summary()
        
        # Create summary table
        table = Table.grid(padding=(0, 2))
        table.add_column(style="dim", justify="right")
        table.add_column()
        
        table.add_row(
            "Messages:",
            f"[cyan]{summary['message_count']}[/cyan]"
        )
        table.add_row(
            "Input tokens:",
            f"[cyan]{self.format_number(summary['input_tokens'])}[/cyan]"
        )
        table.add_row(
            "Output tokens:",
            f"[cyan]{self.format_number(summary['output_tokens'])}[/cyan]"
        )
        
        if summary['cache_creation'] > 0:
            table.add_row(
                "Cache created:",
                f"[yellow]{self.format_number(summary['cache_creation'])}[/yellow]"
            )
        
        if summary['cache_read'] > 0:
            table.add_row(
                "Cache read:",
                f"[green]{self.format_number(summary['cache_read'])}[/green] [dim](FREE!)[/dim]"
            )
        
        table.add_row(
            "Total tokens:",
            f"[bold cyan]{self.format_number(summary['total_tokens'])}[/bold cyan]"
        )
        
        if summary['total_cost'] > 0:
            table.add_row(
                "Total cost:",
                f"[bold yellow]{self.format_cost(summary['total_cost'])}[/bold yellow]"
            )
        
        panel = Panel(
            table,
            title="[bold cyan]Chat Session Summary[/bold cyan]",
            border_style="cyan",
            padding=(0, 1)
        )
        
        self.console.print(panel)
        
        # Optionally show message breakdown
        if show_message_breakdown and tracker.messages:
            self.console.print("\n[bold]Message Breakdown:[/bold]")
            
            msg_table = Table(show_header=True, header_style="bold cyan")
            msg_table.add_column("#", style="dim", width=4)
            msg_table.add_column("Input", justify="right")
            msg_table.add_column("Output", justify="right")
            msg_table.add_column("Cache", justify="right")
            msg_table.add_column("Total", justify="right")
            msg_table.add_column("Cost", justify="right")
            
            for i, msg in enumerate(tracker.messages, 1):
                cache_str = ""
                if msg.cache_read_tokens > 0:
                    cache_str = f"[green]{self.format_number(msg.cache_read_tokens)}[/green]"
                
                msg_table.add_row(
                    str(i),
                    self.format_number(msg.input_tokens),
                    self.format_number(msg.output_tokens),
                    cache_str,
                    self.format_number(msg.total_tokens),
                    self.format_cost(msg.cost) if msg.cost > 0 else "-"
                )
            
            self.console.print(msg_table)
    
    def display_streaming_tokens(
        self,
        current_output_tokens: int,
        estimated_input_tokens: int = 0
    ):
        """Display real-time token count during streaming.
        
        Args:
            current_output_tokens: Current output token count
            estimated_input_tokens: Estimated input tokens
        """
        # This would be shown in the status indicator
        # E.g., "Thinking... (1,234 tokens)"
        if current_output_tokens > 0:
            return f"[dim]({self.format_number(current_output_tokens)} tokens)[/dim]"
        return ""
```

### Phase 3: CLI Integration

**File:** `testmcpy/cli.py` (MODIFIED)

```python
# Add imports at top
from testmcpy.token_tracking import TokenTracker, ModelPricing
from testmcpy.token_display import TokenDisplay

# Modify chat() command
@app.command()
def chat(
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model to use"),
    provider: ModelProvider = typer.Option(DEFAULT_PROVIDER, "--provider", "-p", help="Model provider"),
    mcp_url: Optional[str] = typer.Option(None, "--mcp-url", help="MCP service URL (overrides profile)"),
    profile: Optional[str] = typer.Option(None, "--profile", help="MCP service profile from .mcp_services.yaml"),
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Chat without MCP tools"),
    show_tokens: bool = typer.Option(True, "--show-tokens/--hide-tokens", help="Show token usage"),  # NEW
    compact_tokens: bool = typer.Option(False, "--compact-tokens", help="Show tokens in compact format"),  # NEW
):
    """
    Interactive chat with LLM that has access to MCP tools.
    
    Start a chat session where you can directly talk to the LLM and it can use
    MCP tools from your service. Type 'exit' or 'quit' to end the session.
    
    Token usage is displayed after each response. Use --hide-tokens to disable.
    """
    # ... existing config loading ...
    
    console.print(Panel.fit(
        f"[bold cyan]Interactive Chat with {model}[/bold cyan]\n"
        f"Provider: {provider.value}\n"
        f"Mode: {'Standalone (no MCP tools)' if no_mcp else f'MCP Service: {effective_mcp_url}'}\n\n"
        "[dim]Type your message and press Enter. Type 'exit', 'quit', or 'tokens' for session summary.[/dim]",
        border_style="cyan"
    ))
    
    async def chat_session():
        # ... existing setup ...
        
        # NEW: Initialize token tracking
        token_tracker = TokenTracker()
        token_display = TokenDisplay(console)
        
        # Chat loop
        while True:
            try:
                # Get user input
                user_input = console.input("[bold blue]You:[/bold blue] ")
                
                if user_input.lower() in ['exit', 'quit', 'bye']:
                    console.print("[yellow]Goodbye![/yellow]\n")
                    # NEW: Show session summary
                    if show_tokens and len(token_tracker.messages) > 0:
                        token_display.display_session_summary(
                            token_tracker,
                            show_message_breakdown=True
                        )
                    break
                
                # NEW: Special command to show token summary
                if user_input.lower() == 'tokens':
                    if len(token_tracker.messages) > 0:
                        token_display.display_session_summary(
                            token_tracker,
                            show_message_breakdown=True
                        )
                    else:
                        console.print("[dim]No messages yet[/dim]")
                    continue
                
                if not user_input.strip():
                    continue
                
                # Generate response
                with console.status("[dim]Thinking...[/dim]"):
                    # Convert MCPTool objects to dictionaries for LLM
                    tools_dict = []
                    for tool in tools:
                        tools_dict.append({
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.input_schema
                        })
                    
                    # Generate response with available tools
                    response = await llm.generate_with_tools(user_input, tools_dict)
                
                # Display response
                console.print(f"[bold green]{model}:[/bold green] {response.response}")
                
                # Show tool calls if any
                if response.tool_calls:
                    console.print(f"[dim]Used {len(response.tool_calls)} tool call(s)[/dim]")
                    for tool_call in response.tool_calls:
                        console.print(f"[dim]→ {tool_call['name']}({tool_call['arguments']})[/dim]")
                
                # NEW: Display token usage
                if show_tokens and response.token_usage:
                    # Calculate accurate cost
                    accurate_cost = ModelPricing.calculate_cost(
                        model,
                        response.token_usage
                    )
                    
                    # Update tracker
                    token_tracker.update(response.token_usage, accurate_cost)
                    
                    # Display based on mode
                    token_display.display_message_tokens(
                        response.token_usage,
                        accurate_cost,
                        compact=compact_tokens
                    )
                
                console.print()  # Empty line for spacing
            
            except KeyboardInterrupt:
                console.print("\n[yellow]Chat interrupted.[/yellow]\n")
                # Show summary on interrupt too
                if show_tokens and len(token_tracker.messages) > 0:
                    token_display.display_session_summary(
                        token_tracker,
                        show_message_breakdown=False
                    )
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
        
        # Cleanup
        if mcp_client:
            await mcp_client.close()
        await llm.close()
    
    asyncio.run(chat_session())
```

---

## UI/UX Design

### Display Modes

#### 1. Compact Mode (Default)
```
You: Create a bar chart

Claude: I'll create a bar chart for you...

  1,234 tokens | 456 cached | $0.0123

You: 
```

#### 2. Detailed Mode
```
You: Create a bar chart

Claude: I'll create a bar chart for you...

┌─ Token Usage ────────────────────┐
│     Input:  1,234 tokens         │
│    Output:    567 tokens         │
│Cache read:    456 tokens (FREE!) │
│     Total:  1,801 tokens         │
│      Cost:  $0.0123              │
└──────────────────────────────────┘

You: 
```

#### 3. Session Summary (on exit)
```
Goodbye!

┌─ Chat Session Summary ───────────────┐
│     Messages:  5                     │
│ Input tokens:  12,345                │
│Output tokens:  6,789                 │
│   Cache read:  45,678 (FREE!)        │
│ Total tokens:  19,134                │
│   Total cost:  $0.2456               │
└──────────────────────────────────────┘

Message Breakdown:
┌───┬────────┬────────┬────────┬────────┬─────────┐
│ # │  Input │ Output │  Cache │  Total │    Cost │
├───┼────────┼────────┼────────┼────────┼─────────┤
│ 1 │  1,234 │    567 │      0 │  1,801 │ $0.0123 │
│ 2 │  2,345 │    890 │  1,234 │  3,235 │ $0.0234 │
│ 3 │  1,567 │    456 │ 15,678 │  2,023 │ $0.0089 │
│ 4 │  3,456 │  2,345 │ 12,345 │  5,801 │ $0.0456 │
│ 5 │  3,743 │  2,531 │ 16,421 │  6,274 │ $0.1554 │
└───┴────────┴────────┴────────┴────────┴─────────┘
```

### Color Scheme

- **Input tokens:** Cyan
- **Output tokens:** Cyan
- **Cache creation:** Yellow (costs extra)
- **Cache read:** Green (FREE!)
- **Total:** Bold Cyan
- **Cost:** Yellow
- **Labels:** Dim gray
- **Borders:** Dim blue

### ASCII Art Examples

#### Compact Display
```
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   1,234 tokens │ 456 cached │ $0.0123
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### Detailed Panel
```
  ┌─────────────────────────────────────────┐
  │  Token Usage                            │
  ├─────────────────────────────────────────┤
  │       Input:   1,234 tokens             │
  │      Output:     567 tokens             │
  │  Cache read:     456 tokens (FREE!)     │
  │       Total:   1,801 tokens             │
  │        Cost:   $0.0123                  │
  └─────────────────────────────────────────┘
```

#### With Cache Creation
```
  ┌─────────────────────────────────────────┐
  │  Token Usage                            │
  ├─────────────────────────────────────────┤
  │         Input:   1,234 tokens           │
  │        Output:     567 tokens           │
  │ Cache created:  15,678 tokens           │
  │    Cache read:       0 tokens           │
  │         Total:  17,479 tokens           │
  │          Cost:   $0.0678                │
  └─────────────────────────────────────────┘
```

---

## Testing Strategy

### Unit Tests

**File:** `tests/test_token_tracking.py` (NEW)

```python
import pytest
from testmcpy.token_tracking import TokenTracker, ModelPricing, MessageTokens


def test_token_tracker_initialization():
    """Test TokenTracker initializes correctly."""
    tracker = TokenTracker()
    assert tracker.session_input_tokens == 0
    assert tracker.session_output_tokens == 0
    assert tracker.session_total_cost == 0.0
    assert len(tracker.messages) == 0


def test_token_tracker_update():
    """Test TokenTracker updates correctly."""
    tracker = TokenTracker()
    
    token_usage = {
        "prompt": 1000,
        "completion": 500,
        "total": 1500,
        "cache_read": 200
    }
    
    message = tracker.update(token_usage, 0.05)
    
    assert message.input_tokens == 1000
    assert message.output_tokens == 500
    assert message.cache_read_tokens == 200
    assert tracker.session_input_tokens == 1000
    assert tracker.session_output_tokens == 500
    assert len(tracker.messages) == 1


def test_model_pricing_claude():
    """Test cost calculation for Claude models."""
    token_usage = {
        "input_tokens": 1000,
        "output_tokens": 500,
        "cache_read": 200
    }
    
    cost = ModelPricing.calculate_cost("claude-haiku-4-5", token_usage)
    
    # 1000 * 0.0008 / 1000 = 0.0008 (input)
    # 500 * 0.004 / 1000 = 0.002 (output)
    # 200 * 0.00008 / 1000 = 0.000016 (cache read)
    # Total ≈ 0.002816
    assert abs(cost - 0.002816) < 0.00001


def test_model_pricing_ollama():
    """Test cost calculation for Ollama (free)."""
    token_usage = {
        "input_tokens": 1000,
        "output_tokens": 500
    }
    
    cost = ModelPricing.calculate_cost("llama3.1:8b", token_usage)
    assert cost == 0.0


def test_session_summary():
    """Test session summary."""
    tracker = TokenTracker()
    
    # Add multiple messages
    tracker.update({"prompt": 1000, "completion": 500, "total": 1500}, 0.05)
    tracker.update({"prompt": 2000, "completion": 1000, "total": 3000}, 0.10)
    
    summary = tracker.get_summary()
    
    assert summary["message_count"] == 2
    assert summary["input_tokens"] == 3000
    assert summary["output_tokens"] == 1500
    assert summary["total_tokens"] == 4500
    assert summary["total_cost"] == 0.15
```

**File:** `tests/test_token_display.py` (NEW)

```python
import pytest
from rich.console import Console
from io import StringIO
from testmcpy.token_display import TokenDisplay
from testmcpy.token_tracking import TokenTracker


def test_format_number():
    """Test number formatting."""
    console = Console(file=StringIO())
    display = TokenDisplay(console)
    
    assert display.format_number(1234) == "1,234"
    assert display.format_number(1234567) == "1,234,567"


def test_format_cost():
    """Test cost formatting."""
    console = Console(file=StringIO())
    display = TokenDisplay(console)
    
    assert display.format_cost(0.1234) == "$0.1234"
    assert display.format_cost(1.5) == "$1.5000"


def test_display_message_tokens_compact():
    """Test compact token display."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    display = TokenDisplay(console)
    
    token_usage = {
        "prompt": 1234,
        "completion": 567,
        "total": 1801,
        "cache_read": 456
    }
    
    display.display_message_tokens(token_usage, 0.0123, compact=True)
    
    result = output.getvalue()
    assert "1,801 tokens" in result
    assert "456 cached" in result
    assert "$0.0123" in result


def test_display_session_summary():
    """Test session summary display."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    display = TokenDisplay(console)
    
    tracker = TokenTracker()
    tracker.update({"prompt": 1000, "completion": 500, "total": 1500}, 0.05)
    tracker.update({"prompt": 2000, "completion": 1000, "total": 3000}, 0.10)
    
    display.display_session_summary(tracker)
    
    result = output.getvalue()
    assert "Chat Session Summary" in result
    assert "Messages:" in result
    assert "2" in result
    assert "Total cost:" in result
```

### Integration Tests

**File:** `tests/integration/test_cli_chat_tokens.py` (NEW)

```python
import pytest
from click.testing import CliRunner
from testmcpy.cli import app
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_chat_displays_tokens():
    """Test that chat command displays token usage."""
    runner = CliRunner()
    
    # Mock LLM response
    mock_response = MagicMock()
    mock_response.response = "Hello!"
    mock_response.tool_calls = []
    mock_response.token_usage = {
        "prompt": 100,
        "completion": 50,
        "total": 150
    }
    mock_response.cost = 0.001
    
    # Mock LLM provider
    with patch('testmcpy.cli.create_llm_provider') as mock_create:
        mock_llm = AsyncMock()
        mock_llm.generate_with_tools = AsyncMock(return_value=mock_response)
        mock_llm.initialize = AsyncMock()
        mock_llm.close = AsyncMock()
        mock_create.return_value = mock_llm
        
        # Mock MCP client
        with patch('testmcpy.cli.MCPClient') as mock_mcp:
            mock_client = AsyncMock()
            mock_client.initialize = AsyncMock()
            mock_client.list_tools = AsyncMock(return_value=[])
            mock_client.close = AsyncMock()
            mock_mcp.return_value = mock_client
            
            # Run chat with input
            result = runner.invoke(app, ['chat', '--no-mcp'], input='hello\nexit\n')
            
            # Verify token display in output
            assert "150 tokens" in result.output or "Token Usage" in result.output
            assert result.exit_code == 0


@pytest.mark.asyncio
async def test_chat_session_summary():
    """Test that chat shows session summary on exit."""
    runner = CliRunner()
    
    # Test will be similar to above but check for session summary
    # ...
```

### Manual Testing Checklist

- [ ] Chat starts successfully with token display enabled
- [ ] Token usage displays after each message
- [ ] Compact mode shows inline token info
- [ ] Detailed mode shows panel with breakdown
- [ ] Cache tokens are highlighted as FREE
- [ ] Session summary displays on exit
- [ ] Special 'tokens' command shows current summary
- [ ] Costs are calculated correctly for different models
- [ ] Works with Anthropic (Claude) models
- [ ] Works with OpenAI models
- [ ] Works with Ollama models (shows $0.00)
- [ ] --hide-tokens flag works correctly
- [ ] --compact-tokens flag works correctly
- [ ] Ctrl+C shows summary before exit
- [ ] Numbers are formatted with commas
- [ ] Costs are formatted with 4 decimal places

---

## Rollout Plan

### Phase 1: Core Implementation (Day 1)

**Tasks:**
1. Create `testmcpy/token_tracking.py`
   - Implement `TokenTracker` class
   - Implement `ModelPricing` class
   - Add unit tests

2. Create `testmcpy/token_display.py`
   - Implement `TokenDisplay` class
   - Add display methods (compact, detailed, summary)
   - Add unit tests

**Deliverables:**
- Working token tracking system
- Rich console display components
- Unit tests passing

### Phase 2: CLI Integration (Day 2)

**Tasks:**
1. Modify `testmcpy/cli.py`
   - Add imports
   - Add command-line flags
   - Integrate TokenTracker
   - Integrate TokenDisplay
   - Add 'tokens' special command

2. Test integration
   - Manual testing with different models
   - Test with different display modes
   - Test session summaries

**Deliverables:**
- Working CLI integration
- Manual testing complete
- Integration tests

### Phase 3: Polish & Documentation (Day 3)

**Tasks:**
1. Polish display formatting
   - Adjust colors and styles
   - Ensure consistent spacing
   - Test on different terminal sizes

2. Update documentation
   - Add token display docs to README
   - Update CLI help text
   - Add examples to docs

3. Code review and cleanup
   - Remove debug code
   - Add docstrings
   - Format code

**Deliverables:**
- Production-ready feature
- Complete documentation
- All tests passing

---

## Dependencies

### New Files
- `testmcpy/token_tracking.py` - Core tracking logic
- `testmcpy/token_display.py` - Rich display components
- `tests/test_token_tracking.py` - Unit tests
- `tests/test_token_display.py` - Display tests
- `tests/integration/test_cli_chat_tokens.py` - Integration tests

### Modified Files
- `testmcpy/cli.py` - Add token display to chat command

### External Dependencies
- No new dependencies required!
- Uses existing `rich` library
- Uses existing `typer` library

---

## Future Enhancements

### Phase 4: Streaming Token Display (Future)
- Show token count in real-time during streaming
- Update status indicator with current tokens
- Requires streaming API support

### Phase 5: Token Budget Warnings (Future)
- Warn user when approaching budget limits
- Show remaining budget in session
- Configurable budget limits

### Phase 6: Token Analytics (Future)
- Save token usage to history
- Generate usage reports
- Track costs over time
- Export to CSV/JSON

### Phase 7: Multi-Provider Enhancements (Future)
- Better cost estimation for all providers
- Provider-specific optimizations
- Compare costs across providers

---

## Success Metrics

### Functionality
- [ ] Token usage displays after every message
- [ ] Costs are accurate within 0.01%
- [ ] Cache tokens are correctly identified
- [ ] Session summaries are accurate
- [ ] Works with all supported providers

### Usability
- [ ] Display is non-intrusive
- [ ] Information is clear and readable
- [ ] Compact mode is truly compact
- [ ] Detailed mode provides useful breakdown
- [ ] Session summary is informative

### Performance
- [ ] No noticeable latency from token tracking
- [ ] Memory usage remains low
- [ ] Display renders instantly

### Code Quality
- [ ] 100% test coverage for new code
- [ ] All tests passing
- [ ] No linting errors
- [ ] Well documented

---

## Risk Mitigation

### Risk 1: Inaccurate Cost Calculation
**Mitigation:** 
- Use official pricing from provider docs
- Add tests to verify calculations
- Allow manual cost override

### Risk 2: Display Clutters UI
**Mitigation:**
- Provide compact mode
- Allow hiding with flag
- Use dim colors for less distraction

### Risk 3: Missing Token Data
**Mitigation:**
- Handle missing/incomplete token usage gracefully
- Show "N/A" for unavailable data
- Don't crash if token_usage is None

### Risk 4: Pricing Changes
**Mitigation:**
- Make pricing easily updatable
- Add version comments to pricing table
- Provide configuration override

---

## Conclusion

This plan provides a comprehensive roadmap for implementing real-time token usage display in the testmcpy CLI chat interface. The implementation will:

1. **Enhance Transparency:** Users will see exactly how many tokens they're using
2. **Enable Cost Awareness:** Clear cost display helps users manage budgets
3. **Highlight Cache Benefits:** Show users when they're benefiting from caching
4. **Improve User Experience:** Beautiful Rich formatting makes data accessible

**Key Features:**
- Real-time token display after each message
- Accurate model-specific cost calculation
- Cache token highlighting
- Session summaries with breakdowns
- Flexible display modes (compact/detailed)
- Command-line flags for customization

**Implementation Timeline:** 2-3 days

**Next Steps:**
1. Review and approve this plan
2. Create feature branch
3. Implement Phase 1 (token tracking)
4. Implement Phase 2 (CLI integration)
5. Test and polish
6. Merge to main

---

**Questions or Feedback?** Please review and provide comments!
