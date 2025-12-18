"""
Documentation optimizer module using LLM.

Provides AI-powered documentation improvement for MCP tools.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from testmcpy.config import get_config
from testmcpy.src.llm_integration import create_llm_provider
from testmcpy.src.mcp_client import MCPTool


@dataclass
class OptimizationResult:
    """Result from optimizing tool documentation."""

    original_description: str
    optimized_description: str
    suggestions: list[str]
    parameter_improvements: dict[str, str]
    cost: float = 0.0
    tokens_used: int = 0


class DocsOptimizer:
    """Optimizes MCP tool documentation using LLM."""

    def __init__(self, model: str | None = None, provider: str | None = None):
        """
        Initialize docs optimizer.

        Args:
            model: LLM model to use (defaults to config)
            provider: LLM provider to use (defaults to config)
        """
        config = get_config()
        self.model = model or config.default_model or "claude-haiku-4-5"
        self.provider = provider or config.default_provider or "anthropic"
        self.llm = None

    async def initialize(self):
        """Initialize the LLM provider."""
        if not self.llm:
            self.llm = create_llm_provider(self.provider, self.model)
            await self.llm.initialize()

    async def close(self):
        """Close the LLM provider."""
        if self.llm:
            await self.llm.close()
            self.llm = None

    async def optimize_tool_docs(self, tool: MCPTool) -> OptimizationResult:
        """
        Optimize documentation for a single tool.

        Args:
            tool: MCPTool to optimize

        Returns:
            OptimizationResult with improvements
        """
        await self.initialize()

        # Build prompt for LLM
        prompt = self._build_optimization_prompt(tool)

        # Generate optimization
        response = await self.llm.generate(prompt)

        # Parse response
        result = self._parse_optimization_response(
            tool, response.response, response.token_usage or {}
        )

        return result

    def _build_optimization_prompt(self, tool: MCPTool) -> str:
        """Build prompt for optimizing tool documentation."""
        schema_str = str(tool.input_schema)
        if len(schema_str) > 500:
            schema_str = schema_str[:500] + "..."

        prompt = f"""You are a technical documentation expert. Analyze and improve the documentation for this MCP tool.

Tool Name: {tool.name}

Current Description:
{tool.description}

Input Schema:
{schema_str}

Please provide:
1. An improved, clearer description (2-3 sentences)
2. 3 specific suggestions for improvement
3. Better descriptions for any unclear parameters

Format your response as:

IMPROVED DESCRIPTION:
[Your improved description here]

SUGGESTIONS:
- [Suggestion 1]
- [Suggestion 2]
- [Suggestion 3]

PARAMETER IMPROVEMENTS:
[parameter_name]: [improved description]
[parameter_name]: [improved description]

Keep responses concise and actionable."""

        return prompt

    def _parse_optimization_response(
        self, tool: MCPTool, response: str, token_usage: dict[str, Any]
    ) -> OptimizationResult:
        """Parse LLM response into OptimizationResult."""
        lines = response.split("\n")

        optimized_description = ""
        suggestions = []
        parameter_improvements = {}

        current_section = None

        for line in lines:
            line = line.strip()

            if line.startswith("IMPROVED DESCRIPTION:"):
                current_section = "description"
                continue
            elif line.startswith("SUGGESTIONS:"):
                current_section = "suggestions"
                continue
            elif line.startswith("PARAMETER IMPROVEMENTS:"):
                current_section = "parameters"
                continue

            if not line:
                continue

            if current_section == "description":
                optimized_description += line + " "
            elif current_section == "suggestions" and line.startswith("-"):
                suggestions.append(line[1:].strip())
            elif current_section == "parameters" and ":" in line:
                param_name, param_desc = line.split(":", 1)
                parameter_improvements[param_name.strip()] = param_desc.strip()

        # Calculate approximate cost (rough estimate)
        total_tokens = token_usage.get("total_tokens", 0)
        cost = total_tokens * 0.000001  # Rough estimate

        return OptimizationResult(
            original_description=tool.description,
            optimized_description=optimized_description.strip() or tool.description,
            suggestions=suggestions or ["No suggestions provided"],
            parameter_improvements=parameter_improvements,
            cost=cost,
            tokens_used=total_tokens,
        )

    async def batch_optimize(self, tools: list[MCPTool]) -> list[OptimizationResult]:
        """
        Optimize documentation for multiple tools.

        Args:
            tools: List of MCPTool objects

        Returns:
            List of OptimizationResult objects
        """
        results = []
        for tool in tools:
            result = await self.optimize_tool_docs(tool)
            results.append(result)
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

        return results


async def optimize_tool(
    tool: MCPTool, model: str | None = None, provider: str | None = None
) -> OptimizationResult:
    """
    Optimize documentation for a single tool.

    Args:
        tool: MCPTool to optimize
        model: LLM model to use
        provider: LLM provider to use

    Returns:
        OptimizationResult with improvements
    """
    optimizer = DocsOptimizer(model, provider)
    try:
        result = await optimizer.optimize_tool_docs(tool)
        return result
    finally:
        await optimizer.close()
