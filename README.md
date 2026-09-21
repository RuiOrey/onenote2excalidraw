# onenote2excalidraw

Convert OneNote pages exported as HTML into [Obsidian Excalidraw](https://github.com/zsviczian/obsidian-excalidraw-plugin) files — **including handwritten ink strokes**, images and text, laid out like the original page.

OneNote's HTML export preserves handwriting as positioned SVG paths and notes as absolutely-positioned text containers. This tool reads that export and rebuilds the page as a real Excalidraw scene: ink strokes become native freedraw elements, text becomes text elements at the original positions, and images are linked to your vault files.

## What it converts

| OneNote export        | Excalidraw element                          |
|-----------------------|---------------------------------------------|
| Typed text / lists    | Text elements at the original positions     |
| Handwritten ink (pen, highlighter) | Freedraw strokes with original colors and relative widths |
| Images                | Image elements linked to the image files already exported next to the HTML |
| Embedded files (`<embed>`), audio/video | Gray text label with the file name, so nothing is lost |
| Monospace text (Courier New, Consolas, ...) | Text in Excalidraw's monospace font (Cascadia) |
| Page title & date     | Text elements                               |

Output is a `.excalidraw.md` file in the exact internal format the Excalidraw plugin writes itself (frontmatter, `## Text Elements`, `## Embedded Files`, `## Drawing` with a compressed JSON block), so files open and re-save cleanly, and the file stays small — ink data is LZ-compressed and images are referenced, not embedded.

## Getting the HTML out of OneNote

You can either start from **ready-made HTML files** (any of the paths below) or feed `.one` section files directly to the converter (see `--from-one` in the Usage section).

**Option 1 — one2html** (this converter has only been tested with HTML produced by this tool):

A Rust CLI that converts OneNote `.one`/`.onetoc2` section files directly into HTML — **no Windows, no OneNote app needed** (works on macOS and Linux). The author's own 426-page vault was produced with it on macOS:

```bash
one2html --input MyNotebook/ --output exported/
```

Point it at your local notebook files, then copy the output into your Obsidian vault. The generated HTML uses the OneNote layout format (positioned containers, images as separate files, ink as inline SVG) and converts without any tweaks.

~~**Other options (not tested with this converter — may not work):**~~

- ~~OneNote desktop (Windows): *File → Export → HTML*, page by page~~
- ~~[onenote-html-export](https://github.com/meichthys/onenote-html-export) — PowerShell script that exports entire notebooks via the OneNote COM API (Windows)~~

These are listed for completeness, but they have **not** been verified to produce HTML that this converter can parse — use [one2html](https://github.com/msiemens/one2html) instead.

**A note on MHT and ink as PNG:** OneNote's "Single File Web Page" (`.mht`) export embeds the images inside a single file, and some export paths rasterize handwritten ink to PNG instead of keeping it as vector SVG. This converter needs the ink as SVG strokes (which one2html produces) — ink that arrives as a raster image will become a static image element, not editable freedraw strokes. `.mht` input is not supported.

Notes:

- The `container-outline` layout format produced by one2html is what this tool parses.
- OneNote for Mac and the web version have **no** HTML export option of their own.
- Each section file becomes one HTML file per page.

## Requirements

- Python 3.9+
- `pip3 install beautifulsoup4 pillow lzstring`
- The [obsidian-excalidraw-plugin](https://github.com/zsviczian/obsidian-excalidraw-plugin) in Obsidian

## Usage

Convert a single page (images are expected next to the HTML):

```bash
python3 onenote2excalidraw.py "My Notes/Week 3 - Shooter rewrite.html"
```

Convert every OneNote HTML export found under a vault root (skips pages that already have a `.excalidraw.md`, and writes a timestamped Markdown report in the root — one table row per page with result, links to both files, and separate counts of text elements, images and ink strokes):

```bash
cd /path/to/vault
python3 onenote2excalidraw.py --all
```

More options:

```bash
python3 onenote2excalidraw.py --all --vault /path/to/vault   # explicit vault root (otherwise: current directory)
python3 onenote2excalidraw.py --all --force                  # overwrite existing .excalidraw.md files
python3 onenote2excalidraw.py --all --dry-run                # list what would be converted, write nothing
python3 onenote2excalidraw.py page.html --embed-images       # embed images as base64 data URLs instead of linking
python3 onenote2excalidraw.py page.html --pure               # pure .excalidraw JSON instead of the Obsidian markdown format
python3 onenote2excalidraw.py page.html --out result.excalidraw.md
```

Convert a whole `.one` section file (or `.onetoc2` notebook) without touching OneNote: the script runs [one2html](https://github.com/msiemens/one2html) on it (in PATH, or auto-downloaded on first use) and converts the generated HTML in one go:

```bash
python3 onenote2excalidraw.py MySection.one --from-one ./output-folder/
python3 onenote2excalidraw.py MyNotebook.onetoc2 --from-one ./output-folder/
```

The classic HTML-first workflow is fully kept as well:

```bash
python3 onenote2excalidraw.py page.html                 # single HTML page
python3 onenote2excalidraw.py --all /path/to/folder/    # every OneNote HTML under a folder
```

### Pure `.excalidraw` JSON vs Obsidian `.excalidraw.md`

Two output formats are supported:

- **`.excalidraw.md`** (default) — the Obsidian Excalidraw plugin's own markdown format. Best inside Obsidian: images are linked to your vault files (small files), text is searchable in the markdown `## Text Elements` section.
- **`.excalidraw`** (`--pure`, or any `--out` ending in `.excalidraw`) — the standard Excalidraw JSON format used by [excalidraw.com](https://excalidraw.com). Opens there via *Open*, and **also opens in the Obsidian plugin** (it registers the `.excalidraw` extension and loads it in "compatibility mode"). In this format there are no vault links, so images are embedded as base64 data URLs — files are bigger but fully portable. *Caveat: this output format has not been tested on excalidraw.com or in the Obsidian plugin yet — the default `.excalidraw.md` output is the thoroughly tested path.*

How the vault root is resolved (used for the vault-relative image links):

- `--vault PATH` when given;
- otherwise, in single-file mode, the folder of the input `.html`;
- otherwise (with `--all`), the current directory.

### Obsidian vault or plain folders?

Both work. Inside an Obsidian vault, images are referenced with vault-relative `[[...]]` links that the Excalidraw plugin resolves automatically. In a plain folder, the output is exactly the same — the `[[...]]` links are just relative paths, and each `.excalidraw.md` sits next to its images (OneNote exports them together), so you can drop the folder into a vault later or open the files with any tool that understands the Excalidraw markdown format. The conversion report is plain Markdown with `[[...]]` links, which Obsidian renders as clickable but is readable anywhere.

## Validating the generated files

`excalidraw_validate.py` checks any Excalidraw file the same way the plugin loads it (frontmatter, compressed Drawing block, element schema, 8-char text ids, duplicate detection, image references):

```bash
python3 excalidraw_validate.py "Week 3 - Shooter rewrite.excalidraw.md"
python3 excalidraw_validate.py --all            # validate every excalidraw file under the current folder
```

## Tips & limitations

- Fonts: text is mapped to Excalidraw's Helvetica (font family 2) — the closest match to OneNote's Calibri. Sizing is compensated so proportions look similar.
- Ink stroke width is calibrated to match the OneNote rendering; tweak the `/ 6` divisor in `walk_strokes()` if you prefer thinner/thicker lines.
- Images are **linked, not embedded**: keep the exported image files in your vault. If you delete them, the drawing still opens but images won't render. Use `--embed-images` if you prefer fully self-contained files (much larger).
- Text formatting like bold/italic/colors beyond gray text is simplified to plain text.
- If a page has multiple overlapping containers in OneNote, the conversion keeps their positions, so it can look just as messy as the original — that's faithful. :wink:

## Credits

- Created with **GLM 5.3** (model by [Z.ai](https://github.com/zai-org)), written with the [opencode CLI](https://opencode.ai).
- Built on top of [obsidian-excalidraw-plugin](https://github.com/zsviczian/obsidian-excalidraw-plugin) by Zsolt Viczian.