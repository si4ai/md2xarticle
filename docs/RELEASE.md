# Releasing md2xarticle

Trusted publishing from GitHub Actions. There is no stored PyPI token. The
workflow file is `.github/workflows/release.yml`. The GitHub environment is
`pypi`. Renaming the workflow file or that environment breaks the pending
publisher. The `testpypi` environment is unused.

This document is the runbook. It does not itself publish, tag, or dispatch.

## Ship a version

1. Bump the version in `src/md2xarticle/__init__.py` (that is the pyproject
   version) in a pull request, then merge it to `main`.
2. On `main`, run the `release` workflow with `workflow_dispatch`. That is a
   dry run: it builds the package, runs the tests, `twine check --strict`,
   and a wheel smoke test (install the built wheel into a clean venv and run
   `md2xarticle --help`). It uploads nothing.
3. On `main`, push the tag `vX.Y.Z`, with the same version as pyproject. The
   workflow fails clearly if the tag and the built package version differ. A
   tag that is not an ancestor of `main` also fails. The same checks run
   again, then the package is published to PyPI through the `pypi`
   environment.
4. If the `pypi` environment has a required reviewer, approve that
   deployment.
5. Confirm the live package:

   ```
   pip install md2xarticle==VERSION
   md2xarticle --help
   ```

A human can run the dispatch or push the tag from the GitHub UI or `git`. A
bot can do the same only with the permissions below.

## What the PM needs to press the button

- **Dry run:** `Actions: Write` on this repository, to call
  `workflow_dispatch` on `release.yml`. `Actions: Read` is not enough; the
  dispatch API returns 403.
- **PyPI release:** `Contents: Write`, to push a `v*` tag on `main`. A human
  with that right can push the tag instead of a bot. The tag push is what
  starts the PyPI job; no separate dispatch is required.
- **The `pypi` environment must already exist.** The `publish_pypi` job uses
  it. If the environment is missing, the publish job cannot start. The
  `testpypi` environment is unused.
- **Confirm the GitHub identity first.** Grant the permissions above to the
  GitHub App or account that will press the button, or have a human dispatch
  and tag.

## Admin setup (one-time)

Do these steps in the GitHub and PyPI UIs. They are not part of the workflow.

1. Open `si4ai/md2xarticle` on GitHub. Go to **Settings -> Environments ->
   New environment**.
2. Create an environment named `pypi` (or edit it if it already exists).
   Under **Deployment branches and tags**, choose **Selected branches and
   tags** and add a tag rule for `v*` only. Recommended: add a required
   reviewer (a human admin) so a PyPI publish waits for approval. Do not add
   secrets (trusted publishing uses OIDC, not a token). Save.
3. The `testpypi` environment is unused. Do not point a publisher at it.
   If it already exists, leave it unused or delete it.
4. Confirm the pending trusted publisher on pypi.org matches these fields
   exactly:

   | Field | Value |
   |---|---|
   | Owner | `si4ai` |
   | Repository | `md2xarticle` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

5. If a bot will run the dry-run `workflow_dispatch`, grant that bot's
   GitHub App **Actions: Write** on this repository (change it from
   **Actions: Read** if that is all it has). If a bot will push the `v*`
   tag, also grant **Contents: Write**. If a human will dispatch and tag, no
   app permission change is required for those two actions.

The first PyPI publish also needs the pending publisher to be approved on
pypi.org when PyPI prompts for it.
