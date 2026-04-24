# TestMCPy — Talking Points

## Slide 1: Title
- TestMCPy is an open-source evaluation framework for LLM + MCP tool calling
- Apache 2.0 licensed, available at `preset-io/testmcpy`
- Built at Preset to solve a real problem: ensuring our MCP tools work correctly across models

## Slide 2: The Problem
- **Model updates break things silently.** A new Claude/GPT release can change tool selection behavior. Without evals, regressions go unnoticed until users report them.
- **Cost drift is invisible.** Switching models can save 80% on cost, but without data, we don't know the accuracy tradeoff per tool.
- **MCP service changes need validation.** When we modify tool schemas or add parameters, we need confidence that LLMs still call them correctly.
- **There's no standard testing framework.** Teams test by hand with Claude Desktop. That doesn't scale and isn't reproducible.

## Slide 3: What is TestMCPy
- **"pytest for MCP"** — write YAML test definitions, run against any model, get scored results
- Pipeline: YAML Tests -> LLM Provider -> MCP Service -> Evaluators -> Results
- Show the YAML example — emphasize simplicity: a test is just a prompt + evaluators
- Tests are declarative, versionable, and composable

## Slide 4: What's Built (Current State)
- **17 evaluators** covering tool calls, execution, cost, timing, SQL validation, and LLM-as-judge
- **8 LLM providers** — Anthropic, OpenAI, Ollama, Gemini, Claude CLI/SDK, Codex CLI, local models
- **10 UI pages** — web-based explorer, test manager, reports, interactive chat, config
- Emphasize: the data model matches Max's original spec exactly (TestSuite -> Question -> TestRun -> QuestionResult)
- POC is fully functional — storage, versioning, rate limiting, multi-turn support all working

## Slide 5: Data Model / Architecture
- Walk through the pipeline: TestSuite contains Questions, a TestRun produces QuestionResults, which roll up to Summary
- **Question** = prompt + evaluators + weight (weighted scoring for prioritization)
- **Runner tools** are pluggable — mcp-client (direct FastMCP), anthropic-direct, claude-cli/sdk
- Extensible via `register_runner_tool()` — teams can bring their own runners

## Slide 6: Evaluators
- Three categories: **Tool Calling** (did it call the right tool with right params?), **Execution** (did it succeed in time/budget?), **Advanced** (SQL validity, hallucination detection, LLM judge)
- All evaluators return a standard `EvalResult(passed, score, reason, details)` — scores are 0-1, composable
- Highlight: LLM-as-judge evaluator lets you use one model to evaluate another's response quality
- CompositeEvaluator combines multiple evaluators with AND/OR logic

## Slide 7: Superset MCP Tools
- **19 tools across 6 categories**: Chart (7), Dashboard (4), Dataset (2), Explore (1), SQL Lab (2), System (3)
- **Current coverage: 16%** — only 3 tools have basic evals (list_charts, list_dashboards, list_datasets)
- **V1.0 target: 100%** — comprehensive evals for every tool with parameter validation, cost checks, error handling
- This is where the bulk of Phase A work goes

## Slide 8: V1.0 New Features
- **Prompt Mutation Engine** (Valence-inspired): auto-generate prompt variations when tests fail to map failure boundaries
- **Metamorphic Testing** (Valence-inspired): test invariants like "top 5 is subset of top 10", paraphrase consistency, determinism
- **Multi-Model Comparison**: one command to compare accuracy, cost, latency across models side-by-side
- **Regression Detection**: save baselines, fingerprint failures, distinguish new vs known issues in CI
- **Reusable GitHub Action**: any repo can run MCP evals with `uses: preset-io/testmcpy-action@v1`
- **Hosted at Preset**: `testmcpy.sandbox.preset.io` for browsing results and running tests

## Slide 9: Mutation Example (Deep Dive)
- Walk through the example: "List the first 5 datasets" fails
- Mutations auto-generated: paraphrase, simplify, constrain, role-inject, add noise
- **Key insight**: model fails on "first N" phrasing (parameter sensitivity), not capability
- This is actionable intelligence — we now know to either fix the tool description or avoid that phrasing pattern
- Contrast with manual debugging: would take hours to isolate, mutations do it automatically

## Slide 10: Roadmap
- **Phase A (March - mid April, 18 pts)**: Multi-model runner, full eval suites for 19 tools, multi-turn workflows
- **Phase B (mid April - early June, 28 pts)**: Mutation engine, metamorphic testing, regression detection, GitHub Action, deployment, CI activation
- **Phase C (June, 9 pts)**: Evaluator packs, HTML reports, multi-environment orchestration, stability + PyPI release
- **16 stories, 55 points, 4 months, 3 repos** (testmcpy framework, superset-shell evals, testmcpy-action)
- Human + AI development workflow — leveraging Claude for acceleration

## Slide 11: Impact
- **Catch regressions before users do** — every MCP PR runs evals automatically
- **Optimize costs with data** — know exactly what model switching costs in accuracy
- **Understand prompt sensitivity** — mutation testing reveals fragile vs robust prompts
- **Open source leadership** — first comprehensive MCP eval framework, sets the standard
- The transformation: from "I tested it in Claude Desktop" to "19/19 tools passing across 4 models, $0.03/run, zero regressions"

## Slide 12: Closing
- Open source, Apache 2.0, `pip install testmcpy`
- Contributions welcome
- Questions?

---

## Q&A Prep

**Q: Why not just use pytest directly?**
A: pytest tests code logic. TestMCPy tests LLM behavior — stochastic, model-dependent, cost-sensitive. You need specialized evaluators, multi-model comparison, and cost tracking that pytest doesn't provide.

**Q: How does this compare to other LLM eval frameworks (Langsmith, Braintrust, etc.)?**
A: Those are general-purpose LLM evals. TestMCPy is purpose-built for MCP tool calling — it understands tool schemas, can evaluate parameter correctness, and tracks tool-specific metrics. It's "narrow and deep" vs "wide and shallow."

**Q: What models do you recommend for MCP tool calling?**
A: That's exactly what TestMCPy will answer with data. Early results show Claude Sonnet has the best accuracy-to-cost ratio for our tools, but it varies by tool category.

**Q: How long does a full eval suite run take?**
A: Depends on the number of tests and model latency. A 19-tool suite with ~50 tests typically takes 2-5 minutes per model. Multi-model comparison runs models in parallel.

**Q: What's the cost of running evals?**
A: Very low. Each test is a single LLM call. A full suite of 50 tests on Sonnet costs roughly $0.03-0.05. That's pennies to catch a regression that could affect thousands of users.
