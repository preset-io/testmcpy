"""
Example usage of auth-specific evaluators for testmcpy.

This example demonstrates how to use the authentication evaluators
to validate OAuth2, JWT, and Bearer token authentication flows.
"""

from testmcpy.evals import (
    AuthErrorHandlingEvaluator,
    AuthSuccessfulEvaluator,
    OAuth2FlowEvaluator,
    TokenValidEvaluator,
    create_evaluator,
)


def example_1_auth_successful():
    """Example: Check if authentication succeeded."""
    print("\n" + "=" * 70)
    print("Example 1: AuthSuccessfulEvaluator")
    print("=" * 70)

    evaluator = AuthSuccessfulEvaluator()

    # Successful authentication
    context = {
        "metadata": {
            "auth_success": True,
            "auth_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "auth_error": None,
        }
    }

    result = evaluator.evaluate(context)
    print(f"\nTest Case: Successful authentication")
    print(f"Passed: {result.passed}")
    print(f"Score: {result.score}")
    print(f"Reason: {result.reason}")

    # Failed authentication
    context_failed = {
        "metadata": {
            "auth_success": False,
            "auth_error": "Invalid credentials provided",
        }
    }

    result_failed = evaluator.evaluate(context_failed)
    print(f"\nTest Case: Failed authentication")
    print(f"Passed: {result_failed.passed}")
    print(f"Score: {result_failed.score}")
    print(f"Reason: {result_failed.reason}")


def example_2_token_validation():
    """Example: Validate JWT token format and claims."""
    print("\n" + "=" * 70)
    print("Example 2: TokenValidEvaluator")
    print("=" * 70)

    # JWT validation with minimum length
    evaluator = TokenValidEvaluator(
        args={"format": "jwt", "min_length": 100, "check_expiration": False}
    )

    # Valid JWT token (header.payload.signature)
    valid_jwt = (
        "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0."
        "NHVaYe26MbtOYhSKkoKYdFVomg4i8ZJd8_-RU8VNbftc4TSMb4bXP3l3YlNWACwyXPGffz5aXHc6lty1Y2t4SWRqGteragsVdZufDn5BlnJl9pdR_kdVFUsra2rWKEofkZeIC4yWytE58sMIihvo9H1ScmmVwBcQP6XETqYd0aSHp1gOa9RdUPDvoXQ5oqygTqVtxaDr6wUFKrKItgBMzWIdNZ6y7O9E0DhEPTbE9rfBo6KTFsHAZnMg4k68CDp2woYIaXbmYTWcvbzIuHO7_37GT79XdIwkm95QJ7hYC9RiwrV7mesbY4PAahERJawntho0my942XheVLmGwLMBkQ"
    )

    context = {"metadata": {"auth_token": valid_jwt}}

    result = evaluator.evaluate(context)
    print(f"\nTest Case: Valid JWT token")
    print(f"Passed: {result.passed}")
    print(f"Score: {result.score}")
    print(f"Reason: {result.reason}")
    if result.details:
        print(f"Claims found: {result.details.get('claims', [])}")

    # Invalid JWT (wrong structure)
    invalid_jwt = "invalid.token"
    context_invalid = {"metadata": {"auth_token": invalid_jwt}}

    result_invalid = evaluator.evaluate(context_invalid)
    print(f"\nTest Case: Invalid JWT structure")
    print(f"Passed: {result_invalid.passed}")
    print(f"Score: {result_invalid.score}")
    print(f"Reason: {result_invalid.reason}")


def example_3_oauth_flow():
    """Example: Validate OAuth2 flow completion."""
    print("\n" + "=" * 70)
    print("Example 3: OAuth2FlowEvaluator")
    print("=" * 70)

    evaluator = OAuth2FlowEvaluator()

    # Complete OAuth2 flow
    context_complete = {
        "metadata": {
            "auth_flow_steps": [
                "request_prepared",
                "token_endpoint_called",
                "response_received",
                "token_extracted",
            ]
        }
    }

    result_complete = evaluator.evaluate(context_complete)
    print(f"\nTest Case: Complete OAuth2 flow")
    print(f"Passed: {result_complete.passed}")
    print(f"Score: {result_complete.score}")
    print(f"Reason: {result_complete.reason}")

    # Incomplete OAuth2 flow
    context_incomplete = {
        "metadata": {
            "auth_flow_steps": ["request_prepared", "token_endpoint_called"]
        }
    }

    result_incomplete = evaluator.evaluate(context_incomplete)
    print(f"\nTest Case: Incomplete OAuth2 flow")
    print(f"Passed: {result_incomplete.passed}")
    print(f"Score: {result_incomplete.score}")
    print(f"Reason: {result_incomplete.reason}")
    if result_incomplete.details:
        print(f"Missing steps: {result_incomplete.details.get('missing_steps', [])}")


