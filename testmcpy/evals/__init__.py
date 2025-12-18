"""testmcpy evaluation functions."""

from testmcpy.evals.auth_evaluators import (
    AuthErrorHandlingEvaluator,
    AuthSuccessfulEvaluator,
    OAuth2FlowEvaluator,
    TokenValidEvaluator,
)
from testmcpy.evals.base_evaluators import (
    AnswerContainsLink,
    BaseEvaluator,
    CompositeEvaluator,
    EvalResult,
    ExecutionSuccessful,
    FinalAnswerContains,
    ParameterValueInRange,
    SQLQueryValid,
    TokenUsageReasonable,
    ToolCallCount,
    ToolCalledWithParameter,
    ToolCalledWithParameters,
    ToolCallSequence,
    WasChartCreated,
    WasMCPToolCalled,
    WithinTimeLimit,
    create_evaluator,
)

# Backward compatibility alias
WasSupersetChartCreated = WasChartCreated

__all__ = [
    # Base evaluators
    "BaseEvaluator",
    "EvalResult",
    "WasMCPToolCalled",
    "ExecutionSuccessful",
    "FinalAnswerContains",
    "AnswerContainsLink",
    "WithinTimeLimit",
    "TokenUsageReasonable",
    "ToolCalledWithParameter",
    "ToolCalledWithParameters",
    "ParameterValueInRange",
    "ToolCallCount",
    "ToolCallSequence",
    "WasChartCreated",
    "WasSupersetChartCreated",  # Backward compatibility alias
    "SQLQueryValid",
    "CompositeEvaluator",
    "create_evaluator",
    # Auth evaluators
    "AuthSuccessfulEvaluator",
    "TokenValidEvaluator",
    "OAuth2FlowEvaluator",
    "AuthErrorHandlingEvaluator",
]
