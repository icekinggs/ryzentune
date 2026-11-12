"""Gera recursos/ryzentune.ico (precisa de Pillow). Só é usado quando o ícone muda."""
import os

from PIL import Image, ImageDraw, ImageFont

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
# pinos do chip
for i in range(5):
    p = 58 + i * 35
    for x0, y0, x1, y1 in ((p - 7, 8, p + 7, 40), (p - 7, S - 40, p + 7, S - 8),
                           (8, p - 7, 40, p + 7), (S - 40, p - 7, S - 8, p + 7)):
        d.rounded_rectangle((x0, y0, x1, y1), 4, fill=(180, 186, 196, 255))
# corpo
d.rounded_rectangle((32, 32, S - 32, S - 32), 28, fill=(28, 30, 36, 255), outline=(237, 28, 36, 255), width=10)
# seta de "subir"
d.polygon([(128, 62), (186, 128), (150, 128), (150, 190), (106, 190), (106, 128), (70, 128)],
          fill=(237, 28, 36, 255))
try:
    fonte = ImageFont.truetype("segoeuib.ttf", 34)
    d.text((128, 214), "RT", font=fonte, fill=(255, 255, 255, 0), anchor="mm")
except OSError:
    pass
os.makedirs(os.path.join(RAIZ, "recursos"), exist_ok=True)
img.save(os.path.join(RAIZ, "recursos", "ryzentune.ico"),
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(os.path.join(RAIZ, "recursos", "ryzentune.png"))
print("ok")
