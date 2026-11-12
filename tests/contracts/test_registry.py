"""Every concrete subclass of a base is registered in the factory, so it runs its contract suite."""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import md2xarticle
from md2xarticle import factory
from md2xarticle.compose.base import ImageComposer
from md2xarticle.parse.base import MarkdownParser
from md2xarticle.platform.base import Platform
from md2xarticle.render.base import DiagramRenderer
from md2xarticle.write.base import ArticleWriter


def _all_subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _all_subclasses(sub)


def test_every_concrete_subclass_is_registered():
    for mod in pkgutil.walk_packages(md2xarticle.__path__, "md2xarticle."):
        if mod.name != "md2xarticle.__main__":
            importlib.import_module(mod.name)
    registries = {
        MarkdownParser: factory.PARSERS,
        DiagramRenderer: factory.RENDERERS,
        ImageComposer: {**factory.BODY_COMPOSERS, **factory.COVER_COMPOSERS},
        ArticleWriter: factory.WRITERS,
        Platform: factory.PLATFORMS,
    }
    for base, registry in registries.items():
        concrete = {
            c for c in _all_subclasses(base)
            if not inspect.isabstract(c) and c.__module__.startswith("md2xarticle.")
        }
        assert concrete == set(registry.values()), base.__name__
