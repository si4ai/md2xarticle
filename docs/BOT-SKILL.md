# md2xarticle skill for bots

Markdown in, X Article out. Use this when a bot should turn a Markdown article, Mermaid diagrams included, into a paste-ready X Article draft and then finish the upload steps a human would do by hand.

Examples below use only generic paths: `article.md`, `out/`, and `images/01.png`.

## Install

```
pip install md2xarticle
```

Python 3.11 to 3.13. No Node, no browser, and no network at run time.

## Convert

```
md2xarticle article.md -o out/ --json
```

Until the full conversion ships, render images with:

```
md2xarticle diagrams article.md -o out/ --json
```

Other commands:

```
md2xarticle outline article.md
md2xarticle check article.md
```

`outline` prints the heading structure after it is reshaped for X's two levels. `check` runs the privacy scan only and writes nothing.

Useful flags on `diagrams` (and on the full conversion, once it ships): `--cover`, `--theme mono`, `--custom-path article.toml`, `--size 1600x900`, `--only 1`, `--renderer mermaidx`, `-v` / `--verbose`.

## Read `--json` and `manifest.json`

`--json` prints a machine-readable summary to stdout. Warnings, errors, and `try:` / `or:` hints go to stderr. A typical successful summary looks like:

```json
{
  "ok": true,
  "out_dir": "out",
  "html": "out/article.html",
  "manifest": "out/manifest.json",
  "images": 2,
  "cover": true,
  "warnings": [],
  "privacy_findings": []
}
```

The `diagrams --json` shape lists each image (order, file, source line, ok, error) instead of `html` and `manifest`. Treat `"ok": false` or a non-zero exit as a failed or partial run: some images may still have been written.

Then read `out/manifest.json`. It lists the cover (if any) and every body image in reading order, with the marker text, caption, the paragraph just before the image (`anchor_text`), and the source line:

```json
{
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
      "source_line": 42
    }
  ]
}
```

## Upload in order

1. Open `out/article.html`, copy all of it, and paste it into the X Article editor. Images do not come through paste.
2. Upload each file from the manifest in order, at its marker (for example `[Image 01: System overview]`). The file is `out/images/01.png`. If the marker is gone, search for `anchor_text`.
3. Delete the marker after the upload.
4. If the manifest has a cover, set `out/images/cover.png` as the article cover (5:2).

Do not post to X, drive the X editor with a browser, or invent a shorter upload path than the editor allows.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Ok. |
| 1 | Findings: a diagram failed, privacy findings, or a heading needed a forced fallback. Output that could be written was written. |
| 2 | Usage error (bad flag, missing file, wrong size ratio). |
| 3 | Internal error. |

Every error on stderr starts with `error:` and is followed by the exact next command to try:

```
error: diagram 03 (article.md line 88) failed to render: Parse error on line 4
try:   md2xarticle diagrams article.md --only 3 --verbose
```

Exit 3 prints a short message, not a traceback, unless you pass `--verbose`.

## Privacy check

```
md2xarticle check article.md
```

Or pass `--check-privacy` on the conversion. The scan flags email addresses, phone-number shapes, local paths, and secret-shaped strings in the Markdown source. An optional local deny-list of names can be set in the `MD2XARTICLE_PRIVACY_DENYLIST` environment variable; that list never leaves the machine. Findings print the kind and the line, never the matched text. Findings exit 1 and do not rewrite the output.
