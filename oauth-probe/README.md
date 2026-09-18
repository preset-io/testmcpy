# testmcpy-oauth-probe

The independently installable, headless distribution of testmcpy's OAuth/MCP
interoperability probe. It depends on **HTTPX and PyYAML only** — installing it
into a release pipeline will not pull in an agent runtime, a web server or an
ORM, and so cannot conflict with whatever that pipeline already pins.

```bash
pip install "testmcpy-oauth-probe==0.1.0"
```

This distribution owns the `testmcpy-oauth` console script. The main `testmcpy`
wheel depends on this one and exposes the same core as `testmcpy auth`; it does
not ship a second copy of the package, so installing both is safe.

It reports observable interoperability and configured policy outcomes. It is
not a formal OAuth or MCP compliance certification.

```bash
testmcpy-oauth validate --config auth-smoke.yaml
testmcpy-oauth schema --kind report > oauth-smoke-report-v1.schema.json
testmcpy-oauth check --config auth-smoke.yaml --format json --output report.json
```

`--config` and `--manifest` are accepted interchangeably.

`--service`, `--region`, `--revision` and `--deployment-id` are report labels
recorded in the `correlation` block. They are never compared against the
deployed target; the probe does not assert the running revision.

## Versioning

Versioned independently of `testmcpy`, because consumers pin it into release
pipelines and rely on its dependency closure staying at two libraries. The
manifest and report schemas carry their own version strings
(`testmcpy.io/oauth-smoke/v1`, `testmcpy.io/oauth-smoke-report/v1`) and do not
move with this package's version.

## Provenance

CI builds publish a `testmcpy-oauth-probe-<full Git SHA>` artifact containing
the wheel, source archive, `SOURCE_COMMIT`, and `SHA256SUMS`. Pin the full
commit/artifact name, confirm `SOURCE_COMMIT`, and verify the checksums before
installation.
