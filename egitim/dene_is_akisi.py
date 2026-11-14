"""Panelin Studio işlerinin (video analizi, canlı izleme) kapanış kurallarını Studio olmadan sınar.

  python egitim/dene_is_akisi.py

Studio çağrıları sahte işlevlerle değiştirilir; veri klasörü geçicidir. Denetlenenler:
  - aynı koşunun hata kaydı "bitti"den önce de sonra da işi hatayla bitirir; başka koşunun kaydı sayılmaz ve üstüne yazmaz
  - sahnenin durduğu doğrulanamazsa ya da kuyruk boşalmazsa iş hatayla biter, açık olay ve yarım klip temizliği yapılmaz
  - kuyruk bekleyicisi, klip dönüştürme içeri alma kilidini tutarken de süresini aşmadan False döner
  - Yangın Kurallar, Bitti=True geldiğinde (motor kurulmamış olsa da) görüntü çıkışını boş bırakır
"""
import asyncio
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kok = Path(__file__).resolve().parent.parent
os.environ["YANGIN_KAMERA_VERI"] = tempfile.mkdtemp(prefix="yangin_is_akisi_")
sys.path.insert(0, str(kok))
sys.path.insert(0, str(kok / "motor"))

import numpy as np  # noqa: E402

import kamera  # noqa: E402
import kuyruk  # noqa: E402
import studio  # noqa: E402
import uygulama  # noqa: E402
from yangin_motor import blok  # noqa: E402

KOD, KOSU = "dnm", "k1"
sonuc: list[tuple[str, bool]] = []
gercek_bosalsin = kuyruk.bosalsin


class _Zaman:  # uygulama içindeki beklemeler atlanır
    def __getattr__(self, ad):
        return getattr(time, ad)

    def sleep(self, _):
        pass


uygulama.time = _Zaman()
uygulama.ayar_oku = lambda kod: {"ad": "Deneme", "kod": kod, "kamera": {"tur": "rtsp", "adres": "x"}}
kamera.kaynak = lambda ayar, sifre: ("rtsp://ornek", "rtsp://ornek")


def kur(*, bitti=True, hata=None, gec_hata=None, eski_hata=None, durdur_hatasi=False, bosalir=True):
    """Sahte Studio: `hata` çalışırken, `gec_hata` sahne durdurulurken (bitti'den sonra) gelen bu koşunun hata kaydı;
    `eski_hata` önceki koşudan kalan, sonradan işlenen kayıt."""
    temizlik = []

    async def sahne_kur(kod, ayar):
        return {}

    async def yeni_kosu(bilgi, kod):
        return KOSU

    async def calistir(bilgi, sure_ms=None):
        if hata:
            kuyruk.HATALAR.setdefault(KOD, {})[KOSU] = hata
        if eski_hata:
            kuyruk.HATALAR.setdefault(KOD, {})["eski"] = eski_hata
        if bitti:
            kuyruk.BITENLER.setdefault(KOD, {})[KOSU] = time.time()
        return {}

    async def durdur(bilgi):
        if gec_hata:
            kuyruk.HATALAR.setdefault(KOD, {})[KOSU] = gec_hata
        if durdur_hatasi:
            raise studio.StudioHatasi("bağlantı koptu")

    async def kamera_adresi(bilgi, adres):
        return None

    studio.sahne_kur, studio.yeni_kosu, studio.calistir, studio.durdur, studio.kamera_adresi = sahne_kur, yeni_kosu, calistir, durdur, kamera_adresi
    kuyruk.bosalsin = lambda kod, *a, **k: bosalir
    uygulama._acik_olaylari_kapat = lambda kod: temizlik.append(kod)
    kuyruk.BITENLER.clear()
    kuyruk.HATALAR.clear()
    return temizlik


def kos(islev, *arg):
    """(sonuç: "tamam" ya da hata metni)"""
    try:
        islev(*arg)
        return "tamam"
    except SystemExit as e:
        return str(e)


def denetle(ad, kosul):
    sonuc.append((ad, bool(kosul)))
    print(("  geçti  " if kosul else "  KALDI  ") + ad, flush=True)


def video(**k):
    temizlik = kur(**k)
    return kos(uygulama.studioda_analiz, uygulama.Is("video", "deneme"), KOD), temizlik


def izle(dur=True, **k):
    temizlik = kur(bitti=False, **k)
    is_ = uygulama.Is("izle", "deneme")
    if dur:
        is_.dur.set()
    return kos(uygulama.is_izle, is_, KOD, None, 1.0), temizlik


print("Video analizi")
r, t = video()
denetle("olağan bitiş: iş başarılı, temizlik yapılmaz", r == "tamam" and not t)
r, t = video(hata="model yok")
denetle("çalışırken gelen hata: iş hatalı, temizlik yapılır", "tespit çalışmıyor" in r and t == [KOD])
r, t = video(gec_hata="model yok")
denetle("bitti'den sonra işlenen aynı koşu hatası: iş hatalı", "tespit çalışmıyor" in r and t == [KOD])
r, t = video(eski_hata="eski koşu")
denetle("önceki koşunun geç hatası: iş başarılı", r == "tamam" and not t)
r, t = video(hata="güncel", eski_hata="eski koşu")
denetle("önceki koşunun kaydı güncel koşunun hatasını ezmez", "(güncel)" in r)
r, t = video(durdur_hatasi=True)
denetle("durdurma doğrulanamadı: iş hatalı, temizlik atlanır", "doğrulanamadı" in r and not t)
r, t = video(bosalir=False)
denetle("kuyruk boşalmadı: iş hatalı, temizlik atlanır", "kuyruk boşalmadı" in r and not t)
r, t = video(hata="model yok", durdur_hatasi=True)
denetle("hata + durdurma doğrulanamadı: asıl hata bildirilir, temizlik atlanır", "tespit çalışmıyor" in r and not t)
r, t = video(hata="model yok", bosalir=False)
denetle("hata + kuyruk boşalmadı: asıl hata bildirilir, temizlik atlanır", "tespit çalışmıyor" in r and not t)

