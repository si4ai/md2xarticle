"""Fail the run when more tests skip than expected.

EXPECTED_SKIPS is the one place the number lives. Raise it only with a reason
next to it; a new skip otherwise means a check silently stopped running.
"""

from __future__ import annotations

import pytest

# 0: XArticleHtmlWriter and ManifestWriter are registered, so the ArticleWriter contract runs.
EXPECTED_SKIPS = 0


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    skipped = len(reporter.stats.get("skipped", []))
    if skipped > EXPECTED_SKIPS:
        reporter.write_line(
            f"skip budget exceeded: {skipped} skipped, expected at most {EXPECTED_SKIPS} "
            "(tests/skip_budget.py). Fix the new skip or raise the budget with a reason.",
            red=True,
            bold=True,
        )
        if session.exitstatus == pytest.ExitCode.OK:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
