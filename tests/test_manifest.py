"""ManifestWriter writes a stable manifest.json."""

from __future__ import annotations

import json

from md2xarticle.factory import make_writer
from md2xarticle.model import Article, ImageRef
from md2xarticle.write.manifest import ManifestWriter, manifest_text


def sample_article() -> Article:
    return Article(
        source="article.md",
        cover="images/cover.png",
        images=(
            ImageRef(
                order=1,
                file="images/01.png",
                marker="[Image 01: System overview]",
                caption="System overview",
                anchor_text="The pieces fit together like this:",
                source_line=42,
            ),
        ),
    )


def test_manifest_matches_readme_shape(tmp_path):
    paths = ManifestWriter().write(sample_article(), tmp_path)
    assert paths == [tmp_path / "manifest.json"]
    data = json.loads(paths[0].read_text(encoding="utf-8"))
    assert data == {
        "version": 1,
        "source": "article.md",
        "cover": "images/cover.png",
        "images": [
            {
                "order": 1,
                "file": "images/01.png",
                "marker": "[Image 01: System overview]",
                "caption": "System overview",
                "anchor_text": "The pieces fit together like this:",
                "source_line": 42,
            }
        ],
    }


def test_empty_article_has_null_cover_and_empty_images(tmp_path):
    path = ManifestWriter().write(Article(), tmp_path)[0]
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"version": 1, "source": "article.md", "cover": None, "images": []}


def test_same_input_twice_is_byte_identical(tmp_path):
    writer = ManifestWriter()
    a = writer.write(sample_article(), tmp_path / "a")[0].read_bytes()
    b = writer.write(sample_article(), tmp_path / "b")[0].read_bytes()
    assert a == b
    assert a.decode("utf-8").endswith("\n")
    assert manifest_text(sample_article()).encode("utf-8") == a


def test_factory_make_writer_is_the_manifest_writer(tmp_path):
    writer = make_writer()
    assert isinstance(writer, ManifestWriter)
    assert writer.name == "manifest"
    paths = writer.write(Article(), tmp_path)
    assert paths[0].exists()
