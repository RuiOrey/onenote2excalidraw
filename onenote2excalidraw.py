#!/usr/bin/env python3
"""OneNote HTML export -> Obsidian Excalidraw (.excalidraw.md, plugin file format).

Converts OneNote pages exported as HTML (the "container-outline" export format,
including handwritten ink strokes) into Obsidian Excalidraw markdown files that
open directly in the obsidian-excalidraw-plugin.

Vault root resolution:
  - --vault PATH            explicit
  - single file mode        defaults to the folder of the input .html
  - --all mode              defaults to the current directory

Requires: beautifulsoup4, pillow, lzstring   (pip3 install bs4 pillow lzstring)

Created with GLM 5.3 (https://github.com/zai-org) — written with the opencode CLI.
"""
import argparse, base64, json, os, random, re, sys, time
from bs4 import BeautifulSoup, NavigableString, Tag
from PIL import Image, ImageFont

try:
    from lzstring import LZString
except ImportError:
    LZString = None

TS = int(time.time() * 1000)
NANOID8 = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Helvetica Neue.ttf",
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
]
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp"}
WARNING = ("==\u26a0  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this "
           "document. \u26a0== You can decompress Drawing data with the command "
           "palette: 'Decompress current Excalidraw file'. For more info check "
           "in plugin settings under 'Saving'")
_font_cache = {}


def nid(chars=17):
    a = NANOID8 + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    return "".join(random.choices(a, k=chars))


def nid8(used):
    while True:
        i = "".join(random.choices(NANOID8, k=8))
        if i not in used:
            used.add(i)
            return i


def parse_style(s):
    d = {}
    if not s:
        return d
    for decl in s.split(";"):
        if ":" in decl:
            k, v = decl.split(":", 1)
            d[k.strip().lower()] = v.strip()
    return d


def px(v, default=0.0):
    if v is None:
        return default
    m = re.match(r"^(-?[\d.]+)px$", v.strip()) or re.match(r"^(-?[\d.]+)$", v.strip())
    return float(m.group(1)) if m else default


def pt2px(v):
    return v * 96.0 / 72.0


def color_to_hex(c, default="#1e1e1e"):
    if not c:
        return default
    m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", c.strip())
    if m:
        return "#{:02x}{:02x}{:02x}".format(*(int(x) for x in m.groups()))
    return c.strip() if c.strip().startswith("#") else default


def get_font(size):
    key = int(round(size))
    if key in _font_cache:
        return _font_cache[key]
    f = None
    for p in FONT_PATHS:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, key)
                break
            except Exception:
                continue
    _font_cache[key] = f
    return f


def measure(text, size):
    f = get_font(size)
    if f:
        try:
            return f.getlength(text)
        except Exception:
            pass
    return len(text) * size * 0.52


def wrap(text, maxw, size):
    if maxw < 40:
        maxw = 40
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if measure(t, size) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def base_el(etype, x, y, w, h, el_id=None):
    return {
        "id": el_id or nid(), "type": etype, "x": round(x, 1), "y": round(y, 1),
        "width": round(max(w, 0), 1), "height": round(max(h, 0), 1),
        "angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
        "fillStyle": "hachure", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 1 if etype == "text" else 0, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": None,
        "seed": random.randrange(2 ** 31), "version": 1,
        "versionNonce": random.randrange(2 ** 31), "isDeleted": False,
        "boundElements": None, "updated": TS, "link": None, "locked": False,
    }


