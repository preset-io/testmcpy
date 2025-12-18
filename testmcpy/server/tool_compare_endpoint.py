"""
Tool comparison endpoint for api.py

Insert this code into api.py after the optimize-docs endpoint (around line 2866)
and before the debug-tool endpoint.
"""


@app.post("/api/tools/compare")
async def compare_tools(request: ToolCompareRequest):
    """
    Compare the same tool across two different MCP profiles/servers.

    This endpoint runs the specified tool multiple times on two different
    MCP servers and returns performance metrics and results for comparison.
    """
    import time

    # Parse profile IDs
    profile1_parts = request.profile1.split(":", 1)
    profile2_parts = request.profile2.split(":", 1)

    if len(profile1_parts) != 2 or len(profile2_parts) != 2:
        raise HTTPException(status_code=400, detail="Profile format must be 'profile_id:mcp_name'")

    profile1_id, mcp1_name = profile1_parts
    profile2_id, mcp2_name = profile2_parts

    # Load profiles
    try:
        profile1_data = load_profile(profile1_id)
        profile2_data = load_profile(profile2_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Profile not found: {str(e)}")

    if not profile1_data or not profile2_data:
        raise HTTPException(status_code=404, detail="One or both profiles not found")

    # Find MCP configs
    mcp1 = next((m for m in profile1_data.mcps if m.name == mcp1_name), None)
    mcp2 = next((m for m in profile2_data.mcps if m.name == mcp2_name), None)

    if not mcp1 or not mcp2:
        raise HTTPException(status_code=404, detail="MCP server not found in profile")

    # Helper function to run a single iteration
    async def run_iteration(mcp_config, iteration_num):
        result = {
            "iteration": iteration_num,
            "success": False,
            "result": None,
            "error": None,
            "duration_ms": 0,
        }

        client = None
        try:
            start_time = time.time()

            # Initialize client
            client = MCPClient(mcp_url=mcp_config.mcp_url, auth=mcp_config.auth)
            await client.initialize()

            # Call the tool
            tool_result = await client.call_tool(
                name=request.tool_name, arguments=request.parameters
            )

            result["success"] = True
            result["result"] = tool_result
            result["duration_ms"] = (time.time() - start_time) * 1000

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            result["duration_ms"] = (time.time() - start_time) * 1000
        finally:
            if client:
                try:
                    await client.cleanup()
                except Exception:
                    pass

        return result

    # Run iterations for both profiles
    results1 = []
    results2 = []

    try:
        for i in range(request.iterations):
            # Run on profile 1
            result1 = await run_iteration(mcp1, i + 1)
            results1.append(result1)

            # Run on profile 2
            result2 = await run_iteration(mcp2, i + 1)
            results2.append(result2)

        # Calculate metrics
        avg_time1 = sum(r["duration_ms"] for r in results1) / len(results1)
        avg_time2 = sum(r["duration_ms"] for r in results2) / len(results2)
        success_rate1 = (sum(1 for r in results1 if r["success"]) / len(results1)) * 100
        success_rate2 = (sum(1 for r in results2 if r["success"]) / len(results2)) * 100

        return {
            "tool_name": request.tool_name,
            "profile1": f"{profile1_data.name} ({mcp1_name})",
            "profile2": f"{profile2_data.name} ({mcp2_name})",
            "parameters": request.parameters,
            "iterations": request.iterations,
            "results1": results1,
            "results2": results2,
            "metrics": {
                "avg_time1_ms": avg_time1,
                "avg_time2_ms": avg_time2,
                "success_rate1_pct": success_rate1,
                "success_rate2_pct": success_rate2,
                "faster_profile": 1 if avg_time1 < avg_time2 else 2,
                "time_difference_ms": abs(avg_time1 - avg_time2),
                "time_difference_pct": (abs(avg_time1 - avg_time2) / max(avg_time1, avg_time2))
                * 100,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")
