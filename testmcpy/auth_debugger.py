"""
Authentication flow debugger with rich console output.

This module provides detailed logging and visualization for OAuth, JWT,
and other authentication flows to help debug authentication issues.
"""

import json
import time
from pathlib import Path
from typing import Any, Literal

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.tree import Tree


class AuthDebugger:
    """Debug authentication flows with detailed logging."""

    def __init__(self, enabled: bool = False, recorder=None):
        """Initialize the auth debugger.

        Args:
            enabled: Whether debugging is enabled
            recorder: Optional AuthFlowRecorder instance for recording flows
        """
        self.enabled = enabled
        self.console = Console()
        self.steps: list[dict[str, Any]] = []
        self.start_time = time.time()
        self.recorder = recorder
        self._current_flow_name: str | None = None
        self._current_auth_type: Literal["oauth", "jwt", "bearer"] | None = None

    def start_flow_recording(
        self,
        flow_name: str,
        auth_type: Literal["oauth", "jwt", "bearer"],
        protocol_version: str | None = None,
    ) -> None:
        """Start recording an authentication flow.

        Args:
            flow_name: Name/description of the flow
            auth_type: Type of authentication
            protocol_version: Version of the auth protocol
        """
        self._current_flow_name = flow_name
        self._current_auth_type = auth_type
        if self.recorder:
            self.recorder.start_recording(
                flow_name=flow_name,
                auth_type=auth_type,
                protocol_version=protocol_version,
            )

    def log_step(
        self,
        step_name: str,
        data: dict[str, Any],
        success: bool = True,
        step_type: Literal[
            "request", "response", "validation", "extraction", "error"
        ] = "validation",
    ):
        """Log a step in the auth flow.

        Args:
            step_name: Name of the authentication step
            data: Data associated with the step
            success: Whether the step was successful
            step_type: Type of step (for recorder)
        """
        if not self.enabled:
            return

        timestamp = time.time() - self.start_time

        self.steps.append(
            {"step": step_name, "data": data, "success": success, "timestamp": timestamp}
        )

        # Record to recorder if available
        if self.recorder and self.recorder.current_recording:
            self.recorder.record_step(
                step_name=step_name,
                step_type=step_type,
                data=data.copy(),
                success=success,
            )

        # Pretty print the step
        color = "green" if success else "red"
        icon = "✓" if success else "✗"

        self.console.print(f"\n[{color}]{icon} {step_name}[/{color}]")

        # Sanitize sensitive data for display
        display_data = self._sanitize_data(data)

        self.console.print(
            Panel(
                Syntax(json.dumps(display_data, indent=2), "json"),
                title=f"{step_name} Details",
                border_style=color,
            )
        )

    def _sanitize_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Sanitize sensitive data for display.

        Args:
            data: Data to sanitize

        Returns:
            Sanitized data dictionary
        """
        sanitized = {}
        sensitive_keys = ["client_secret", "api_secret", "password"]
        # Don't sanitize token_length or token_preview keys, only "token" and "access_token"
        sensitive_token_keys = ["token", "access_token"]

        for key, value in data.items():
            key_lower = key.lower()

            # Check if it's a sensitive key (but not token_length or token_preview)
            is_sensitive = any(sensitive in key_lower for sensitive in sensitive_keys)
            is_token = any(token_key == key_lower for token_key in sensitive_token_keys)

            if is_sensitive or is_token:
                # Show only first 8 characters for secrets
                if isinstance(value, str) and len(value) > 8:
                    sanitized[key] = value[:8] + "..."
                elif isinstance(value, str):
                    sanitized[key] = "***"
                else:
                    sanitized[key] = value
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_data(value)
            else:
                sanitized[key] = value

        return sanitized

    def log_oauth_flow(self, flow_type: str, steps: dict[str, dict[str, Any]]):
        """Log complete OAuth flow with tree visualization.

        Args:
            flow_type: Type of OAuth flow (e.g., "Client Credentials")
            steps: Dictionary of steps and their data
        """
        if not self.enabled:
            return

        tree = Tree(f"[cyan]OAuth {flow_type} Flow[/cyan]")

        for step_name, step_data in steps.items():
            branch = tree.add(f"[green]{step_name}[/green]")
            sanitized_data = self._sanitize_data(step_data)
            for key, value in sanitized_data.items():
                branch.add(f"{key}: {value}")

        self.console.print(tree)

    def summarize(self) -> dict[str, Any]:
        """Print summary of all auth steps and return summary data.

        Returns:
            Summary dictionary with flow statistics
        """
        if not self.enabled or not self.steps:
            return {}

        total_time = time.time() - self.start_time
        success_count = sum(1 for step in self.steps if step["success"])
        failure_count = len(self.steps) - success_count

        self.console.print("\n[cyan]Authentication Flow Summary[/cyan]")
        for i, step in enumerate(self.steps, 1):
            icon = "✓" if step["success"] else "✗"
            color = "green" if step["success"] else "red"
            self.console.print(f"  [{color}]{i}. {icon} {step['step']}[/{color}]")

        self.console.print(f"\n[dim]Total time: {total_time:.2f}s[/dim]")

        if failure_count == 0:
            self.console.print("\n[bold green]Authentication successful![/bold green]")
        else:
            self.console.print(
                f"\n[bold red]Authentication failed ({failure_count} error(s))[/bold red]"
            )

        return {
            "total_steps": len(self.steps),
            "successful_steps": success_count,
            "failed_steps": failure_count,
            "total_time": total_time,
            "steps": self.steps,
        }

    def get_trace(self) -> dict[str, Any]:
        """Get the complete debug trace.

        Returns:
            Dictionary containing all debug information
        """
        return {
            "enabled": self.enabled,
            "steps": self.steps,
            "total_time": time.time() - self.start_time if self.steps else 0,
        }

    def clear(self) -> None:
        """Clear all logged steps.

        Useful for resetting the debugger state between different authentication
        attempts or test runs.

        Example:
            ```python
            debugger = AuthDebugger(enabled=True)
            # ... log some steps ...
            debugger.summarize()
            debugger.clear()  # Reset for next authentication flow
            ```
        """
        self.steps = []
        self.start_time = time.time()

    def get_steps(self) -> list[dict[str, Any]]:
        """Get all logged steps.

        Returns:
            List of step dictionaries, each containing 'step', 'data', 'success', and 'timestamp' keys.

        Example:
            ```python
            debugger = AuthDebugger(enabled=True)
            # ... log some steps ...
            steps = debugger.get_steps()
            assert len(steps) == 4
            assert steps[0]['success'] is True
            ```
        """
        return self.steps.copy()

    def has_failures(self) -> bool:
        """Check if any logged step failed.

        Returns:
            True if any step has success=False, False otherwise.

        Example:
            ```python
            debugger = AuthDebugger(enabled=True)
            debugger.log_step("Token Fetch", {"error": "timeout"}, success=False)
            assert debugger.has_failures() is True
            ```
        """
        return any(not step["success"] for step in self.steps)

    def get_failure_steps(self) -> list[dict[str, Any]]:
        """Get all steps that failed.

        Returns:
            List of step dictionaries where success=False.

        Example:
            ```python
            debugger = AuthDebugger(enabled=True)
            # ... log some steps ...
            failures = debugger.get_failure_steps()
            for failure in failures:
                print(f"Failed: {failure['step']}")
            ```
        """
        return [step for step in self.steps if not step["success"]]

    def export_trace(self, filepath: str) -> None:
        """Export the complete debug trace to a JSON file.

        Args:
            filepath: Path to the output JSON file

        Example:
            ```python
            debugger = AuthDebugger(enabled=True)
            # ... log some steps ...
            debugger.export_trace("auth-trace.json")
            ```
        """
        import json
        from pathlib import Path

        trace = self.get_trace()
        Path(filepath).write_text(json.dumps(trace, indent=2))

        if self.enabled:
            self.console.print(f"\n[dim]Debug trace saved to: {filepath}[/dim]")

    def save_flow_recording(
        self, success: bool = True, error: str | None = None, filename: str | None = None
    ) -> Path | None:
        """Save the current flow recording.

        Args:
            success: Whether the overall flow was successful
            error: Error message if flow failed
            filename: Optional custom filename

        Returns:
            Path to the saved recording file, or None if no recorder is active

        Example:
            ```python
            debugger = AuthDebugger(enabled=True, recorder=recorder)
            debugger.start_flow_recording("OAuth Login", "oauth")
            # ... log some steps ...
            filepath = debugger.save_flow_recording(success=True)
            ```
        """
        if not self.recorder or not self.recorder.current_recording:
            return None

        recording = self.recorder.stop_recording(success=success, error=error, auto_save=False)
        filepath = self.recorder.save_recording(recording, filename=filename)

        if self.enabled:
            self.console.print(f"\n[green]Flow recording saved to: {filepath}[/green]")

        return filepath


async def discover_oauth_endpoints(
    mcp_url: str,
    debugger: AuthDebugger | None = None,
    insecure: bool = False,
) -> dict[str, Any]:
    """Discover OAuth endpoints using RFC 8414 well-known endpoint.

    Args:
        mcp_url: The MCP service URL to discover OAuth config from
        debugger: Optional AuthDebugger instance
        insecure: Skip SSL certificate verification

    Returns:
        Dictionary with OAuth server metadata including token_endpoint, etc.

    Raises:
        Exception: If discovery fails
    """
    if debugger is None:
        debugger = AuthDebugger(enabled=False)

    # Parse the MCP URL to get the base URL
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(mcp_url)
    base_url = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))

    # RFC 8414 well-known endpoint
    well_known_url = f"{base_url}/.well-known/oauth-authorization-server"

    debugger.log_step(
        "1. OAuth Discovery Started",
        {
            "mcp_url": mcp_url,
            "base_url": base_url,
            "well_known_url": well_known_url,
        },
        step_type="request",
    )

    try:
        async with httpx.AsyncClient(verify=not insecure) as client:
            request_headers = {
                "Accept": "application/json",
                "User-Agent": "testmcpy/1.0",
            }
            debugger.log_step(
                "2. Fetching OAuth Server Metadata",
                {
                    "url": well_known_url,
                    "method": "GET",
                    "headers": request_headers,
                    "raw_request": f"GET {well_known_url} HTTP/1.1\nAccept: application/json\nUser-Agent: testmcpy/1.0",
                },
                step_type="request",
            )

            response = await client.get(well_known_url, headers=request_headers, timeout=10.0)

            # Capture raw response
            raw_response = f"HTTP/1.1 {response.status_code} {response.reason_phrase}\n"
            for key, value in response.headers.items():
                raw_response += f"{key}: {value}\n"
            raw_response += f"\n{response.text[:2000]}"

            debugger.log_step(
                "3. Discovery Response Received",
                {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "raw_response": raw_response,
                    "response_body": response.text[:2000],
                },
                success=response.status_code == 200,
                step_type="response",
            )

            if response.status_code != 200:
                debugger.log_step(
                    "3. Discovery Failed",
                    {
                        "error": f"HTTP {response.status_code}",
                        "response_body": response.text[:500],
                    },
                    success=False,
                    step_type="error",
                )
                raise Exception(
                    f"OAuth discovery failed: HTTP {response.status_code} from {well_known_url}"
                )

            metadata = response.json()

            debugger.log_step(
                "4. OAuth Metadata Parsed",
                {
                    "issuer": metadata.get("issuer"),
                    "token_endpoint": metadata.get("token_endpoint"),
                    "authorization_endpoint": metadata.get("authorization_endpoint"),
                    "registration_endpoint": metadata.get("registration_endpoint"),
                    "scopes_supported": metadata.get("scopes_supported", []),
                    "grant_types_supported": metadata.get("grant_types_supported", []),
                    "response_types_supported": metadata.get("response_types_supported", []),
                },
                success=True,
                step_type="extraction",
            )

            return metadata

    except httpx.HTTPError as e:
        error_data = {
            "error": str(e),
            "error_type": type(e).__name__,
        }
        if hasattr(e, "response") and e.response is not None:
            error_data["status_code"] = e.response.status_code
            error_data["response_body"] = e.response.text[:500]

        debugger.log_step("ERROR: Discovery HTTP Request Failed", error_data, success=False)
        raise Exception(f"OAuth discovery failed: {e}")
    except json.JSONDecodeError as e:
        debugger.log_step(
            "ERROR: Invalid JSON in Discovery Response",
            {"error": str(e)},
            success=False,
        )
        raise Exception(f"OAuth discovery returned invalid JSON: {e}")
    except Exception as e:
        if "OAuth discovery failed" in str(e):
            raise
        debugger.log_step(
            "ERROR: Unexpected Discovery Error",
            {"error": str(e), "error_type": type(e).__name__},
            success=False,
        )
        raise


async def debug_oauth_auto_discover_flow(
    mcp_url: str,
    debugger: AuthDebugger | None = None,
    insecure: bool = False,
) -> dict[str, Any]:
    """Debug OAuth flow using RFC 8414 auto-discovery.

    This function discovers OAuth endpoints from the MCP server and returns
    the metadata. It does NOT perform token exchange since dynamic client
    registration would be needed.

    Args:
        mcp_url: The MCP service URL
        debugger: Optional AuthDebugger instance
        insecure: Skip SSL certificate verification

    Returns:
        Dictionary with discovered OAuth metadata

    Raises:
        Exception: If discovery fails
    """
    if debugger is None:
        debugger = AuthDebugger(enabled=False)

    # Discover OAuth endpoints
    metadata = await discover_oauth_endpoints(mcp_url, debugger, insecure)

    # Check for required endpoints
    if not metadata.get("token_endpoint"):
        debugger.log_step(
            "5. Missing Token Endpoint",
            {
                "error": "OAuth metadata does not include token_endpoint",
                "available_fields": list(metadata.keys()),
            },
            success=False,
            step_type="validation",
        )
        raise Exception("OAuth discovery succeeded but no token_endpoint found")

    # Check for registration endpoint (needed for dynamic client registration)
    if metadata.get("registration_endpoint"):
        debugger.log_step(
            "5. Dynamic Client Registration Available",
            {
                "registration_endpoint": metadata["registration_endpoint"],
                "note": "Server supports dynamic client registration (RFC 7591)",
            },
            success=True,
            step_type="validation",
        )
    else:
        debugger.log_step(
            "5. No Dynamic Client Registration",
            {
                "note": "Server does not support dynamic client registration",
                "action_required": "Manual client_id and client_secret required",
            },
            success=True,
            step_type="validation",
        )

    debugger.log_step(
        "6. OAuth Discovery Complete",
        {
            "token_endpoint": metadata.get("token_endpoint"),
            "authorization_endpoint": metadata.get("authorization_endpoint"),
            "scopes_supported": metadata.get("scopes_supported", []),
            "grant_types_supported": metadata.get("grant_types_supported", []),
        },
        success=True,
        step_type="validation",
    )

    return metadata


async def debug_oauth_flow(
    client_id: str,
    client_secret: str,
    token_url: str,
    scopes: list[str] | None = None,
    debugger: AuthDebugger | None = None,
) -> str:
    """Debug OAuth client credentials flow.

    Args:
        client_id: OAuth client ID
        client_secret: OAuth client secret
        token_url: OAuth token endpoint URL
        scopes: Optional list of OAuth scopes
        debugger: Optional AuthDebugger instance

    Returns:
        OAuth access token

    Raises:
        Exception: If token fetch fails
    """
    if debugger is None:
        debugger = AuthDebugger(enabled=False)

    # Step 1: Prepare request
    request_data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": " ".join(scopes) if scopes else "",
    }

    # Build raw request for display
    request_body = f"grant_type=client_credentials&client_id={client_id}&client_secret=***&scope={' '.join(scopes) if scopes else ''}"
    raw_request = f"POST {token_url} HTTP/1.1\nContent-Type: application/x-www-form-urlencoded\n\n{request_body}"

    debugger.log_step(
        "1. OAuth Request Prepared",
        {
            **request_data,
            "raw_request": raw_request,
        },
        step_type="request",
    )

    try:
        async with httpx.AsyncClient() as client:
            # Step 2: Send request
            debugger.log_step(
                "2. Sending POST to Token Endpoint",
                {
                    "url": token_url,
                    "method": "POST",
                    "headers": {"Content-Type": "application/x-www-form-urlencoded"},
                    "body": request_body,
                },
                step_type="request",
            )

            response = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": " ".join(scopes) if scopes else "",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )

            # Capture raw response
            raw_response = f"HTTP/1.1 {response.status_code} {response.reason_phrase}\n"
            for key, value in response.headers.items():
                raw_response += f"{key}: {value}\n"
            raw_response += f"\n{response.text[:2000]}"

            # Step 3: Response received
            debugger.log_step(
                "3. Response Received",
                {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "raw_response": raw_response,
                    "response_body": response.text[:2000],
                },
                step_type="response",
            )

            response.raise_for_status()
            data = response.json()

            # Step 4: Token extracted
            if "access_token" not in data:
                debugger.log_step(
                    "4. Token Extraction Failed",
                    {
                        "error": "No access_token found in response",
                        "response_keys": list(data.keys()),
                    },
                    success=False,
                )
                raise Exception("No access_token found in OAuth response")

            token = data["access_token"]
            debugger.log_step(
                "4. Token Extracted",
                {
                    "access_token": token,
                    "expires_in": data.get("expires_in", "unknown"),
                    "scope": data.get("scope", "unknown"),
                    "token_type": data.get("token_type", "unknown"),
                },
                success=True,
            )

            return token

    except httpx.HTTPError as e:
        error_data = {
            "error": str(e),
            "error_type": type(e).__name__,
        }
        if hasattr(e, "response"):
            error_data["status_code"] = e.response.status_code
            error_data["response_body"] = e.response.text[:500]  # Limit response size

        debugger.log_step("ERROR: HTTP Request Failed", error_data, success=False)
        raise
    except Exception as e:
        debugger.log_step(
            "ERROR: Unexpected Error",
            {"error": str(e), "error_type": type(e).__name__},
            success=False,
        )
        raise


async def debug_jwt_flow(
    api_url: str,
    api_token: str,
    api_secret: str,
    debugger: AuthDebugger | None = None,
    insecure: bool = False,
) -> str:
    """Debug JWT dynamic token fetch flow.

    Args:
        api_url: JWT API endpoint URL
        api_token: API token for authentication
        api_secret: API secret for authentication
        debugger: Optional AuthDebugger instance
        insecure: Skip SSL certificate verification

    Returns:
        JWT access token

    Raises:
        Exception: If token fetch fails
    """
    if debugger is None:
        debugger = AuthDebugger(enabled=False)

    # Step 1: Prepare request
    request_data = {
        "name": api_token,
        "secret": api_secret,
    }

    # Build raw request for display (mask secret)
    request_body_display = json.dumps({"name": api_token, "secret": "***"}, indent=2)
    raw_request = f"POST {api_url} HTTP/1.1\nContent-Type: application/json\nAccept: application/json\n\n{request_body_display}"

    debugger.log_step(
        "1. JWT Request Prepared",
        {
            **request_data,
            "raw_request": raw_request,
        },
        step_type="request",
    )

    try:
        async with httpx.AsyncClient(verify=not insecure) as client:
            # Step 2: Send request
            debugger.log_step(
                "2. Sending POST to JWT Endpoint",
                {
                    "url": api_url,
                    "method": "POST",
                    "headers": {"Content-Type": "application/json", "Accept": "application/json"},
                    "body": request_body_display,
                },
                step_type="request",
            )

            response = await client.post(
                api_url,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json=request_data,
                timeout=10.0,
            )

            # Capture raw response
            raw_response = f"HTTP/1.1 {response.status_code} {response.reason_phrase}\n"
            for key, value in response.headers.items():
                raw_response += f"{key}: {value}\n"
            raw_response += f"\n{response.text[:2000]}"

            # Step 3: Response received
            debugger.log_step(
                "3. Response Received",
                {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "raw_response": raw_response,
                    "response_body": response.text[:2000],
                },
                step_type="response",
            )

            response.raise_for_status()
            data = response.json()

            # Step 4: Token extracted
            # Supports both {"payload": {"access_token": "..."}} and {"access_token": "..."}
            token = None
            if "payload" in data and "access_token" in data["payload"]:
                token = data["payload"]["access_token"]
            elif "access_token" in data:
                token = data["access_token"]

            if not token:
                debugger.log_step(
                    "4. Token Extraction Failed",
                    {
                        "error": "No access_token found in response",
                        "response_keys": list(data.keys()),
                    },
                    success=False,
                )
                raise Exception("No access_token found in JWT response")

            debugger.log_step(
                "4. Token Extracted",
                {
                    "access_token": token,
                },
                success=True,
            )

            return token

    except httpx.HTTPError as e:
        error_data = {
            "error": str(e),
            "error_type": type(e).__name__,
        }
        if hasattr(e, "response"):
            error_data["status_code"] = e.response.status_code
            error_data["response_body"] = e.response.text[:500]  # Limit response size

        debugger.log_step("ERROR: HTTP Request Failed", error_data, success=False)
        raise
    except Exception as e:
        debugger.log_step(
            "ERROR: Unexpected Error",
            {"error": str(e), "error_type": type(e).__name__},
            success=False,
        )
        raise


async def debug_bearer_token(
    token: str, mcp_url: str | None = None, debugger: AuthDebugger | None = None
) -> str:
    """Debug bearer token authentication by testing against MCP endpoint.

    Args:
        token: Bearer token
        mcp_url: MCP endpoint URL to test against
        debugger: Optional AuthDebugger instance

    Returns:
        The bearer token

    Raises:
        Exception: If token validation fails
    """
    if debugger is None:
        debugger = AuthDebugger(enabled=False)

    debugger.log_step(
        "1. Bearer Token Provided",
        {
            "access_token": token,
        },
        success=True,
    )

    if not mcp_url:
        debugger.log_step(
            "2. No MCP URL provided",
            {
                "warning": "Cannot validate token without MCP URL",
            },
            success=True,
        )
        return token

    # Test the token against MCP endpoint
    try:
        debugger.log_step(
            "2. Testing token against MCP endpoint",
            {
                "mcp_url": mcp_url,
            },
            success=True,
        )

        async with httpx.AsyncClient() as client:
            # Send tools/list request to MCP
            response = await client.post(
                mcp_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                timeout=10.0,
            )

            debugger.log_step(
                "3. Response Received",
                {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                },
                success=response.status_code == 200,
            )

            if response.status_code == 401:
                debugger.log_step(
                    "4. Token Rejected",
                    {
                        "error": "Unauthorized - token is invalid or expired",
                        "response_body": response.text[:500],
                    },
                    success=False,
                )
                raise Exception("Bearer token rejected by MCP server (401 Unauthorized)")

            if response.status_code != 200:
                debugger.log_step(
                    "4. Request Failed",
                    {
                        "error": f"HTTP {response.status_code}",
                        "response_body": response.text[:500],
                    },
                    success=False,
                )
                raise Exception(f"MCP request failed with status {response.status_code}")

            # Parse response - handle both JSON and SSE formats
            content_type = response.headers.get("content-type", "")
            response_text = response.text

            if "text/event-stream" in content_type:
                # SSE format - parse the data lines
                tools_count = 0
                for line in response_text.split("\n"):
                    if line.startswith("data:"):
                        try:
                            import json

                            data = json.loads(line[5:].strip())
                            if "result" in data and "tools" in data["result"]:
                                tools_count = len(data["result"]["tools"])
                                break
                        except json.JSONDecodeError:
                            pass

                debugger.log_step(
                    "4. Token Validated Successfully",
                    {
                        "tools_available": tools_count,
                        "response_format": "SSE",
                        "response": response_text,
                    },
                    success=True,
                )
            else:
                # JSON format
                data = response.json()
                tools_count = len(data.get("result", {}).get("tools", []))

                debugger.log_step(
                    "4. Token Validated Successfully",
                    {
                        "tools_available": tools_count,
                        "response_format": "JSON",
                        "response": data,
                    },
                    success=True,
                )

            return token

    except httpx.HTTPError as e:
        debugger.log_step(
            "ERROR: HTTP Request Failed",
            {
                "error": str(e),
                "error_type": type(e).__name__,
            },
            success=False,
        )
        raise
    except Exception as e:
        if "Bearer token rejected" in str(e) or "MCP request failed" in str(e):
            raise
        debugger.log_step(
            "ERROR: Unexpected Error",
            {
                "error": str(e),
                "error_type": type(e).__name__,
            },
            success=False,
        )
        raise
