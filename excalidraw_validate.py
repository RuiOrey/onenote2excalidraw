#!/usr/bin/env python3
"""Validate Excalidraw files by replicating the loading logic of the
obsidian-excalidraw-plugin (getTextMode / getJSON / loadData sections).

Checks frontmatter, compressed/uncompressed Drawing blocks, element schema,
text-element ids (8 chars, as expected by the plugin), duplicate elements,
Text Elements section consistency and Embedded Files image references.

Usage:
  python3 excalidraw_validate.py <file.excalidraw.md> [more files...]
  python3 excalidraw_validate.py --all [vault_root]

Vault root defaults to the current directory (used to check that images
referenced in "## Embedded Files" exist in the vault).

Requires: lzstring (pip3 install lzstring)

Created with GLM 5.3 (https://github.com/zai-org) — written with the opencode CLI.
"""
import json, os, re, sys
from collections import Counter

REQ = {"id", "type", "x", "y", "width", "height", "angle", "strokeColor", "backgroundColor",
       "fillStyle", "strokeWidth", "strokeStyle", "roughness", "opacity", "groupIds",
       "frameId", "roundness", "seed", "version", "versionNonce", "isDeleted",
       "boundElements", "updated", "link", "locked"}


def find_image(vault, target):
    if os.path.exists(os.path.join(vault, target)):
        return True
    base = os.path.basename(target)
    for dirpath, dirnames, filenames in os.walk(vault):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if base in filenames:
            return True
    return False


