# Release scripts

Releases are tag-driven and published by GitHub Actions via PyPI Trusted
Publishing. See [`RELEASING.md`](../RELEASING.md) for the full flow, the tag
convention, and the one-time GitHub/PyPI setup.

| Script                          | Purpose                                                                                                   |
| ------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `publish.sh`                    | Prepare a release from `main`: validate, test, build, create the tag locally, push it after confirmation. **Never uploads to PyPI.** |
| `release_check.py`              | Tag/version validation, artifact verification, build of the planned distributions. Used by `publish.sh` and the publish workflow. |
| `update_homebrew_formula.py`    | Point `Formula/testmcpy.rb` at a released sdist (url and sha256 from the real, verified download). Run by the workflow; safe to run by hand. |

```bash
scripts/publish.sh --dry-run     # checks + builds; no tag, no push
scripts/publish.sh               # also creates the tag and asks before pushing it
```

Pushing a tag only starts the workflow. The upload happens after a required
reviewer approves the `pypi` GitHub environment.
