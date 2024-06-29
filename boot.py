# This is script that run when device boot up or wake from sleep.

from machine import Pin
from neopixel import NeoPixel
import time

np = NeoPixel(Pin(8), 1)

# 定义一个函数来设置LED的颜色
def set_color(r, g, b):
    np[0] = (r, g, b)
    np.write()

# 循环显示不同的颜色
set_color(1, 0, 0)  # 红色
