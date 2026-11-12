"""Contract: every Platform answers font dirs, output folder, and notes without side effects."""

from __future__ import annotations

from pathlib import Path

import pytest

from md2xarticle import factory
from md2xarticle.platform.base import Platform

PLATFORMS = sorted(factory.PLATFORMS.items())


@pytest.fixture(params=[cls for _, cls in PLATFORMS], ids=[n for n, _ in PLATFORMS])
def platform(request) -> Platform:
    return request.param()


def test_font_dirs_are_paths(platform):
    dirs = platform.font_dirs()
    assert isinstance(dirs, list)
    assert all(isinstance(d, Path) for d in dirs)


def test_default_output_dir_is_relative(platform):
    out = platform.default_output_dir()
    assert isinstance(out, Path)
    assert not out.is_absolute()


def test_notes_are_strings(platform):
    notes = platform.notes()
    assert isinstance(notes, list)
    assert all(isinstance(n, str) and n for n in notes)


def test_wsl_explains_where_output_lands():
    notes = factory.PLATFORMS["wsl"]().notes()
    assert any("/mnt/c/" in n for n in notes)


def test_detect_platform_returns_registered_class():
    assert type(factory.detect_platform()) in factory.PLATFORMS.values()
