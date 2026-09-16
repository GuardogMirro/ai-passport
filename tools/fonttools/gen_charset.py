import sys, json

chars = set()
# ASCII 可见字符
chars.update(chr(c) for c in range(0x20, 0x7F))
# GB2312 一级字表(rows 16-55, 3755 字, 按拼音序)——离线枚举, 无需外部字表
lv1 = 0
for hi in range(0xB0, 0xD8):
    for lo in range(0xA1, 0xFF):
        try:
            ch = bytes([hi, lo]).decode("gb2312")
        except UnicodeDecodeError:
            continue
        if len(ch) == 1:
            chars.add(ch)
            lv1 += 1
# 常用中文标点与符号(GB2312 符号区之外补齐)
extra = "、。《》〈〉【】〔〕·—…￥✓✗℃℉±×÷°①②③④⑤⑥⑦⑧⑨⑩▲▼◆●○□■★☆↑↓←→"
chars.update(extra)

out = sorted(chars)
path = sys.argv[1] if len(sys.argv) > 1 else "output/fonttools/charset.txt"
with open(path, "w", encoding="utf-8") as f:
    f.write("".join(out))
print("gb2312 level-1 decoded:", lv1)
print("charset total:", len(out), "-> ", path)
print("sample:", "".join(out[95:135]))
