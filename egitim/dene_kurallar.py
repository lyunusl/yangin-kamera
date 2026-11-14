"""Yangın kurallarını (motor/yangin_motor/kural.py) yapay tespit dizileriyle sınar; model ve Studio gerekmez.

  python egitim/dene_kurallar.py

Her durum bir tespit dizisidir (saniyede iki analiz, gerçekteki gibi) ve her kural için bir beklenti taşır:
"var" = en az bir olay başlamalı, "yok" = hiç olay başlamamalı (yanlış alarm denetimi). Ardından zamanlama, kapanma,
bölge ve risk puanı denetimleri gelir. Sonuç sayıları motor/yangin_motor/sinama.py dosyasına yazılır; panel bunları
Kurallar ekranında gösterir.

Bu sınama kural mantığını ölçer, modeli değil: tespitler elle üretilmiştir.
"""
import datetime as dt
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kok = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(kok / "motor"))

from yangin_motor import katalog, kural  # noqa: E402

katalog.eksik_modeller = lambda klasor=None: {}  # kurallar model dosyası olmadan da sınanır

W, H = 1000, 600
BAS = dt.datetime(2026, 1, 5, 9, 0, 0)
KURALLAR = [k["kod"] for k in katalog.KURALLAR]
sonuc: list[tuple[str, bool]] = []


def denetle(ad, kosul):
    sonuc.append((ad, bool(kosul)))
    print(("  geçti  " if kosul else "  KALDI  ") + ad, flush=True)


def kutu(s, cx, cy, w, h, p=0.6):
    return {"s": s, "b": [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], "p": p}


def alev(cx=500, cy=400, w=60, h=80, p=0.6):
    return kutu("alev", cx, cy, w, h, p)


def duman(cx=500, cy=200, w=200, h=150, p=0.4):
    return kutu("duman", cx, cy, w, h, p)


def kos(ayar, dizi, sure, adim=0.5):
    """`dizi(t)` → o andaki tespitler (None: o anda analiz yok). Dönüş: (başlayan kayıtlar, biten kayıtlar, motor).
    Her kayda olayın başladığı an ("an") eklenir."""
    motor = kural.Motor(ayar, W, H, BAS)
    baslayan, biten = [], []
    n = 0
    while n * adim <= sure + 1e-9:
        t = round(n * adim, 3)
        n += 1
        tespitler = dizi(t)
        if tespitler is None:
            continue
        r = motor.adim(t, tespitler, True)
        baslayan += [{**o, "an": t} for o in r["baslayan"]]
        biten += [{**o, "an": t} for o in r["biten"]]
        # aradaki (analiz edilmeyen) görüntü karesi: yalnızca zaman ilerler, yeni olay çıkmamalı
        ara = motor.adim(t + adim / 2, tespitler, False)
        assert not ara["baslayan"] and not ara["biten"]
    return baslayan, biten, motor


TUM = {"bolgeler": []}
KARE = lambda x1, y1, x2, y2: [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]  # noqa: E731
KRITIK = {"bolgeler": [{"ad": "Elektrik odası", "tur": "kritik", "poly": KARE(0.6, 0.5, 1.0, 1.0)}]}
IZINLI = {"bolgeler": [{"ad": "Kaynak tezgâhı", "tur": "izinli", "poly": KARE(0.0, 0.5, 0.4, 1.0)}]}
buyuyen = lambda s, t, kat, sn: (1 + (kat - 1) * min(1.0, t / sn)) ** 0.5  # noqa: E731  (kenar çarpanı: alan `sn` saniyede `kat` katına çıkar)

