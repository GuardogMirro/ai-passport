import sys

chars = set()
# ASCII 可见字符
chars.update(chr(c) for c in range(0x20, 0x7F))


def add_gb2312_rows(lo_row, hi_row):
    """枚举 GB2312 指定区(行)的全部字符,返回成功解码数。离线可得,无需外部字表。"""
    n = 0
    for hi in range(0xA0 + lo_row, 0xA0 + hi_row + 1):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("gb2312")
            except UnicodeDecodeError:
                continue
            if len(ch) == 1:
                chars.add(ch)
                n += 1
    return n


# 第 1-9 区:符号区(全角标点 U+FF0C/U+FF1A 等、全角字母数字、单位符号、制表线)
syms = add_gb2312_rows(1, 9)
# 第 16-55 区:一级字表 3755 字(按拼音序)
lv1 = add_gb2312_rows(16, 55)
# GB2312 之外补齐的常用符号
extra = "\u2713\u2717\u2022\u2014\u2026\uffe5\u2460\u2461\u2462\u2463\u2464" \
        "\u25b2\u25bc\u25c6\u25cf\u25cb\u25a0\u2605\u2191\u2193\u2190\u2192" \
        "\u2103\u2109\u00b1\u00d7\u00f7\u00b0"
chars.update(extra)

out = sorted(chars)
path = sys.argv[1] if len(sys.argv) > 1 else "output/fonttools/charset.txt"
with open(path, "w", encoding="utf-8") as f:
    f.write("".join(out))
print("gb2312 symbol rows 1-9:", syms)
print("gb2312 level-1 rows 16-55:", lv1)
print("charset total:", len(out), "->", path)
print("fullwidth comma U+FF0C present:", "\uff0c" in chars)
print("fullwidth colon U+FF1A present:", "\uff1a" in chars)
print("ideographic space U+3000 present:", "\u3000" in chars)
