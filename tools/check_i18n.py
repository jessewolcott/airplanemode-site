#!/usr/bin/env python3
"""Check that the translated homepages are in step with the English one (CI runs this).

    python tools/check_i18n.py            # exit 1 with one line per problem

For each language (es fr it zh ja vi), compared with English index.html:
- i18n/<lang>.json has exactly the keys the English page needs, none empty, and each
  translation keeps the key's {placeholders};
- <lang>/index.html is byte-for-byte what tools/build_i18n.py renders now (so nobody edited
  a generated page by hand, and nobody forgot to re-run the generator);
- the same elements in the same order: tags, ids, classes, href/src (resolved), data-*,
  and every other attribute except the translated ones (alt, aria-label, placeholder,
  title, meta description text); so the same sections, app cards, steps and images;
- <code>, <pre>, <kbd>, <script>, <style> and translate="no" content byte-identical
  (the install command, paths, the language list);
- <html lang>, canonical, og:url, the switcher's current name, and hreflang links for all
  seven languages plus x-default, on every page (English too);
- no leftover English: a text node or translated attribute that is the same as in English
  and still has words once the names and commands in i18n/allowlist.json are taken out
  (or listed for that language under "same" in the allowlist).
Also, when the platform repo sits next to this one (../airplanemode/portal/apps.json, or
--apps PATH), the English app cards must match apps.json: names, descriptions, categories.
"""
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_i18n as b  # noqa: E402

TRANSLATED_ATTRS = set(b.TEXT_ATTRS)


class Page:
    """Flat view of a page: element tokens, text slots, protected text, translated attrs."""

    def __init__(self, src, url):
        self.tree = b.Tree(src)
        self.src, self.url = src, url
        self.elements = []   # (path, tag, attrs-for-comparison)
        self.texts = {}      # element index -> [(raw text, protected?)] of that element's own text
        self.attr_text = []  # (path, name, value) of translated attributes, in order
        self._walk(self.tree.root, protected=False)

    def _walk(self, node, protected):
        for c in node.children:
            self._element(c, protected)

    def _element(self, node, protected):
        prot = protected or node.tag in b.SKIP or node.attrs.get("translate") == "no"
        if node.attrs.get("id") == "ui-strings":
            prot = False  # translated JSON, compared key by key in check_ui_strings
        attrs = {}
        meta_text = node.tag == "meta" and any(node.attrs.get(k) == v for k, v in b.META_TEXT)
        for k, v in node.attrs.items():
            v = v or ""
            if (k in TRANSLATED_ATTRS or (meta_text and k == "content")) and not prot:
                self.attr_text.append((node.path(), k, v))
                v = "<translated>"
            elif k in ("href", "src") and not v.startswith("#"):
                v = urljoin(self.url, v)
            attrs[k] = v
        # Per-page values, checked on their own.
        if node.tag == "html":
            attrs.pop("lang", None)
        if node.tag == "link" and node.attrs.get("rel") == "canonical":
            attrs.pop("href", None)
        if node.tag == "meta" and node.attrs.get("property") == "og:url":
            attrs.pop("content", None)
        idx = len(self.elements)
        self.elements.append((node.path(), node.tag, attrs))
        own = [(raw, prot or node.attrs.get("id") == "lang-now") for _, raw in node.texts]
        self.texts[idx] = own
        self._walk(node, prot)

    def find(self, pred):
        return [n for n in b.iter_nodes(self.tree.root) if pred(n)]


def leftover(text, names_re, same):
    """English words left in text that should have been translated."""
    t = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if not t or t in same:
        return False
    return b.needs_translation(t, names_re)


