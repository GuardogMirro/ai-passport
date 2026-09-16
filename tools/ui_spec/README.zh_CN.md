<p align="right">
  <strong>简体中文</strong> · <a href="README.md">English</a>
</p>

# tools/ui_spec —— 描述页面 → 预览 → 生成固件

一个页面只描述一次（JSON）。`render.py` 把它画成与屏幕一致的 PNG，
`gen_page.py` 把同一份描述翻译成 `main/demo_<page>.c` 及其注册代码。几何只存在于
`layout.py` 一处，所以预览与固件是**同一份描述的两种渲染**，而不是两套会各自漂移
的实现。

## 循环

```sh
# 1. 描述页面
$EDITOR tools/ui_spec/pages/<page>.json

# 2. 看效果（整屏 / 只看截屏容器）
python tools/ui_spec/render.py tools/ui_spec/pages/<page>.json /tmp/<page>.png \
  --font-dir /tmp/fusion12
python tools/ui_spec/render.py tools/ui_spec/pages/<page>.json /tmp/<page>_cap.png \
  --font-dir /tmp/fusion12 --capture

# 3. 先过字形门禁，再生成并注册页面
python tools/fonttools/check_font_coverage.py tools/fonttools/charset_body.txt \
  main/*.c tools/ui_spec/pages/*.json
python tools/ui_spec/gen_page.py tools/ui_spec/pages/<page>.json \
  --out main/demo_<page>.c --register --repo . --force

# 4. 构建烧录后抓真机图，与预览对拍
python tools/capture_screen.py COM5 /tmp/device.png
python tools/ui_spec/diff_capture.py /tmp/<page>_cap.png /tmp/device.png --max-pct 1.0
```

`--font-dir` 指向解压后的 Fusion Pixel 12px 字族（用
`tools/fonttools/fetch_asset.mjs` 下载）。`--capture` 只渲染 240x192 容器（黑底），
与 `capture_screen.py` 的产物同构。

## 页面原型（archetype）

spec 只声明原型与内容，几何由 `layout.py` 推导。坐标是**容器局部坐标**，与固件把
子节点挂到截屏容器的方式一致。

| 原型 | 形态 | 示例 |
| --- | --- | --- |
| `dashboard` | 指标块：12px 标签 + 24px 主数值 + 带预估刻度线的进度条；底部状态行 | `pages/balance.json` |
| `list` | iOS 设置式分组行：组标题、左标签、右取值、`>` 箭头、细分隔线、可移动光标 | `pages/settings.json` |

## 实测保真度

对手写的余额页真机截图：**46080 像素中 154 个不同（0.33%）**。对本工具端到端
生成的设置页（spec → C → 构建 → 烧录 → 抓图）：**46080 像素中 0 个不同
（0.00%）**。文字 X 坐标与墨迹像素数完全一致；余额页的残差来自 LVGL 对进度条
圆角的抗锯齿混色（渲染器保持硬边——实测建模混色反而更差）与一个字形细节。
`diff_capture.py --max-pct` 把这个地板变成门禁：版式错误表现为成片行带，
远高于该阈值。

## 生成器编码了哪些规则

取自 `AGENTS.md`、agent 指南与 `main.c`，让生成的页面与手写页面行为一致：

- `enter`/`exit` 由 `main.c` 持 LVGL 锁调用；`key` **不持锁**，所以生成的按键处理
  自己取 `bsp_lvgl_lock()`。
- `exit` 先清截屏目标、再删屏、并把指针置空。静态页面不拥有任务或定时器；若将来
  spec 需要，必须先在删除前停掉它们。
- OK 长按返回是 `main.c` 的全局交互，页面不重复实现。
- 页面把自己的截屏容器注册给 `serial_screenshot_set_target`，第 4 步才成立。
- `--register` 会改 `main/demo.h`、`main/CMakeLists.txt`、`main/main.c`：加
  `DEMOS[]` 条目、对应的**按位置索引**的 `s_ok[]`（漏赋值会显示 `[FAIL]` 并禁止
  进入）、`DEMO_COUNT` 为奇数时把吉祥物挪进网格空格、以及按名字是否含非 ASCII
  选择菜单标签字体。

## 文件

| 文件 | 职责 |
| --- | --- |
| `layout.py` | 主题常量与原型展开——几何只在这里计算 |
| `render.py` | 布局 → PNG（RGB565 量化、真字体文件、标定过的基线） |
| `gen_page.py` | 布局 → `main/demo_<page>.c`，外加 `--register` |
| `diff_capture.py` | 渲染图 vs 真机截图 → 不一致率、密度图、颜色对、行带 |
| `pages/*.json` | 页面描述 |

文字基线带一个**实测**的每字面校正量（`layout.FACES` 里的 `dy_corr`），由真机截图
标定，与字面主值 `.ofs_y`（12px 为 -2、24px 为 -4）一致。换字体后用
`diff_capture.py` 重新标定。

## 数据页

带 `"data"` 节的页面是活的。v1 内置一个适配器:

```json
"data":   { "kind": "glm_quota", "poll_ms": 300000 },
"samples": { "w5.pct": 17, "w5.theo": 20, "w5.reset": "13:19", ... }
```

`glm_quota` **设备直连**智谱配额端点(HTTPS,key 来自 net_config.h,默认证书包
校验),归一化两个窗口并在 SNTP 对时后于设备端算理论节奏——不经过电脑,电脑关机
也能取数。占位符(`{{w5.pct}}` 等)把控件绑定到适配器;`samples` 只用于预览,
不进固件。

2026-09-16 真机端到端验证:TLS 握手与证书链校验通过、端点返回 200,渲染出的
进度条与预估刻度线同 PC 侧代理逐像素一致。过程中沉淀了两条固件经验:92KB 截屏
缓冲改为**懒分配**(拍时取、拍完还)——常驻会把空闲堆压到 13.7KB,mbedtls 直接
失败;以及**不用 WIFI_PS_NONE**——它什么都没治好(超时是堆不足的症状),反而
与手持设备时出现的幽灵按键相关。

## 尚未实现

行动作与子页面、NVS 持久化、glm_quota 之外的适配器,以及把 `diff_capture.py`
接进 CI。局域网版余额页仍手写;迁移它意味着在两条数据路径里二选一。