def parse_path(d):
    stream = []
    for cmd, num in re.findall(r"([A-Za-z])|(-?(?:\d+\.?\d*|\.\d+))", d):
        stream.append(cmd if cmd else float(num))
    pts, i, cmd, cx, cy = [], 0, None, 0.0, 0.0
    n = len(stream)

    def take_pair(idx):
        if idx + 1 < n and isinstance(stream[idx], float) and isinstance(stream[idx + 1], float):
            return stream[idx], stream[idx + 1], idx + 2
        return None, None, idx + 1

    while i < n:
        t = stream[i]
        if isinstance(t, str):
            cmd = t
            i += 1
            if cmd in ("M", "m"):
                a, b, i = take_pair(i)
                if a is not None:
                    if cmd == "M":
                        cx, cy = a, b
                    else:
                        cx, cy = cx + a, cy + b
                    pts.append((cx, cy))
            continue
        if cmd in ("l", "L", "M"):
            a, b, i = take_pair(i)
            if a is not None:
                if cmd in ("L", "M"):
                    cx, cy = a, b
                else:
                    cx, cy = cx + a, cy + b
                pts.append((cx, cy))
        elif cmd == "m":
            a, b, i = take_pair(i)
            if a is not None:
                cx, cy = cx + a, cy + b
                pts.append((cx, cy))
        else:
            i += 1
    return pts


def compress_block(payload):
    if not LZString:
        return None
    b = LZString.compressToBase64(payload)
    chunks = [b[i:i + 256] for i in range(0, len(b), 256)]
    block = "\n\n".join(chunks)
    if LZString.decompressFromBase64(block.replace("\n", "").replace("\r", "")) != payload:
        return None
    return block


