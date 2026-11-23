#!/usr/bin/env python3
"""Render the translated homepages from the English one.

English index.html is the source of truth and stays plain, hand-edited HTML. This script
finds every piece of text a visitor reads in it, looks each one up in i18n/<lang>.json
(keys are the English text, values the translation) and writes <dir>/index.html for each
language. Python 3.8+, standard library only.

    python tools/build_i18n.py               # write es/ fr/ it/ zh/ ja/ vi/ index.html
    python tools/build_i18n.py --sync-keys   # after changing English: add new keys (null),
                                             # drop old ones, keep page order; then translate
                                             # the nulls and run without flags

What counts as one piece of text ("unit"):
- an element that has text of its own and only inline markup inside (a <p>, <li>, <h3>,
  <td>, <label>, ...): its whole inner HTML, so a translation can move words around the
  <b>, <a> and <code> inside it (but must keep those elements, in the same order);
- the attributes alt, aria-label, placeholder and title, and <meta> description/og text;
- the values of the JSON in <script id="ui-strings"> (the strings site.js writes).
Skipped: <pre>, <code>, <kbd>, <script>, <style>, <svg>, anything under translate="no",
and text made only of names and commands from i18n/allowlist.json (AirplaneMode, Docker...).
Per page, the script also sets <html lang>, the canonical and og:url, the language
switcher's current name (#lang-now), and adds ../ to relative links.
"""
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from posixpath import normpath

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://airplanemode.xin/"
# code: (html lang / hreflang, folder, the language's own name). English first.
LANGS = [
    ("en", "en", "", "English"),
    ("es", "es", "es/", "Español"),
    ("fr", "fr", "fr/", "Français"),
    ("it", "it", "it/", "Italiano"),
    ("zh", "zh-Hans", "zh/", "中文"),
    ("ja", "ja", "ja/", "日本語"),
    ("vi", "vi", "vi/", "Tiếng Việt"),
]
TRANSLATED = [l for l in LANGS if l[0] != "en"]

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
INLINE = {"a", "b", "strong", "em", "i", "span", "small", "code", "kbd", "br", "input", "img", "abbr", "sub", "sup", "label"}
SKIP = {"script", "style", "pre", "code", "kbd", "svg"}
TEXT_ATTRS = ("alt", "aria-label", "placeholder", "title")
META_TEXT = {("name", "description"), ("property", "og:description"), ("property", "og:title")}


class Node:
    def __init__(self, tag, attrs, start, open_end, parent):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.start, self.open_end = start, open_end      # the start tag: src[start:open_end]
        self.close_start = self.end = open_end            # the end tag: src[close_start:end]
        self.children, self.texts = [], []                # texts: (offset, raw text) of own text

    def path(self):
        parts, n = [], self
        while n and n.tag != "#root":
            s = n.tag + (f"#{n.attrs['id']}" if n.attrs.get("id") else "")
            if n.attrs.get("class"):
                s += "." + ".".join(n.attrs["class"].split())
            parts.append(s)
            n = n.parent
        return " > ".join(reversed(parts[:4]))


