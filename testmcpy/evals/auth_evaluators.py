"""
Authentication-specific evaluators for testmcpy.

These evaluators validate authentication flows including OAuth2, JWT,
and Bearer token authentication. They can be used to test auth success,
token validity, OAuth flow completion, and error handling.
"""

import re
from typing import Any

from testmcpy.evals.base_evaluators import BaseEvaluator, EvalResult


class AuthSuccessfulEvaluator(BaseEvaluator):
    """
    Evaluate if authentication was successful.

    Checks if authentication completed without errors by examining:
    - auth_success flag in metadata
    - absence of auth_error in metadata
    - presence of auth_token in metadata

    Args:
        args: Optional configuration dict (currently unused)

    Example:
        ```python
        evaluator = AuthSuccessfulEvaluator()
        result = evaluator.evaluate({
            "metadata": {
                "auth_success": True,
                "auth_error": None
            }
        })
        ```
    """

    def __init__(self, args: dict[str, Any] | None = None):
        """
        Initialize the evaluator.

        Args:
            args: Optional configuration dictionary
        """
        self.args = args or {}

    @property
    def name(self) -> str:
        return "auth_successful"

    @property
    def description(self) -> str:
        return "Checks if authentication was successful"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        """
        Evaluate authentication success.

        Args:
            context: Dictionary containing metadata with auth information

        Returns:
            EvalResult with pass/fail status
        """
        metadata = context.get("metadata", {})

        # Check for auth success flag
        auth_success = metadata.get("auth_success", False)
        auth_error = metadata.get("auth_error")
        auth_token = metadata.get("auth_token")

        # Success if auth_success is True and no error
        if auth_success and not auth_error:
            return EvalResult(
                passed=True,
                score=1.0,
                reason="Authentication completed successfully",
                details={
                    "has_token": bool(auth_token),
                    "token_length": len(auth_token) if auth_token else 0,
                },
            )

        # Partial success if we have a token but no explicit success flag
        if auth_token and not auth_error:
            return EvalResult(
                passed=True,
                score=0.9,
                reason="Authentication token present (success flag not set)",
                details={"token_length": len(auth_token)},
            )

        # Failure cases
        if auth_error:
            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"Authentication failed: {auth_error}",
                details={"error": auth_error},
            )

        return EvalResult(
            passed=False, score=0.0, reason="No authentication information found in metadata"
        )


