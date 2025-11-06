"""Reusable TUI widgets."""

from .error_modal import (
    ConfirmModal,
    ConnectionErrorModal,
    ErrorModal,
    TestFailureModal,
    WarningModal,
)
from .help_modal import (
    CHAT_HINTS,
    CONFIG_HINTS,
    EXPLORER_HINTS,
    HOME_HINTS,
    TESTS_HINTS,
    HelpModal,
    ScreenSpecificHelp,
)
from .loading import (
    ConnectionStatus,
    CostTracker,
    LiveIndicator,
    LoadingSpinner,
    OperationProgress,
)
from .search_modal import GlobalSearchModal, SearchResult, SearchResultItem
from .status_bar import SimpleStatusBar, StatusBar

__all__ = [
    # Error modals
    "ConfirmModal",
    "ConnectionErrorModal",
    "ErrorModal",
    "TestFailureModal",
    "WarningModal",
    # Help modals
    "HelpModal",
    "ScreenSpecificHelp",
    "HOME_HINTS",
    "EXPLORER_HINTS",
    "TESTS_HINTS",
    "CHAT_HINTS",
    "CONFIG_HINTS",
    # Loading widgets
    "LoadingSpinner",
    "OperationProgress",
    "ConnectionStatus",
    "LiveIndicator",
    "CostTracker",
    # Search widgets
    "GlobalSearchModal",
    "SearchResult",
    "SearchResultItem",
    # Status bar
    "StatusBar",
    "SimpleStatusBar",
]
