"""Kural kataloğu: alev ve duman tespitlerinden hangi uyarı nasıl çıkar.

Kurallar saniyede yaklaşık iki kez gelen tespitlerle, kayan bir zaman penceresinde değerlendirilir (kural.py); tek bir
gürültülü kare uyarı başlatmaz. Her kuralın bir "mekanizma"sı vardır:

  oran       son `sure_sn` saniyede analiz edilen karelerin en az `oran` kadarında tespit var     (sinif: alev | duman)
  birlikte   aynı pencerede hem alev hem duman için oran koşulu sağlanıyor
  buyume     tespitlerin toplam alanı son `sure_sn` saniye içinde en az `kat` katına çıktı        (sinif)
  bolge      merkezi "kritik bölge" içinde olan alev ya da duman için oran koşulu (bölge başına)

Alanlar:
  duzey  "kritik" | "yuksek": uyarının düzeyi (panelde rozet; kritik uyarı siren çalar)
  onem   1-5: risk puanının çarpanı · taban: olay başlarken olasılık (1-5); olay sürdükçe artar
  durum  "hazir": kural mantığı yapay tespit dizileriyle sınandı · "deneysel": mantık sınandı, modelin kutu alanı
         gerçek görüntüde ölçülmedi · "yok": kapalı. Sınama: egitim/dene_kurallar.py (sonuç sayıları: sinama.py)
"""
from __future__ import annotations

import os
import time

from . import community_model

KATEGORILER = {
    "alev": "Alev",
    "duman": "Duman",
    "bolge": "Bölge",
}

# bölge türleri (kamera ayarında çizilir)
BOLGE_TURLERI = {
    "kritik": "Kritik bölge",
    "izinli": "İzinli ateş bölgesi",
}

SINIF_ADLARI = {"alev": "Alev", "duman": "Duman"}

# kameranın "hassasiyet" ayarı → sınıf başına güven eşiği (model belirgin bir duman sütununa da 0,20-0,38 güven veriyor;
# bu yüzden dumanın eşiği alevinkinden düşüktür)
HASSASIYET = {
    "dusuk": {"alev": 0.45, "duman": 0.30},
    "orta": {"alev": 0.30, "duman": 0.20},
    "yuksek": {"alev": 0.20, "duman": 0.15},
}
HASSASIYET_ADLARI = {"dusuk": "Düşük (az yanlış alarm)", "orta": "Orta", "yuksek": "Yüksek (erken uyarı)"}
VARSAYILAN_HASSASIYET = "orta"

KURALLAR: list[dict] = [
    {"kod": "alev", "ad": "Alev algılandı", "kategori": "alev", "mekanizma": "oran", "sinif": "alev", "duzey": "kritik",
     "onem": 5, "taban": 3, "sure_sn": 2.0, "oran": 0.6, "durum": "hazir",
     "aciklama": "Son saniyelerde analiz edilen karelerin çoğunda alev görüldü."},
    {"kod": "alev_duman", "ad": "Alev ve duman birlikte", "kategori": "alev", "mekanizma": "birlikte", "duzey": "kritik",
     "onem": 5, "taban": 5, "sure_sn": 4.0, "oran": 0.6, "durum": "hazir",
     "aciklama": "Aynı sürede hem alev hem duman görüldü; risk puanı en yüksek uyarıdır."},
    {"kod": "alev_buyuyor", "ad": "Alev büyüyor", "kategori": "alev", "mekanizma": "buyume", "sinif": "alev", "duzey": "kritik",
     "onem": 5, "taban": 4, "sure_sn": 10.0, "kat": 2.0, "durum": "deneysel",
     "aciklama": "Alev kutularının toplam alanı bu süre içinde en az iki katına çıktı."},
    {"kod": "duman", "ad": "Duman algılandı", "kategori": "duman", "mekanizma": "oran", "sinif": "duman", "duzey": "yuksek",
     "onem": 4, "taban": 3, "sure_sn": 4.0, "oran": 0.6, "durum": "hazir",
     "aciklama": "Son saniyelerde analiz edilen karelerin çoğunda duman görüldü."},
    {"kod": "duman_yayiliyor", "ad": "Duman yayılıyor", "kategori": "duman", "mekanizma": "buyume", "sinif": "duman", "duzey": "yuksek",
     "onem": 4, "taban": 4, "sure_sn": 15.0, "kat": 2.0, "durum": "deneysel",
     "aciklama": "Duman kutularının toplam alanı bu süre içinde en az iki katına çıktı."},
    {"kod": "kritik_bolge", "ad": "Kritik bölgede alev ya da duman", "kategori": "bolge", "mekanizma": "bolge", "bolge_turu": "kritik",
     "duzey": "kritik", "onem": 5, "taban": 4, "sure_sn": 1.0, "oran": 0.6, "durum": "hazir",
     "aciklama": "Kritik bölge olarak çizilen alanda (ör. elektrik odası, kimyasal deposu) alev ya da duman görüldü; daha çabuk uyarır."},
]
for _k in KURALLAR:
    _k["ciddi"] = _k["duzey"] == "kritik"