class TokenValidEvaluator(BaseEvaluator):
    """
    Evaluate if OAuth/JWT token is valid and meets format requirements.

    Validates tokens based on:
    - Format (JWT, Bearer, etc.)
    - Minimum length requirements
    - JWT structure and claims (if format=jwt)
    - Expiration (if included in JWT claims)

    Args:
        args: Configuration dict with optional keys:
            - format: Token format to validate ("jwt", "bearer", or None for any)
            - min_length: Minimum token length (default: 10)
            - check_expiration: Whether to validate JWT expiration (default: False)

    Example:
        ```python
        # Check for valid JWT token
        evaluator = TokenValidEvaluator(args={
            "format": "jwt",
            "min_length": 100,
            "check_expiration": True
        })
        ```
    """

    def __init__(self, args: dict[str, Any] | None = None):
        """
        Initialize the evaluator.

        Args:
            args: Configuration dictionary
        """
        self.args = args or {}

    @property
    def name(self) -> str:
        token_format = self.args.get("format", "any")
        return f"token_valid:{token_format}"

    @property
    def description(self) -> str:
        token_format = self.args.get("format", "any")
        min_length = self.args.get("min_length", 10)
        return f"Checks if {token_format} token is valid (min length: {min_length})"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        """
        Evaluate token validity.

        Args:
            context: Dictionary containing metadata with auth_token

        Returns:
            EvalResult with validation details
        """
        metadata = context.get("metadata", {})
        auth_token = metadata.get("auth_token")

        if not auth_token:
            return EvalResult(
                passed=False, score=0.0, reason="No authentication token found in metadata"
            )

        # Check minimum length
        min_length = self.args.get("min_length", 10)
        if len(auth_token) < min_length:
            return EvalResult(
                passed=False,
                score=0.3,
                reason=f"Token too short: {len(auth_token)} chars (minimum: {min_length})",
                details={"token_length": len(auth_token)},
            )

        # Format-specific validation
        token_format = self.args.get("format")

        if token_format == "jwt":
            return self._validate_jwt(auth_token)
        elif token_format == "bearer":
            return self._validate_bearer(auth_token)
        else:
            # Generic validation - just check it's a reasonable string
            return EvalResult(
                passed=True,
                score=1.0,
                reason=f"Token present and valid length ({len(auth_token)} chars)",
                details={"token_length": len(auth_token)},
            )

    def _validate_jwt(self, token: str) -> EvalResult:
        """
        Validate JWT token structure and claims.

        Args:
            token: JWT token string

        Returns:
            EvalResult with JWT validation details
        """
        # Check JWT structure (header.payload.signature)
        parts = token.split(".")
        if len(parts) != 3:
            return EvalResult(
                passed=False,
                score=0.5,
                reason=f"Invalid JWT structure: expected 3 parts, got {len(parts)}",
                details={"parts": len(parts)},
            )

        # Try to decode JWT (without signature verification)
        try:
            import base64
            import json

            # Decode payload (second part)
            # Add padding if needed
            payload_part = parts[1]
            padding = 4 - len(payload_part) % 4
            if padding != 4:
                payload_part += "=" * padding

            payload_bytes = base64.urlsafe_b64decode(payload_part)
            payload = json.loads(payload_bytes)

            details = {
                "token_length": len(token),
                "has_payload": True,
                "claims": list(payload.keys()),
            }

            # Check expiration if requested
            if self.args.get("check_expiration", False):
                if "exp" in payload:
                    import time

                    exp_time = payload["exp"]
                    current_time = time.time()

                    if exp_time < current_time:
                        return EvalResult(
                            passed=False,
                            score=0.7,
                            reason="JWT token has expired",
                            details={**details, "expired": True, "exp": exp_time},
                        )

                    details["expires_in"] = int(exp_time - current_time)
                else:
                    return EvalResult(
                        passed=False,
                        score=0.8,
                        reason="JWT token missing expiration claim",
                        details={**details, "has_exp": False},
                    )

            return EvalResult(
                passed=True,
                score=1.0,
                reason="JWT token is valid and properly formatted",
                details=details,
            )

        except Exception as e:
            return EvalResult(
                passed=False,
                score=0.4,
                reason=f"Failed to decode JWT payload: {str(e)}",
                details={"error": str(e)},
            )

    def _validate_bearer(self, token: str) -> EvalResult:
        """
        Validate Bearer token format.

        Args:
            token: Bearer token string

        Returns:
            EvalResult with Bearer token validation
        """
        # Bearer tokens should be alphanumeric with possible special chars
        if not re.match(r"^[A-Za-z0-9_\-\.~\+\/=]+$", token):
            return EvalResult(
                passed=False,
                score=0.6,
                reason="Bearer token contains invalid characters",
                details={"token_length": len(token)},
            )

        return EvalResult(
            passed=True,
            score=1.0,
            reason="Bearer token is valid",
            details={"token_length": len(token)},
        )


class OAuth2FlowEvaluator(BaseEvaluator):
    """
    Evaluate OAuth2 flow completion by checking all required steps.

    Verifies that the OAuth2 flow completed all necessary steps:
    1. Request prepared (with client_id, client_secret, scopes)
    2. Token endpoint called (POST to token URL)
    3. Response received (200 OK)
    4. Token extracted (access_token parsed from response)

    Args:
        args: Optional configuration dict with:
            - required_steps: List of step names that must be present
                            (default: standard OAuth2 flow steps)

    Example:
        ```python
        evaluator = OAuth2FlowEvaluator(args={
            "required_steps": [
                "request_prepared",
                "token_endpoint_called",
                "response_received",
                "token_extracted"
            ]
        })
        ```
    """

    def __init__(self, args: dict[str, Any] | None = None):
        """
        Initialize the evaluator.

        Args:
            args: Configuration dictionary
        """
        self.args = args or {}

    @property
    def name(self) -> str:
        return "oauth2_flow_complete"

    @property
    def description(self) -> str:
        return "Checks if OAuth2 flow completed all required steps"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        """
        Evaluate OAuth2 flow completion.

        Args:
            context: Dictionary containing metadata with auth_flow_steps

        Returns:
            EvalResult with flow completion details
        """
        metadata = context.get("metadata", {})
        auth_flow_steps = metadata.get("auth_flow_steps", [])

        if not auth_flow_steps:
            return EvalResult(
                passed=False, score=0.0, reason="No OAuth2 flow steps recorded in metadata"
            )

        # Get required steps from args or use defaults
        required_steps = self.args.get(
            "required_steps",
            ["request_prepared", "token_endpoint_called", "response_received", "token_extracted"],
        )

        # Check which steps are present
        completed_steps = []
        missing_steps = []

        for step in required_steps:
            if step in auth_flow_steps:
                completed_steps.append(step)
            else:
                missing_steps.append(step)

        # Calculate score based on completion
        score = len(completed_steps) / len(required_steps) if required_steps else 0.0

        if not missing_steps:
            return EvalResult(
                passed=True,
                score=1.0,
                reason=f"OAuth2 flow completed all {len(required_steps)} required steps",
                details={"completed_steps": completed_steps, "total_steps": len(auth_flow_steps)},
            )

        return EvalResult(
            passed=False,
            score=score,
            reason=f"OAuth2 flow incomplete: {len(missing_steps)} step(s) missing",
            details={
                "completed_steps": completed_steps,
                "missing_steps": missing_steps,
                "total_steps": len(auth_flow_steps),
            },
        )


