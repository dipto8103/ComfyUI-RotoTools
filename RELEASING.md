# Releasing

One-time setup (owner only)
1. Create a publisher on https://registry.comfy.org (publisher ID must equal `PublisherId` in `pyproject.toml`).
2. Create an API key for that publisher.
3. GitHub repo -> Settings -> Secrets and variables -> Actions -> New repository secret `REGISTRY_ACCESS_TOKEN` = the key.

Every release
1. Add the entry to `CHANGELOG.md` (move items under a new `## [X.Y.Z] - date` heading).
2. Bump `version` in `pyproject.toml` (SemVer: breaking = MAJOR, new feature = MINOR, fix = PATCH).
3. Run `pytest`.
4. Commit and push to `main`. The *Publish to Comfy Registry* action runs because `pyproject.toml` changed.
5. Tag the commit: `git tag vX.Y.Z && git push origin vX.Y.Z`.

The registry `name` (`rototools`) can never change; `DisplayName` can.
