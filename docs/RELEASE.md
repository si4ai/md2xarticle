# Releasing md2xarticle

Trusted publishing from GitHub Actions. There is no stored PyPI token. The
workflow file is `.github/workflows/release.yml`. The GitHub environments are
`testpypi` (TestPyPI rehearsal) and `pypi` (PyPI). Renaming the workflow file
or either environment breaks the pending publishers.

This document is the runbook. It does not itself publish, tag, or dispatch.

## Ship a version

1. Bump the version in `src/md2xarticle/__init__.py` (that is the pyproject
   version) in a pull request, then merge it to `main`.
2. On `main`, run the `release` workflow with `workflow_dispatch`. That is the
   TestPyPI rehearsal. It builds the package, checks it, and publishes to
   TestPyPI through the `testpypi` environment.
3. Confirm the rehearsal:

   ```
   pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ md2xarticle==VERSION
   md2xarticle --help
   ```

   Use the version you just bumped. The extra index is only for dependencies
   that are not on TestPyPI.
4. On `main`, push the tag `vX.Y.Z`, with the same version as pyproject. The
   workflow fails clearly if the tag and the built package version differ. A
   tag that is not an ancestor of `main` also fails.
5. If the `pypi` environment has a required reviewer, approve that deployment.
6. Confirm the live package:

   ```
   pip install md2xarticle==VERSION
   md2xarticle --help
   ```

A human can run the dispatch or push the tag from the GitHub UI or `git`. A
bot can do the same only with the permissions below.

## What the PM needs to press the button

- **TestPyPI rehearsal:** `Actions: Write` on this repository, to call
  `workflow_dispatch` on `release.yml`. `Actions: Read` is not enough; the
  dispatch API returns 403.
- **PyPI release:** `Contents: Write`, to push a `v*` tag on `main`. A human
  with that right can push the tag instead of a bot. The tag push is what
  starts the PyPI job; no separate dispatch is required.
- **Environments must already exist.** The `publish_testpypi` and
  `publish_pypi` jobs use the `testpypi` and `pypi` environments. If those
  environments are missing, the publish jobs cannot start.
- **Confirm the GitHub identity first.** Grant the permissions above to the
  GitHub App or account that will press the button, or have a human dispatch
  and tag.

## Admin setup (one-time)

Do these steps in the GitHub and PyPI UIs. They are not part of the workflow.

1. Open `si4ai/md2xarticle` on GitHub. Go to **Settings -> Environments ->
   New environment**.
2. Create an environment named `testpypi`. Under **Deployment branches and
   tags**, choose **Selected branches and tags** and add a branch rule for
   `main`. Do not add required reviewers. Do not add secrets (trusted
   publishing uses OIDC, not a token). Save.
3. Create an environment named `pypi`. Under **Deployment branches and
   tags**, choose **Selected branches and tags** and add a tag rule for
   `v*`. Recommended: add a required reviewer (a human admin) so a PyPI
   publish waits for approval. Do not add secrets. Save.
4. Confirm the pending trusted publishers already created on TestPyPI and
   PyPI match these fields exactly:

   | Field | TestPyPI (`test.pypi.org`) | PyPI (`pypi.org`) |
   |---|---|---|
   | Owner | `si4ai` | `si4ai` |
   | Repository | `md2xarticle` | `md2xarticle` |
   | Workflow name | `release.yml` | `release.yml` |
   | Environment name | `testpypi` | `pypi` |

5. If a bot will run `workflow_dispatch`, grant that bot's GitHub App
   **Actions: Write** on this repository (change it from **Actions: Read**
   if that is all it has). If a bot will push the `v*` tag, also grant
   **Contents: Write**. If a human will dispatch and tag, no app permission
   change is required for those two actions.

The first TestPyPI publish also needs the pending publisher to be approved
on test.pypi.org when PyPI prompts for it; the first PyPI publish is the
same on pypi.org.
