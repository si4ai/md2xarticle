"""Contract: every ImageComposer gives the exact canvas size, centered, with 4% margins."""

from __future__ import annotations

import pytest

from md2xarticle import factory
from md2xarticle.compose.measure import measure
from md2xarticle.theme import hex_to_rgb, load_builtin
from tests.helpers import assert_canvas, fake_rendered

COMPOSERS = sorted({**factory.BODY_COMPOSERS, **factory.COVER_COMPOSERS}.items())
SHAPES = {"wide": (900, 90), "tall": (90, 900), "tiny": (40, 20), "square": (300, 300), "odd": (333, 177)}


@pytest.fixture(params=[cls for _, cls in COMPOSERS], ids=[n for n, _ in COMPOSERS])
def composer_cls(request):
    return request.param


@pytest.mark.parametrize("theme_name", ["soft", "mono", "warm"])
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_centered_exact_size(composer_cls, theme_name, shape):
    theme = load_builtin(theme_name)
    composer = composer_cls(theme)
    size = composer.default_size
    out = composer.compose(fake_rendered(*SHAPES[shape], background=theme.canvas), size)
    assert out.mode == "RGB"
    assert_canvas(out, size, theme.canvas, composer.center_tolerance)


@pytest.mark.parametrize("scale", [1, 2])
def test_other_sizes_of_the_same_ratio(composer_cls, soft_theme, scale):
    composer = composer_cls(soft_theme)
    w, h = composer.ratio
    size = (w * 80 * scale, h * 80 * scale)
    out = composer.compose(fake_rendered(500, 200, soft_theme.canvas), size)
    assert_canvas(out, size, soft_theme.canvas, composer.center_tolerance)


def test_rejects_wrong_ratio(composer_cls, soft_theme):
    composer = composer_cls(soft_theme)
    with pytest.raises(ValueError):
        composer.compose(fake_rendered(100, 100), (1000, 1000))


def test_none_gives_blank_canvas(composer_cls, soft_theme):
    composer = composer_cls(soft_theme)
    out = composer.compose(None, composer.default_size)
    assert out.size == composer.default_size
    assert measure(out, hex_to_rgb(soft_theme.canvas)) is None


def test_fills_the_tight_axis(composer_cls, soft_theme):
    """Scale to fit: a wide diagram spans the width minus the theme margin."""
    composer = composer_cls(soft_theme)
    size = composer.default_size
    out = composer.compose(fake_rendered(900, 90, soft_theme.canvas), size)
    m = measure(out, hex_to_rgb(soft_theme.canvas))
    expected = size[0] * soft_theme.margin
    assert abs(m.left - expected) <= 3 and abs(m.right - expected) <= 3


@pytest.mark.parametrize("title", ["Pipeline Sketch", "A much longer synthetic cover title that has to shrink to fit"])
@pytest.mark.parametrize("with_image", [True, False])
def test_titled_cover(soft_theme, title, with_image):
    composer = factory.COVER_COMPOSERS["cover"](soft_theme, title=title)
    assert composer.center_tolerance == 8
    image = fake_rendered(600, 120, soft_theme.canvas) if with_image else None
    out = composer.compose(image, (1500, 600))
    assert_canvas(out, (1500, 600), soft_theme.canvas, 8)


def test_compose_is_deterministic(composer_cls, soft_theme):
    composer = composer_cls(soft_theme)
    a = composer.compose(fake_rendered(333, 177, soft_theme.canvas), composer.default_size)
    b = composer.compose(fake_rendered(333, 177, soft_theme.canvas), composer.default_size)
    assert a.tobytes() == b.tobytes()
