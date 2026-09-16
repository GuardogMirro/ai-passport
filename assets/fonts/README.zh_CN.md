<p align="right">
  <strong>简体中文</strong> · <a href="README.md">English</a>
</p>

# CJK 像素字面（assets/fonts）

设备上屏的中文由这两个编译进固件的字面提供；Latin 与数字由 Montserrat 兜底。

## 文件与命名

| 文件 | 符号 | 字号 | 用途 |
| --- | --- | --- | --- |
| `ui_font_cjk_12.c` | `ui_font_cjk_12` | 12px | 正文、标签、状态行 —— `ui_pixel_font_body()` |
| `ui_font_cjk_24.c` | `ui_font_cjk_24` | 24px（12px 设计的整数倍放大） | 标题、主数值 —— `ui_pixel_font_title()` |

命名规则：`ui_font_cjk_<px>.c`，符号与文件同名。两者都是 `lv_font_conv` 生成的
`const` 数据（位图 + 字形表 + cmap），留在 flash，**不占堆**——本机无 PSRAM、
内部 DRAM 紧张，所以不走运行时 `.bin` 加载（那会按字形数在堆上建表）。

## 集成方式

- `main/CMakeLists.txt` 的 `SRCS` 引用这两个 `.c`。
- 应用代码只通过 `main/ui_pixel.h` 的 `ui_pixel_font_body()` /
  `ui_pixel_font_title()` 取字面，不直接 extern 符号（主题层单一入口）。
- 中文屏标题用 `ui_pixel_screen_create_font(title, ui_pixel_font_title())`；
  纯 ASCII 标题继续用 `ui_pixel_screen_create(title)`。

## 字符集

共 4505 字，清单在 `tools/fonttools/charset_body.txt`。请求集为：ASCII
`0x20-0x7E`、GB2312 第 1-9 区（682 字：全角标点如 U+FF0C/U+FF1A、全角字母数字、
单位符号）、GB2312 一级字表（3755 字）与少量补充符号，合计 4538 字。字源覆盖其中
4505 字；未覆盖的 33 个是数学符号（U+2208、U+2211、U+221A、U+2264 一类），界面
用不到——由 `emit_charset.mjs` **实测字体后剔除**，而不是维护一份手写排除清单。

上屏前用门禁核对覆盖，缺字在编译前报出，而不是在屏上显示方框：

```sh
python tools/fonttools/check_font_coverage.py tools/fonttools/charset_body.txt main/*.c
```

## 来源与授权

- 字源：**Fusion Pixel 12px Monospaced zh_hans**，v2026.09.01，仓库
  `TakWolf/fusion-pixel-font`，**SIL Open Font License 1.1**（全文见同目录 `OFL.txt`）。
- 选型为 2026-09-16 实测而非推断：Ark Pixel 的 10px/16px 是精简字集，对当时的
  字符集只覆盖 3721/3895（缺 174 个 GB2312 一级字，含 U+5373、U+52BF、U+6267、
  U+60A0、U+60D1）；Ark Pixel 12px 七个语言变体取并集同样停在 3721。Fusion
  Pixel 12px 除上述数学符号外全覆盖。
- 系统字体（黑体/宋体/雅黑）为微软授权、不可再分发，故不用于本仓库。

## 再生成

见 `tools/fonttools/README.md`（一条命令链，约 1 分钟；需要 Node.js 与
`npm i lv_font_conv`）。
