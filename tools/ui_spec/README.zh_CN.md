<p align="right">
  <strong>简体中文</strong> · <a href="README.md">English</a>
</p>

# tools/ui_spec —— 声明式页面描述与像素级预览

一个页面只描述一次（JSON），在主机上渲染成与屏幕一致的 PNG。预览就是评审面：
版式问题一秒内看出来，不必先编译固件；同一份文件也是代码生成的输入。

## 预览为什么可信

`render.py` 用与 `main/ui_pixel.h` 相同的调色板、与 `ui_pixel_panel_create`
相同的面板几何（4px 墨色边框、7px 内边距、投影偏移 +5/+6）、与设备相同的字体
文件，并把每个颜色按 ST7789 的存法量化到 RGB565。对真机串口截图实测：
**46080 像素中 128 个不同（0.28%）**，且全部落在进度条圆角的抗锯齿边缘与一个
字形细节上——版式零误差，文字 X 坐标与墨迹像素数完全一致。

复现：

```sh
python tools/ui_spec/render.py tools/ui_spec/pages/balance.json /tmp/preview.png \
  --font-dir /tmp/fusion12 --capture
python tools/capture_screen.py COM5 /tmp/device.png   # 设备需停在该页
python tools/ui_spec/diff_capture.py /tmp/preview.png /tmp/device.png
```

`--font-dir` 指向解压后的 Fusion Pixel 12px 字族（用
`tools/fonttools/fetch_asset.mjs` 下载）。`--capture` 只渲染 240x192 截屏容器
（黑底），与 `capture_screen.py` 的产物同构；不加则渲染整块 240x320 屏幕，含天空、
白云、草地与标题牌。

## 页面原型（archetype）

spec 只声明原型与内容，几何在这里推导，所以描述保持声明式。

| 原型 | 形态 | 用于 |
| --- | --- | --- |
| `dashboard` | 竖排指标块：12px 标签 + 24px 主数值 + 带预估刻度线的进度条；底部状态行 | 余额页 |
| `list` | iOS 设置式分组行：组标题、行内"左标签 / 右取值 / 右箭头"、细分隔线 | 设置类菜单 |

spec 里的坐标是**容器局部坐标**，与固件把子节点挂到 240x192 截屏容器的方式一致。

## 文件

| 文件 | 职责 |
| --- | --- |
| `render.py` | spec → PNG（原型展开、主题几何、RGB565 量化、标定过的文字基线） |
| `diff_capture.py` | 渲染图 vs 真机截图 → 不一致率、8px 密度图、颜色对、失配行带 |
| `pages/*.json` | 页面描述 |

文字基线带一个**实测**的每字面校正量（`FACES` 里的 `dy_corr`），由真机截图标定，
与字面主值 `.ofs_y`（12px 为 -2、24px 为 -4）一致。换字体后用 `diff_capture.py`
重新标定。

## 渲染或编译之前

上屏文字必须在已编译的字符集里，否则屏上是方框：

```sh
python tools/fonttools/check_font_coverage.py tools/fonttools/charset_body.txt \
  main/*.c tools/ui_spec/pages/*.json
```

该门禁同时读 `.json` spec 与 C 源码。

## 尚未实现

spec → C 代码生成器（产出 `main/demo_<page>.c` 并注册进 `DEMOS[]`），以及把
`diff_capture.py` 接进 CI。当前可用的是预览与门禁两部分；固件页面仍手写。
