"""LLM provider profile and model registry endpoints."""

import os
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/llm", tags=["llm"])


class CostEstimateRequest(BaseModel):
    model_id: str
    input_tokens: int
    output_tokens: int


class LLMTestRequest(BaseModel):
    provider: str
    model: str
    api_key: str | None = None  # Direct API key
    api_key_env: str | None = None  # Or env var name
    base_url: str | None = None
    timeout: int = 30


# LLM Provider Profile endpoints


@router.get("/profiles")
async def list_llm_profiles():
    """List available LLM provider profiles from .llm_providers.yaml."""
    from testmcpy.llm_profiles import get_llm_profile_config

    try:
        profile_config = get_llm_profile_config()
        if not profile_config.has_profiles():
            return {
                "profiles": [],
                "default": None,
                "message": "No .llm_providers.yaml file found",
            }

        profiles_list = []
        for profile_id in profile_config.list_profiles():
            profile = profile_config.get_profile(profile_id)
            if not profile:
                continue

            providers_info = []
            for provider in profile.providers:
                provider_dict = {
                    "name": provider.name,
                    "provider": provider.provider,
                    "model": provider.model,
                    "api_key": provider.api_key,
                    "api_key_env": provider.api_key_env,
                    "base_url": provider.base_url,
                    "timeout": provider.timeout,
                    "default": provider.default,
                }
                providers_info.append(provider_dict)

            profiles_list.append(
                {
                    "profile_id": profile.profile_id,
                    "name": profile.name,
                    "description": profile.description,
                    "providers": providers_info,
                }
            )

        return {
            "profiles": profiles_list,
            "default": profile_config.default_profile_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profiles/{profile_id}")
async def create_llm_profile(profile_id: str, request: dict):
    """Create a new LLM provider profile."""
    from testmcpy.llm_profiles import (
        LLMProfile,
        LLMProviderConfig,
        get_llm_profile_config,
        reload_llm_profile_config,
    )

    try:
        profile_config = get_llm_profile_config()

        providers = []
        for p in request.get("providers", []):
            provider = LLMProviderConfig(
                name=p.get("name"),
                provider=p.get("provider"),
                model=p.get("model"),
                api_key=p.get("api_key"),
                api_key_env=p.get("api_key_env"),
                base_url=p.get("base_url"),
                timeout=p.get("timeout", 60),
                default=p.get("default", False),
            )
            providers.append(provider)

        profile = LLMProfile(
            profile_id=profile_id,
            name=request.get("name", profile_id),
            description=request.get("description", ""),
            providers=providers,
        )

        profile_config.add_profile(profile)
        profile_config.save()
        reload_llm_profile_config()

        return {"success": True, "profile_id": profile_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/profiles/{profile_id}")
async def update_llm_profile(profile_id: str, request: dict):
    """Update an existing LLM provider profile."""
    from testmcpy.llm_profiles import (
        LLMProfile,
        LLMProviderConfig,
        get_llm_profile_config,
        reload_llm_profile_config,
    )

    try:
        profile_config = get_llm_profile_config()

        if profile_id not in profile_config.profiles:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        providers = []
        for p in request.get("providers", []):
            provider = LLMProviderConfig(
                name=p.get("name"),
                provider=p.get("provider"),
                model=p.get("model"),
                api_key=p.get("api_key"),
                api_key_env=p.get("api_key_env"),
                base_url=p.get("base_url"),
                timeout=p.get("timeout", 60),
                default=p.get("default", False),
            )
            providers.append(provider)

        profile = LLMProfile(
            profile_id=profile_id,
            name=request.get("name", profile_id),
            description=request.get("description", ""),
            providers=providers,
        )

        profile_config.add_profile(profile)
        profile_config.save()
        reload_llm_profile_config()

        return {"success": True, "profile_id": profile_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/profiles/{profile_id}")
async def delete_llm_profile(profile_id: str):
    """Delete an LLM provider profile."""
    from testmcpy.llm_profiles import get_llm_profile_config, reload_llm_profile_config

    try:
        profile_config = get_llm_profile_config()

        if profile_id not in profile_config.profiles:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        profile_config.remove_profile(profile_id)
        profile_config.save()
        reload_llm_profile_config()

        return {"success": True, "profile_id": profile_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/profiles/default/{profile_id}")
async def set_default_llm_profile(profile_id: str):
    """Set the default LLM provider profile."""
    from testmcpy.llm_profiles import get_llm_profile_config, reload_llm_profile_config

    try:
        profile_config = get_llm_profile_config()
        profile_config.set_default_profile(profile_id)
        profile_config.save()
        reload_llm_profile_config()

        return {"success": True, "default_profile": profile_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Model Registry endpoints


@router.get("/models")
async def list_all_models():
    """List all available LLM models with metadata."""
    from testmcpy.src.model_registry import list_all_models

    return {"models": list_all_models()}


@router.get("/providers")
async def list_all_providers():
    """List all available LLM providers with their models."""
    from testmcpy.src.model_registry import list_providers

    return {"providers": list_providers()}


@router.get("/models/{model_id}")
async def get_model_info(model_id: str):
    """Get detailed info for a specific model."""
    from testmcpy.src.model_registry import get_model

    model = get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")

    return model.to_dict()


@router.get("/providers/{provider}/models")
async def get_provider_models(provider: str):
    """Get all models for a specific provider."""
    from testmcpy.src.model_registry import get_default_model, get_models_by_provider

    models = get_models_by_provider(provider)
    if not models:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")

    default = get_default_model(provider)
    return {
        "provider": provider,
        "models": [m.to_dict() for m in models],
        "default_model": default.id if default else None,
    }


@router.post("/estimate-cost")
async def estimate_model_cost(request: CostEstimateRequest):
    """Estimate cost for a model with given token usage."""
    from testmcpy.src.model_registry import estimate_cost, get_model

    model = get_model(request.model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{request.model_id}' not found")

    cost = estimate_cost(request.model_id, request.input_tokens, request.output_tokens)
    return {
        "model_id": request.model_id,
        "input_tokens": request.input_tokens,
        "output_tokens": request.output_tokens,
        "estimated_cost_usd": round(cost, 6),
        "input_price_per_1m": model.input_price_per_1m,
        "output_price_per_1m": model.output_price_per_1m,
    }


@router.post("/test")
async def test_llm_provider(request: LLMTestRequest):
    """Test an LLM provider connection with a simple prompt."""
    start_time = time.time()

    try:
        # Determine API key - priority: direct > env var > default env var
        api_key = None

        if request.api_key:
            api_key = request.api_key
        elif request.api_key_env:
            api_key = os.environ.get(request.api_key_env)
            if not api_key:
                return {
                    "success": False,
                    "error": f"Environment variable {request.api_key_env} not set",
                    "duration": time.time() - start_time,
                }
        else:
            env_var_map = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
                "google": "GOOGLE_API_KEY",
                "gemini": "GOOGLE_API_KEY",
            }
            env_var = env_var_map.get(request.provider.lower())
            if env_var:
                api_key = os.environ.get(env_var)
                if not api_key:
                    return {
                        "success": False,
                        "error": f"Environment variable {env_var} not set. Provide API key directly or set the env var.",
                        "duration": time.time() - start_time,
                    }

        provider = request.provider.lower()

        if provider == "anthropic":
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=request.model,
                max_tokens=50,
                messages=[{"role": "user", "content": "Say 'test successful' in exactly 2 words."}],
            )
            result_text = response.content[0].text
            return {
                "success": True,
                "response": result_text,
                "model": request.model,
                "duration": time.time() - start_time,
            }

        elif provider == "openai":
            import openai

            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=request.model,
                max_tokens=50,
                messages=[{"role": "user", "content": "Say 'test successful' in exactly 2 words."}],
            )
            result_text = response.choices[0].message.content
            return {
                "success": True,
                "response": result_text,
                "model": request.model,
                "duration": time.time() - start_time,
            }

        elif provider in ("google", "gemini"):
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(request.model)
            response = model.generate_content("Say 'test successful' in exactly 2 words.")
            result_text = response.text
            return {
                "success": True,
                "response": result_text,
                "model": request.model,
                "duration": time.time() - start_time,
            }

        elif provider == "ollama":
            import httpx

            base_url = request.base_url or "http://localhost:11434"
            async with httpx.AsyncClient(timeout=request.timeout) as client:
                response = await client.post(
                    f"{base_url}/api/generate",
                    json={
                        "model": request.model,
                        "prompt": "Say 'test successful' in exactly 2 words.",
                        "stream": False,
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "response": data.get("response", ""),
                        "model": request.model,
                        "duration": time.time() - start_time,
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Ollama returned status {response.status_code}",
                        "duration": time.time() - start_time,
                    }

        elif provider in ("claude-code", "claude-cli", "claude-sdk"):
            return {
                "success": True,
                "response": f"{provider} provider configured (requires CLI/SDK for full test)",
                "model": request.model,
                "duration": time.time() - start_time,
            }

        else:
            return {
                "success": False,
                "error": f"Unknown provider: {request.provider}",
                "duration": time.time() - start_time,
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "duration": time.time() - start_time,
        }