def check_lang(code, hreflang, folder, own_name, en, allow, names_re, keys, problems):
    def bad(msg):
        problems.append(f"[{code}] {msg}")

    # 1. the string file
    path = b.ROOT / "i18n" / f"{code}.json"
    try:
        strings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        bad(f"i18n/{code}.json can't be read: {e}")
        return
    for k in keys:
        if k not in strings:
            bad(f"i18n/{code}.json is missing the key for English text: {k[:100]!r} (run tools/build_i18n.py --sync-keys)")
        elif not isinstance(strings[k], str) or not strings[k].strip():
            bad(f"i18n/{code}.json has no translation for: {k[:100]!r}")
        elif set(re.findall(r"\{\w+\}", strings[k])) != set(re.findall(r"\{\w+\}", k)):
            bad(f"i18n/{code}.json: placeholders differ for {k[:80]!r}: {strings[k][:80]!r}")
    for k in strings:
        if k not in keys:
            bad(f"i18n/{code}.json has a key the English page no longer has: {k[:100]!r} (run tools/build_i18n.py --sync-keys)")

    # 2. the committed page equals a fresh render
    page_path = b.ROOT / folder / "index.html"
    if not page_path.exists():
        bad(f"{folder}index.html is missing (run tools/build_i18n.py)")
        return
    committed = page_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    try:
        fresh = b.render(code, en.src, en.tree, strings=strings, allow=allow)
        if fresh != committed:
            line = next((i for i, (x, y) in enumerate(zip(fresh.split("\n"), committed.split("\n")), 1) if x != y),
                        min(fresh.count("\n"), committed.count("\n")) + 1)
            bad(f"{folder}index.html is not what tools/build_i18n.py renders (first difference at line {line}); "
                f"edit English index.html or i18n/{code}.json and re-run the generator, never the generated page")
    except b.MissingStrings:
        pass  # already reported above
    except ValueError as e:
        bad(f"can't render: {e}")

    # 3. structure, protected text, leftovers: from the committed page
    try:
        tr = Page(committed, b.SITE + folder)
    except ValueError as e:
        bad(f"{folder}index.html doesn't parse: {e}")
        return
    check_structure(code, en, tr, bad)
    check_text(code, en, tr, names_re, set(allow.get("same", {}).get(code, [])), bad)
    check_page_meta(tr, hreflang, folder, own_name, bad)
    check_ui_strings(en, tr, names_re, set(allow.get("same", {}).get(code, [])), bad)


def check_structure(code, en, tr, bad):
    for sel, name in ((lambda n: n.tag == "a" and "app" in n.attrs.get("class", "").split(), "app cards"),
                      (lambda n: n.tag == "li" and "data-step" in n.attrs, "setup steps"),
                      (lambda n: n.tag == "section", "sections"),
                      (lambda n: n.tag == "img", "images")):
        x, y = len(en.find(sel)), len(tr.find(sel))
        if x != y:
            bad(f"{y} {name}, English has {x}")
    if len(en.elements) != len(tr.elements):
        bad(f"{len(tr.elements)} elements, English has {len(en.elements)}")
    for i, (a, c) in enumerate(zip(en.elements, tr.elements)):
        if a[1] != c[1] or a[2] != c[2]:
            if a[1] != c[1]:
                what = f"<{c[1]}> where English has <{a[1]}>"
            else:
                diff = sorted(k for k in set(a[2]) | set(c[2]) if a[2].get(k) != c[2].get(k))
                what = "; ".join(f"{k}={c[2].get(k)!r}, English {a[2].get(k)!r}" for k in diff)
            bad(f"element {i} ({a[0]}): {what}")
            return  # everything after the first difference is shifted


def check_text(code, en, tr, names_re, same, bad):
    if len(en.elements) != len(tr.elements):
        return
    for i, (path, tag, _) in enumerate(en.elements):
        a, c = en.texts[i], tr.texts[i]
        a_prot = "".join(t for t, p in a if p)
        c_prot = "".join(t for t, p in c if p)
        if a_prot != c_prot and not (tag == "span" and en.elements[i][2].get("id") == "lang-now"):
            bad(f"{path}: protected text (code, command or translate=no) differs: {c_prot[:80]!r}, English {a_prot[:80]!r}")
        a_txt = "".join(t for t, p in a if not p)
        c_txt = "".join(t for t, p in c if not p)
        if tag not in ("script", "style", "svg") and a_txt.strip() and re.sub(r"\s+", " ", a_txt).strip() == re.sub(r"\s+", " ", c_txt).strip() \
                and leftover(c_txt, names_re, same):
            bad(f"{path}: still in English: {c_txt.strip()[:100]!r}")
    for (path, name, v_en), (_, _, v_tr) in zip(en.attr_text, tr.attr_text):
        if v_en == v_tr and leftover(v_tr, names_re, same):
            bad(f"{path}: {name} still in English: {v_tr[:100]!r}")


