"""Test profile management endpoints."""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/test", tags=["test-profiles"])


@router.get("/profiles")
async def list_test_profiles():
    """List available test profiles from .test_profiles.yaml."""
    from testmcpy.test_profiles import get_test_profile_config

    try:
        profile_config = get_test_profile_config()
        if not profile_config.has_profiles():
            return {
                "profiles": [],
                "default": None,
                "message": "No .test_profiles.yaml file found",
            }

        profiles_list = []
        for profile_id in profile_config.list_profiles():
            profile = profile_config.get_profile(profile_id)
            if not profile:
                continue

            configs_info = []
            for config in profile.test_configs:
                config_dict = {
                    "name": config.name,
                    "description": config.description,
                    "tests_dir": config.tests_dir,
                    "evaluators": config.evaluators,
                    "timeout": config.timeout,
                    "parallel": config.parallel,
                    "max_retries": config.max_retries,
                    "default": config.default,
                }
                configs_info.append(config_dict)

            profiles_list.append(
                {
                    "profile_id": profile.profile_id,
                    "name": profile.name,
                    "description": profile.description,
                    "test_configs": configs_info,
                }
            )

        return {
            "profiles": profiles_list,
            "default": profile_config.default_profile_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profiles/{profile_id}")
async def create_test_profile(profile_id: str, request: dict):
    """Create a new test profile."""
    from testmcpy.test_profiles import (
        TestConfig,
        TestProfile,
        get_test_profile_config,
        reload_test_profile_config,
    )

    try:
        profile_config = get_test_profile_config()

        test_configs = []
        for c in request.get("test_configs", []):
            config = TestConfig(
                name=c.get("name"),
                description=c.get("description", ""),
                tests_dir=c.get("tests_dir", "tests"),
                evaluators=c.get("evaluators", []),
                timeout=c.get("timeout", 120),
                parallel=c.get("parallel", False),
                max_retries=c.get("max_retries", 0),
                default=c.get("default", False),
            )
            test_configs.append(config)

        profile = TestProfile(
            profile_id=profile_id,
            name=request.get("name", profile_id),
            description=request.get("description", ""),
            test_configs=test_configs,
        )

        profile_config.add_profile(profile)
        profile_config.save()
        reload_test_profile_config()

        return {"success": True, "profile_id": profile_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/profiles/{profile_id}")
async def update_test_profile(profile_id: str, request: dict):
    """Update an existing test profile."""
    from testmcpy.test_profiles import (
        TestConfig,
        TestProfile,
        get_test_profile_config,
        reload_test_profile_config,
    )

    try:
        profile_config = get_test_profile_config()

        if profile_id not in profile_config.profiles:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        test_configs = []
        for c in request.get("test_configs", []):
            config = TestConfig(
                name=c.get("name"),
                description=c.get("description", ""),
                tests_dir=c.get("tests_dir", "tests"),
                evaluators=c.get("evaluators", []),
                timeout=c.get("timeout", 120),
                parallel=c.get("parallel", False),
                max_retries=c.get("max_retries", 0),
                default=c.get("default", False),
            )
            test_configs.append(config)

        profile = TestProfile(
            profile_id=profile_id,
            name=request.get("name", profile_id),
            description=request.get("description", ""),
            test_configs=test_configs,
        )

        profile_config.add_profile(profile)
        profile_config.save()
        reload_test_profile_config()

        return {"success": True, "profile_id": profile_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/profiles/{profile_id}")
async def delete_test_profile(profile_id: str):
    """Delete a test profile."""
    from testmcpy.test_profiles import get_test_profile_config, reload_test_profile_config

    try:
        profile_config = get_test_profile_config()

        if profile_id not in profile_config.profiles:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        profile_config.remove_profile(profile_id)
        profile_config.save()
        reload_test_profile_config()

        return {"success": True, "profile_id": profile_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/profiles/default/{profile_id}")
async def set_default_test_profile(profile_id: str):
    """Set the default test profile."""
    from testmcpy.test_profiles import get_test_profile_config, reload_test_profile_config

    try:
        profile_config = get_test_profile_config()
        profile_config.set_default_profile(profile_id)
        profile_config.save()
        reload_test_profile_config()

        return {"success": True, "default_profile": profile_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