KURAL = {k["kod"]: k for k in KURALLAR}

try:  # sınama sonuçları (egitim/dene_kurallar.py yazar): panelde kuralın yanında gösterilir
    from .sinama import SINAMA
except ImportError:
    SINAMA = {}
for _k in KURALLAR:
    if _k["kod"] in SINAMA:
        _k["sinama"] = SINAMA[_k["kod"]]

MODEL_DOSYASI = "yangin-duman-512.onnx"
MODEL_DOSYALARI = [MODEL_DOSYASI]
MODEL_KLASORU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modeller")


def model_var(yol: str) -> bool:
    """Model dosyası (kaynak koddan çalışırken düz .onnx) ya da paket girdisi yerinde mi."""
    if community_model.model_mi(yol):
        return os.path.isfile(yol + community_model.UZANTI)
    return os.path.isfile(yol)


def model_kilidi(klasor: str | None = None) -> dict:
    """Model paketinin durumu. Korumalı paket yalnızca AugeLab Studio'nun içinde, etkin lisansla açılır; panel modeli
    hiç açmaz, yalnızca dosyaların yerinde olup olmadığına bakar."""
    klasor = klasor or MODEL_KLASORU
    if community_model.isaretli(klasor) or any(community_model.model_mi(os.path.join(klasor, d)) for d in MODEL_DOSYALARI):
        return community_model.durum(klasor, MODEL_DOSYALARI)
    return {"sifreli": False, "durum": "duz"}


_EKSIK = {"t": 0.0, "klasor": None, "v": {}}


def eksik_modeller(klasor: str | None = None) -> dict[str, str]:
    """Model dosyası yerinde değilse çalışamayacak kurallar: {kural kodu: eksik dosyanın adı} (hepsi tek modele bağlıdır).
    Sonuç beş saniye saklanır (her karede diske bakılmasın)."""
    klasor = klasor or MODEL_KLASORU
    simdi = time.monotonic()
    if _EKSIK["klasor"] == klasor and simdi - _EKSIK["t"] < 5.0:
        return _EKSIK["v"]
    out = {} if model_var(os.path.join(klasor, MODEL_DOSYASI)) else {k["kod"]: MODEL_DOSYASI for k in KURALLAR}
    _EKSIK.update(t=simdi, klasor=klasor, v=out)
    return out


def esikler(ayar: dict) -> dict[str, float]:
    """Kameranın hassasiyet ayarına göre sınıf başına güven eşiği."""
    return dict(HASSASIYET.get(ayar.get("hassasiyet"), HASSASIYET[VARSAYILAN_HASSASIYET]))


def coz(ayar: dict) -> list[dict]:
    """Kamera ayarındaki "kurallar" listesini katalogla birleştirir.

    Ayarda: "kurallar": [{"kod": "alev"}, {"kod": "duman", "sure_sn": 6}, ...]
    Liste yoksa: çizilmiş bölge türlerine uyan bütün kurallar.
    Model dosyası yerinde değilse (eksik_modeller) hiçbir kural listeye girmez; panel bunu "model dosyası yok" diye gösterir.
    """
    turler = {b.get("tur") for b in ayar.get("bolgeler") or []}
    istenen = ayar.get("kurallar")
    eksik = eksik_modeller()
    out = []
    if istenen is None:
        for k in KURALLAR:
            if k["durum"] == "yok" or k["kod"] in eksik:
                continue
            if k.get("bolge_turu") and k["bolge_turu"] not in turler:
                continue
            out.append(dict(k))
        return out
    for i in istenen:
        taban = KURAL.get(i.get("kod", ""))
        if taban is None or taban["durum"] == "yok" or i.get("kapali") or taban["kod"] in eksik:
            continue
        out.append({**taban, **{a: v for a, v in i.items() if a != "kapali"}})
    return out


def olasilik(sure_sn: float, taban: int = 3) -> int:
    """1-5: kuralın taban olasılığı; olay sürdükçe artar (10 sn ve 30 sn'de birer basamak)."""
    return int(min(5, max(1, int(taban) + (sure_sn >= 10) + (sure_sn >= 30))))


def risk(onem: int, olas: int) -> int:
    """Risk puanı = önem × olasılık (1-25)."""
    return int(onem) * int(olas)