# (ad, ayar, dizi, süre, {kural: "var" | "yok"})
DURUMLAR = [
    ("sürekli alev", TUM, lambda t: [alev()], 10,
     {"alev": "var", "duman": "yok", "alev_duman": "yok", "alev_buyuyor": "yok", "duman_yayiliyor": "yok"}),
    ("tek karede alev (gürültü)", TUM, lambda t: [alev(p=0.9)] if t == 3.0 else [], 10, {k: "yok" for k in KURALLAR}),
    ("iki ayrı karede alev (gürültü)", TUM, lambda t: [alev()] if t in (2.0, 5.0) else [], 10, {k: "yok" for k in KURALLAR}),
    ("seyrek alev (karelerin %40'ı)", TUM, lambda t: [alev()] if int(round(t * 2)) % 5 in (0, 3) else [], 12, {"alev": "yok", "alev_buyuyor": "yok"}),
    ("titreyen alev (üç karede bir kayıp)", TUM, lambda t: [alev()] if int(round(t * 2)) % 3 else [], 12, {"alev": "var", "duman": "yok"}),
    ("alanı oynayan alev (±%20)", TUM, lambda t: [alev(w=60 * (1.1 if int(round(t * 2)) % 2 else 0.9))], 14, {"alev": "var", "alev_buyuyor": "yok"}),
    ("sürekli duman", TUM, lambda t: [duman()], 12,
     {"duman": "var", "alev": "yok", "alev_duman": "yok", "duman_yayiliyor": "yok", "alev_buyuyor": "yok"}),
    ("iki saniyelik duman", TUM, lambda t: [duman()] if t <= 2.0 else [], 12, {"duman": "yok", "duman_yayiliyor": "yok"}),
    ("alev ve duman birlikte", TUM, lambda t: [alev(), duman()], 12, {"alev": "var", "duman": "var", "alev_duman": "var"}),
    ("alev sürekli, duman tek karede", TUM, lambda t: [alev()] + ([duman()] if t == 4.0 else []), 12, {"alev": "var", "duman": "yok", "alev_duman": "yok"}),
    ("büyüyen alev (6 sn'de 4 kat)", TUM, lambda t: [alev(w=60 * buyuyen("a", t, 4, 6), h=80 * buyuyen("a", t, 4, 6))], 12,
     {"alev": "var", "alev_buyuyor": "var", "duman_yayiliyor": "yok"}),
    ("yavaş büyüyen alev (30 sn'de 2 kat)", TUM, lambda t: [alev(w=60 * buyuyen("a", t, 2, 30), h=80 * buyuyen("a", t, 2, 30))], 30,
     {"alev": "var", "alev_buyuyor": "yok"}),
    ("yayılan duman (10 sn'de 3 kat)", TUM, lambda t: [duman(w=200 * buyuyen("d", t, 3, 10), h=150 * buyuyen("d", t, 3, 10))], 16,
     {"duman": "var", "duman_yayiliyor": "var", "alev_buyuyor": "yok"}),
    ("kritik bölgede alev", KRITIK, lambda t: [alev(cx=800, cy=450)], 8, {"kritik_bolge": "var", "alev": "var"}),
    ("kritik bölgede duman", KRITIK, lambda t: [duman(cx=800, cy=400)], 8, {"kritik_bolge": "var", "duman": "var", "alev": "yok"}),
    ("kritik bölgenin dışında alev", KRITIK, lambda t: [alev(cx=200, cy=450)], 8, {"kritik_bolge": "yok", "alev": "var"}),
    ("kritik bölgede tek karede alev", KRITIK, lambda t: [alev(cx=800, cy=450)] if t == 2.0 else [], 8, {"kritik_bolge": "yok", "alev": "yok"}),
    ("izinli ateş bölgesinde alev", IZINLI, lambda t: [alev(cx=200, cy=450), duman(cx=200, cy=400)], 12, {k: "yok" for k in KURALLAR}),
    ("izinli bölgede alev, dışarıda duman", IZINLI, lambda t: [alev(cx=200, cy=450), duman(cx=700, cy=200)], 12,
     {"alev": "yok", "duman": "var", "alev_duman": "yok"}),
    ("akış kesintisi: birer saniyelik iki alev", TUM, lambda t: [alev()] if t <= 1.0 or 11.0 <= t <= 12.0 else (None if t < 11.0 else []), 12, {"alev": "yok"}),
]

print("Durumlar")
sayim = {k: {"yakalanan": 0, "beklenen": 0, "yanlis": 0, "denetim": 0} for k in KURALLAR}
for ad, ayar, dizi, sure, beklenti in DURUMLAR:
    baslayan, _, _ = kos(ayar, dizi, sure)
    gorulen = {o["kural"] for o in baslayan}
    for k, b in beklenti.items():
        if k not in {x["kod"] for x in katalog.coz(ayar)}:
            continue  # bu ayarda değerlendirilmeyen kural (ör. kritik bölge çizilmemiş)
        if b == "var":
            sayim[k]["beklenen"] += 1
            sayim[k]["yakalanan"] += k in gorulen
        else:
            sayim[k]["denetim"] += 1
            sayim[k]["yanlis"] += k in gorulen
        denetle(f"{ad}: {katalog.KURAL[k]['ad']} {'başlar' if b == 'var' else 'başlamaz'}", (k in gorulen) == (b == "var"))

