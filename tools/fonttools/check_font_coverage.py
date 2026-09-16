#!/usr/bin/env python3
"""tools/fonttools/check_font_coverage.py -- glyph coverage gate.

Fails when a character that will reach the screen is absent from the compiled
CJK charset, so a missing glyph is caught before build instead of appearing as
a placeholder box on the panel.

Scans two kinds of source:
  *.c / *.h   non-ASCII characters inside string literals (comments stripped)
  *.json      every string value in a ui_spec page description

usage: python tools/fonttools/check_font_coverage.py <charset.txt> <file> [...]
exit 0 = covered, 1 = missing glyphs listed, 2 = usage error.
"""
import json
import re
import sys


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def c_literals(src):
    return re.findall(r'"((?:[^"\\\n]|\\.)*)"', src)


def json_strings(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from json_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from json_strings(v)
    elif isinstance(node, str):
        yield node


def texts_of(path):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    if path.lower().endswith(".json"):
        return list(json_strings(json.loads(raw)))
    return c_literals(strip_comments(raw))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    charset_path, sources = sys.argv[1], sys.argv[2:]
    with open(charset_path, encoding="utf-8") as f:
        charset = set(f.read())

    missing_all = {}
    for path in sources:
        missing = {}
        for text in texts_of(path):
            for ch in text:
                if ord(ch) > 0x7F and ch not in charset:
                    missing[ch] = missing.get(ch, 0) + 1
        if missing:
            print("MISSING in %s:" % path)
            for ch, n in sorted(missing.items()):
                print("  U+%04X %s  x%d" % (ord(ch), ch, n))
            missing_all.update(missing)

    if missing_all:
        print("FAIL: %d distinct glyphs not in %s" % (len(missing_all), charset_path))
        return 1
    print("PASS: all non-ASCII screen text covered by %s (%d chars, %d files)"
          % (charset_path, len(charset), len(sources)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
