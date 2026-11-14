"""Yangın kural motoru: analiz edilen her karenin alev ve duman tespitlerini alır, kuralları kayan pencerede uygular.

Bir olay, kuralın koşulu sağlandığı anda BAŞLAR (uyarı ve çıkışlar o anda tetiklenir) ve koşul kısa bir tutma süresi
boyunca sağlanmadığında KAPANIR (yanıp sönmesin diye). Tespitler saniyede yaklaşık iki kez gelir; aradaki görüntü
karelerinde yalnızca zaman ilerler, kurallar yeniden değerlendirilmez.
Yalnızca numpy ve OpenCV kullanır; AugeLab Studio'nun içinde (Yangın Kurallar bloğu) çalışır.
"""
from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict, deque

import cv2
import numpy as np

from . import katalog

IZGARA = (32, 18)        # ısı haritası hücreleri (en, boy)
SINIFLAR = ("alev", "duman")
TUTMA_SN = 3.0           # koşul en az bu kadar süre sağlanmazsa olay kapanır (uzun pencereli kurallarda 6 sn'ye kadar)
GECMIS_SN = 40.0         # bu kadar eski örnekler atılır
BOSLUK_SN = 5.0          # analiz bu kadar ara verdiyse (akış koptu) pencere baştan dolar
YUMUSATMA_SN = 1.5       # büyüme kuralları: alan bu sürenin ortancasıyla yumuşatılır
EN_AZ_ALAN = 0.001       # büyüme kuralları: karenin en az bu kadarını kaplayan tespit (küçük kutunun oynaması büyüme sayılmaz)
TOLERANS = 0.1           # saniye: pencerenin dolu sayılması için kare zamanlarındaki oynama payı
EN_UZUN_SURE = 30.0      # kuralın süresi en çok bu kadar olabilir


def icinde(poly: np.ndarray, p) -> bool:
    return cv2.pointPolygonTest(poly, (float(p[0]), float(p[1])), False) >= 0


