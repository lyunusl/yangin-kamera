"""Yangın modelini (düz ONNX) motorun kendi tespit koduyla iki sınama görselinde çalıştırır.

  python egitim/dene_model.py

motor/modeller/yangin-duman-512.onnx gerekir (depoda tutulmaz). Görseller yapay zekâ ile üretilmiştir
(egitim/gorseller/alev.png, duman.png); bu sınama modelin gerçek kamera görüntüsündeki başarısını ölçmez.
Denetlenenler: modelin giriş ve çıkış biçimi, ön işleme, beklenen kutular, sıfır boyutlu sahte kutuların atılması,
hassasiyet eşikleri.
"""
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kok = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(kok / "motor"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from yangin_motor import algila, katalog  # noqa: E402

MODEL = kok / "motor" / "modeller" / katalog.MODEL_DOSYASI
if not MODEL.is_file():
    raise SystemExit(f"Düz model dosyası yok: {MODEL}")
sonuc: list[tuple[str, bool]] = []


def denetle(ad, kosul):
    sonuc.append((ad, bool(kosul)))
    print(("  geçti  " if kosul else "  KALDI  ") + ad, flush=True)


def oku(ad):
    return cv2.imdecode(np.fromfile(str(kok / "egitim" / "gorseller" / ad), np.uint8), cv2.IMREAD_COLOR)


def yaz(ad, tespitler):
    print(f"  {ad}: " + (", ".join(f"{d['s']} %{round(100 * d['p'])} [{d['b'][0]:.0f},{d['b'][1]:.0f} – {d['b'][2]:.0f},{d['b'][3]:.0f}]" for d in tespitler) or "tespit yok"))


print("Model")
a = algila.Algilayici(str(MODEL))
g, c = a.oturum.get_inputs()[0], a.oturum.get_outputs()[0]
denetle("giriş: goruntu float32 [1, 3, 512, 512]", (g.name, list(g.shape), g.type) == ("goruntu", [1, 3, 512, 512], "tensor(float)"))
denetle("çıkış: tespit float32 [1, 16128, 7]", (c.name, list(c.shape), c.type) == ("tespit", [1, 16128, 7], "tensor(float)"))
duman, alev = oku("duman.png"), oku("alev.png")
x = algila.on_isle(alev)
denetle("ön işleme: 512×512, RGB, 0-1, oran korunmadan", x.shape == (1, 3, 512, 512) and x.dtype == np.float32 and 0.0 <= x.min() and x.max() <= 1.0
        and np.allclose(x[0, :, 0, 0], cv2.resize(alev, (512, 512), interpolation=cv2.INTER_LINEAR)[0, 0, ::-1] / 255.0))

print("Duman görseli (1344×752)")
t0 = time.perf_counter()
d = a.calistir(duman, katalog.esikler({}))
sure = time.perf_counter() - t0
yaz("varsayılan eşikler", d)
denetle("tek duman kutusu, güveni %50-60", len(d) == 1 and d[0]["s"] == "duman" and 0.50 <= d[0]["p"] <= 0.60)
denetle("kutu görüntünün üst yarısındaki duman bulutunu kaplar", d and d[0]["b"][0] < 450 and d[0]["b"][2] > 1000 and d[0]["b"][3] < 400)

print("Alev görseli (1344×752)")
d = a.calistir(alev, katalog.esikler({}))
yaz("varsayılan eşikler", d)
alevler = [x for x in d if x["s"] == "alev"]
denetle("varsayılan eşiklerde yalnızca alev kutusu, güveni %25-45", len(d) == len(alevler) == 1 and 0.25 <= alevler[0]["p"] <= 0.45)
denetle("alev kutusu beklenen yerde (x 540-585, y 360-445)", alevler and 540 <= alevler[0]["b"][0] and alevler[0]["b"][2] <= 585
        and 360 <= alevler[0]["b"][1] and alevler[0]["b"][3] <= 445)
y = a.calistir(alev, katalog.esikler({"hassasiyet": "yuksek"}))
yaz("yüksek hassasiyet", y)
dumanlar = [x for x in y if x["s"] == "duman"]
denetle("yüksek hassasiyette alevin üstündeki duman da bulunur", len(dumanlar) == 1 and dumanlar[0]["b"][1] < alevler[0]["b"][1]
        and dumanlar[0]["b"][0] < alevler[0]["b"][2] and dumanlar[0]["b"][2] > alevler[0]["b"][0])
denetle("yüksek hassasiyet daha çok, düşük hassasiyet daha az kutu verir", len(y) > len(d) and a.calistir(alev, katalog.esikler({"hassasiyet": "dusuk"})) == [])

print("Sıfır boyutlu sahte kutular")
ham = a.oturum.run(None, {a.girdi: x})[0][0]
puan = (ham[:, 5:7] * ham[:, 4:5]).max(1)
kucuk = (ham[:, 2] * alev.shape[1] < algila.EN_AZ_KENAR) | (ham[:, 3] * alev.shape[0] < algila.EN_AZ_KENAR)
print(f"  ham çıkışta güveni %30'u geçen {int((puan >= 0.3).sum())} adaydan {int(((puan >= 0.3) & kucuk).sum())} tanesi 6 pikselden küçük")
denetle("model bu görselde küçük sahte kutular üretiyor (süzgecin sınandığı durum)", ((puan >= 0.3) & kucuk).any())
hepsi = a.calistir(alev, {"alev": 0.05, "duman": 0.05})
denetle("eni ya da boyu 6 pikselden küçük kutu hiçbir eşikte çıkmaz", hepsi and all(k["b"][2] - k["b"][0] >= 6 and k["b"][3] - k["b"][1] >= 6 for k in hepsi))
denetle("kutular kare sınırları içinde ve güvene göre sıralı", all(0 <= k["b"][0] < k["b"][2] <= alev.shape[1] and 0 <= k["b"][1] < k["b"][3] <= alev.shape[0] for k in hepsi)
        and [k["p"] for k in hepsi] == sorted((k["p"] for k in hepsi), reverse=True))
denetle("boş (siyah) karede tespit yok", a.calistir(np.zeros((360, 640, 3), np.uint8)) == [])
print(f"  bir analiz: {1000 * sure:.0f} ms ({a.ozet()})")

kalan = [ad for ad, ok in sonuc if not ok]
print(f"\n{len(sonuc) - len(kalan)}/{len(sonuc)} denetim geçti" + (f" · kalanlar: {kalan}" if kalan else ""))
sys.exit(1 if kalan else 0)
