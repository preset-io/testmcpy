# testmcpy OAuth probe

This directory is the independently installable, headless distribution of
testmcpy's OAuth/MCP interoperability probe. It intentionally depends only on
HTTPX and PyYAML. The main `testmcpy` wheel embeds the same package and exposes
it as `testmcpy auth`; CI consumers that do not need the UI or LLM stack can
pin this subdirectory by immutable commit or use its separately built wheel.

This tool reports observable interoperability and configured policy outcomes.
It is not a formal OAuth or MCP compliance certification.

```bash
testmcpy-oauth validate --config auth-smoke.yaml
testmcpy-oauth schema --kind report > oauth-smoke-report-v1.schema.json
testmcpy-oauth check --config auth-smoke.yaml --format json --output report.json
```

CI builds publish a `testmcpy-oauth-probe-<full Git SHA>` artifact containing
the wheel, source archive, and `SHA256SUMS`. Pin the full commit/artifact name
and verify the checksums before installation.
