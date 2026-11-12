# Phase 0 findings

Renderer and composition notes from a synthetic Mermaid set, rendered with mermaidx 0.11.3, novasvg 0.11.5, quickjs-ng 0.18.0.1, and Pillow 13.0.0.

The X paste test and an owner pick of theme samples are still open. The owner runs the paste test. Until then, the default theme is `soft`.

## What renders well

flowchart, sequence, class, state, ER, and pie diagrams render clearly.

Time is about 0.5 to 2 seconds per diagram.

## Fidelity problems

- **gitGraph.** Commit and tag labels overlap.
- **gantt.** Date-axis labels collide.
- **Tall top-down diagrams.** Fitted to a 16:9 canvas, the diagram shrinks and the text becomes small. An open item for Phase 1 is a layout override (for example left-to-right) or splitting the diagram. Mermaid source stays as written unless a customization file or flag overrides it.
- **Parse error line numbers.** mermaidx reports `line N`, but that number is not a reliable offset in the source file. The tool must map each block's offsets itself and use that in error messages.
- **Font.** mermaidx hardwires the bundled DejaVu Sans. There is no public hook to inject another font. Custom fonts are a later item.

## Determinism

With the versions above pinned, repeat runs in fresh processes on one platform produce byte-identical PNGs. Cross-OS output is compared with a perceptual diff, not a byte compare.

## Still open

- X paste test: which elements survive paste into the X editor.
- Owner review of theme samples. This only sets or confirms the default. Look-and-feel after that is `--custom-path`.