print("Zamanlama")
b, _, _ = kos(TUM, lambda t: [alev()], 10)
o = next(x for x in b if x["kural"] == "alev")
denetle("alev: izlemenin ilk 2 saniyesi dolmadan başlamaz", o["an"] == 2.0 and o["bas"] == 0.0 and len([x for x in b if x["kural"] == "alev"]) == 1)
b, _, _ = kos(TUM, lambda t: [duman()], 12)
denetle("duman: izlemenin ilk 4 saniyesi dolmadan başlamaz", next(x for x in b if x["kural"] == "duman")["an"] == 4.0)
b, _, _ = kos(KRITIK, lambda t: [alev(cx=800, cy=450)], 8)
an = {x["kural"]: x["an"] for x in b}
denetle("kritik bölge: 1 sn'de, alev kuralından önce başlar", an["kritik_bolge"] == 1.0 and an["alev"] == 2.0)
denetle("kritik bölge olayı bölgenin adını taşır", next(x for x in b if x["kural"] == "kritik_bolge")["bolge"] == "Elektrik odası")
b, _, _ = kos(TUM, lambda t: [alev()], 10, adim=0.52)
denetle("25 kare/sn videodaki analiz aralığında (0,52 sn) alev en geç 2,6 sn'de başlar", 2.0 <= next(x for x in b if x["kural"] == "alev")["an"] <= 2.6)
b, _, _ = kos(TUM, lambda t: [alev()], 10, adim=1.0)
denetle("yavaş bilgisayarda (saniyede bir analiz) alev yine başlar", any(x["kural"] == "alev" and x["an"] <= 3.0 for x in b))
b, _, _ = kos({"bolgeler": [], "kurallar": [{"kod": "alev", "sure_sn": 5}]}, lambda t: [alev(), duman()], 12)
denetle("kameranın ayarındaki süre geçerlidir; kapalı kural olay üretmez", [(x["kural"], x["an"]) for x in b] == [("alev", 5.0)])
b, _, _ = kos(TUM, lambda t: [alev()] if int(round(t * 2)) % 3 else [], 30)
denetle("titreyen alev tek olay olarak sürer (yanıp sönmez)", len([x for x in b if x["kural"] == "alev"]) == 1)

print("Kapanma")
b, s, _ = kos(TUM, lambda t: [alev()] if t <= 6.0 or 20.0 <= t <= 26.0 else [], 34)
alevler = [x for x in b if x["kural"] == "alev"]
kapanan = [x for x in s if x["kural"] == "alev"]
denetle("alev bitince olay kısa bir tutma süresinden sonra kapanır", len(kapanan) == 2 and 8.0 <= kapanan[0]["an"] <= 12.0 and kapanan[0]["bitti"] is True)
denetle("kapanan olayın süresi alevin göründüğü süreye yakındır", 6.0 <= kapanan[0]["sure_sn"] <= 8.0)
denetle("alev yeniden görülürse yeni bir olay başlar", len(alevler) == 2 and alevler[0]["kimlik"] != alevler[1]["kimlik"])
denetle("izleme sürerken alev, 2 sn'lik pencerenin %60'ını doldurunca (üç analiz, 1 sn) başlar", alevler[1]["an"] == 21.0 and alevler[1]["bas"] == 20.0)
_, _, m = kos(TUM, lambda t: [alev()], 6)
kalan = m.kapat()
denetle("akış bitince açık olay kapanış kaydı bırakır", [x["kural"] for x in kalan] == ["alev"] and kalan[0]["bitti"] and not m.acik)

