"""Contract: every ArticleWriter writes at least one file under out_dir."""

from __future__ import annotations

import inspect

import pytest

from md2xarticle import factory
from md2xarticle.model import Article
from md2xarticle.write.base import ArticleWriter

WRITERS = sorted(factory.WRITERS.items())


def test_base_is_abstract():
    assert inspect.isabstract(ArticleWriter)
    with pytest.raises(TypeError):
        ArticleWriter()  # type: ignore[abstract]


@pytest.mark.parametrize("cls", [c for _, c in WRITERS] or [None], ids=[n for n, _ in WRITERS] or ["none-yet"])
def test_writer_returns_written_paths(cls, tmp_path):
    if cls is None:
        pytest.skip("no concrete ArticleWriter until Phase 2")
    paths = cls().write(Article(), tmp_path)
    assert paths and all(p.exists() and tmp_path in p.parents for p in paths)