class Converter:
    def __init__(self, html_path, vault_root=None, embed_images=False):
        self.html_path = html_path
        self.html_dir = os.path.dirname(os.path.abspath(html_path))
        self.vault_root = os.path.abspath(vault_root) if vault_root else self.html_dir
        self.embed_images = embed_images
        with open(html_path, encoding="utf-8", errors="ignore") as f:
            self.soup = BeautifulSoup(f.read(), "html.parser")
        self.elements, self.strokes = [], []
        self.files = {}
        self.embedded_links = {}
        self.warnings = []
        self.processed = set()
        self.used_ids = set()
        self.img_cache = {}
        self.markers = self._css_markers()

    def _css_markers(self):
        m = {"0": "•"}
        st = self.soup.find("style")
        if st and st.string:
            for cls, content in re.findall(
                    r'\.list-(\d+)\s+li\s*::marker\s*\{\s*content:\s*["\']([^"\']*)["\']',
                    st.string):
                m[cls] = content
        return m

    def warn(self, msg):
        if len(self.warnings) < 50:
            self.warnings.append(msg)

    @staticmethod
    def get_text(el):
        t = el.get_text(" ") if el is not None else ""
        t = t.replace("\u00a0", " ")
        return re.sub(r"\s+", " ", t).strip()

    @staticmethod
    def font_pt(el, default=11.0):
        if el is None:
            return default
        st = parse_style(el.get("style")) if isinstance(el, Tag) else {}
        m = re.match(r"^([\d.]+)pt$", st.get("font-size", ""))
        if m:
            return float(m.group(1))
        for sp in el.find_all("span"):
            st2 = parse_style(sp.get("style"))
            m = re.match(r"^([\d.]+)pt$", st2.get("font-size", ""))
            if m:
                return float(m.group(1))
        return default

    @staticmethod
    def color_of(el, default="#1e1e1e"):
        if el is None or not isinstance(el, Tag):
            return default
        st = parse_style(el.get("style"))
        if st.get("color"):
            return color_to_hex(st["color"], default)
        for sp in el.find_all("span"):
            st2 = parse_style(sp.get("style"))
            if st2.get("color"):
                return color_to_hex(st2["color"], default)
        return default

    @staticmethod
    def font_family_of(el):
        MONOSPACE = ("courier", "consolas", "lucida console", "menlo", "mono")
        st = parse_style(el.get("style")) if isinstance(el, Tag) else {}
        fonts = [st.get("font-family", "")]
        if isinstance(el, Tag):
            fonts += [parse_style(sp.get("style")).get("font-family", "")
                      for sp in el.find_all("span")]
        for f in fonts:
            f = (f or "").lower().strip("'\" ")
            if any(m in f for m in MONOSPACE):
                return 3
        return 2

    def emit_text(self, x, y, text, pt, color, max_w, family=2):
        size = max(8, int(round(pt2px(pt) * 0.88)))
        lines = wrap(text, max_w, size)
        w = max(measure(l, size) for l in lines) * 1.15 + 8
        h = len(lines) * size * 1.25
        el = base_el("text", x, y, w, h, el_id=nid8(self.used_ids))
        el.update({
            "strokeColor": color, "fontSize": size, "fontFamily": family,
            "text": "\n".join(lines), "rawText": "\n".join(lines),
            "originalText": "\n".join(lines), "textAlign": "left",
            "verticalAlign": "top", "containerId": None, "lineHeight": 1.25,
            "autoResize": False, "roundness": None,
        })
        self.elements.append(el)
        return h

    def emit_paragraph(self, x, y, el, max_w, default_pt=11.0):
        if el is None:
            return pt2px(default_pt) * 1.25
        text = self.get_text(el)
        pt = self.font_pt(el, default_pt)
        lh = pt2px(pt) * 0.88 * 1.25
        if not text:
            return lh
        h = self.emit_text(x, y, text, pt, self.color_of(el), max_w,
                           family=self.font_family_of(el))
        return h + 4

    def emit_media(self, el, x, y):
        src = el.get("src")
        if not src:
            src = el.find("source").get("src") if el.find("source") else None
        src = src or ""
        name = os.path.basename(src.split("?")[0].replace("%20", " "))
        if src:
            p = os.path.normpath(os.path.join(self.html_dir, src.split("?")[0]))
            if not os.path.exists(p):
                self.warn(f"media file missing: {src}")
        label = f"[{el.name}: {name or 'untitled'}]"
        return self.emit_text(x, y, label, 11, "#767676", 600) + 6

    def image_data(self, src):
        src = (src or "").split("?")[0].lstrip()
        if not src:
            return None
        p = os.path.normpath(os.path.join(self.html_dir, src))
        if p in self.img_cache:
            return self.img_cache[p]
        rec = None
        if os.path.exists(p):
            mime = MIME.get(os.path.splitext(p)[1].lower())
            try:
                with Image.open(p) as im:
                    nw, nh = im.size
                    fmt = (im.format or "").upper()
                if not mime:
                    mime = {"JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif",
                            "BMP": "image/bmp", "WEBP": "image/webp"}.get(fmt, "image/png")
                rec = {"path": p, "nw": nw, "nh": nh, "mime": mime}
            except Exception as e:
                self.warn(f"unreadable image: {src} ({e})")
        else:
            self.warn(f"missing image: {src}")
        self.img_cache[p] = rec
        return rec

    def emit_image(self, img_tag, x, y):
        rec = self.image_data(img_tag.get("src"))
        if not rec:
            return 0
        st = parse_style(img_tag.get("style"))
        mw, mh = px(st.get("max-width"), 0), px(st.get("max-height"), 0)
        nw, nh = rec["nw"], rec["nh"]
        if mw > 0 and mh > 0 and nw > 0 and nh > 0:
            scale = min(mw / nw, mh / nh, 1.0)
        else:
            scale = 1.0
        w, h = nw * scale, nh * scale
        if w < 5 or h < 5:
            return 0
        fid = nid()
        if self.embed_images:
            with open(rec["path"], "rb") as f:
                data = f.read()
            self.files[fid] = {
                "id": fid, "mimeType": rec["mime"], "created": TS,
                "dataURL": "data:{};base64,{}".format(
                    rec["mime"], base64.b64encode(data).decode("ascii")),
            }
        else:
            try:
                link = os.path.relpath(rec["path"], self.vault_root)
            except ValueError:
                link = os.path.basename(rec["path"])
            self.embedded_links[fid] = link.replace("\\", "/")
        el = base_el("image", x, y, w, h)
        el.update({"strokeColor": "transparent", "fileId": fid, "status": "saved",
                   "scale": [1, 1], "roughness": 0})
        self.elements.append(el)
        return h + 10

    def marker_of(self, lst):
        cls = lst.get("class") or []
        for c in cls:
            m = re.match(r"^list-(\d+)$", c)
            if m:
                return self.markers.get(m.group(1), "•")
        return "•"

    def li_direct_text(self, li):
        parts = []
        for c in li.children:
            if isinstance(c, NavigableString):
                parts.append(str(c))
            elif c.name in ("ul", "ol"):
                pass
            else:
                parts.append(c.get_text(" "))
        t = " ".join(parts).replace("\u00a0", " ")
        return re.sub(r"\s+", " ", t).strip()

    def walk_list(self, lst, x, y, depth, max_w, default_pt=11.0):
        st = parse_style(lst.get("style"))
        x = x + px(st.get("left"), 0)
        ordered = lst.name == "ol"
        idx = 0
        ycur = y
        for li in lst.find_all("li", recursive=False):
            idx += 1
            li_st = parse_style(li.get("style"))
            ml = px(li_st.get("margin-left"), 0)
            li_x = x + ml + depth * 30
            nested = li.find_all(["ul", "ol"], recursive=False)
            text = self.li_direct_text(li)
            prefix = f"{idx}. " if ordered else self.marker_of(lst) + " "
            if text:
                ycur += self.emit_text(li_x, ycur, prefix + text, default_pt,
                                       "#1e1e1e", max(60, max_w - (li_x - x))) + 4
            for sub in nested:
                ycur = self.walk_list(sub, li_x, ycur, depth + 1, max_w, default_pt)
        return ycur

    def walk_table(self, tbl, x, y, max_w, default_pt=11.0):
        ycur = y
        for tr in tbl.find_all("tr"):
            cells = [self.get_text(td) for td in tr.find_all("td")]
            text = " | ".join(c for c in cells if c)
            if text:
                ycur += self.emit_text(x, ycur, text, default_pt, "#1e1e1e", max_w) + 4
        return ycur

    def walk_block(self, el, x, y, max_w, default_pt=11.0):
        if el.name in ("p", "span"):
            return y + self.emit_paragraph(x, y, el, max_w, default_pt)
        if el.name == "img":
            return y + self.emit_image(el, x, y)
        if el.name in ("video", "audio", "embed", "object", "iframe"):
            return y + self.emit_media(el, x, y)
        if el.name in ("ul", "ol"):
            return self.walk_list(el, x, y, 0, max_w, default_pt)
        if el.name == "table":
            return self.walk_table(el, x, y, max_w, default_pt)
        if el.name == "div":
            classes = el.get("class") or []
            if "outline-element" in classes:
                st = parse_style(el.get("style"))
                x2 = x + px(st.get("margin-left"), 0)
                ycur = y
                for c in el.children:
                    if isinstance(c, Tag):
                        ycur = self.walk_block(c, x2, ycur, max(60, max_w - (x2 - x)), default_pt)
                return ycur
            if "container-outline" in classes:
                self.warn("nested container-outline skipped")
                return y
        if el.name in ("a", "cite", "b", "i", "br"):
            return y + self.emit_paragraph(x, y, el, max_w, default_pt)
        if el.get_text(strip=True) or el.find("img"):
            return y + self.emit_paragraph(x, y, el, max_w, default_pt)
        self.warn(f"tag skipped in flow: <{el.name}>")
        return y

    def walk_container(self, cont):
        self.processed.add(id(cont))
        st = parse_style(cont.get("style"))
        x, y = px(st.get("left"), 0), px(st.get("top"), 0)
        max_w = px(st.get("max-width"), 600) or 600
        ycur = y
        for child in cont.children:
            if isinstance(child, Tag):
                ycur = self.walk_block(child, x, ycur, max_w)

    def handle_title(self):
        t = self.soup.find("div", class_="title")
        if not t:
            return
        self.processed.add(id(t))
        for c in t.find_all("div", class_="container-outline"):
            self.processed.add(id(c))
        st = parse_style(t.get("style"))
        x, y = px(st.get("left"), 48), px(st.get("top"), 24)
        spans = t.find_all("span")
        texts = [self.get_text(s) for s in spans]
        title = next((tx for tx in texts if tx), "")
        if title:
            self.emit_text(x, y, title, 20, "#1e1e1e", 1000)
        meta = " ".join(tx for tx in texts[1:] if tx and tx != title)
        if meta:
            self.emit_text(x, y + pt2px(20) * 1.25 + 6, meta, 10, "#767676", 1000)

    def walk_strokes(self):
        for svg in self.soup.body.find_all("svg") if self.soup.body else []:
            st = parse_style(svg.get("style"))
            vb = (svg.get("viewbox") or "").strip()
            m = re.match(r"([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)", vb)
            if not m:
                continue
            vbx, vby, vbw, vbh = (float(g) for g in m.groups())
            left, top = px(st.get("left")), px(st.get("top"))
            w, h = px(st.get("width")), px(st.get("height"))
            if vbw <= 0 or vbh <= 0 or w <= 0 or h <= 0:
                continue
            sx, sy = w / vbw, h / vbh
            for path in svg.find_all("path"):
                d = path.get("d") or ""
                pts = parse_path(d)
                if len(pts) < 2:
                    continue
                stroke = color_to_hex(path.get("stroke") or "rgb(0,0,0)", "#000000")
                try:
                    sw = float(path.get("stroke-width") or 10)
                except (TypeError, ValueError):
                    sw = 10.0
                try:
                    opac = max(1, min(100, int(round(float(path.get("opacity", "1")) * 100))))
                except (TypeError, ValueError):
                    opac = 100
                page = [(left + (x_ - vbx) * sx, top + (y_ - vby) * sy) for x_, y_ in pts]
                if not all(p[0] == p[0] and p[1] == p[1] for p in page):
                    continue
                xs = [p[0] for p in page]
                ys = [p[1] for p in page]
                minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
                el = base_el("freedraw", minx, miny, maxx - minx, maxy - miny)
                el.update({
                    "strokeColor": stroke,
                    "strokeWidth": max(0.05, round(sw * min(sx, sy) / 6, 2)),
                    "opacity": opac,
                    "roughness": 0,
                    "points": [[round(p[0] - minx, 1), round(p[1] - miny, 1)] for p in page],
                    "lastCommittedPoint": None,
                    "simulatePressure": False,
                })
                self.strokes.append(el)

    def run(self):
        self.handle_title()
        body = self.soup.body
        if body:
            for child in list(body.children):
                if not isinstance(child, Tag):
                    continue
                classes = child.get("class") or []
                if child.name == "div":
                    if "title" in classes:
                        continue
                    if "container-outline" in classes:
                        self.walk_container(child)
                    else:
                        for cont in child.find_all("div", class_="container-outline"):
                            if id(cont) not in self.processed:
                                self.walk_container(cont)
                elif child.name == "img":
                    st = parse_style(child.get("style"))
                    if "left" in st or "top" in st:
                        self.emit_image(child, px(st.get("left")), px(st.get("top")))
                    else:
                        self.warn("body img without position skipped")
                elif child.name in ("video", "audio", "embed", "object", "iframe"):
                    st = parse_style(child.get("style"))
                    x, y = px(st.get("left"), 48), px(st.get("top"), 0)
                    self.emit_media(child, x, y)
            for cont in body.find_all("div", class_="container-outline"):
                if id(cont) not in self.processed:
                    self.walk_container(cont)
        self.walk_strokes()
        return self.build()

    def build(self):
        scene = {
            "type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
            "elements": self.elements + self.strokes,
            "appState": {"viewBackgroundColor": "#ffffff"},
        }
        if self.files:
            scene["files"] = self.files
        return scene

    def write_md(self, out_path):
        payload = json.dumps(self.build(), ensure_ascii=False, separators=(",", ":"))
        if "\n" in payload:
            raise ValueError("scene JSON must be single-line")
        parts = ["---\n\nexcalidraw-plugin: raw\ntags: [excalidraw]\n\n---\n",
                 WARNING + "\n\n\n# Excalidraw Data\n\n"]
        text_els = [e for e in self.elements if e["type"] == "text"]
        if text_els:
            body = "".join(f"{e['originalText']} ^{e['id']}\n\n" for e in text_els)
            parts.append("## Text Elements\n" + body)
        if self.embedded_links:
            body = "".join(f"{fid}: [[{link}]]\n\n" for fid, link in self.embedded_links.items())
            parts.append("## Embedded Files\n" + body)
        block = compress_block(payload)
        if block is not None:
            parts.append("%%\n## Drawing\n```compressed-json\n" + block + "\n```\n%%")
        else:
            self.warn("lzstring unavailable/roundtrip failed: plain json block")
            parts.append("%%\n## Drawing\n```json\n" + payload + "\n```\n%%")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("".join(parts))

    def write_pure(self, out_path):
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.build(), f, ensure_ascii=False, indent=1)
            f.write("\n")