def check_page_meta(page, hreflang, folder, own_name, bad):
    want_url = b.SITE + folder
    html_nodes = page.find(lambda n: n.tag == "html")
    if not html_nodes or html_nodes[0].attrs.get("lang") != hreflang:
        bad(f'<html lang> is {html_nodes[0].attrs.get("lang") if html_nodes else None!r}, should be {hreflang!r}')
    canon = page.find(lambda n: n.tag == "link" and n.attrs.get("rel") == "canonical")
    if [n.attrs.get("href") for n in canon] != [want_url]:
        bad(f"canonical should be one link to {want_url}, found {[n.attrs.get('href') for n in canon]}")
    og = page.find(lambda n: n.tag == "meta" and n.attrs.get("property") == "og:url")
    if [n.attrs.get("content") for n in og] != [want_url]:
        bad(f"og:url should be {want_url}")
    alts = {n.attrs.get("hreflang"): n.attrs.get("href") for n in page.find(
        lambda n: n.tag == "link" and n.attrs.get("rel") == "alternate" and n.attrs.get("hreflang"))}
    want = {l[1]: b.SITE + l[2] for l in b.LANGS}
    want["x-default"] = b.SITE
    if alts != want:
        missing = sorted(set(want) - set(alts)) + sorted(k for k in want if k in alts and alts[k] != want[k])
        bad(f"hreflang links wrong or missing: {missing or sorted(set(alts) - set(want))}")
    now = page.find(lambda n: n.attrs.get("id") == "lang-now")
    if not now or "".join(t for _, t in now[0].texts) != own_name:
        bad(f"the language switcher should name the page's language as {own_name!r}")
    links = {n.attrs.get("hreflang"): urljoin(page.url, n.attrs.get("href", ""))
             for n in page.find(lambda n: n.tag == "a" and n.parent and n.parent.tag == "li" and n.attrs.get("hreflang"))}
    want_links = {l[1]: b.SITE + l[2] for l in b.LANGS}
    if links != want_links:
        bad(f"the language switcher should link all seven pages, found {links}")


def check_ui_strings(en, tr, names_re, same, bad):
    try:
        _, a = b.ui_strings(en.tree)
        _, c = b.ui_strings(tr.tree)
    except ValueError as e:
        bad(f"ui-strings: {e}")
        return
    if list(a) != list(c):
        bad(f"ui-strings keys differ from English: {sorted(set(a) ^ set(c))}")
        return
    for k in a:
        if set(re.findall(r"\{\w+\}", a[k])) != set(re.findall(r"\{\w+\}", c[k])):
            bad(f"ui-strings {k!r}: placeholders differ: {c[k]!r}")
        if a[k] == c[k] and leftover(c[k], names_re, same):
            bad(f"ui-strings {k!r} still in English: {c[k]!r}")


def check_apps(en, path, problems):
    """English app cards against the platform's portal/apps.json (when it's available)."""
    apps = json.loads(Path(path).read_text(encoding="utf-8"))
    cards = en.find(lambda n: n.tag == "a" and "app" in n.attrs.get("class", "").split())
    def text(n):
        return html.unescape(re.sub(r"<[^>]+>", "", en.src[n.open_end:n.close_start])).strip()
    found = []
    for card in cards:
        h3 = [n for n in b.iter_nodes(card) if n.tag == "h3"]
        p = [n for n in b.iter_nodes(card) if n.tag == "p"]
        tag = [n for n in b.iter_nodes(card) if "tag" in n.attrs.get("class", "").split()]
        found.append((text(h3[0]) if h3 else "", text(p[0]) if p else "", text(tag[0]) if tag else ""))
    by_name = {f[0]: f for f in found}
    for app in apps:
        card = by_name.get(app["name"])
        if not card:
            problems.append(f"[en] apps.json has {app['name']!r} but the homepage has no card for it")
            continue
        if card[1] != app["description"]:
            problems.append(f"[en] {app['name']} card description differs from apps.json: {card[1][:80]!r}")
        if card[2].split(" · ")[0] != app["category"]:
            problems.append(f"[en] {app['name']} card tag {card[2]!r} should start with the category {app['category']!r}")
        if bool(app.get("uses_llm")) != ("model" in card[2]):
            problems.append(f"[en] {app['name']} card tag {card[2]!r} doesn't match uses_llm={app.get('uses_llm')}")
    for name in by_name:
        if name not in {a["name"] for a in apps}:
            problems.append(f"[en] homepage card {name!r} isn't in apps.json")


def main(argv):
    problems = []
    allow = b.load_allow()
    names_re = b.names_pattern(allow)
    src, _ = b.english()
    en = Page(src, b.SITE)
    keys = b.english_keys(src, en.tree, allow)
    check_page_meta(en, "en", "", "English", lambda m: problems.append(f"[en] {m}"))
    for code, hreflang, folder, own_name in b.TRANSLATED:
        check_lang(code, hreflang, folder, own_name, en, allow, names_re, keys, problems)

    apps = argv[argv.index("--apps") + 1] if "--apps" in argv else b.ROOT.parent / "airplanemode" / "portal" / "apps.json"
    if Path(apps).exists():
        check_apps(en, apps, problems)
    else:
        print(f"note: {apps} not found, app cards not compared with apps.json")

    if problems:
        print(f"check_i18n: {len(problems)} problem(s). Translations must follow English index.html:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        print("Fix: change English, update i18n/<lang>.json (tools/build_i18n.py --sync-keys lists what's new), "
              "run tools/build_i18n.py, then this check.", file=sys.stderr)
        return 1
    print(f"check_i18n: OK ({len(b.TRANSLATED)} languages, {len(keys)} strings each, in step with English)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
