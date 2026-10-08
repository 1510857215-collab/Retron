# -*- coding: utf-8 -*-
"""生成 Retron 应用图标（icon.ico）。用 tools/venv-vision 运行（它有 PIL）。"""
import math

from PIL import Image, ImageDraw, ImageFont

SIZE = 512
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

# 渐变背景（深蓝紫 → 近黑）
bg = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
bd = ImageDraw.Draw(bg)
for y in range(SIZE):
    t = y / float(SIZE)
    r = int(27 + (10 - 27) * t)
    g = int(42 + (13 - 42) * t)
    b = int(73 + (19 - 73) * t)
    bd.line([(0, y), (SIZE, y)], fill=(r, g, b, 255))

# 圆角遮罩
mask = Image.new("L", (SIZE, SIZE), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=104, fill=255)
img.paste(bg, (0, 0), mask)

d = ImageDraw.Draw(img)

# 白色六边形（苯环）轮廓
cx, cy, R = SIZE / 2.0, SIZE / 2.0 - 6, SIZE * 0.315
pts = []
for i in range(6):
    ang = math.radians(60 * i - 90)
    pts.append((cx + R * math.cos(ang), cy + R * math.sin(ang)))
d.line(pts + [pts[0]], fill=(233, 236, 244, 255), width=20, joint="curve")

# 中心字母 R
try:
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 200)
except Exception:
    font = ImageFont.load_default()
text = "R"
bbox = d.textbbox((0, 0), text, font=font)
tw = bbox[2] - bbox[0]
th = bbox[3] - bbox[1]
d.text((cx - tw / 2.0 - bbox[0], cy - th / 2.0 - bbox[1]), text,
       font=font, fill=(233, 236, 244, 255))

out = r"C:/Users/zzl/Desktop/hx/shell/icon.ico"
img.save(out, format="ICO",
         sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("icon.ico 生成完成:", out)