def validate(path, vault):
    errs, warns = [], []
    try:
        raw = open(path, encoding="utf-8").read()
    except OSError as e:
        return [f"unreadable: {e}"], [], {}, "", False
    s = raw.replace("\r\n", "\n").replace("\r", "\n")
    ext = os.path.splitext(path)[1].lower()
    mode = "parsed" if ("excalidraw-plugin: parsed\n" in s or "excalidraw-plugin: locked\n" in s) else "raw"
    if ext == ".md" and "excalidraw-plugin:" not in s[:300]:
        errs.append("frontmatter missing 'excalidraw-plugin'")
    compressed = re.search(r"```compressed-json\n", s) is not None

    scene_str, pos = None, 0
    if compressed:
        m = re.search(r"(\n##? Drawing\n[^`]*(?:```compressed-json\n))([\s\S]*?)(```\n)", s)
        if not m:
            errs.append("compressed-json without a ## Drawing section")
        else:
            pos = m.start()
            try:
                from lzstring import LZString
                dec = LZString.decompressFromBase64(m.group(2).replace("\n", "").replace("\r", ""))
                if not dec:
                    errs.append("compressed-json: decompress returned nothing")
                else:
                    scene_str = dec[:dec.rfind("}") + 1]
            except ImportError:
                errs.append("install lzstring: pip3 install lzstring")
    elif ext == ".md":
        m = re.search(r"\n##? Drawing\n[^`]*(```json\n)([\s\S]*?)```\n", s)
        if m:
            pos = m.start()
            g = m.group(2)
            scene_str = g[:g.rfind("}") + 1]
        else:
            scene_str = s
            errs.append(".excalidraw.md without a ## Drawing section (the plugin would fail)")
    else:
        scene_str = s

    scene = None
    if scene_str:
        try:
            scene = json.loads(scene_str.replace("&#91;", "["))
        except Exception as e:
            errs.append(f"invalid JSON: {e}")
    if scene is None:
        return errs, warns, {}, mode, compressed

    els = scene.get("elements")
    stats = Counter()
    if not isinstance(els, list) or not els:
        warns.append("empty scene (no elements)")
        return errs, warns, {}, mode, compressed
    stats = Counter(e.get("type") for e in els)
    ids = [e.get("id") for e in els]
    if len(ids) != len(set(ids)):
        dup = [i for i, c in Counter(ids).items() if c > 1]
        errs.append(f"duplicate ids: {dup[:3]}")
    for e in els:
        miss = REQ - e.keys()
        if miss:
            errs.append(f"element {e.get('id')} missing fields: {sorted(miss)}")
            break
    tx = [e for e in els if e["type"] == "text"]
    for e in tx:
        if len(e["id"]) != 8:
            warns.append(f"text id {e['id']} has {len(e['id'])} chars (plugin expects 8 and duplicates the element)")
        if not (e.get("rawText") or e.get("text")):
            warns.append(f"text {e['id']} is empty")
    seen = Counter((e["x"], e["y"], (e.get("rawText") or e.get("text") or "")) for e in tx)
    dupd = [k for k, c in seen.items() if c > 1]
    if dupd:
        errs.append(f"{len(dupd)} text element(s) duplicated at the same position")

    head = re.search(r"^((%%\n*)?# Excalidraw Data\n\n?## Text Elements(?:\n|$))", s, re.M) or \
           re.search(r"^((%%\n*)?##? Text Elements(?:\n|$))", s, re.M)
    if head and ext == ".md":
        body = s[head.end():pos if pos else len(s)]
        blocks = list(re.finditer(r"\s\^(.{8})[\n]+", body))
        sec_ids = [b.group(1) for b in blocks]
        if len(sec_ids) != len(set(sec_ids)):
            errs.append("duplicate block refs in Text Elements section")
        scene_tx = {e["id"] for e in tx}
        missing = set(sec_ids) - scene_tx
        if missing:
            errs.append(f"block refs without matching element: {sorted(missing)[:3]}")
        unmatched = scene_tx - set(sec_ids)
        if unmatched:
            errs.append(f"{len(unmatched)} text element(s) without a block ref in the section")

    emb_fids = []
    m = re.search(r"^## Embedded Files$", s, re.M)
    if m and ext == ".md":
        body = s[m.end():pos if pos else len(s)]
        entries = re.findall(r"([\w\d]*):\s*!?\[\[([^\]]*)]]\s*(\{[^}]*})?\n", body)
        emb_fids = [a for a, _, _ in entries]
        if len(emb_fids) != len(set(emb_fids)):
            errs.append("duplicate fileIds in Embedded Files")
        for _, link, _ in entries:
            target = link.split("#")[0].split("|")[0].strip()
            if not find_image(vault, target):
                warns.append(f"referenced image not found in vault: {link}")

    files = scene.get("files") or {}
    for e in els:
        if e["type"] == "image":
            fid = e.get("fileId")
            if fid and fid not in files and fid not in emb_fids:
                errs.append(f"image {e['id']} has neither a dataURL nor an Embedded File")

    return errs, warns, dict(stats), mode, compressed


def main():
    args = sys.argv[1:]
    vault = os.path.abspath(".")
    if "--vault" in args:
        i = args.index("--vault")
        vault = os.path.abspath(args[i + 1])
        args = [a for j, a in enumerate(args) if j not in (i, i + 1)]
    files = []
    if args and args[0] == "--all":
        root = args[1] if len(args) > 1 and not args[1].startswith("-") else vault
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if fn.endswith(".excalidraw.md") or fn.endswith(".excalidraw") or fn.endswith(".excalidraw.json"):
                    files.append(os.path.join(dirpath, fn))
        files.sort()
    else:
        files = args
    if not files:
        print("nothing to validate")
        return
    ok = bad = 0
    for p in files:
        errs, warns, stats, mode, compressed = validate(p, vault)
        name = os.path.basename(p)
        if errs:
            bad += 1
            print(f"ERROR {name}")
            for e in errs:
                print(f"   - {e}")
        else:
            ok += 1
            print(f"OK    {name}  [{mode}{'|compressed' if compressed else ''}] {stats}")
        for w in warns[:5]:
            print(f"   note: {w}")
        if len(warns) > 5:
            print(f"   ... {len(warns) - 5} more notes")
    print(f"\n{ok} ok, {bad} with errors, {len(files)} validated")


if __name__ == "__main__":
    main()