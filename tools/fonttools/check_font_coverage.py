#!/usr/bin/env python3
# tools/check_font_coverage.py -- verify every non-ASCII char used in UI string
# literals is present in the compiled CJK charset, so a missing glyph (rendered
# as a placeholder box on screen) is caught before build/flash instead of after.
#
# usage: python tools/check_font_coverage.py <charset.txt> <src.c> [<src2.c> ...]
# exit 0 = covered, 1 = missing glyphs listed.
import re
import sys


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def literals(src):
    return re.findall(r'"((?:[^"\\\n]|\\.)*)"', src)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    charset_path, sources = sys.argv[1], sys.argv[2:]
    with open(charset_path, encoding="utf-8") as f:
        charset = set(f.read())

    total_missing = {}
    for path in sources:
        with open(path, encoding="utf-8") as f:
            src = strip_comments(f.read())
        file_missing = {}
        for lit in literals(src):
            for ch in lit:
                if ord(ch) > 0x7F and ch not in charset:
                    file_missing[ch] = file_missing.get(ch, 0) + 1
        if file_missing:
            print("MISSING in %s:" % path)
            for ch, n in sorted(file_missing.items()):
                print("  U+%04X %s  x%d" % (ord(ch), ch, n))
            total_missing.update(file_missing)

    if total_missing:
        print("FAIL: %d distinct glyphs not in %s" % (len(total_missing), charset_path))
        return 1
    print("PASS: all non-ASCII UI literals covered by %s (%d chars)"
          % (charset_path, len(charset)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
