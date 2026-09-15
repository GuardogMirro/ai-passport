#pragma once

#include "lvgl.h"

// 安装 FAP_SCREENSHOT_V1 串口截屏服务(只读观测,不影响 UI)。
void serial_screenshot_init(void);

// 指定截屏目标对象(尺寸须不超过缓冲);NULL=当前整屏。
void serial_screenshot_set_target(lv_obj_t *target);
