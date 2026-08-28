# testmcpy OAuth probe

This directory is the independently installable, headless distribution of
testmcpy's OAuth/MCP interoperability probe. It intentionally depends only on
HTTPX and PyYAML. The main `testmcpy` wheel embeds the same package and exposes
it as `testmcpy auth`; CI consumers that do not need the UI or LLM stack can
pin this subdirectory by immutable commit or use its separately built wheel.

This tool reports observable interoperability and configured policy outcomes.
It is not a formal OAuth or MCP compliance certification.
