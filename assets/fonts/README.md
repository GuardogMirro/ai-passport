# CJK 像素字面（assets/fonts）

设备上屏的中文由这两个编译进固件的字面提供；Latin 与数字由 Montserrat 兜底。

## 文件与命名

| 文件 | 符号 | 字号 | 用途 |
| --- | --- | --- | --- |
| `ui_font_cjk_12.c` | `ui_font_cjk_12` | 12px | 正文、标签、状态行 —— `ui_pixel_font_body()` |
| `ui_font_cjk_24.c` | `ui_font_cjk_24` | 24px（12px 设计的整数倍放大） | 标题、主数值 —— `ui_pixel_font_title()` |

命名规则：`ui_font_cjk_<px>.c`，符号与文件同名。两者都是 `lv_font_conv` 生成的
`const` 数据（位图 + 字形表 + cmap），留在 flash，**不占堆**——本机无 PSRAM、
DRAM 紧张，所以不走运行时 `.bin` 加载（那会按字形数在堆上建表）。

## 集成方式

- `main/CMakeLists.txt` 的 `SRCS` 引用这两个 `.c`。
- 应用代码只通过 `main/ui_pixel.h` 的 `ui_pixel_font_body()` /
  `ui_pixel_font_title()` 取字面，不直接 extern 符号（主题层单一入口）。
- 中文屏标题用 `ui_pixel_screen_create_font(title, ui_pixel_font_title())`；
  纯 ASCII 标题继续用 `ui_pixel_screen_create(title)`。

## 字符集

ASCII `0x20-0x7E` + GB2312 一级字表 3755 字 + 常用中文标点 = **3893 字**。
清单：`tools/fonttools/charset_body.txt`。

上屏前用门禁核对覆盖，缺字在编译前报出，而不是在屏上显示方框：

```sh
python tools/fonttools/check_font_coverage.py tools/fonttools/charset_body.txt main/*.c
```

## 来源与授权

- 字源：**Fusion Pixel 12px Monospaced zh_hans**，v2026.09.01，仓库
  `TakWolf/fusion-pixel-font`，**SIL Open Font License 1.1**（全文见同目录 `OFL.txt`）。
- 选型实测（2026-09-16）：Ark Pixel 的 10px/16px 是精简字集，对本字符集只覆盖
  3721/3895，缺「即 势 执 悠 惑」等 174 个 GB2312 一级字；Ark/Fusion 的 12px 才是
  全字集。Fusion Pixel 12px 覆盖 3893/3895（仅缺 `✓ ✗` 两个装饰符，已从字符集剔除）。
- 系统字体（黑体/宋体/雅黑）为微软授权、不可再分发，故不用于本仓库。

## 再生成

见 `tools/fonttools/README.md`（一条命令链，约 1 分钟；需要 node + `npm i lv_font_conv`）。
