"""
API routers for testmcpy.
"""

from testmcpy.server.routers.llm import router as llm_router
from testmcpy.server.routers.test_profiles import router as test_profiles_router

__all__ = ["llm_router", "test_profiles_router"]