class Tree(HTMLParser):
    """A tree of elements with their source offsets (well-formed HTML expected)."""

    def __init__(self, src):
        super().__init__(convert_charrefs=False)
        self.src = src
        self.lines = [0]
        for m in re.finditer("\n", src):
            self.lines.append(m.end())
        self.root = Node("#root", {}, 0, 0, None)
        self.stack = [self.root]
        self.feed(src)
        self.close()
        if len(self.stack) != 1:
            raise ValueError(f"unclosed element {self.stack[-1].path()}")
        self.root.close_start = self.root.end = len(src)

    def off(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self.off()
        node = Node(tag, attrs, start, start + len(self.get_starttag_text()), self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        start = self.off()
        self.stack[-1].children.append(Node(tag, attrs, start, start + len(self.get_starttag_text()), self.stack[-1]))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        top = self.stack.pop()
        if top.tag != tag:
            line, col = self.getpos()
            raise ValueError(f"line {line}: </{tag}> closes <{top.tag}> ({top.path()})")
        top.close_start = self.off()
        top.end = self.src.index(">", top.close_start) + 1

    def _text(self, raw):
        self.stack[-1].texts.append((self.off(), raw))

    def handle_data(self, data):
        self._text(data)

    def handle_entityref(self, name):
        self._text(f"&{name};")

    def handle_charref(self, name):
        self._text(f"&#{name};")


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def load_allow():
    return json.loads((ROOT / "i18n" / "allowlist.json").read_text(encoding="utf-8"))


def names_pattern(allow):
    names = sorted(allow["names"], key=len, reverse=True)
    return re.compile("|".join(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])" for n in names))


def visible_text(fragment):
    """Text a reader sees in an HTML fragment, without <code>/<kbd>/<pre> (never translated)."""
    s = re.sub(r"<(code|kbd|pre)\b[^>]*>.*?</\1>", " ", fragment, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(s)


def needs_translation(text, names_re):
    """True when English text has words left once names and commands are taken out."""
    text = re.sub(r"[a-z][a-z0-9+.-]*://\S*", " ", text)          # URLs
    return re.search(r"[A-Za-z]{2,}", names_re.sub(" ", text)) is not None


def skipped(node):
    n = node
    while n:
        if n.attrs.get("translate") == "no" or n.tag in SKIP or n.attrs.get("id") == "lang-now":
            return True
        n = n.parent
    return False


def all_inline(node):
    return all(c.tag in INLINE and all_inline(c) for c in node.children)


def find_units(tree, names_re):
    """Yield ("inner", node, start, end) and ("attr", node, start, end) for each unit, in page order."""
    src = tree.src
    out = []

    def attr_units(node):
        if skipped(node):
            return
        raw = src[node.start:node.open_end]
        names = list(TEXT_ATTRS)
        if node.tag == "meta" and any(node.attrs.get(k) == v for k, v in META_TEXT):
            names.append("content")
        for name in names:
            m = re.search(r'\s' + re.escape(name) + r'="([^"]*)"', raw)
            if m and needs_translation(html.unescape(m.group(1)), names_re):
                out.append(("attr", node, node.start + m.start(1), node.start + m.end(1)))

    def walk(node, in_unit):
        if node.tag != "#root" and not in_unit:
            attr_units(node)
        if in_unit or skipped(node):
            return
        own = "".join(t for _, t in node.texts).strip()
        if node.tag != "#root" and own and all_inline(node):
            inner = src[node.open_end:node.close_start]
            if needs_translation(visible_text(inner), names_re):
                out.append(("inner", node, node.open_end, node.close_start))
            in_unit = True
        for c in node.children:
            walk(c, in_unit)

    walk(tree.root, False)
    return out


def ui_strings(tree):
    """The <script id="ui-strings"> node and its parsed JSON."""
    for node in iter_nodes(tree.root):
        if node.tag == "script" and node.attrs.get("id") == "ui-strings":
            return node, json.loads(tree.src[node.open_end:node.close_start])
    raise ValueError('index.html has no <script id="ui-strings">')


def iter_nodes(node):
    for c in node.children:
        yield c
        yield from iter_nodes(c)


def english():
    src = (ROOT / "index.html").read_text(encoding="utf-8").replace("\r\n", "\n")
    return src, Tree(src)


def english_keys(src=None, tree=None, allow=None):
    """Every key a string file must have, in page order (text units, then the script's)."""
    if tree is None:
        src, tree = english()
    names_re = names_pattern(allow or load_allow())
    keys = []
    for _, _, a, b in find_units(tree, names_re):
        k = norm(src[a:b])
        if k not in keys:
            keys.append(k)
    for v in ui_strings(tree)[1].values():
        if v not in keys:
            keys.append(v)
    return keys


def load_strings(code):
    return json.loads((ROOT / "i18n" / f"{code}.json").read_text(encoding="utf-8"))


def rel_url(value, prefix):
    """A relative link as seen from a page one folder down."""
    if not value or value.startswith(("#", "/", "data:")) or re.match(r"^[a-z][a-z0-9+.-]*:", value, re.I):
        return value
    out = normpath(prefix + value)
    return out + "/" if value.endswith("/") and not out.endswith("/") else out


def render(code, src=None, tree=None, strings=None, allow=None):
    """The translated page for one language, as a string (LF line endings)."""
    if tree is None:
        src, tree = english()
    lang = next(l for l in LANGS if l[0] == code)
    _, hreflang, folder, own_name = lang
    strings = load_strings(code) if strings is None else strings
    names_re = names_pattern(allow or load_allow())
    missing = []

    def tr(key):
        val = strings.get(key)
        if not isinstance(val, str) or not val.strip():
            missing.append(key)
            return key
        return val

    edits = []  # (start, end, replacement); never overlapping
    for kind, node, a, b in find_units(tree, names_re):
        raw = src[a:b]
        t = tr(norm(raw))
        if kind == "attr":
            t = t.replace('"', "&quot;")
        else:
            lead = raw[:len(raw) - len(raw.lstrip())]
            trail = raw[len(raw.rstrip()):]
            t = lead + t + trail
        edits.append((a, b, t))

    for node in iter_nodes(tree.root):
        raw = src[node.start:node.open_end]
        if node.tag == "html":
            m = re.search(r'\slang="([^"]*)"', raw)
            edits.append((node.start + m.start(1), node.start + m.end(1), hreflang))
        elif (node.tag == "link" and node.attrs.get("rel") == "canonical") or (
                node.tag == "meta" and node.attrs.get("property") == "og:url"):
            attr = "href" if node.tag == "link" else "content"
            m = re.search(r'\s' + attr + r'="([^"]*)"', raw)
            edits.append((node.start + m.start(1), node.start + m.end(1), SITE + folder))
        elif node.attrs.get("id") == "lang-now":
            edits.append((node.open_end, node.close_start, own_name))

    ui_node, ui = ui_strings(tree)
    body = json.dumps({k: tr(v) for k, v in ui.items()}, ensure_ascii=False, indent=2).replace("</", "<\\/")
    edits.append((ui_node.open_end, ui_node.close_start, "\n" + body + "\n"))

    if missing:
        raise MissingStrings(code, missing)

    edits.sort()
    out, pos = [], 0
    for a, b, t in edits:
        if a < pos:
            raise ValueError(f"overlapping edits at offset {a}")
        out.append(src[pos:a])
        out.append(t)
        pos = b
    out.append(src[pos:])
    page = "".join(out)

    # Relative links (assets/, install.sh, the other languages) from one folder down.
    def fix_tag(m):
        return re.sub(r'(\s(?:href|src)=")([^"]*)(")', lambda n: n.group(1) + rel_url(n.group(2), "../") + n.group(3), m.group(0))
    return re.sub(r"<[a-zA-Z][^<>]*>", fix_tag, page)


class MissingStrings(Exception):
    def __init__(self, code, keys):
        self.code, self.keys = code, keys
        super().__init__(f"i18n/{code}.json: {len(keys)} missing or empty: " + "; ".join(k[:70] for k in keys[:5]))


def sync_keys():
    """Rewrite every i18n/<lang>.json in page order: new keys as null, stale keys dropped."""
    keys = english_keys()
    for code, *_ in TRANSLATED:
        path = ROOT / "i18n" / f"{code}.json"
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        new = {k: old.get(k) for k in keys}
        added = [k for k in keys if old.get(k) is None]
        dropped = [k for k in old if k not in new]
        write_json(path, new)
        print(f"{path.relative_to(ROOT)}: {len(added)} to translate, {len(dropped)} dropped")
        for k in dropped:
            print(f"  dropped: {k[:90]}")


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv):
    if "--sync-keys" in argv:
        sync_keys()
        return 0
    src, tree = english()
    allow = load_allow()
    failed = False
    for code, _, folder, _ in TRANSLATED:
        try:
            page = render(code, src, tree, allow=allow)
        except MissingStrings as e:
            failed = True
            print(f"FAIL {code}: {len(e.keys)} strings missing in i18n/{code}.json (run --sync-keys, then translate the nulls):", file=sys.stderr)
            for k in e.keys:
                print(f"  - {k[:110]}", file=sys.stderr)
            continue
        out = ROOT / folder / "index.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(page, encoding="utf-8", newline="\n")
        print(f"wrote {folder}index.html")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
