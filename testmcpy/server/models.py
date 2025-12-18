"""
Shared Pydantic models and enums for the testmcpy API.
"""

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# Enums for validation
class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    LOCAL = "local"
    ANTHROPIC = "anthropic"
    CLAUDE_SDK = "claude-sdk"
    CLAUDE_CLI = "claude-cli"


class AuthType(str, Enum):
    NONE = "none"
    BEARER = "bearer"
    JWT = "jwt"
    OAUTH = "oauth"


# Shared Auth Configuration
class AuthConfig(BaseModel):
    """Unified auth configuration used across the application."""

    type: AuthType
    token: str | None = None
    api_url: str | None = None
    api_token: str | None = None
    api_secret: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str | None = None
    scopes: list[str] | None = None
    insecure: bool = False  # Skip SSL verification
    oauth_auto_discover: bool = False  # Use RFC 8414 auto-discovery for OAuth


# Chat models
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    model: str | None = None
    provider: LLMProvider | None = None
    llm_profile: str | None = None  # LLM profile ID to use
    profiles: list[str] | None = None  # List of MCP profile IDs to use
    history: list[dict[str, Any]] | None = None  # Chat history for context
    stream: bool = False  # Enable streaming responses


class ChatResponse(BaseModel):
    response: str
    tool_calls: list[dict[str, Any]] = []
    token_usage: dict[str, int] | None = None
    cost: float = 0.0
    duration: float = 0.0


# Test models
class TestFileCreate(BaseModel):
    # Support both structured data and raw YAML content
    filename: str | None = None
    content: str | None = None
    # Structured test data fields
    name: str | None = None
    description: str | None = None
    test_cases: list[dict[str, Any]] | None = None


class TestFileUpdate(BaseModel):
    # Support both structured data and raw YAML content
    content: str | None = None
    # Structured test data fields
    name: str | None = None
    description: str | None = None
    test_cases: list[dict[str, Any]] | None = None


class TestRunRequest(BaseModel):
    test_path: str
    model: str | None = None
    provider: str | None = None
    profile: str | None = None  # MCP profile selection (e.g., "sandbox:My Workspace")
    test_name: str | None = None  # Optional: run only a specific test by name
    stream: bool = False  # Enable streaming test output


class EvalRunRequest(BaseModel):
    prompt: str
    response: str
    tool_calls: list[dict[str, Any]] = []
    model: str | None = None
    provider: str | None = None


class GenerateTestsRequest(BaseModel):
    tool_name: str
    tool_description: str
    tool_schema: dict[str, Any]
    coverage_level: str  # "basic", "mid", "comprehensive"
    custom_instructions: str | None = None
    model: str | None = None
    provider: str | None = None


# Format models
class FormatSchemaRequest(BaseModel):
    tool_schema: dict[str, Any] = Field(..., alias="schema")
    tool_name: str
    format: str  # e.g., "python_client", "javascript_client", "typescript_client"
    mcp_url: str | None = None  # For curl format with actual values
    auth_token: str | None = None  # For curl format with actual values
    profile: str | None = None  # MCP profile to get auth from (e.g., "sandbox:My Workspace")

    model_config = {"populate_by_name": True}


class OptimizeDocsRequest(BaseModel):
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    model: str | None = None
    provider: str | None = None


class OptimizeDocsResponse(BaseModel):
    analysis: dict[str, Any]
    suggestions: dict[str, Any]
    original: dict[str, Any]
    cost: float
    duration: float


# Profile models
class ProfileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=1000)
    set_as_default: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "Profile name must contain only alphanumeric characters, hyphens, and underscores"
            )
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Profile name cannot contain path traversal characters")
        if "\x00" in v:
            raise ValueError("Profile name cannot contain null bytes")
        return v


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    set_as_default: bool | None = None


class MCPCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    mcp_url: str
    auth: AuthConfig
    timeout: int | None = None
    rate_limit_rpm: int | None = None


class MCPUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    mcp_url: str | None = None
    auth: AuthConfig | None = None
    timeout: int | None = None
    rate_limit_rpm: int | None = None


class MCPReorderRequest(BaseModel):
    from_index: int
    to_index: int


# Auth debugging models
class DebugAuthRequest(BaseModel):
    auth_type: str  # "oauth", "jwt", "bearer"
    mcp_url: str | None = None  # MCP endpoint to test token against
    # OAuth fields
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str | None = None
    scopes: list[str] | None = None
    oauth_auto_discover: bool = False  # Use RFC 8414 auto-discovery for OAuth
    # JWT fields
    api_url: str | None = None
    api_token: str | None = None
    api_secret: str | None = None
    insecure: bool = False  # Skip SSL verification
    # Bearer fields
    token: str | None = None


class DebugAuthResponse(BaseModel):
    success: bool
    auth_type: str
    steps: list[dict[str, Any]]
    total_time: float
    error: str | None = None


class SaveAuthFlowRequest(BaseModel):
    flow_name: str
    filename: str | None = None


class AuthFlowListItem(BaseModel):
    filepath: str
    filename: str
    recording_id: str
    flow_name: str
    auth_type: str
    created_at: str
    duration: float
    success: bool | None
    step_count: int


class AuthFlowCompareRequest(BaseModel):
    filepath1: str
    filepath2: str


# Tool models
class ToolCompareRequest(BaseModel):
    tool_name: str
    profile1: str  # Format: "profile_id:mcp_name"
    profile2: str  # Format: "profile_id:mcp_name"
    parameters: dict[str, Any] = {}
    iterations: int = 3


class ToolDebugRequest(BaseModel):
    parameters: dict[str, Any]
    profile: str | None = None


class ToolDebugResponse(BaseModel):
    success: bool
    response: dict[str, Any] | list[Any] | str | None
    steps: list[dict[str, Any]]
    total_time: float
    error: str | None = None


# Smoke test models
class SmokeTestRequest(BaseModel):
    profile: str  # MCP profile selection
    mcp_index: int = 0  # Which MCP in the profile to test