def convert_file(html_path, out_path=None, vault_root=None, embed_images=False, pure=False):
    if pure and not embed_images:
        embed_images = True
    conv = Converter(html_path, vault_root=vault_root, embed_images=embed_images)
    scene = conv.run()
    if pure:
        out = out_path or os.path.splitext(html_path)[0] + ".excalidraw"
        conv.write_pure(out)
    else:
        out = out_path or os.path.splitext(html_path)[0] + ".excalidraw.md"
        conv.write_md(out)
    counts = {"text": 0, "image": 0, "freedraw": 0}
    for e in scene["elements"]:
        if e["type"] in counts:
            counts[e["type"]] += 1
    return {
        "out": out, "counts": counts,
        "linked": len(conv.embedded_links), "embedded": len(conv.files),
        "size_mb": os.path.getsize(out) / 1e6, "warnings": conv.warnings,
    }


def find_onenote_htmls(root):
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if not fn.lower().endswith(".html"):
                continue
            p = os.path.join(dirpath, fn)
            try:
                with open(p, "rb") as f:
                    head = f.read(65536).decode("utf-8", errors="ignore")
            except OSError:
                continue
            if "container-outline" in head:
                results.append(p)
    return sorted(results)


def main():
    ap = argparse.ArgumentParser(
        description="Convert OneNote HTML exports into Obsidian Excalidraw (.excalidraw.md) files")
    ap.add_argument("input", nargs="?", help="a single OneNote .html file, or the vault root with --all")
    ap.add_argument("--out", help="output path (single-file mode)")
    ap.add_argument("--all", action="store_true",
                    help="convert every OneNote HTML export under the vault root "
                         "(skips files that already have a .excalidraw.md)")
    ap.add_argument("--vault", help="vault root used to resolve image links "
                                    "(defaults to the input file's folder, or the current directory with --all)")
    ap.add_argument("--force", action="store_true", help="overwrite existing .excalidraw.md files")
    ap.add_argument("--embed-images", action="store_true",
                    help="embed images as base64 data URLs instead of linking to vault files")
    ap.add_argument("--pure", action="store_true",
                    help="write pure .excalidraw JSON (opens on excalidraw.com and in the "
                         "Obsidian plugin); images are embedded as data URLs in this mode")
    ap.add_argument("--dry-run", action="store_true", help="list what would be converted, write nothing")
    args = ap.parse_args()
    if not args.input and not args.all:
        ap.error("provide a .html file or use --all")
    if args.input and args.out and args.out.lower().endswith(".excalidraw"):
        args.pure = True
    if args.input:
        st = convert_file(args.input, args.out,
                          vault_root=args.vault or os.path.dirname(os.path.abspath(args.input)),
                          embed_images=args.embed_images, pure=args.pure)
        c = st["counts"]
        print(f"ok: {st['out']}")
        print(f"  text={c['text']} images={c['image']} (linked={st['linked']} "
              f"embedded={st['embedded']}) ink strokes={c['freedraw']} size={st['size_mb']:.1f}MB")
        for w in st["warnings"][:10]:
            print("  warning:", w)
        if len(st["warnings"]) > 10:
            print(f"  ... {len(st['warnings']) - 10} more warnings")
        return
    vault = args.vault or os.path.abspath(args.input or ".")
    files = find_onenote_htmls(vault)
    ext = ".excalidraw" if args.pure else ".excalidraw.md"
    done = skipped = failed = 0
    results = []
    for i, p in enumerate(files, 1):
        rel = os.path.relpath(p, vault)
        out = os.path.splitext(p)[0] + ext
        if os.path.exists(out) and not args.force:
            skipped += 1
            status = "exists (skipped)"
            results.append({"html": rel, "out": os.path.relpath(out, vault),
                            "result": "SKIPPED (already existed)", "text": 0, "images": 0,
                            "ink": 0, "size": 0.0, "warnings": 0})
        elif args.dry_run:
            status = "to convert"
        else:
            try:
                st = convert_file(p, out, vault_root=vault,
                                  embed_images=args.embed_images, pure=args.pure)
                c = st["counts"]
                done += 1
                status = (f"ok text={c['text']} ink strokes={c['freedraw']} {st['size_mb']:.1f}MB")
                results.append({"html": rel, "out": os.path.relpath(st["out"], vault),
                                "result": "OK" if not st["warnings"] else "OK (with warnings)",
                                "text": c["text"], "images": c["image"],
                                "ink": c["freedraw"], "size": st["size_mb"],
                                "warnings": len(st["warnings"])})
            except Exception as e:
                failed += 1
                status = f"ERROR: {e}"
                results.append({"html": rel, "out": os.path.relpath(out, vault),
                                "result": "ERROR", "text": 0, "images": 0, "ink": 0,
                                "size": 0.0, "warnings": 0, "error": str(e)})
        print(f"[{i}/{len(files)}] {rel} -> {status}")
    print(f"\nsummary: {done} converted, {skipped} skipped, "
          f"{failed} errors, {len(files)} OneNote export(s)")
    if results and not args.dry_run:
        write_report(vault, files, results, done, skipped, failed, args.force)


