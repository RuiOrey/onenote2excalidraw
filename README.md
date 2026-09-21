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

**Option 1 — OneNote desktop (Windows):**

1. Open the notebook in **OneNote for Windows** (desktop).
2. Right-click a page or section → **Export** (or *File → Export*).
3. Choose **Page** (or *Section*) and format **HTML** (`*.htm`).
4. OneNote writes `Page Name.html` plus the page's images as `.jpg`/`.png` files next to it. **Keep the images in the same folder** — the converter links to them.
5. Copy the whole folder into your Obsidian vault.

**Option 2 — bulk export with a PowerShell script:**

[onenote-html-export](https://github.com/meichthys/onenote-html-export) is a community PowerShell script that exports **entire notebooks** (all sections, pages, sub-pages and attachments) to the same HTML format in one run — much faster than exporting page by page. It drives the OneNote desktop app through its COM API, so it still needs Windows with OneNote desktop installed (if your notebook is only online, sync/import it into the desktop app first).

Notes:

- The `container-outline` layout format produced by OneNote 2016/2019/365 exports is what this tool parses.
- OneNote for Mac and the web version have **no** HTML export option — the exports are produced by the Windows desktop app (either manually or via the script above).
- Each page exports one HTML file; section exports contain one HTML per page.

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