def example_4_error_handling():
    """Example: Validate authentication error messages."""
    print("\n" + "=" * 70)
    print("Example 4: AuthErrorHandlingEvaluator")
    print("=" * 70)

    # Require specific information in error message
    evaluator = AuthErrorHandlingEvaluator(
        args={"required_info": ["invalid_client", "401"], "min_length": 20}
    )

    # Good error message with required info
    context_good = {
        "metadata": {
            "auth_error": True,
            "auth_error_message": (
                "OAuth authentication failed: 401 Unauthorized - "
                "invalid_client: The client credentials are invalid"
            ),
        }
    }

    result_good = evaluator.evaluate(context_good)
    print(f"\nTest Case: Detailed error message")
    print(f"Passed: {result_good.passed}")
    print(f"Score: {result_good.score}")
    print(f"Reason: {result_good.reason}")

    # Generic error message
    evaluator_generic = AuthErrorHandlingEvaluator()
    context_generic = {
        "metadata": {"auth_error": True, "auth_error_message": "error"}
    }

    result_generic = evaluator_generic.evaluate(context_generic)
    print(f"\nTest Case: Generic error message (too short)")
    print(f"Passed: {result_generic.passed}")
    print(f"Score: {result_generic.score}")
    print(f"Reason: {result_generic.reason}")


def example_5_factory_usage():
    """Example: Using the factory to create evaluators."""
    print("\n" + "=" * 70)
    print("Example 5: Factory Pattern Usage")
    print("=" * 70)

    # Create evaluators using factory
    print("\nCreating evaluators via factory:")

    auth_eval = create_evaluator("auth_successful")
    print(f"- {auth_eval.name}: {auth_eval.description}")

    token_eval = create_evaluator("token_valid", args={"format": "jwt", "min_length": 50})
    print(f"- {token_eval.name}: {token_eval.description}")

    oauth_eval = create_evaluator("oauth2_flow_complete")
    print(f"- {oauth_eval.name}: {oauth_eval.description}")

    error_eval = create_evaluator(
        "auth_error_handling", args={"required_info": ["timeout", "connection"]}
    )
    print(f"- {error_eval.name}: {error_eval.description}")


def example_6_yaml_test_suite():
    """Example: How these evaluators would be used in YAML test suites."""
    print("\n" + "=" * 70)
    print("Example 6: YAML Test Suite Configuration")
    print("=" * 70)

    yaml_example = """
# Example auth test suite YAML configuration

version: "1.0"
name: "OAuth Authentication Test Suite"

tests:
  - name: "test_oauth_success"
    description: "Verify OAuth client credentials flow succeeds"
    auth:
      type: oauth
      client_id: ${OAUTH_CLIENT_ID}
      client_secret: ${OAUTH_CLIENT_SECRET}
      token_url: "https://auth.example.com/oauth/token"
      scopes: ["read", "write"]
    evaluators:
      - name: "auth_successful"
      - name: "token_valid"
        args:
          format: "jwt"
          min_length: 100
      - name: "oauth2_flow_complete"

  - name: "test_jwt_dynamic_fetch"
    description: "Verify dynamic JWT token fetch"
    auth:
      type: jwt
      api_url: "https://api.example.com/auth/token"
      api_token: ${JWT_API_TOKEN}
    evaluators:
      - name: "auth_successful"
      - name: "token_valid"
        args:
          format: "jwt"

  - name: "test_invalid_credentials"
    description: "Verify proper error handling for invalid credentials"
    auth:
      type: oauth
      client_id: "invalid-client"
      client_secret: "invalid-secret"
      token_url: "https://auth.example.com/oauth/token"
    expect_failure: true
    evaluators:
      - name: "auth_error_handling"
        args:
          required_info: ["invalid_client", "unauthorized"]
    """

    print(yaml_example)


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("testmcpy Auth Evaluators - Examples")
    print("=" * 70)

    example_1_auth_successful()
    example_2_token_validation()
    example_3_oauth_flow()
    example_4_error_handling()
    example_5_factory_usage()
    example_6_yaml_test_suite()

    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70)