def write_report(vault, files, results, done, skipped, failed, force):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    rel_path = f"onenote-excalidraw conversion {stamp}.md"
    out = os.path.join(vault, rel_path)
    lines = [f"# OneNote -> Excalidraw conversion — {time.strftime('%Y-%m-%d %H:%M')}", "",
             f"- OneNote HTML exports found: **{len(files)}**",
             f"- Converted in this run: **{done}**",
             f"- Skipped (already existed): **{skipped}**" + (" (reconverted with --force)" if force else ""),
             f"- Errors: **{failed}**", "",
             "| Result | OneNote HTML | Generated Excalidraw | Text | Images | Ink strokes | Size | Warnings |",
             "|---|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda r: (r["result"] != "ERROR", -(r["ink"] + r["text"]))):
        w = "" if r["warnings"] in (None, 0) else str(r["warnings"])
        size = f"{r['size']:.1f} MB" if r["result"] != "ERROR" else "—"
        note = f" ({r['error']})" if r["result"] == "ERROR" else ""
        lines.append(f"| {r['result']}{note} | [[{r['html']}]] | [[{r['out']}]] | "
                     f"{r['text']} | {r['images']} | {r['ink']} | {size} | {w} |")
    lines.append("")
    lines.append("*Warnings = missing images or media files, or skipped tags; open each excalidraw to double-check.*")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"report: {rel_path}")


if __name__ == "__main__":
    main()