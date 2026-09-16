import sys

src = sys.argv[1] if len(sys.argv) > 1 else "output/fonttools/charset.txt"
dst = sys.argv[2] if len(sys.argv) > 2 else "output/fonttools/charset_body.txt"
# 字体实测不覆盖的装饰符(U+2713/U+2717),剔除;界面改用 ASCII 或图形符号
drop = {"\u2713", "\u2717"}
s = open(src, encoding="utf-8").read()
kept = "".join(c for c in s if c not in drop)
open(dst, "w", encoding="utf-8").write(kept)
print("kept", len(kept), "of", len(s), "->", dst)
print("dropped", len(s) - len(kept))
