"""kurulum/yangin-kamera.ico dosyasını çizer (depoda ikili çizim tutulmasın diye): koyu zemin üstünde kırmızı alev ve
içinde turuncu çekirdek. Panelin renkleriyle aynıdır (--ray #17110f, --vurgu #e0260f, --alev #ffa41f).

  python kurulum/simge.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024  # büyük çizilip küçültülür: kenarlar yumuşak olsun


def bezier(p0, p1, p2, p3, n=40):
    """Üçüncü derece Bézier eğrisinin noktaları."""
    out = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def alev(cx, ust, alt, en):
    """Damla biçiminde alev: sivri tepe, yuvarlak taban, sol yanda küçük bir dil."""
    y = alt - ust
    sag = bezier((cx + 0.06 * en, ust), (cx + 0.10 * en, ust + 0.34 * y), (cx + 0.98 * en, ust + 0.50 * y), (cx + 0.50 * en, alt - 0.12 * y))
    taban = bezier((cx + 0.50 * en, alt - 0.12 * y), (cx + 0.30 * en, alt + 0.03 * y), (cx - 0.30 * en, alt + 0.03 * y), (cx - 0.50 * en, alt - 0.12 * y))
    sol = bezier((cx - 0.50 * en, alt - 0.12 * y), (cx - 0.82 * en, ust + 0.62 * y), (cx - 0.52 * en, ust + 0.44 * y), (cx - 0.40 * en, ust + 0.30 * y))
    dil = bezier((cx - 0.40 * en, ust + 0.30 * y), (cx - 0.34 * en, ust + 0.46 * y), (cx - 0.22 * en, ust + 0.54 * y), (cx - 0.10 * en, ust + 0.56 * y))
    ic = bezier((cx - 0.10 * en, ust + 0.56 * y), (cx - 0.22 * en, ust + 0.34 * y), (cx - 0.10 * en, ust + 0.14 * y), (cx + 0.06 * en, ust))
    return sag + taban + sol + dil + ic


img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((32, 32, S - 32, S - 32), radius=224, fill=(23, 17, 15))
d.polygon(alev(S // 2, 150, 880, 560), fill=(224, 38, 15))
d.polygon(alev(S // 2 + 6, 500, 850, 300), fill=(255, 164, 31))

out = Path(__file__).with_name("yangin-kamera.ico")
img.resize((256, 256), Image.LANCZOS).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