class Motor:
    """Bir kameranın kural motoru. `adim()` her görüntü karesi için çağrılır."""

    def __init__(self, ayar: dict, W: int, H: int, bas_zaman: dt.datetime, kare_araligi: float = 0.5):
        self.ayar, self.W, self.H = ayar, W, H
        self.bas_zaman = bas_zaman
        self.aralik = kare_araligi  # görüntü kareleri arasındaki süre (blok günceller; klip hızı bundan gelir)
        olcek = np.array([W, H], dtype=np.float32)
        self.bolgeler = [{"ad": b.get("ad") or katalog.BOLGE_TURLERI[b["tur"]], "tur": b["tur"], "poly": np.array(b["poly"], dtype=np.float32) * olcek}
                         for b in ayar.get("bolgeler") or [] if b.get("tur") in katalog.BOLGE_TURLERI and len(b.get("poly") or []) >= 3]
        self.kritik = [b for b in self.bolgeler if b["tur"] == "kritik"]
        self.izinli = [b for b in self.bolgeler if b["tur"] == "izinli"]
        self.kurallar = katalog.coz(ayar)
        self.ornekler: deque = deque()            # analiz edilen karelerin özeti (zaman sırasıyla)
        self.acik: dict[tuple, dict] = {}         # (kural kodu, anahtar) → süren olay
        self.sayi: dict[str, int] = defaultdict(int)
        self.son = {"tespitler": [], "vurgu": []}  # son analiz edilen karenin çizilecekleri
        self._sifirla_olcum()

    # ---------------------------------------------------------------- ölçüm
    def _sifirla_olcum(self) -> None:
        self.o_bas = None
        self.o_son = None
        self.o_izgara = {s: np.zeros((IZGARA[1], IZGARA[0]), np.float32) for s in SINIFLAR}
        self.o_sn = {s: 0.0 for s in SINIFLAR}
        self.o_analiz = 0

    def _olc(self, o: dict, dtk: float) -> None:
        if self.o_bas is None:
            self.o_bas = o["t"]
        self.o_son = o["t"]
        self.o_analiz += 1
        for s in SINIFLAR:
            if o[s]:
                self.o_sn[s] += dtk
            for d in o[s]:  # kutunun kapladığı hücreler
                x1 = min(IZGARA[0] - 1, max(0, int(d["b"][0] / self.W * IZGARA[0])))
                x2 = min(IZGARA[0] - 1, max(0, int(d["b"][2] / self.W * IZGARA[0])))
                y1 = min(IZGARA[1] - 1, max(0, int(d["b"][1] / self.H * IZGARA[1])))
                y2 = min(IZGARA[1] - 1, max(0, int(d["b"][3] / self.H * IZGARA[1])))
                self.o_izgara[s][y1:y2 + 1, x1:x2 + 1] += dtk

    def olcum(self) -> dict | None:
        """Son çağrıdan bu yana biriken sayılar (ısı haritası, tespit süreleri); sayaçlar sıfırlanır."""
        if self.o_bas is None or not self.o_analiz:
            return None
        out = {
            "bas": (self.bas_zaman + dt.timedelta(seconds=self.o_bas)).replace(microsecond=0).isoformat(),
            "sure_sn": round(self.o_son - self.o_bas + 0.5, 2), "analiz": self.o_analiz,
            "alev_sn": round(self.o_sn["alev"], 1), "duman_sn": round(self.o_sn["duman"], 1),
            "izgara": {"gen": IZGARA[0], "yuk": IZGARA[1], **{s: [[round(float(v), 1) for v in satir] for satir in self.o_izgara[s]] for s in SINIFLAR}},
        }
        self._sifirla_olcum()
        return out

    # ---------------------------------------------------------------- örnek (analiz edilen kare)
    def _ornek(self, t: float, tespitler: list[dict]) -> dict:
        alan = float(self.W * self.H)
        kutular = []
        for d in tespitler:
            if d.get("s") not in SINIFLAR:
                continue
            b = d["b"]
            m = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            kutular.append({"s": d["s"], "b": b, "p": float(d.get("p", 0.0)), "m": m,
                            "izinli": any(icinde(z["poly"], m) for z in self.izinli),  # izinli ateş bölgesi: hiçbir kural saymaz
                            "alan": max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1]) / alan})
        gecerli = [d for d in kutular if not d["izinli"]]
        o = {"t": t, "kutular": kutular}
        for s in SINIFLAR:
            o[s] = [d for d in gecerli if d["s"] == s]
            o[s + "_alan"] = min(1.0, sum(d["alan"] for d in o[s]))
            yakin = [x for x in self.ornekler if t - x["t"] <= YUMUSATMA_SN + 1e-6] + [o]
            dolu = sum(1 for x in yakin if x[s])
            o[s + "_y"] = float(np.median([x[s + "_alan"] for x in yakin])) if len(yakin) >= 2 and dolu >= 0.6 * len(yakin) else None
        o["kritik"] = {z["ad"]: [d for d in gecerli if icinde(z["poly"], d["m"])] for z in self.kritik}
        return o

    # ---------------------------------------------------------------- koşullar
    @staticmethod
    def _sure(k: dict) -> float:
        try:
            return min(EN_UZUN_SURE, max(0.5, float(k.get("sure_sn", 2.0))))
        except (TypeError, ValueError):
            return 2.0

    def _oran(self, t: float, sure: float, oran: float, sec) -> dict | None:
        """Son `sure` saniyede analiz edilen karelerin en az `oran` kadarında (ve en az ikisinde) `sec(örnek)` dolu mu.
        Pencere dolmadan (gözlem `sure` saniyeden kısayken) koşul sağlanmış sayılmaz."""
        if not self.ornekler or self.ornekler[0]["t"] > t - sure + TOLERANS:
            return None
        pencere = [x for x in self.ornekler if t - x["t"] <= sure + 1e-6]
        var = [x for x in pencere if sec(x)]
        if len(var) < 2 or len(var) < oran * len(pencere) - 1e-9:
            return None
        return {"ilk": var[0]["t"], "kutular": sec(pencere[-1]), "yer": sec(var[-1]), "guven": max(d["p"] for x in var for d in sec(x))}

    def _degerlendir(self, k: dict, t: float) -> dict:
        """Kuralın o anda sağlandığı durumlar: {anahtar: bilgi}. Anahtar bölge kuralında bölgenin adı, ötekilerde ""."""
        mek, sure = k["mekanizma"], self._sure(k)
        try:
            oran = min(1.0, max(0.1, float(k.get("oran", 0.6))))
        except (TypeError, ValueError):
            oran = 0.6
        if mek == "oran":
            r = self._oran(t, sure, oran, lambda x, s=k["sinif"]: x[s])
            return {"": r} if r else {}
        if mek == "birlikte":
            a, d = (self._oran(t, sure, oran, lambda x, s=s: x[s]) for s in SINIFLAR)
            if not (a and d):
                return {}
            return {"": {"ilk": max(a["ilk"], d["ilk"]), "kutular": a["kutular"] + d["kutular"], "yer": a["yer"], "guven": min(a["guven"], d["guven"])}}
        if mek == "bolge":
            out = {}
            for z in self.kritik:
                if k.get("bolge") and z["ad"] != k["bolge"]:
                    continue
                r = self._oran(t, sure, oran, lambda x, ad=z["ad"]: x["kritik"].get(ad) or [])
                if r:
                    out[z["ad"]] = {**r, "bolge": z["ad"]}
            return out
        if mek == "buyume":
            s, simdi = k["sinif"], self.ornekler[-1]
            y = simdi[s + "_y"]
            if y is None or y < EN_AZ_ALAN:
                return {}
            try:
                kat = max(1.1, float(k.get("kat", 2.0)))
            except (TypeError, ValueError):
                kat = 2.0
            # pencerenin içinde, şimdiki yumuşatma aralığıyla çakışmayan en küçük (sıfırdan büyük) yumuşatılmış alan
            once = [x[s + "_y"] for x in self.ornekler if YUMUSATMA_SN - 1e-6 <= t - x["t"] <= sure + 1e-6 and x[s + "_y"]]
            if not once or y < kat * min(once):
                return {}
            return {"": {"ilk": t, "kutular": simdi[s], "yer": simdi[s], "guven": max((d["p"] for d in simdi[s]), default=0.0),
                         "ek": round(y / min(once), 1)}}
        return {}

    # ---------------------------------------------------------------- olaylar
    def _olaylari_guncelle(self, k: dict, t: float, tutanlar: dict) -> tuple[list[dict], list[dict], list[dict]]:
        baslayan, biten, vurgu = [], [], []
        for anahtar, b in tutanlar.items():
            kimlik = (k["kod"], anahtar)
            yer = b.get("yer") or b["kutular"]
            xy = (float(np.mean([d["m"][0] for d in yer])) / self.W, float(np.mean([d["m"][1] for d in yer])) / self.H) if yer else None
            o = self.acik.get(kimlik)
            if o is None:
                self.sayi[k["kod"]] += 1
                o = self.acik[kimlik] = {"kimlik": uuid.uuid4().hex, "k": k, "kural": k["kod"], "bas": b["ilk"], "son": t, "xy": [], "m": xy or (0.5, 0.5),
                                         "bolge": b.get("bolge"), "guven": 0.0, "ek": None, "sira": self.sayi[k["kod"]]}
                baslayan.append(o)
            o["son"] = t
            o["guven"] = max(o["guven"], float(b.get("guven") or 0.0))
            if b.get("ek") is not None:
                o["ek"] = max(o["ek"] or 0.0, b["ek"])
            if xy:
                o["xy"].append(xy)
                o["m"] = tuple(float(v) for v in np.mean(o["xy"][-40:], axis=0))
            vurgu += [{"b": d["b"], "etiket": k["ad"]} for d in b["kutular"]]
        tutma = max(TUTMA_SN, min(self._sure(k) + 1.0, 6.0))
        for kimlik in [a for a, o in self.acik.items() if a[0] == k["kod"] and a[1] not in tutanlar and t - o["son"] > tutma]:
            biten.append(self.acik.pop(kimlik))
        return baslayan, biten, vurgu

    def _kayit(self, o: dict, t: float, bitti: bool = False) -> dict:
        """Olayın panele giden kaydı."""
        k = o["k"]
        sure = max(0.0, t - o["bas"])
        olas = katalog.olasilik(sure, k.get("taban", 3))
        metin = k["aciklama"]
        if o.get("bolge"):
            metin = f"{o['bolge']}: " + metin
        if o.get("ek"):
            metin += f" Alan yaklaşık {o['ek']:g} katına çıktı."
        if o["guven"] > 0:
            metin += f" En yüksek güven %{round(100 * o['guven'])}."
        return {
            "kimlik": o["kimlik"], "bitti": bitti, "kural": k["kod"], "kural_ad": k["ad"], "kategori": k["kategori"], "duzey": k["duzey"],
            "bolge": o["bolge"], "onem": int(k["onem"]), "olasilik": olas, "puan": katalog.risk(k["onem"], olas), "ciddi": int(bool(k.get("ciddi"))),
            "zaman": (self.bas_zaman + dt.timedelta(seconds=o["bas"])).replace(microsecond=0).isoformat(), "bas": round(o["bas"], 2),
            "sure_sn": round(sure, 1), "x": round(float(o["m"][0]), 4), "y": round(float(o["m"][1]), 4), "aciklama": metin,
        }

    # ---------------------------------------------------------------- kare
    def adim(self, t: float, tespitler: list[dict], yeni: bool = True) -> dict:
        """`yeni`: bu karenin tespitleri yeni bir analizden mi geliyor (değilse yalnızca zaman ilerler).
        Dönüş: {"tespitler": çizilecek kutular, "vurgu": olay kutuları, "baslayan": [kayıt], "biten": [kayıt],
                "suren": [kayıt], "acik": [süren olaylar]}."""
        baslayan, biten = [], []
        if yeni:
            if self.ornekler and t - self.ornekler[-1]["t"] > BOSLUK_SN:
                self.ornekler.clear()
            dtk = min(1.0, max(0.0, t - self.ornekler[-1]["t"])) if self.ornekler else 0.5
            o = self._ornek(t, tespitler)
            self.ornekler.append(o)
            while t - self.ornekler[0]["t"] > GECMIS_SN:
                self.ornekler.popleft()
            self._olc(o, dtk)
            vurgu = []
            for k in self.kurallar:
                bas, bit, vur = self._olaylari_guncelle(k, t, self._degerlendir(k, t))
                vurgu += vur
                baslayan += [self._kayit(x, t) for x in bas]
                biten += [self._kayit(x, x["son"], bitti=True) for x in bit]
            self.son = {"tespitler": o["kutular"], "vurgu": vurgu}
        acik = list(self.acik.values())
        return {"tespitler": self.son["tespitler"], "vurgu": self.son["vurgu"], "baslayan": baslayan, "biten": biten,
                "suren": [self._kayit(x, t) for x in acik], "acik": acik}

    def kapat(self) -> list[dict]:
        """Açık kalan olayları kapatır (akış bittiğinde)."""
        biten = [self._kayit(o, o["son"], bitti=True) for o in self.acik.values()]
        self.acik = {}
        return biten
