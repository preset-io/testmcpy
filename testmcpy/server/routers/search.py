"""Global search endpoint for the Command Palette (Cmd+K)."""

from pathlib import Path

import yaml
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search(q: str = Query(..., min_length=1, max_length=200)) -> dict:
    """
    Search across test suites, pages, MCP profiles, and LLM profiles.
    Returns categorized results for the command palette.
    """
    query = q.lower().strip()
    results: list[dict] = []

    # 1. Search pages (static list)
    pages = [
        {"name": "Explorer", "path": "/", "keywords": "mcp explorer tools smoke"},
        {"name": "Tests", "path": "/tests", "keywords": "test manager yaml editor"},
        {"name": "Reports", "path": "/reports", "keywords": "reports results history"},
        {"name": "Compatibility", "path": "/compatibility", "keywords": "compat matrix"},
        {
            "name": "Generation History",
            "path": "/generation-history",
            "keywords": "gen ai generation history",
        },
        {"name": "Chat", "path": "/chat", "keywords": "chat interact llm"},
        {"name": "Metrics", "path": "/metrics", "keywords": "metrics dashboard analytics"},
        {"name": "Compare", "path": "/compare", "keywords": "compare runs diff"},
        {"name": "MCP Health", "path": "/health", "keywords": "mcp health status"},
        {"name": "Security", "path": "/security", "keywords": "security audit"},
        {"name": "Auth Debugger", "path": "/auth-debugger", "keywords": "auth debug oauth jwt"},
        {"name": "Config", "path": "/config", "keywords": "config settings configuration"},
        {"name": "MCP Profiles", "path": "/mcp-profiles", "keywords": "mcp profiles server"},
        {
            "name": "LLM Profiles",
            "path": "/llm-profiles",
            "keywords": "llm profiles provider model",
        },
    ]

    for page in pages:
        if query in page["name"].lower() or query in page["keywords"]:
            results.append(
                {
                    "type": "page",
                    "name": page["name"],
                    "url": page["path"],
                    "description": f"Navigate to {page['name']}",
                }
            )

    # 2. Search test files
    tests_dir = Path.cwd() / "tests"
    if tests_dir.exists():
        for file in tests_dir.rglob("*.yaml"):
            rel = str(file.relative_to(tests_dir))
            if query in file.name.lower() or query in rel.lower():
                results.append(
                    {
                        "type": "test",
                        "name": file.name,
                        "url": f"/tests?file={rel}",
                        "description": f"Test file: {rel}",
                    }
                )
            else:
                # Search inside test names
                try:
                    with open(file) as f:
                        data = yaml.safe_load(f)
                    for test in data.get("tests", []):
                        name = test.get("name", "")
                        if query in name.lower():
                            results.append(
                                {
                                    "type": "test",
                                    "name": name,
                                    "url": f"/tests?file={rel}",
                                    "description": f"Test in {rel}",
                                }
                            )
                except (yaml.YAMLError, OSError, ValueError):
                    pass

    # 3. Search MCP profiles
    mcp_config_path = Path.cwd() / ".mcp_services.yaml"
    if mcp_config_path.exists():
        try:
            with open(mcp_config_path) as f:
                mcp_data = yaml.safe_load(f)
            for profile_id, profile in (mcp_data.get("profiles") or {}).items():
                pname = profile.get("name", profile_id)
                if query in profile_id.lower() or query in pname.lower():
                    results.append(
                        {
                            "type": "profile",
                            "name": pname,
                            "url": "/mcp-profiles",
                            "description": f"MCP Profile: {profile_id}",
                        }
                    )
                for mcp in profile.get("mcps", []):
                    mcp_name = mcp.get("name", "")
                    if query in mcp_name.lower():
                        results.append(
                            {
                                "type": "profile",
                                "name": mcp_name,
                                "url": "/mcp-profiles",
                                "description": f"MCP Server in {pname}",
                            }
                        )
        except (yaml.YAMLError, OSError):
            pass

    # 4. Search LLM profiles
    llm_config_path = Path.cwd() / ".llm_profiles.yaml"
    if llm_config_path.exists():
        try:
            with open(llm_config_path) as f:
                llm_data = yaml.safe_load(f)
            for profile in llm_data.get("profiles", []):
                pid = profile.get("profile_id", "")
                pname = profile.get("name", pid)
                if query in pid.lower() or query in pname.lower():
                    results.append(
                        {
                            "type": "llm_profile",
                            "name": pname,
                            "url": "/llm-profiles",
                            "description": f"LLM Profile: {pid}",
                        }
                    )
                for prov in profile.get("providers", []):
                    model = prov.get("model", "")
                    if query in model.lower():
                        results.append(
                            {
                                "type": "llm_profile",
                                "name": model,
                                "url": "/llm-profiles",
                                "description": f"Model in {pname}",
                            }
                        )
        except (yaml.YAMLError, OSError):
            pass

    # Deduplicate by (type, name, url)
    seen = set()
    unique = []
    for r in results:
        key = (r["type"], r["name"], r["url"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return {"results": unique[:20], "query": q}
