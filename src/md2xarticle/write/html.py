"""``article.html`` and ``outline.txt`` for pasting into the X Article editor.

The markup is plain and semantic: no classes, no inline styles, no scripts.
Each Markdown element is rendered by exactly one function below, named after
the element, so a paste-test result that changes one element changes one
function. The element decisions and their evidence are listed in the README
under "Decided".

The writer renders the Markdown body itself with markdown-it-py (CommonMark
plus tables and strikethrough) because ``Document`` carries headings and
Mermaid blocks, not the full body. Headings take their X level from
``shape.headings.restructure``; Mermaid blocks become image marker paragraphs.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from md2xarticle.model import Document
from md2xarticle.shape.headings import (
    KIND_HEADING,
    KIND_LEAD_IN,
    KIND_LIST_ITEM,
    KIND_SUBHEADING,
    MAP_AUTO,
    Outline,
    OutlineEntry,
    format_outline,
    restructure,
)
from md2xarticle.write.base import ArticleWriter

ARTICLE_FILE = "article.html"
OUTLINE_FILE = "outline.txt"

# Nested lists: "flatten" lifts sub-items into the top-level list with a dash
# prefix per level; "nest" keeps real nested <ul>/<ol>.
NEST = "nest"
FLATTEN = "flatten"
NESTED_LIST_CHOICES = (FLATTEN, NEST)
SUB_ITEM_PREFIX = "\u2013 "  # en dash, once per nesting level

# Same shape as the parser's front matter block; the body starts after it.
_FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?\n)(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.DOTALL)
_EMPTY_DOCUMENT = Document(title=None, subtitle=None, blocks=(), headings=())


@dataclass(frozen=True)
class HtmlOptions:
    nested_lists: str = FLATTEN

    def __post_init__(self) -> None:
        if self.nested_lists not in NESTED_LIST_CHOICES:
            raise ValueError(
                f"nested_lists must be one of {', '.join(NESTED_LIST_CHOICES)}; "
                f"got {self.nested_lists!r}"
            )


@dataclass(frozen=True)
class HtmlArticle:
    """What the HTML writer needs: the Markdown text and its parsed ``Document``."""

    markdown: str
    document: Document
    heading_map: str = MAP_AUTO


# --- image markers ----------------------------------------------------------

# Fields on the parsed document that may carry image references with a
# ``marker`` string (the markers lane owns their shape).
_IMAGE_REF_FIELDS = ("images", "image_refs")


def image_marker(document: Any, index: int) -> str:
    """Marker text for the 1-based Mermaid block ``index``.

    Prefers a ``marker`` from an image reference on the document, then one on
    the block itself, then a plain numbered fallback.
    """
    for name in _IMAGE_REF_FIELDS:
        for ref in getattr(document, name, None) or ():
            if getattr(ref, "index", None) == index and getattr(ref, "marker", None):
                return str(ref.marker)
    for block in getattr(document, "blocks", None) or ():
        if getattr(block, "index", None) == index and getattr(block, "marker", None):
            return str(block.marker)
    return f"[Image {index:02d}]"


# --- escaping ----------------------------------------------------------------


def _text(value: str) -> str:
    return html.escape(value, quote=False)


def _attr(value: str) -> str:
    return html.escape(value, quote=True)


# --- inline elements ---------------------------------------------------------


def _inline_text(node: SyntaxTreeNode, ctx: _Context) -> str:
    return _text(node.content)


def _inline_softbreak(node: SyntaxTreeNode, ctx: _Context) -> str:
    return " "


def _inline_hardbreak(node: SyntaxTreeNode, ctx: _Context) -> str:
    return "<br>"


def _inline_strong(node: SyntaxTreeNode, ctx: _Context) -> str:
    return f"<strong>{ctx.inlines(node)}</strong>"


def _inline_em(node: SyntaxTreeNode, ctx: _Context) -> str:
    return f"<em>{ctx.inlines(node)}</em>"


def _inline_strike(node: SyntaxTreeNode, ctx: _Context) -> str:
    return f"<s>{ctx.inlines(node)}</s>"


def _inline_code(node: SyntaxTreeNode, ctx: _Context) -> str:
    return f"<code>{_text(node.content)}</code>"


def _inline_link(node: SyntaxTreeNode, ctx: _Context) -> str:
    href = str(node.attrs.get("href", ""))
    return f'<a href="{_attr(href)}">{ctx.inlines(node)}</a>'


def _inline_image(node: SyntaxTreeNode, ctx: _Context) -> str:
    # Paste drops images; leave a visible placeholder named by the alt text.
    alt = "".join(child.content for child in node.walk() if child.type == "text").strip()
    return _text(f"[Image: {alt}]" if alt else "[Image]")


def _inline_raw_html(node: SyntaxTreeNode, ctx: _Context) -> str:
    return _text(node.content)


_INLINE: dict[str, Callable[[SyntaxTreeNode, _Context], str]] = {
    "text": _inline_text,
    "softbreak": _inline_softbreak,
    "hardbreak": _inline_hardbreak,
    "strong": _inline_strong,
    "em": _inline_em,
    "s": _inline_strike,
    "code_inline": _inline_code,
    "link": _inline_link,
    "image": _inline_image,
    "html_inline": _inline_raw_html,
}


# --- block elements ----------------------------------------------------------


def _paragraph(node: SyntaxTreeNode, ctx: _Context) -> list[str]:
    body = ctx.inlines(node).strip()
    return [f"<p>{body}</p>"] if body else []


def _x_heading(text: str) -> str:
    return f"<h2>{_text(text)}</h2>"


def _x_subheading(text: str) -> str:
    return f"<h3>{_text(text)}</h3>"


def _x_lead_in(text: str) -> str:
    return f"<p><strong>{_text(text)}</strong></p>"


def _x_heading_list(texts: list[str]) -> list[str]:
    return ["<ul>", *(f"<li>{_text(t)}</li>" for t in texts), "</ul>"]


def _heading(node: SyntaxTreeNode, ctx: _Context) -> list[str]:
    """A heading outside a block sequence (e.g. inside a list item)."""
    return _heading_entry(ctx.next_heading(int(node.tag[1:])))


def _list_item_body(item: SyntaxTreeNode, ctx: _Context, depth: int) -> tuple[str, list[str]]:
    """(inline HTML for the item, extra lines: nested lists or other blocks)."""
    parts: list[str] = []
    extra: list[str] = []
    for child in item.children:
        if child.type == "paragraph":
            text = ctx.inlines(child).strip()
            if text:
                parts.append(text)
        elif child.type in ("bullet_list", "ordered_list"):
            extra.extend(ctx.render_list(child, depth + 1))
        else:
            extra.extend(ctx.block(child))
    return "<br>".join(parts), extra


def _sub_item_prefix(node: SyntaxTreeNode, depth: int, number: int) -> str:
    """Flattened sub-items keep their level as dashes and their number if ordered."""
    if depth == 0:
        return ""
    number_text = f"{number}. " if node.type == "ordered_list" else ""
    return _text(SUB_ITEM_PREFIX * depth + number_text)


def _list(node: SyntaxTreeNode, ctx: _Context, depth: int = 0) -> list[str]:
    """One <ul>/<ol>. With FLATTEN, nested items come back as sibling <li>s."""
    items: list[str] = []
    start = node.attrs.get("start")
    first = int(start) if start is not None else 1
    for number, item in enumerate(node.children, first):
        text, extra = _list_item_body(item, ctx, depth)
        if ctx.options.nested_lists == FLATTEN:
            items.append(f"<li>{_sub_item_prefix(node, depth, number)}{text}</li>")
            items.extend(extra)
        elif extra:
            items.extend([f"<li>{text}", *extra, "</li>"])
        else:
            items.append(f"<li>{text}</li>")
    if ctx.options.nested_lists == FLATTEN and depth > 0:
        return items
    if node.type == "ordered_list":
        open_tag = f'<ol start="{first}">' if first != 1 else "<ol>"
        return [open_tag, *items, "</ol>"]
    return ["<ul>", *items, "</ul>"]


def _blockquote(node: SyntaxTreeNode, ctx: _Context) -> list[str]:
    inner = ctx.blocks(node.children)
    return ["<blockquote>", *inner, "</blockquote>"] if inner else []


def _code(content: str) -> list[str]:
    body = _text(content.rstrip("\n"))
    return [f"<pre><code>{body}</code></pre>"]


def _fence(node: SyntaxTreeNode, ctx: _Context) -> list[str]:
    info = node.info.strip().split(maxsplit=1)
    if info and info[0].lower() == "mermaid":
        return [_marker(ctx.next_marker())]
    return _code(node.content)


def _code_block(node: SyntaxTreeNode, ctx: _Context) -> list[str]:
    return _code(node.content)


def _marker(text: str) -> str:
    """An image marker on its own line, as its own paragraph."""
    return f"<p>{_text(text)}</p>"


def _hr(node: SyntaxTreeNode, ctx: _Context) -> list[str]:
    return ["<hr>"]


def _table(node: SyntaxTreeNode, ctx: _Context) -> list[str]:
    lines = ["<table>"]
    for section in node.children:  # thead, tbody
        lines.append(f"<{section.type}>")
        for row in section.children:
            cells = "".join(
                f"<{cell.type}>{ctx.inlines(cell).strip()}</{cell.type}>" for cell in row.children
            )
            lines.append(f"<tr>{cells}</tr>")
        lines.append(f"</{section.type}>")
    lines.append("</table>")
    return lines


def _raw_html_block(node: SyntaxTreeNode, ctx: _Context) -> list[str]:
    text = node.content.strip()
    return [f"<p>{_text(text)}</p>"] if text else []


_BLOCK: dict[str, Callable[[SyntaxTreeNode, _Context], list[str]]] = {
    "paragraph": _paragraph,
    "heading": _heading,
    "bullet_list": _list,
    "ordered_list": _list,
    "blockquote": _blockquote,
    "fence": _fence,
    "code_block": _code_block,
    "hr": _hr,
    "table": _table,
    "html_block": _raw_html_block,
}


# --- traversal -----------------------------------------------------------------


@dataclass
class _Context:
    document: Any
    outline: Outline
    options: HtmlOptions
    _entries: Iterator[OutlineEntry] = field(init=False)
    _title_skipped: bool = field(init=False, default=False)
    _markers: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self._entries = iter(self.outline.entries)

    def next_heading(self, level: int) -> OutlineEntry | None:
        # Mirrors shape.headings: the first "#" is the title, not body.
        if level == 1 and not self._title_skipped:
            self._title_skipped = True
            return None
        entry = next(self._entries, None)
        if entry is None or entry.source_level != level:
            raise ValueError("Markdown headings do not match the parsed document")
        return entry

    def next_marker(self) -> str:
        self._markers += 1
        return image_marker(self.document, self._markers)

    def inlines(self, node: SyntaxTreeNode) -> str:
        out = []
        for child in node.children:
            if child.type == "inline":
                out.append(self.inlines(child))
                continue
            render = _INLINE.get(child.type)
            out.append(render(child, self) if render else self.inlines(child))
        return "".join(out)

    def block(self, node: SyntaxTreeNode) -> list[str]:
        render = _BLOCK.get(node.type)
        if render is None:
            return self.blocks(node.children)
        return render(node, self)

    def render_list(self, node: SyntaxTreeNode, depth: int) -> list[str]:
        return _list(node, self, depth)

    def blocks(self, nodes: list[SyntaxTreeNode]) -> list[str]:
        """Render a block sequence, grouping runs of list-item headings into one <ul>."""
        lines: list[str] = []
        run: list[OutlineEntry] = []

        def flush() -> None:
            if run:
                lines.extend(_x_heading_list([e.text for e in run]))
                run.clear()

        for node in nodes:
            if node.type == "heading":
                entry = self.next_heading(int(node.tag[1:]))
                if entry is not None and entry.kind == KIND_LIST_ITEM:
                    if run and run[-1].source_level != entry.source_level:
                        flush()
                    run.append(entry)
                    continue
                flush()
                lines.extend(_heading_entry(entry))
                continue
            flush()
            lines.extend(self.block(node))
        flush()
        return lines


def _heading_entry(entry: OutlineEntry | None) -> list[str]:
    """X level for one restructured heading; ``None`` is the title, kept out of the body."""
    if entry is None:
        return []
    if entry.kind == KIND_SUBHEADING:
        return [_x_subheading(entry.text)]
    if entry.kind == KIND_LEAD_IN:
        return [_x_lead_in(entry.text)]
    if entry.kind == KIND_LIST_ITEM:
        return _x_heading_list([entry.text])
    return [_x_heading(entry.text)]


def _markdown() -> MarkdownIt:
    # html=False: raw HTML in the source is shown as text, never passed through.
    return MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


def _body(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]
    m = _FRONT_MATTER.match(text)
    return text[m.end():] if m else text


def render_body(article: HtmlArticle, options: HtmlOptions | None = None) -> list[str]:
    """The body lines of ``article.html``: one block element per line, in order."""
    ctx = _Context(
        document=article.document,
        outline=restructure(article.document, article.heading_map),
        options=options or HtmlOptions(),
    )
    tree = SyntaxTreeNode(_markdown().parse(_body(article.markdown)))
    lines = ctx.blocks(tree.children)
    if next(ctx._entries, None) is not None:
        raise ValueError("Markdown headings do not match the parsed document")
    return lines


def render_html(article: HtmlArticle, options: HtmlOptions | None = None) -> str:
    """The full ``article.html``. Same input, same bytes."""
    outline = restructure(article.document, article.heading_map)
    title = outline.title or ""
    head = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{_text(title)}</title>",
        "</head>",
        "<body>",
    ]
    return "\n".join([*head, *render_body(article, options), "</body>", "</html>"]) + "\n"


def _coerce(article: Any) -> HtmlArticle:
    if isinstance(article, HtmlArticle):
        return article
    # Anything else (the writer contract passes a bare object) is an empty article.
    return HtmlArticle(markdown="", document=_EMPTY_DOCUMENT)


class XArticleHtmlWriter(ArticleWriter):
    """Writes ``article.html`` (paste into X) and ``outline.txt`` (check the structure)."""

    name = "x-article-html"

    def __init__(self, options: HtmlOptions | None = None) -> None:
        self.options = options or HtmlOptions()

    def write(self, article: Any, out_dir: Path) -> list[Path]:
        article = _coerce(article)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / ARTICLE_FILE
        outline_path = out_dir / OUTLINE_FILE
        outline = restructure(article.document, article.heading_map)
        html_path.write_bytes(render_html(article, self.options).encode("utf-8"))
        outline_path.write_bytes(format_outline(outline).encode("utf-8"))
        return [html_path, outline_path]
