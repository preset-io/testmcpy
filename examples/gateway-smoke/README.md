# Gateway smoke lane examples

- `gateway-smoke.example.yaml`: the config format. Placeholders only; running it
  unedited is BLOCKED before any request.
- `fake_gateway.py`: a stdlib-only local fake gateway (metadata, token endpoint,
  MCP endpoint, selectable misbehaviours) used by the tests and for local dry runs.

The runbook, status semantics, limits, output formats and a proposed (disabled)
daily schedule are in [`docs/gateway-smoke-lane.md`](../../docs/gateway-smoke-lane.md).