class AuthErrorHandlingEvaluator(BaseEvaluator):
    """
    Evaluate proper error handling for authentication failures.

    Validates that when authentication fails, the error messages contain
    useful information for debugging. Checks for:
    - Clear error message presence
    - Required information in error message (e.g., "invalid_client", "unauthorized")
    - Error message quality (not generic "error occurred")

    Args:
        args: Configuration dict with:
            - required_info: List of strings that must appear in error message
            - min_length: Minimum error message length (default: 10)
            - forbid_generic: Reject generic error messages (default: True)

    Example:
        ```python
        # Ensure error mentions invalid client
        evaluator = AuthErrorHandlingEvaluator(args={
            "required_info": ["invalid_client", "401"],
            "min_length": 20
        })
        ```
    """

    def __init__(self, args: dict[str, Any] | None = None):
        """
        Initialize the evaluator.

        Args:
            args: Configuration dictionary
        """
        self.args = args or {}

    @property
    def name(self) -> str:
        return "auth_error_handling"

    @property
    def description(self) -> str:
        required = self.args.get("required_info", [])
        if required:
            return f"Checks auth error message contains: {', '.join(required)}"
        return "Checks for proper authentication error handling"

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        """
        Evaluate authentication error handling quality.

        Args:
            context: Dictionary containing metadata with auth_error

        Returns:
            EvalResult with error handling validation
        """
        metadata = context.get("metadata", {})
        auth_error = metadata.get("auth_error")
        auth_error_message = metadata.get("auth_error_message", "")

        # Use auth_error as message if auth_error_message not present
        if not auth_error_message and auth_error:
            auth_error_message = str(auth_error)

        if not auth_error and not auth_error_message:
            return EvalResult(
                passed=False,
                score=0.0,
                reason="No authentication error found (this evaluator expects auth failure)",
            )

        # Check minimum length
        min_length = self.args.get("min_length", 10)
        if len(auth_error_message) < min_length:
            return EvalResult(
                passed=False,
                score=0.3,
                reason=f"Error message too short: {len(auth_error_message)} chars (minimum: {min_length})",
                details={"message": auth_error_message},
            )

        # Check for generic error messages (if not forbidden, this passes)
        forbid_generic = self.args.get("forbid_generic", True)
        generic_patterns = [
            r"^error$",
            r"^error occurred$",
            r"^failed$",
            r"^authentication failed$",
            r"^auth error$",
        ]

        if forbid_generic:
            for pattern in generic_patterns:
                if re.match(pattern, auth_error_message.strip(), re.IGNORECASE):
                    return EvalResult(
                        passed=False,
                        score=0.4,
                        reason=f"Error message too generic: '{auth_error_message}'",
                        details={"message": auth_error_message},
                    )

        # Check for required information
        required_info = self.args.get("required_info", [])
        if required_info:
            found = []
            missing = []

            error_lower = auth_error_message.lower()
            for info in required_info:
                if info.lower() in error_lower:
                    found.append(info)
                else:
                    missing.append(info)

            score = len(found) / len(required_info) if required_info else 1.0

            if missing:
                return EvalResult(
                    passed=False,
                    score=score,
                    reason=f"Error message missing required info: {', '.join(missing)}",
                    details={"message": auth_error_message, "found": found, "missing": missing},
                )

        # All checks passed
        return EvalResult(
            passed=True,
            score=1.0,
            reason="Error message provides clear, detailed information",
            details={"message": auth_error_message, "length": len(auth_error_message)},
        )
