from __future__ import annotations

import pytest

from md2xarticle.theme import load_builtin
from tests.helpers import FIXTURE_MD


@pytest.fixture(scope="session")
def soft_theme():
    return load_builtin("soft")


@pytest.fixture(scope="session")
def fixture_text() -> str:
    return FIXTURE_MD.read_text(encoding="utf-8")


# The skip budget hook: fails the run when more tests skip than expected.
from tests.skip_budget import pytest_sessionfinish  # noqa: E402,F401
