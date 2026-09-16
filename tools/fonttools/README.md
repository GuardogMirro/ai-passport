# tools/fonttools —— 中文字面生成链

从开源像素字体生成 LVGL 的 C 字面，产物落到 `assets/fonts/`（规范见
`assets/README.md` 的 Fonts 节与 `assets/fonts/README.md`）。

## 依赖

- Node.js（实测 v24）+ `npm i lv_font_conv`（实测 1.5.3；opentype.js 随其安装）
- Python 3（枚举 GB2312 字符集，标准库即可）
- 出网下载字源。**注意**：本机 PowerShell 的 `Invoke-WebRequest` 走 schannel 会被
  TLS 拦截，`node fetch`（undici）可用——下载脚本按此实现。

## 命令链

```sh
# 1. 下载字源（按名字正则匹配 release 资产，用 API 返回的真实下载 URL）
node tools/fonttools/fetch_asset.mjs TakWolf/fusion-pixel-font \
  "^fusion-pixel-font-12px-monospaced-ttf-v.*\.zip$" /tmp/fusion12.zip
#    解压取 fusion-pixel-12px-monospaced-zh_hans.ttf

# 2. 生成字符集（离线枚举 GB2312 一级字表 + ASCII + 标点），剔除字源不覆盖的字符
python tools/fonttools/gen_charset.py /tmp/charset.txt
python tools/fonttools/prep_charset.py /tmp/charset.txt tools/fonttools/charset_body.txt

# 3. 生成两个字面（12px 正文 / 24px 标题）
node tools/fonttools/gen_cjk_font.mjs tools/fonttools/charset_body.txt <ttf> \
  assets/fonts/ui_font_cjk_12.c 12 1 lv_font_montserrat_14
node tools/fonttools/gen_cjk_font.mjs tools/fonttools/charset_body.txt <ttf> \
  assets/fonts/ui_font_cjk_24.c 24 1 lv_font_montserrat_20

# 4. 门禁：UI 字符串用字是否都被字库覆盖
python tools/fonttools/check_font_coverage.py tools/fonttools/charset_body.txt main/*.c
```

## 脚本职责

| 脚本 | 作用 |
| --- | --- |
| `fetch_asset.mjs` | 按名字正则下载 GitHub Releases 资产（走 API 的 `browser_download_url`，不猜 URL） |
| `gen_charset.py` | 离线枚举 GB2312 一级字表 + ASCII + 常用标点 → 字符集 |
| `prep_charset.py` | 剔除字源不覆盖的字符（当前为 `✓ ✗`） |
| `gen_cjk_font.mjs` | 调 lv_font_conv 生成 LVGL C 字面，并报告字形数与体积 |
| `probe_coverage.mjs` | 用 opentype.js 实测某字源对字符集的覆盖率（选字体时用） |
| `check_font_coverage.py` | 门禁：源码 UI 字面量里的非 ASCII 字是否都在字符集内 |

## 参数选择理由

- `--bpp 1`：像素字体只有黑白两态，1bpp 最省 flash 且不会发虚。
- `--no-compress`：不依赖 `LV_USE_FONT_COMPRESSED`，少一个配置变量；flash 有余量
  （两个字面共约 350KB，app 分区 7.9MB）。
- `--autohint-off`：保留字体自身的像素网格设计，避免 hinting 移动笔画。
- `--no-kerning`：等宽像素字体无需字距表，省体积。
- 24px 由 12px 设计整数倍放大（unitsPerEm 1200 → 100 单位/设计像素），每个设计
  像素正好变成 2×2 输出像素，得到干净的"大颗粒"效果，而不是矢量重渲染的模糊边。
- 字面用 `const` C 数组编译进固件而非运行时加载 `.bin`：无 PSRAM 机器上，运行时
  加载要按字形数在堆上建表，我们付不起；`const` 数组留在 flash，零堆开销。