print("Canlı izleme")
r, t = izle()
denetle("durdurma: iş başarılı, açık olaylar kapatılır", r == "tamam" and t == [KOD])
r, t = izle(durdur_hatasi=True)
denetle("durdurma doğrulanamadı: iş hatalı, temizlik atlanır", "doğrulanamadı" in r and not t)
r, t = izle(bosalir=False)
denetle("kuyruk boşalmadı: iş hatalı, temizlik atlanır", "kuyruk boşalmadı" in r and not t)
r, t = izle(dur=False, hata="model yok")
denetle("çalışırken gelen hata: iş hatalı, temizlik yapılır", "tespit çalışmıyor" in r and t == [KOD])
r, t = izle(gec_hata="model yok")
denetle("durdururken işlenen hata: iş hatalı", "tespit çalışmıyor" in r)
r, t = izle(dur=False, hata="model yok", durdur_hatasi=True)
denetle("hata + durdurma doğrulanamadı: asıl hata bildirilir, temizlik atlanır", "tespit çalışmıyor" in r and not t)

print("Kuyruk bekleyicisi (gerçek işlev, içeri alma kilidi tutulurken)")


def kilitliyken(islev, tut_sn=1.2):
    """`islev`i, başka bir iş parçacığı içeri alma kilidini `tut_sn` saniye tutarken çalıştırır. Dönüş: (sonuç, geçen süre)."""
    tutuldu, birak = threading.Event(), threading.Event()

    def tut():
        with kuyruk._KILIT:  # uzun süren klip dönüştürmenin yerine
            tutuldu.set()
            birak.wait(tut_sn)

    t = threading.Thread(target=tut, daemon=True)
    t.start()
    tutuldu.wait(2)
    t0 = time.monotonic()
    try:
        return islev(), time.monotonic() - t0
    finally:
        birak.set()
        t.join()


kuyruk.KLASOR.mkdir(parents=True, exist_ok=True)
r, sure = kilitliyken(lambda: gercek_bosalsin(KOD, en_cok=0.1))
denetle(f"kilit tutulurken en_cok=0,1 sn: False, {sure:.2f} sn içinde döndü", r is False and sure < 0.3)
t0 = time.monotonic()
r = gercek_bosalsin(KOD, en_cok=1.0, sakin=0.3)
denetle("boş kuyruk, kilit boşta: True", r is True and time.monotonic() - t0 < 1.0)
(kuyruk.KLASOR / f"00000000000000000001_{KOD}_00001.json").write_text("{bozuk", encoding="utf-8")
t0 = time.monotonic()
r = gercek_bosalsin(KOD, en_cok=0.5, sakin=0.2)
denetle("işlenmemiş kayıt varken süre dolunca False", r is False and 0.45 <= time.monotonic() - t0 < 0.9)
(kuyruk.KLASOR / f"00000000000000000001_{KOD}_00001.json").unlink()

kuyruk.BOSALMA_SN = 0.2  # iki akış gerçek bekleyiciyle: kilit bırakılmadan süre dolar
temizlik = kur()
kuyruk.bosalsin = gercek_bosalsin
r, sure = kilitliyken(lambda: kos(uygulama.studioda_analiz, uygulama.Is("video", "deneme"), KOD))
denetle(f"video, kilit tutulurken: iş hatalı, temizlik atlanır ({sure:.2f} sn)", "kuyruk boşalmadı" in r and not temizlik and sure < 0.8)
temizlik = kur(bitti=False)
kuyruk.bosalsin = gercek_bosalsin
is_ = uygulama.Is("izle", "deneme")
is_.dur.set()
r, sure = kilitliyken(lambda: kos(uygulama.is_izle, is_, KOD, None, 1.0))
denetle(f"canlı izleme, kilit tutulurken: iş hatalı, temizlik atlanır ({sure:.2f} sn)", "kuyruk boşalmadı" in r and not temizlik and sure < 0.8)
kuyruk.BOSALMA_SN = 300.0

print("Kuyruk kayıtları")
kuyruk.HATALAR.clear()
kuyruk.HATALAR[KOD] = {"": "numarasız"}
denetle("numarasız kayıt numaralı koşuya sayılmaz", kuyruk.kosu_hatasi(KOD, KOSU) is None and kuyruk.kosu_hatasi(KOD) == "numarasız")
kuyruk.HATALAR[KOD] = {KOSU: "güncel"}
kuyruk.HATALAR[KOD]["eski"] = "eski"
denetle("sonradan gelen eski koşu kaydı güncel kaydı ezmez", kuyruk.kosu_hatasi(KOD, KOSU) == "güncel" and kuyruk.kosu_hatasi(KOD, "baska") is None)

# Sahnenin (arayüzsüz Studio sürecinin) durdurulması egitim/dene_arayuzsuz.py'de sınanır.

print("Yangın Kurallar: Bitti=True")
kare = np.full((120, 160, 3), 90, np.uint8)
cikis = blok.kurallar({}, kare, "[]", "dnm#1", 0.0, True)
denetle("motor kurulmamışken dolu girişle: görüntü çıkışı boş", cikis[0] is None and cikis[1] is False)

kalan = [ad for ad, ok in sonuc if not ok]
print(f"\n{len(sonuc) - len(kalan)}/{len(sonuc)} denetim geçti" + (f" · kalanlar: {kalan}" if kalan else ""))
sys.exit(1 if kalan else 0)
