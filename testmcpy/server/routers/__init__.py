"""
API routers for testmcpy.
"""

from testmcpy.server.routers.chat import router as chat_router
from testmcpy.server.routers.auth import router as auth_router
from testmcpy.server.routers.tests import router as tests_router

__all__ = ["chat_router", "auth_router", "tests_router"]
