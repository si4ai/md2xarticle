"""Contract: every DiagramRenderer renders valid source, raises DiagramRenderError on bad source."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from md2xarticle import factory
from md2xarticle.errors import DiagramRenderError
from md2xarticle.model import RenderedImage
from md2xarticle.theme import BUILTIN_THEMES, load_builtin

RENDERERS = sorted(factory.RENDERERS.items())
# The stadium and cylinder shapes use a seeded random path; they must still be stable.
VALID = "flowchart LR\n    S([Start]) --> A[One] --> B[(Store)]\n"
INVALID = "flowchart TD\n    A[Start] --> B{Decision\n    broken line\n    C --> D\n"


@pytest.fixture(params=[cls for _, cls in RENDERERS], ids=[n for n, _ in RENDERERS])
def renderer(request):
    r = request.param()
    if not r.available():
        pytest.skip(f"{r.name} not installed")
    return r


def test_available_is_bool(renderer):
    assert renderer.available() is True
    assert renderer.name
    assert renderer.install_hint


def test_render_valid(renderer, soft_theme):
    out = renderer.render(VALID, soft_theme)
    assert isinstance(out, RenderedImage)
    w, h = out.native_size
    assert w > 0 and h > 0
    with Image.open(BytesIO(out.rasterize(1))) as im:
        assert im.size == out.native_size
    with Image.open(BytesIO(out.rasterize(2))) as im:
        assert abs(im.width - 2 * w) <= 2


def test_render_invalid_raises(renderer, soft_theme):
    with pytest.raises(DiagramRenderError) as info:
        renderer.render(INVALID, soft_theme)
    assert str(info.value)
    assert " on line " not in str(info.value)  # renderer line numbers are not trusted


@pytest.mark.parametrize("theme_name", BUILTIN_THEMES)
def test_render_is_deterministic(renderer, theme_name):
    theme = load_builtin(theme_name)
    assert theme.mermaid_config()["handDrawnSeed"] == 1
    a = renderer.render(VALID, theme).rasterize(2)
    b = renderer.render(VALID, theme).rasterize(2)
    assert a == b