print("Risk puanı ve kayıt alanları")
b, _, m = kos(TUM, lambda t: [alev(p=0.71), duman()], 40)
ilk = {x["kural"]: x for x in b}
denetle("alev kritik, duman yüksek düzeydedir", ilk["alev"]["duzey"] == "kritik" and ilk["alev"]["ciddi"] == 1 and ilk["duman"]["duzey"] == "yuksek" and ilk["duman"]["ciddi"] == 0)
denetle("alev ve duman birlikte: risk puanı tek başına alevden ve dumandan yüksek", ilk["alev_duman"]["puan"] == 25 > ilk["alev"]["puan"] == 15 > ilk["duman"]["puan"] == 12)
son = {x["kural"]: x for x in m.adim(40.5, [alev(), duman()], True)["suren"]}
denetle("olay sürdükçe risk puanı artar", son["alev"]["puan"] == 25 and son["duman"]["puan"] == 20 and son["alev"]["sure_sn"] >= 40)
denetle("olayın konumu tespitin ortasıdır", abs(ilk["alev"]["x"] - 0.5) < 0.01 and abs(ilk["alev"]["y"] - 400 / 600) < 0.01)
denetle("olayın zamanı alevin ilk görüldüğü andır", ilk["alev"]["zaman"] == "2026-01-05T09:00:00" and ilk["alev_duman"]["zaman"] == "2026-01-05T09:00:00")
denetle("açıklamada en yüksek güven yazar", "%71" in ilk["alev"]["aciklama"])
b, _, _ = kos(TUM, lambda t: [alev(w=60 * buyuyen("a", t, 4, 6), h=80 * buyuyen("a", t, 4, 6))], 12)
o = next(x for x in b if x["kural"] == "alev_buyuyor")
denetle("alev büyüyor: büyüme katı açıklamada yazar, olay 10 sn dolmadan başlayabilir", "katına çıktı" in o["aciklama"] and o["an"] < 10.0)

print("Bölgeler ve ölçüm")
_, _, m = kos(IZINLI, lambda t: [alev(cx=200, cy=450), alev(cx=700, cy=300)], 3)
isaretler = sorted((d["izinli"], round(d["m"][0])) for d in m.son["tespitler"])
denetle("izinli bölgedeki tespit işaretlenir, dışarıdaki sayılır", isaretler == [(False, 700), (True, 200)] and [x["kural"] for x in m.acik.values()] == ["alev"])
o = m.olcum()
izgara = o["izgara"]
denetle("ölçüm: analiz sayısı, alev süresi ve ısı haritası yalnızca sayılan tespitlerden", o["analiz"] == 7 and 3.0 <= o["alev_sn"] <= 3.5 and o["duman_sn"] == 0
        and izgara["alev"][9][22] > 0 and izgara["alev"][13][6] == 0 and (izgara["gen"], izgara["yuk"]) == (32, 18))
denetle("ölçüm okununca sayaçlar sıfırlanır", m.olcum() is None)

print("Hassasiyet")
denetle("orta: alev 0,30 / duman 0,20 (varsayılan)", katalog.esikler({}) == {"alev": 0.30, "duman": 0.20} == katalog.esikler({"hassasiyet": "orta"}))
denetle("düşük: alev 0,45 / duman 0,30 · yüksek: alev 0,20 / duman 0,15",
        katalog.esikler({"hassasiyet": "dusuk"}) == {"alev": 0.45, "duman": 0.30} and katalog.esikler({"hassasiyet": "yuksek"}) == {"alev": 0.20, "duman": 0.15})

# ---------------------------------------------------------------- sonuç dosyası
satirlar = [f'    "{k}": {{"yakalanan": {v["yakalanan"]}, "beklenen": {v["beklenen"]}, "yanlis": {v["yanlis"]}, "denetim": {v["denetim"]}}},' for k, v in sayim.items()]
(kok / "motor" / "yangin_motor" / "sinama.py").write_text(
    '"""Kural sınamalarının sonucu. Bu dosyayı egitim/dene_kurallar.py yazar; elle değiştirmeyin.\n\n'
    "yakalanan/beklenen: durumun bulunduğu yapay tespit dizilerinden kaçında olay başladı · yanlis/denetim: durumun\n"
    'bulunmadığı dizilerden kaçında yanlış olay başladı. Tespitler elle üretilmiştir; model bu sınamada çalışmaz.\n"""\n'
    "SINAMA = {\n" + "\n".join(satirlar) + "\n}\n", encoding="utf-8", newline="\n")

kalan = [ad for ad, ok in sonuc if not ok]
print(f"\n{len(sonuc) - len(kalan)}/{len(sonuc)} denetim geçti" + (f" · kalanlar: {kalan}" if kalan else ""))
sys.exit(1 if kalan else 0)
