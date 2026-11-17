"""Yangın Kamera: çift tıklayınca veri klasörünü kurar, yerel sunucuyu başlatır ve tarayıcıda açar.

Sunucu varsayılan olarak yalnızca 127.0.0.1'i dinler. Ayarlar'da ağ erişimi açılırsa bütün ağ arayüzlerini dinler;
ağdan gelen istekler yalnızca API anahtarıyla /api/v1/... adreslerini okuyabilir (olay klipleri ve kareleri dahil).

Ekranlar tek sayfadır (web/index.html); veriler /api/... adreslerinden JSON olarak gelir.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

import yollar

VARSAYILAN_PORT = 8790
KOD_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
TURLER = {
    ".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8", ".jpg": "image/jpeg",
    ".mp4": "video/mp4", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png", ".ico": "image/x-icon", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}

# ---------------------------------------------------------------- arka plan işleri


class Is:
    """Arka planda çalışan bir iş (örnek analiz, bağlantı denemesi, izleme) ve ekrana yazdıkları."""

    sayac = 0

    def __init__(self, tur: str, baslik: str):
        Is.sayac += 1
        self.no = Is.sayac
        self.tur, self.baslik = tur, baslik
        self.kod: str | None = None  # işin o anda çalıştığı kamera (varsa)
        self.satirlar: list[str] = []
        self._yarim = ""
        self.durum = "calisiyor"
        self.sonuc: dict = {}
        self.bas, self.bitis = time.time(), None
        self.dur = threading.Event()
        self.kilit = threading.Lock()

    def ekle(self, metin: str) -> None:
        with self.kilit:
            parca = (self._yarim + metin.replace("\r\n", "\n").replace("\r", "\n")).split("\n")
            self._yarim = parca.pop()
            for s in parca:
                s = s.rstrip()
                if not s:
                    continue
                self.satirlar.append(s)
            del self.satirlar[:-400]

    def ozet(self) -> dict:
        with self.kilit:
            satirlar = self.satirlar + ([self._yarim] if self._yarim.strip() else [])
        return {"no": self.no, "tur": self.tur, "baslik": self.baslik, "kod": self.kod, "durum": self.durum, "satirlar": satirlar[-80:],
                "sonuc": self.sonuc, "sure": round((self.bitis or time.time()) - self.bas, 1), "durduruluyor": self.dur.is_set()}


class Yonlendirici(io.TextIOBase):
    """print() çıktısını, o anda hangi işin iş parçacığındaysa o işin kaydına da yazar."""

    def __init__(self, asil):
        self.asil = asil
        self.yerel = threading.local()

    @property
    def encoding(self):
        return "utf-8"

    def write(self, s):
        is_ = getattr(self.yerel, "is_", None)
        if is_ is not None:
            is_.ekle(s)
        if self.asil is not None:
            try:
                self.asil.write(s)
            except UnicodeEncodeError:
                kod = getattr(self.asil, "encoding", None) or "ascii"
                self.asil.write(s.encode(kod, "replace").decode(kod))
            except Exception:
                pass
        return len(s)

    def flush(self):
        if self.asil is not None:
            try:
                self.asil.flush()
            except Exception:
                pass

    def isatty(self):
        return False


DINLENEN = {"adres": "127.0.0.1", "port": VARSAYILAN_PORT, "ag": []}  # sunucunun dinlediği adres (başlarken dolar)
YON_OUT = Yonlendirici(sys.stdout)
YON_ERR = Yonlendirici(sys.stderr)
AKTIF: Is | None = None
IS_KILIDI = threading.Lock()
KAPANIYOR = threading.Event()  # program kapanmaya başlayınca (IS_KILIDI altında) kurulur: ondan sonra yeni iş kabul edilmez


def is_baslat(tur: str, baslik: str, fn, *args) -> tuple[bool, str]:
    global AKTIF
    with IS_KILIDI:
        if KAPANIYOR.is_set():
            return False, "Yangın Kamera kapanıyor; yeni iş başlatılamaz."
        if AKTIF is not None and AKTIF.durum == "calisiyor":
            return False, f"Şu an \"{AKTIF.baslik}\" çalışıyor. Bitmesini bekleyin ya da durdurun."
        is_ = Is(tur, baslik)
        AKTIF = is_

    def calis():
        YON_OUT.yerel.is_ = YON_ERR.yerel.is_ = is_
        try:
            sonuc = fn(is_, *args)
            is_.sonuc = sonuc or {}
            # "tamamlandi": iş, geç gelen bir durdurma etkili olmadan önce bitti; durdurulmuş gösterilmez
            durduruldu = is_.dur.is_set() and not is_.sonuc.get("tamamlandi")
            is_.durum = "hata" if is_.sonuc.get("hata") else ("durduruldu" if durduruldu else "bitti")
        except SystemExit as e:
            if e.code not in (None, 0):
                if not isinstance(e.code, int):
                    print(str(e.code), flush=True)
                is_.durum = "hata"
            else:
                is_.durum = "bitti"
        except Exception as e:  # beklenmeyen hata: ayrıntı konsola, kısa mesaj ekrana
            traceback.print_exc(file=sys.__stderr__)
            print(f"Hata: {e}", flush=True)
            is_.durum = "hata"
        finally:
            YON_OUT.yerel.is_ = YON_ERR.yerel.is_ = None
            is_.bitis = time.time()

    threading.Thread(target=calis, name=f"is-{is_.no}", daemon=True).start()
    return True, ""


def ayar_yolu(kod: str) -> Path:
    return yollar.AYAR / f"{kod}.json"


class AyarHatasi(Exception):
    """Kamera ayarı kaydedilemedi; ileti kullanıcıya gösterilir."""


_AYAR_KILIDI = threading.Lock()  # ayar dosyalarını yazan bütün işlemler: aynı anda gelen iki kayıt birbirinin arasına giremez


def _ayar_metni_yaz(dosya, ayar: dict) -> None:
    dosya.write(json.dumps(ayar, ensure_ascii=False, indent=1))


def _ayar_sil(kod: str) -> None:
    ayar_yolu(kod).unlink(missing_ok=True)


def _ayar_hazirla(ayar) -> tuple[str, dict, list[str]]:
    """Gelen ayarı denetler: (kısa kod, şifresi temizlenmiş ayar, notlar)."""
    if not isinstance(ayar, dict):
        raise AyarHatasi("Ayar okunamadı.")
    kod = str(ayar.get("kod", ""))
    if not KOD_RE.match(kod):
        raise AyarHatasi("Kısa kod yalnızca küçük harf (a-z), rakam, - ve _ içerebilir (ör. depo2).")
    if kod in yollar.ORNEK_ADLARI:
        raise AyarHatasi(f"\"{kod}\" örnek kameralara ait. Başka bir kısa kod yazın (ör. {kod}2).")
    ayar = json.loads(json.dumps(ayar))  # kopya: çağıranın verisi değişmesin
    ayar["kod"] = kod
    return kod, ayar, sifreyi_temizle(ayar)


def kameralari_olustur(ayarlar) -> dict:
    """Yeni kameraları tek işlemde oluşturur: ya hepsi yazılır ya hiçbiri (toplu kanal ekleme).

    Var olan bir kameranın üstüne yazılmaz. Denetim ve yazma tek kilit altında yapılır ve her dosya "yoksa oluştur" ile
    açılır: aynı anda gelen iki istekten yalnızca biri başarılı olur. Yazarken hata çıkarsa bu çağrının oluşturduğu
    dosyalar silinir; silinemeyen olursa adı iletide açıkça yazılır."""
    if not isinstance(ayarlar, list) or not 1 <= len(ayarlar) <= 64:
        raise AyarHatasi("Bir seferde 1 ile 64 arasında kamera eklenebilir.")
    hazir = [_ayar_hazirla(a) for a in ayarlar]
    kodlar = [kod for kod, _, _ in hazir]
    yinelenen = sorted({k for k in kodlar if kodlar.count(k) > 1})
    if yinelenen:
        raise AyarHatasi(f"Aynı kısa kod birden çok kez geçiyor: {', '.join(yinelenen)}. Hiçbiri eklenmedi.")
    with _AYAR_KILIDI:
        yollar.AYAR.mkdir(parents=True, exist_ok=True)
        varolan = [k for k in kodlar if ayar_yolu(k).exists()]
        if varolan:
            raise AyarHatasi(f"Bu kodlarla kamera zaten var: {', '.join(varolan)}. Üstlerine yazılmadı; hiçbiri eklenmedi.")
        olusan: list[str] = []
        try:
            for kod, ayar, _ in hazir:
                dosya = open(ayar_yolu(kod), "x", encoding="utf-8")  # "x": dosya varsa hata verir, var olanı ezmez
                olusan.append(kod)
                with dosya:
                    _ayar_metni_yaz(dosya, ayar)
        except OSError as e:
            kalan = []
            for kod in olusan:  # yalnızca bu çağrının oluşturdukları geri alınır
                try:
                    _ayar_sil(kod)
                except OSError:
                    kalan.append(kod)
            neden = "aynı kodla bir kamera az önce oluşturulmuş" if isinstance(e, FileExistsError) else f"dosya yazılamadı ({type(e).__name__})"
            raise AyarHatasi(f"Kameralar eklenemedi: {neden}. " + ("Hiçbiri eklenmedi." if not kalan else
                             f"Geri alınamayan kayıtlar kaldı: {', '.join(kalan)}. Bunları Ayarlar'dan silin.")) from None
    return {"kodlar": kodlar, "notlar": sorted({n for _, _, notlar in hazir for n in notlar})}


def kanal_ayarlari(taban, kanallar, profiller=None) -> list[dict]:
    """Bir kayıt cihazının kanalları için kamera ayarlarını üretir: `taban` formdaki ayardır (kod, ad, bağlantı, kurallar).

    Her kanal `<kod>-k<n>` koduyla ayrı bir kamera olur; bölgeler boş başlar, kurallar kopyalanır. `profiller` verilirse
    (ONVIF: cihazdan okunan profil listesi) kanalın profil ve görüntü kaynağı belirteçleri de yazılır: kamera, cihaz
    profilleri sonradan başka sırayla bildirse de aynı fiziksel kanala bağlanır. Listede profili olmayan kanal reddedilir."""
    if not isinstance(taban, dict) or not isinstance(taban.get("kamera"), dict):
        raise AyarHatasi("Ayar okunamadı.")
    kod = str(taban.get("kod", ""))
    if not KOD_RE.match(kod):
        raise AyarHatasi("Önce kısa kodu yazın (ör. nvr1): kanallar nvr1-k1, nvr1-k2… olarak eklenir.")
    if not taban["kamera"].get("ip"):
        raise AyarHatasi("Önce kayıt cihazının IP adresini yazın.")
    try:
        kanallar = [int(n) for n in kanallar]
    except (TypeError, ValueError):
        raise AyarHatasi("Kanal listesi okunamadı.") from None
    if not 1 <= len(kanallar) <= 64 or len(set(kanallar)) != len(kanallar) or min(kanallar) < 1:
        raise AyarHatasi("Kanal sayısı 1 ile 64 arasında olmalı ve her kanal bir kez geçmeli.")
    if taban["kamera"].get("tur") == "onvif" and not (isinstance(profiller, list) and profiller):
        # ONVIF'te kanal, kalıcı profil ve kaynak belirteciyle kaydedilir; liste gelmediyse belirteçsiz ayar yazılmaz
        raise AyarHatasi("ONVIF kanalları eklenmeden önce cihazın kanalları ve profilleri listelenmeli; hiçbiri eklenmedi.")
    if taban["kamera"].get("tur") != "onvif":
        profiller = None  # markaya göre RTSP: kanal adresin içindedir, belirteç yoktur
    out = []
    for n in kanallar:
        kamera = {a: v for a, v in taban["kamera"].items() if a not in ("profil", "profil_ad", "kaynak")}
        kamera["kanal"] = n
        if profiller is not None:
            aday = sorted((p for p in profiller if isinstance(p, dict) and p.get("kanal") == n and p.get("belirtec") and p.get("kaynak")),
                          key=lambda p: int(p.get("en") or 0) * int(p.get("boy") or 0))
            if not aday:
                raise AyarHatasi(f"Cihazın bildirdiği profiller arasında {n}. kanal yok; hiçbiri eklenmedi. Kanalları yeniden listeleyin.")
            p = aday[-1] if kamera.get("akis") == "ana" else aday[0]
            kamera.update(profil=str(p["belirtec"]), kaynak=str(p["kaynak"]),
                          profil_ad=f"Kanal {n} · {p.get('ad') or p['belirtec']} · {p.get('kodlama', '')} {p.get('en', 0)}×{p.get('boy', 0)}")
        out.append({**taban, "kod": f"{kod}-k{n}", "ad": f"{taban.get('ad') or kod} · Kanal {n}", "kamera": kamera, "bolgeler": []})
    return out


def ayar_oku(kod: str) -> dict:
    yol = ayar_yolu(kod)
    if not yol.exists():
        raise SystemExit(f"Ayar bulunamadı: {kod}")
    return json.loads(yol.read_text(encoding="utf-8"))


def _bildir(olay_numaralari: list[int]) -> None:
    """Yeni başlayan olayları tanımlı çıkışlara iletir."""
    import baglanti

    for satir in baglanti.gonder(olay_numaralari):
        print(satir, flush=True)


def _studio(korutin):
    import asyncio

    return asyncio.run(korutin)


def is_studio_dene(is_: Is) -> dict:
    """Studio lisansını bir kez kontrol eder: Studio arka planda kısa süre çalışır, yangın modeli açılır (korumalı paketin
    lisansı burada doğrulanır). Sonuç saklanır; sonraki açılışlarda yeniden yapılmaz."""
    import studio

    engel = _model_indirme_engeli()  # deneme modeli açar: model yokken denenirse sonuç yanlışlıkla "hazır değil" kalırdı
    if engel:
        raise SystemExit(engel)
    print("Lisans kontrol ediliyor…", flush=True)
    try:
        studio.dene()
    except studio.StudioHatasi as e:
        raise SystemExit(str(e)) from None
    finally:
        _STUDIO["an"] = 0.0
    print("Hazır: lisans doğrulandı.", flush=True)
    return {}


def _tespit_hatasi(neden: str | None) -> str:
    return (f"AugeLab Studio'daki tespit çalışmıyor ({neden}). Alev ve duman aranamıyor; "
            "model dosyasını ve AugeLab Studio lisansınızı kontrol edin.")


KUYRUK_BOSALMADI = ("Studio'dan gelen son kayıtlar işlenemedi (kuyruk boşalmadı). Açık olaylar ve yarım klipler olduğu gibi bırakıldı; "
                    "veri klasöründeki kuyruk klasörüne bakın.")


def _sahneyi_kapat(kod: str, durdur, bekle_sn: float) -> str | None:
    """Sahneyi durdurur (`durdur()`: durdurma işini veren işlev) ve kameranın kuyruğunun boşalmasını bekler.

    Dönüş: her şey yolundaysa None; durdurma doğrulanamadıysa ya da kuyruk bekleme süresinde boşalmadıysa nedeni.
    Neden dönerse çağıran açık olayları kapatmaz, yarım klipleri silmez ve işi hatayla bitirir: sahne hâlâ kayıt
    bırakıyor olabilir ya da işlenmemiş kayıtlar ve dönüştürülmemiş klipler vardır."""
    import kuyruk

    try:
        _studio(durdur())
    except Exception as e:
        return (f"AugeLab Studio sürecinin durduğu doğrulanamadı ({type(e).__name__}: {e}). Açık olaylar ve "
                "yarım klipler olduğu gibi bırakıldı. Programı kapatıp yeniden açın.")
    time.sleep(bekle_sn)  # sahnenin son kayıtları kuyruğa düşsün
    if not kuyruk.bosalsin(kod):  # bu koşunun bütün kayıtları içeri alınmalı, klipleri dönüştürülmeli
        return KUYRUK_BOSALMADI
    return None


def studioda_analiz(is_: Is, kod: str, en_cok_sn: float = 1800.0) -> None:
    """Kameranın video dosyasını AugeLab Studio'daki sahnede baştan sona çalıştırır; olaylar kuyruktan panele düşer."""
    import kuyruk
    import studio

    ayar = ayar_oku(kod)
    print("  AugeLab Studio hazırlanıyor (arayüzsüz; pencere açılmaz)", flush=True)
    bilgi = _studio(studio.sahne_kur(kod, ayar))
    kuyruk.BITENLER.pop(kod, None)
    kuyruk.HATALAR.pop(kod, None)

    async def baslat():
        kosu = await studio.yeni_kosu(bilgi, kod)
        await studio.calistir(bilgi, int(en_cok_sn * 1000))
        return kosu

    kosu = _studio(baslat())  # kuyruk kayıtları bu numarayı taşır: önceki çalıştırmadan kalan kayıt bu işe sayılmaz
    hata: BaseException | None = None
    print("  sahne AugeLab Studio'da arayüzsüz çalışıyor (ilk çalıştırmada Studio'nun ve modelin yüklenmesi biraz sürer)", flush=True)
    bas = time.time()
    try:
        while True:
            if kuyruk.kosu_hatasi(kod, kosu):  # "bitti" kaydıyla aynı anda gelse de hata önce gelir
                raise SystemExit(_tespit_hatasi(kuyruk.kosu_hatasi(kod, kosu)))
            if kuyruk.kosu_bitti(kod, kosu):
                break
            if studio.kosu_sorunu(bilgi):
                raise SystemExit(studio.kosu_sorunu(bilgi))
            if is_.dur.is_set():
                print("  durduruldu", flush=True)
                break
            if time.time() - bas > en_cok_sn:
                raise SystemExit("AugeLab Studio'daki analiz beklenen sürede bitmedi.")
            son = kuyruk.SON_KAYIT.get(kod, 0.0)
            # ilk kayıttan önce daha uzun beklenir: motor yenilendiyse Studio blokları ve modeli baştan yükler
            if time.time() - max(bas, son) > (90 if son > bas else 240):
                raise SystemExit("AugeLab Studio'dan uzun süredir kayıt gelmedi. Kurulum sihirbazındaki “Studio’yu dene” adımıyla kontrol edin.")
            time.sleep(0.5)
    except BaseException as e:  # iş hatası: sahne yine de kapatılır, hata aşağıda yeniden yükseltilir
        hata = e
    # Temizlik (açık olayları kapatma, yarım klipleri silme) yalnızca sahnenin durduğu doğrulandıysa ve bu koşunun bütün
    # kuyruk kayıtları içeri alınıp klipleri dönüştürüldüyse yapılır; değilse hiçbir şey silinmez ve iş hatayla biter.
    sorun = _sahneyi_kapat(kod, lambda: studio.durdur(bilgi), 1.2)
    if sorun is not None:
        print("  uyarı: " + sorun, flush=True)
    elif not kuyruk.kosu_bitti(kod, kosu) or kuyruk.kosu_hatasi(kod, kosu):  # hata ya da durdurma: süren olaylar kapanış kaydı bırakamadı
        _acik_olaylari_kapat(kod)
    if hata is not None:
        raise hata
    if kuyruk.kosu_hatasi(kod, kosu):  # bu koşunun hata kaydı "bitti"den sonra, son kayıtlarla işlenmiş olabilir
        raise SystemExit(_tespit_hatasi(kuyruk.kosu_hatasi(kod, kosu)))
    if sorun is not None:
        raise SystemExit(sorun)


def _acik_olaylari_kapat(kod: str) -> None:
    """Sahne durdurulduğunda süren olaylar kapanış kaydı bırakamaz: panelde "sürüyor" olarak kalmasın, yarım klipler silinsin."""
    import depo

    depo.yaz("UPDATE olay SET suruyor = 0 WHERE kamera = ? AND suruyor = 1", kod)
    if (yollar.CIKTI / kod).is_dir():
        for f in (yollar.CIKTI / kod).glob("*.ham.mp4"):
            try:
                f.unlink()
            except OSError:
                pass


def _ornegi_temizle(kod: str) -> None:
    import depo

    depo.kamera_sil(kod, yalniz_ornek=True)
    for f in (yollar.CIKTI / kod).glob("*") if (yollar.CIKTI / kod).is_dir() else []:
        f.unlink(missing_ok=True)


def is_ornek(is_: Is) -> dict:
    import kuyruk

    kodlar = yollar.ornek_kodlar()
    if not kodlar:
        raise SystemExit("Bu sürümde örnek video yok. Bir kamera ya da video dosyası ekleyin.")
    for n, kod in enumerate(kodlar, 1):
        if is_.dur.is_set():
            print("Durduruldu.", flush=True)
            return {}
        ayar = ayar_oku(kod)
        print(f"[{n}/{len(kodlar)}] {ayar.get('ad', kod)} AugeLab Studio'da analiz ediliyor…", flush=True)
        is_.kod = kod
        t0 = time.time()
        _ornegi_temizle(kod)
        kuyruk.SON_KAYIT.pop(kod, None)
        studioda_analiz(is_, kod)
        print(f"[{n}/{len(kodlar)}] bitti ({time.time() - t0:.0f} sn).", flush=True)
    return {"git": "#/"}


def is_test(is_: Is, kod: str, sifre: str | None) -> dict:
    import kamera

    ayar = ayar_oku(kod)
    r = kamera.test(ayar, ayar_yolu(kod), sifre, dur=is_.dur)
    if r == 2:  # kare yazılmadan önce durduruldu: hiçbir şey kaydedilmedi
        return {}
    if r != 0:
        return {"hata": True}
    return {"kare": f"/ayar/_kare_{kamera.kod(ayar, ayar_yolu(kod))}.jpg?t={int(time.time())}", "kod": kod,
            "tamamlandi": True}  # kare kaydedildi: geç gelen bir durdurma denemeyi "durduruldu"ya çevirmez


def is_izle(is_: Is, kod: str, sifre: str | None, dakika: float) -> dict:
    """Canlı kamerayı AugeLab Studio'daki sahnede durdurulana kadar izler; olaylar başladığı anda panele düşer."""
    import kamera
    import kuyruk
    import studio

    ayar = ayar_oku(kod)
    if (ayar.get("kamera") or {}).get("tur") not in ("rtsp", "onvif", "http"):
        raise SystemExit("Canlı izleme IP kamera, kayıt cihazı ya da HTTP akışı içindir. Video dosyasında Videoyu analiz et'i kullanın.")
    adres, goster = kamera.kaynak(ayar, sifre)
    print(f"{ayar.get('ad', kod)}: {goster}", flush=True)
    print("  AugeLab Studio hazırlanıyor (arayüzsüz; pencere açılmaz)", flush=True)
    bilgi = _studio(studio.sahne_kur(kod, ayar))
    kuyruk.SON_KAYIT.pop(kod, None)
    kuyruk.HATALAR.pop(kod, None)

    async def baslat():
        await studio.kamera_adresi(bilgi, str(adres))
        kosu = await studio.yeni_kosu(bilgi, kod)
        await studio.calistir(bilgi)
        return kosu

    async def bitir():
        try:
            await studio.durdur(bilgi)
        finally:
            await studio.kamera_adresi(bilgi, "")  # adres şifre içerebilir: bellekte bırakılmaz

    kosu = _studio(baslat())
    print("  sahne AugeLab Studio'da arayüzsüz çalışıyor; durdurulana kadar izlenir", flush=True)
    bas, uyarildi = time.time(), False
    hata: BaseException | None = None
    try:
        while not is_.dur.is_set():
            if kuyruk.kosu_hatasi(kod, kosu):
                raise SystemExit(_tespit_hatasi(kuyruk.kosu_hatasi(kod, kosu)))
            if studio.kosu_sorunu(bilgi):
                raise SystemExit(studio.kosu_sorunu(bilgi))
            son = kuyruk.SON_KAYIT.get(kod, 0.0)
            if not uyarildi and time.time() - max(bas, son) > 45:
                uyarildi = True
                print("  45 saniyedir Studio'dan kayıt gelmiyor: kamera görüntü vermiyor olabilir (adres, kullanıcı, şifre, ağ).", flush=True)
            elif uyarildi and time.time() - son < 10:
                uyarildi = False
                print("  kayıt yeniden geliyor", flush=True)
            time.sleep(0.5)
        print("  durduruluyor", flush=True)
    except BaseException as e:  # iş hatası: sahne yine de kapatılır, hata aşağıda yeniden yükseltilir
        hata = e
    # Video akışındaki kural: durdurma doğrulanamazsa ya da kuyruk boşalmazsa temizlik atlanır ve iş hatayla biter.
    sorun = _sahneyi_kapat(kod, bitir, 1.5)
    if sorun is None:
        _acik_olaylari_kapat(kod)  # izleme durduruldu: süren olaylar kapanış kaydı bırakamadı
    else:
        print("  uyarı: " + sorun, flush=True)
    if hata is not None:
        raise hata
    if kuyruk.kosu_hatasi(kod, kosu):  # hata kaydı son kayıtlarla işlenmiş olabilir
        raise SystemExit(_tespit_hatasi(kuyruk.kosu_hatasi(kod, kosu)))
    if sorun is not None:
        raise SystemExit(sorun)
    return {"git": "#/"}


def is_video(is_: Is, kod: str) -> dict:
    """Video dosyası türündeki kamerayı (ör. kayıt cihazından alınmış kayıt) AugeLab Studio'da baştan sona analiz eder."""
    import kuyruk

    ayar = ayar_oku(kod)
    if (ayar.get("kamera") or {}).get("tur") != "dosya":
        raise SystemExit("Bu kamera bir video dosyası değil.")
    print(f"{ayar.get('ad', kod)} AugeLab Studio'da analiz ediliyor…", flush=True)
    kuyruk.SON_KAYIT.pop(kod, None)
    studioda_analiz(is_, kod)
    return {"git": "#/"}


# ---------------------------------------------------------------- ayarlar


def sifreyi_temizle(ayar: dict) -> list[str]:
    """Ayar dosyasına şifre yazılmasın: şifre alanlarını siler, adresteki şifreyi {sifre} yapar."""
    notlar = []
    k = ayar.get("kamera")
    if isinstance(k, dict):
        for alan in list(k):
            if alan != "sifre_degiskeni" and re.search(r"sifre|şifre|password|pass$|parola", alan, re.I):
                del k[alan]
                notlar.append("Şifre alanı kaydedilmedi.")
        adres = k.get("adres")
        if isinstance(adres, str):
            m = re.search(r"://([^:/@]+):([^@]*)@", adres)
            if m and m.group(2) not in ("{sifre}", ""):
                k["adres"] = adres[:m.start(2)] + "{sifre}" + adres[m.end(2):]
                notlar.append("Adresteki şifre kaydedilmedi; yerine {sifre} yazıldı. Şifreyi çalışırken şifre kutusuna yazın.")
    ayar.pop("sifre", None)
    return notlar


def model_kilidi() -> dict:
    """Model paketinin durumu. Panel modeli açmaz: korumalı paket yalnızca AugeLab Studio'nun içinde, etkin lisansla açılır."""
    import kurallar
    import studio_kurulum

    if not yollar.DONDURULMUS:
        return kurallar.model_kilidi(str(yollar.MODELLER))
    if not studio_kurulum.model_gerekli():  # düz derleme: model programla gelir
        return kurallar.model_kilidi(str(yollar.PAKET_MODELLER))
    # Exe, korumalı paket: işaret ve DLL programla gelen kopyadan; model veri klasöründen ve yalnızca bu süreçte
    # SHA-256 ile doğrulanmışsa (Studio'ya giden görünüm: studio_kurulum.motor_modelleri).
    from yangin_motor import community_model as cm

    sonuc = {"sifreli": True, "community": True}
    try:
        kimlik = cm._kimlik(yollar.PAKET_MODELLER)
        if not cm._dosya(yollar.PAKET_MODELLER, kimlik).is_file():
            raise cm.LisansHatasi(cm._MESAJ[1])
        if not studio_kurulum.model_dogrulandi():
            return dict(sonuc, durum="hazirlaniyor", mesaj="Algılama modeli hazırlanıyor.")
        with studio_kurulum.model_yolu().open("rb") as f:
            if f.read(24) != cm.SIHIR + kimlik:
                raise cm.LisansHatasi(cm._MESAJ[1])
    except (OSError, cm.LisansHatasi) as e:
        return dict(sonuc, durum="bozuk", mesaj=str(e) if isinstance(e, cm.LisansHatasi) else cm._MESAJ[1])
    return dict(sonuc, durum="studio_kosusunda_dogrulanir")


def _model_var() -> bool:
    """Algılama modeli kullanılabilir mi (exe'de korumalı pakette: bu süreçte doğrulanmış model dosyası)."""
    import kurallar
    import studio_kurulum

    if not yollar.DONDURULMUS:
        return kurallar.model_var(str(yollar.MODEL))
    if studio_kurulum.model_gerekli():
        return studio_kurulum.model_dogrulandi()
    return kurallar.model_var(str(yollar.PAKET_MODELLER / kurallar.MODEL_DOSYASI))


def _model_indirme_engeli() -> str | None:
    """Korumalı paketin model dosyası hazır değilse nedeni (doğrulanıyor, indiriliyor ya da indirilmesi gerekiyor)."""
    import studio_kurulum

    d = studio_kurulum.model_durumu()
    if not d["eksik"]:
        return None
    if d["asama"] == "dogrulaniyor":
        return "Algılama modeli hazırlanıyor (dosya doğrulanıyor). Birkaç saniye sonra analizi yeniden başlatın."
    if d["asama"] == "indiriliyor":
        yuzde = round(100 * d["indirilen"] / d["toplam"]) if d["toplam"] else 0
        return f"Algılama modeli indiriliyor (%{yuzde}). İndirme bitince analizi yeniden başlatın."
    return ("Algılama modeli henüz indirilmedi (yaklaşık 210 MB). Sayfanın üstündeki “Yeniden dene” düğmesiyle indirin; "
            "indirme bitince analizi başlatın.")


def _model_engeli() -> str | None:
    """Analiz başlatılamıyorsa nedeni (model dosyası yok ya da paket bozuk); başlatılabiliyorsa None."""
    indirme = _model_indirme_engeli()
    if indirme:
        return indirme
    kilit = model_kilidi()
    if kilit["sifreli"] and kilit["durum"] != "studio_kosusunda_dogrulanir":
        return kilit.get("mesaj") or "Model paketi açılamıyor."
    if not _model_var():
        return "Model dosyası yerinde değil (motor/modeller). Programı yeniden kurun."
    return None


def durum() -> dict:
    import depo
    import kamera
    import rapor
    import studio_kurulum

    kameralar = rapor.kameralar()
    for k in kameralar:
        try:
            k["sifre"] = kamera.sifre_gerekli(ayar_oku(k["kod"]))
        except SystemExit:
            k["sifre"] = False
    return {
        "uygulama": yollar.UYGULAMA, "surum": yollar.SURUM, "veri": str(yollar.VERI),
        "model": _model_var(), "model_kilidi": model_kilidi(),
        "ornek_var": bool(yollar.ornek_kodlar()), "kameralar": kameralar, "genel": depo.genel(), "dinlenen": DINLENEN,
        "is": AKTIF.ozet() if AKTIF else None, "studio": studio_durumu(), "son_kritik": rapor.son_kritik(),
        "studio_kurulu": studio_kurulum.kurulu_studio() is not None,
        "studio_kurulum": studio_kurulum.durum(), "hesap_url": studio_kurulum.HESAP_URL,
        "model_indirme": studio_kurulum.model_durumu(),
    }


_STUDIO = {"an": 0.0, "durum": None, "yokluyor": False}
_STUDIO_KILIDI = threading.Lock()


def _studio_yokla() -> None:
    try:
        import studio

        d = _studio(studio.durum())
        _STUDIO["durum"] = {"bagli": d.get("hazir") is True, "kurulu": True, **d}
    except Exception as e:
        _STUDIO["durum"] = {"bagli": False, "kurulu": False, "mesaj": str(e)[:200]}
    finally:
        _STUDIO["an"] = time.time()
        _STUDIO["yokluyor"] = False


def studio_durumu() -> dict:
    """AugeLab Studio arayüzsüz çalışmaya hazır mı (kurulu ve deneme geçti). Yoklama arka planda yapılır ve Studio'yu
    çalıştırmaz; bu işlev hiç beklemez ve son bilinen durumu döndürür."""
    with _STUDIO_KILIDI:
        if not _STUDIO["yokluyor"] and time.time() - _STUDIO["an"] > 5:
            _STUDIO["yokluyor"] = True
            threading.Thread(target=_studio_yokla, daemon=True, name="studio-yoklama").start()
    return _STUDIO["durum"] or {"bagli": False, "yoklaniyor": True, "mesaj": "AugeLab Studio yoklanıyor…"}


def katalog() -> dict:
    import baglanti
    import kamera
    import kurallar

    # model kullanılabilir değilse kurallar panelde işaretlenir (exe'de korumalı pakette: doğrulanmış model dosyası)
    eksik = {} if _model_var() else {k["kod"]: kurallar.MODEL_DOSYASI for k in kurallar.KURALLAR}
    return {
        "kurallar": [{**k, "model_eksik": eksik[k["kod"]]} if k["kod"] in eksik else k for k in kurallar.KURALLAR],
        "kategoriler": kurallar.KATEGORILER, "bolge_turleri": kurallar.BOLGE_TURLERI,
        "hassasiyetler": kurallar.HASSASIYET_ADLARI, "varsayilan_hassasiyet": kurallar.VARSAYILAN_HASSASIYET,
        "markalar": {k: v["ad"] for k, v in kamera.MARKALAR.items()},
        "baglanti_turleri": baglanti.TURLER, "api": API_UCLARI,
    }


# ---------------------------------------------------------------- dış sistemler için API (yalnızca okuma)

API_UCLARI = {
    "/api/v1/ozet": "Olay sayıları, açık ve süren uyarılar, günlük seri (gun | bas, bit)",
    "/api/v1/olaylar": "Olay listesi (gun | bas, bit, kamera, kategori, kural, durum, duzey, vardiya, ciddi=1: yalnız kritik, sinir)",
    "/api/v1/olaylar.csv": "Aynı liste CSV olarak (Excel, Power BI)",
    "/api/v1/olay/<no>": "Tek olay",
    "/api/v1/rapor": "Kural / kamera / vardiya / bölge kırılımları ve eğilim (gun | bas, bit)",
    "/api/v1/analitik": "Bir kameranın alev ve duman ısı haritası ve sayıları (kamera, gun | bas, bit)",
    "/api/v1/kameralar": "Kameralar ve son durumları",
    "/api/v1/gorevler": "Görevler ve doğrulama durumları",
    "/api/v1/medya/<yol>": "Olayın klibi ya da karesi (olaydaki klip / kare alanı)",
}
CSV_ALANLARI = ("id", "zaman", "kamera", "kamera_ad", "kural", "kural_ad", "kategori", "duzey", "bolge", "vardiya", "onem", "olasilik", "puan",
                "sure_sn", "durum", "ustlenen", "notlar", "klip", "kare")


def api_v1(yol: str, q: dict):
    """Dönüş: ("json", veri) | ("csv", metin) | ("dosya", Path) | None."""
    import depo
    import rapor

    uc = yol[len("/api/v1"):].rstrip("/")
    if uc == "":
        return "json", {"uygulama": yollar.UYGULAMA, "surum": yollar.SURUM, "uclar": API_UCLARI}
    if uc == "/ozet":
        return "json", rapor.ozet(q)
    if uc in ("/olaylar", "/olaylar.csv"):
        d = rapor.olaylar({"sinir": 1000, **q})
        if uc == "/olaylar":
            return "json", d
        tampon = io.StringIO()
        yaz = csv.writer(tampon, delimiter=";", lineterminator="\n")
        yaz.writerow(CSV_ALANLARI)
        for o in d["olaylar"]:
            yaz.writerow(["" if o.get(a) is None else o[a] for a in CSV_ALANLARI])
        return "csv", tampon.getvalue()
    if uc.startswith("/olay/"):
        try:
            o = depo.sor("SELECT * FROM olay WHERE id = ?", int(uc[len("/olay/"):]))
        except ValueError:
            o = []
        return ("json", o[0]) if o else None
    if uc == "/rapor":
        return "json", rapor.rapor(q)
    if uc == "/analitik":
        return "json", rapor.analitik(q)
    if uc == "/kameralar":
        return "json", {"kameralar": rapor.kameralar()}
    if uc == "/gorevler":
        return "json", {"gorevler": rapor.gorevler()}
    if uc.startswith("/medya/"):
        hedef = (yollar.CIKTI / uc[len("/medya/"):]).resolve()
        if yollar.CIKTI.resolve() in hedef.parents and hedef.suffix.lower() in (".mp4", ".jpg"):
            return "dosya", hedef
    return None


# ---------------------------------------------------------------- HTTP


class Sunucu(ThreadingHTTPServer):
    allow_reuse_address = False  # Windows'ta aynı portu ikinci kez açmasın
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Istek(BaseHTTPRequestHandler):
    server_version = "YanginKamera"
    sys_version = ""

    def log_message(self, *a):  # konsolu istek satırlarıyla doldurma
        pass

    # --- yardımcılar
    def _izinli(self) -> bool:
        """Arayüz ve bütün işlemler yalnızca bu bilgisayardan."""
        port = self.server.server_address[1]
        izinli = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.client_address[0] not in ("127.0.0.1", "::1") or self.headers.get("Host", "") not in izinli:
            return False
        koken = self.headers.get("Origin")
        if self.command == "POST" and koken is not None and koken not in {f"http://{h}" for h in izinli}:
            return False
        return True

    def _anahtarli(self) -> bool:
        """Ağdaki başka bir sistem: yalnızca ağ erişimi açıksa ve doğru API anahtarını gönderiyorsa."""
        import depo

        g = depo.genel()
        anahtar = g.get("api_anahtari") or ""
        if not g.get("ag_erisimi") or len(anahtar) < 20:
            return False
        gelen = self.headers.get("X-API-Key") or ""
        yetki = self.headers.get("Authorization") or ""
        if not gelen and yetki.lower().startswith("bearer "):
            gelen = yetki[7:].strip()
        return hmac.compare_digest(gelen.encode("utf-8"), anahtar.encode("utf-8"))

    def _v1(self, yol: str, q: dict):
        r = api_v1(yol, q)
        if r is None:
            return self._json({"hata": "Bulunamadı."}, 404)
        if r[0] == "json":
            return self._json(r[1])
        if r[0] == "csv":
            return self._gonder(200, ("\ufeff" + r[1]).encode("utf-8"), "text/csv; charset=utf-8", {"Content-Disposition": 'attachment; filename="olaylar.csv"'})
        return self._dosya(r[1])

    def _gonder(self, kod: int, govde: bytes, tur: str, ek: dict | None = None):
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (ek or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(govde)

    def _json(self, veri, kod: int = 200):
        self._gonder(kod, json.dumps(veri, ensure_ascii=False).encode("utf-8"), TURLER[".json"])

    def _yok(self):
        self._gonder(404, "Bulunamadı".encode("utf-8"), "text/plain; charset=utf-8")

    def _dosya(self, yol: Path):
        if not yol.is_file():
            return self._yok()
        tur = TURLER.get(yol.suffix.lower()) or mimetypes.guess_type(yol.name)[0] or "application/octet-stream"
        boyut = yol.stat().st_size
        aralik = self.headers.get("Range")
        bas, son = 0, boyut - 1
        kod = 200
        m = re.match(r"bytes=(\d*)-(\d*)$", aralik or "")
        if m and boyut > 0 and (m.group(1) or m.group(2)):
            if m.group(1):
                bas = int(m.group(1))
                son = min(int(m.group(2)), boyut - 1) if m.group(2) else boyut - 1
            else:
                bas = max(0, boyut - int(m.group(2)))
            if bas > son or bas >= boyut:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{boyut}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            kod = 206
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(son - bas + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        if kod == 206:
            self.send_header("Content-Range", f"bytes {bas}-{son}/{boyut}")
        if yol.suffix.lower() == ".xlsx":
            self.send_header("Content-Disposition", f'attachment; filename="{yol.name}"')
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with open(yol, "rb") as f:
                f.seek(bas)
                kalan = son - bas + 1
                while kalan > 0:
                    parca = f.read(min(1 << 16, kalan))
                    if not parca:
                        break
                    self.wfile.write(parca)
                    kalan -= len(parca)
        except (ConnectionError, OSError):
            pass

    def _altinda(self, kok: Path, goreli: str):
        hedef = (kok / goreli).resolve()
        if kok.resolve() not in hedef.parents:
            return self._yok()
        return self._dosya(hedef)

    def _govde(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 5_000_000:
            raise ValueError("istek çok büyük")
        veri = self.rfile.read(n) if n else b"{}"
        return json.loads(veri.decode("utf-8") or "{}")

    # --- GET
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        ayrik = urlparse(self.path)
        yol = unquote(ayrik.path)
        q = dict(parse_qsl(ayrik.query))
        if not self._izinli():
            if yol.startswith("/api/v1") and self._anahtarli():
                try:
                    return self._v1(yol, q)
                except Exception:
                    traceback.print_exc(file=sys.__stderr__)
                    return self._json({"hata": "Beklenmeyen hata."}, 500)
            return self._gonder(403, b"Forbidden", "text/plain")
        try:
            return self._get(yol, q)
        except SystemExit as e:
            return self._json({"hata": str(e.code)}, 400)
        except Exception as e:
            traceback.print_exc(file=sys.__stderr__)
            return self._json({"hata": f"Beklenmeyen hata: {e}"}, 500)

    def _get(self, yol: str, q: dict):
        import depo
        import rapor

        if yol in ("/", "/index.html"):
            return self._dosya(yollar.WEB / "index.html")
        if yol.startswith("/web/"):
            return self._altinda(yollar.WEB, yol[len("/web/"):])
        if yol == "/favicon.ico":
            return self._dosya(yollar.WEB / "favicon.ico")
        if yol.startswith("/api/v1"):
            return self._v1(yol, q)
        if yol == "/api/durum":
            return self._json(durum())
        if yol == "/api/katalog":
            return self._json(katalog())
        if yol == "/api/ozet":
            return self._json(rapor.ozet(q))
        if yol == "/api/olaylar":
            return self._json(rapor.olaylar(q))
        if yol == "/api/analitik":
            return self._json(rapor.analitik(q))
        if yol == "/api/rapor":
            return self._json(rapor.rapor(q))
        if yol == "/api/gorevler":
            return self._json({"gorevler": rapor.gorevler()})
        if yol == "/api/rapor.xlsx":
            return self._dosya(rapor.excel())
        if yol.startswith("/api/olay/"):
            try:
                o = depo.sor("SELECT * FROM olay WHERE id = ?", int(yol[len("/api/olay/"):]))
            except ValueError:
                o = []
            if not o:
                return self._json({"hata": "Olay bulunamadı."}, 404)
            return self._json(o[0])
        if yol.startswith("/api/ayar/"):
            kod = yol[len("/api/ayar/"):]
            if not KOD_RE.match(kod) or not ayar_yolu(kod).exists():
                return self._json({"hata": "Ayar bulunamadı."}, 404)
            return self._json(json.loads(ayar_yolu(kod).read_text(encoding="utf-8")))
        if yol.startswith("/ayar/"):
            ad = yol[len("/ayar/"):]
            if re.match(r"^_kare_[a-z0-9_-]{1,40}\.jpg$", ad):  # yalnızca bölge çizme kareleri
                return self._dosya(yollar.AYAR / ad)
            return self._yok()
        if yol.startswith("/cikti/"):
            return self._altinda(yollar.CIKTI, yol[len("/cikti/"):])
        return self._yok()

    # --- POST
    def do_POST(self):
        if not self._izinli():
            return self._gonder(403, b"Forbidden", "text/plain")
        yol = urlparse(self.path).path
        try:
            g = self._govde()
        except Exception:
            return self._json({"hata": "İstek okunamadı."}, 400)
        try:
            return self._post(yol, g)
        except SystemExit as e:
            return self._json({"hata": str(e.code)}, 400)
        except Exception as e:
            traceback.print_exc(file=sys.__stderr__)
            return self._json({"hata": f"Beklenmeyen hata: {e}"}, 500)

    def _kod(self, g: dict) -> str:
        kod = str(g.get("kod", ""))
        if not KOD_RE.match(kod):
            raise SystemExit("Kısa kod yalnızca küçük harf (a-z), rakam, - ve _ içerebilir (ör. depo2).")
        return kod

    def _mesgul(self) -> bool:
        return AKTIF is not None and AKTIF.durum == "calisiyor"

    def _post(self, yol: str, g: dict):
        import depo

        if yol in ("/api/is/ornek", "/api/is/izle", "/api/is/video"):  # bağlantı denemesi modeli kullanmaz
            engel = _model_engeli()
            if engel:
                return self._json({"hata": engel}, 409)
        if yol == "/api/studio/kur":
            import studio_kurulum

            ok, m = is_baslat("studio-kurulum", "AugeLab Studio kurulumu", studio_kurulum.kur)
        elif yol == "/api/studio/lisans":
            import studio
            import studio_kurulum

            if self._mesgul():
                return self._json({"hata": "Çalışan işlem bitince lisans kodunu girin."}, 409)
            try:
                studio_kurulum.lisans_kaydet(str(g.get("kod") or ""))  # kod saklanmaz, günlüğe yazılmaz
            except SystemExit as e:
                return self._json({"hata": str(e.code or "Lisans kodu kaydedilemedi.")}, 400)
            studio.kaydet(lisans=time.time(), hazir=None)
            _STUDIO["an"] = 0.0
            ok, m = is_baslat("studio-dene", "AugeLab Studio lisans kontrolü", is_studio_dene)
        elif yol == "/api/studio/dene":
            ok, m = is_baslat("studio-dene", "AugeLab Studio lisans kontrolü", is_studio_dene)
        elif yol == "/api/model/indir":  # arka planda indirilir; panelin işlerini bekletmez (ilerleme /api/durum'da)
            import studio_kurulum

            ok, m = studio_kurulum.model_indirmeyi_baslat()
        elif yol == "/api/is/ornek":
            ok, m = is_baslat("ornek", "Örnek analiz", is_ornek)
        elif yol in ("/api/is/test", "/api/is/izle", "/api/is/video"):
            kod = self._kod(g)
            if not ayar_yolu(kod).exists():
                return self._json({"hata": f"Ayar bulunamadı: {kod}"}, 404)
            sifre = g.get("sifre")
            sifre = str(sifre) if sifre is not None else None
            ad = ayar_oku(kod).get("ad", kod)
            if yol == "/api/is/test":
                ok, m = is_baslat("test", f"Bağlantı denemesi · {ad}", is_test, kod, sifre)
            elif yol == "/api/is/video":
                ok, m = is_baslat("video", f"Video analizi · {ad}", is_video, kod)
            else:
                try:
                    dakika = min(240.0, max(0.25, float(g.get("dakika", 5))))
                except (TypeError, ValueError):
                    dakika = 5.0
                ok, m = is_baslat("izle", f"İzleme · {ad}", is_izle, kod, sifre, dakika)
        elif yol == "/api/is/durdur":
            if self._mesgul():
                AKTIF.dur.set()
                print(f"Durdurma istendi: {AKTIF.baslik}", flush=True)
            return self._json({"tamam": True})
        elif yol == "/api/olay/durum":
            durum_ = str(g.get("durum", ""))
            if durum_ not in ("acik", "ustlenildi", "cozuldu", "yanlis"):
                return self._json({"hata": "Bilinmeyen durum."}, 400)
            kimlikler = [int(x) for x in (g.get("idler") or [g.get("id")]) if x is not None]
            for kimlik in kimlikler:
                depo.yaz("UPDATE olay SET durum = ?, ustlenen = COALESCE(?, ustlenen), notlar = COALESCE(?, notlar), durum_zamani = ? WHERE id = ?",
                         durum_, (str(g["ustlenen"])[:80] if g.get("ustlenen") else None), (str(g["not"])[:2000] if g.get("not") is not None else None),
                         depo.simdi(), kimlik)
            return self._json({"tamam": True})
        elif yol == "/api/gorev":
            baslik = str(g.get("baslik", "")).strip()[:200]
            if not baslik:
                return self._json({"hata": "Görevin başlığı yazılmamış."}, 400)
            durum_ = str(g.get("durum", "acik"))
            if durum_ not in ("acik", "suruyor", "kapandi"):
                return self._json({"hata": "Bilinmeyen durum."}, 400)
            alan = {"baslik": baslik, "aciklama": str(g.get("aciklama") or "")[:4000], "sorumlu": str(g.get("sorumlu") or "")[:80],
                    "son_tarih": (str(g["son_tarih"])[:10] if g.get("son_tarih") else None), "durum": durum_,
                    "kamera": g.get("kamera") or None, "kural": g.get("kural") or None, "bolge": g.get("bolge") or None}
            if g.get("id"):
                kimlik = int(g["id"])
                eski = depo.sor("SELECT durum, kapanma FROM gorev WHERE id = ?", kimlik)
                if not eski:
                    return self._json({"hata": "Görev bulunamadı."}, 404)
                kapanma = eski[0]["kapanma"] if durum_ == "kapandi" and eski[0]["durum"] == "kapandi" else (depo.simdi() if durum_ == "kapandi" else None)
                depo.yaz("UPDATE gorev SET baslik=?, aciklama=?, sorumlu=?, son_tarih=?, durum=?, kamera=?, kural=?, bolge=?, kapanma=? WHERE id=?",
                         *alan.values(), kapanma, kimlik)
            else:
                kimlik = depo.ekle("gorev", {**alan, "olusturma": depo.simdi(), "kapanma": depo.simdi() if durum_ == "kapandi" else None})
            for o in g.get("olaylar") or []:
                depo.yaz("INSERT OR IGNORE INTO gorev_olay (gorev, olay) VALUES (?, ?)", kimlik, int(o))
                depo.yaz("UPDATE olay SET durum = 'ustlenildi', ustlenen = COALESCE(NULLIF(?, ''), ustlenen), durum_zamani = ? WHERE id = ? AND durum = 'acik'",
                         alan["sorumlu"], depo.simdi(), int(o))
            return self._json({"tamam": True, "id": kimlik})
        elif yol == "/api/gorev/sil":
            depo.yaz("DELETE FROM gorev_olay WHERE gorev = ?", int(g.get("id", 0)))
            depo.yaz("DELETE FROM gorev WHERE id = ?", int(g.get("id", 0)))
            return self._json({"tamam": True})
        elif yol == "/api/genel":
            yeni = {}
            if isinstance(g.get("tesis"), str):
                yeni["tesis"] = g["tesis"].strip()[:80] or "Tesis"
            if isinstance(g.get("vardiyalar"), list):
                vs = []
                for v in g["vardiyalar"][:6]:
                    if re.match(r"^\d\d:\d\d$", str(v.get("bas", ""))) and re.match(r"^\d\d:\d\d$", str(v.get("bit", ""))) and str(v.get("ad", "")).strip():
                        vs.append({"ad": str(v["ad"]).strip()[:30], "bas": v["bas"], "bit": v["bit"]})
                if vs:
                    yeni["vardiyalar"] = vs
            if isinstance(g.get("baglantilar"), list):
                import baglanti

                yeni["baglantilar"] = [baglanti.temizle(x) for x in g["baglantilar"][:20] if isinstance(x, dict)]
            if "ag_erisimi" in g:
                yeni["ag_erisimi"] = bool(g["ag_erisimi"])
                if yeni["ag_erisimi"] and not depo.genel().get("api_anahtari"):
                    yeni["api_anahtari"] = secrets.token_urlsafe(32)
            if g.get("anahtar_yenile"):
                yeni["api_anahtari"] = secrets.token_urlsafe(32)
            depo.genel_yaz(yeni)
            return self._json({"tamam": True, "genel": depo.genel()})
        elif yol == "/api/baglanti/dene":
            import baglanti

            tamam, mesaj = baglanti.dene(baglanti.temizle(g.get("baglanti") or {}))
            return self._json({"tamam": tamam, "mesaj": mesaj})
        elif yol == "/api/onvif/kesfet":  # ağdaki ONVIF kameraları ve kayıt cihazları (şifre gerekmez)
            import onvif_istemci

            return self._json({"cihazlar": onvif_istemci.kesfet(3.0)})
        elif yol == "/api/onvif/profiller":  # cihazın kanalları ve profilleri; şifre yalnızca bu istekte kullanılır, saklanmaz
            import onvif_istemci

            try:
                cihaz = onvif_istemci.Cihaz(str(g.get("ip") or "").strip(), int(g.get("port") or 80), str(g.get("kullanici") or "admin"), str(g.get("sifre") or ""))
                profiller = cihaz.profiller()
                return self._json({"cihaz": cihaz.bilgi(), "profiller": profiller})
            except (onvif_istemci.OnvifHatasi, ValueError) as e:
                return self._json({"hata": str(e)}, 400)
        elif yol == "/api/ayar/kanallar":  # kayıt cihazının kanalları ayrı kameralar olarak: ya hepsi eklenir ya hiçbiri
            try:
                return self._json({"tamam": True, **kameralari_olustur(kanal_ayarlari(g.get("taban"), g.get("kanallar"), g.get("profiller")))})
            except AyarHatasi as e:
                return self._json({"hata": str(e)}, 400)
        elif yol == "/api/ayar":
            try:
                if g.get("yeni"):  # yalnızca yeni kamera: var olanın üstüne yazılmaz
                    sonuc = kameralari_olustur([g.get("ayar")])
                    return self._json({"tamam": True, "kod": sonuc["kodlar"][0], "notlar": sonuc["notlar"]})
                kod, ayar, notlar = _ayar_hazirla(g.get("ayar"))
            except AyarHatasi as e:
                return self._json({"hata": str(e)}, 400)
            with _AYAR_KILIDI:
                yollar.AYAR.mkdir(parents=True, exist_ok=True)
                ayar_yolu(kod).write_text(json.dumps(ayar, ensure_ascii=False, indent=1), encoding="utf-8")
            return self._json({"tamam": True, "kod": kod, "notlar": notlar})
        elif yol == "/api/ayar/sil":
            kod = self._kod(g)
            if self._mesgul():
                return self._json({"hata": "Önce çalışan işi bitirin ya da durdurun."}, 409)
            if kod not in yollar.ornek_kodlar():  # örnek kameranın ayarı kalır; olayları ve klipleri silinir
                ayar_yolu(kod).unlink(missing_ok=True)
                (yollar.AYAR / f"_kare_{kod}.jpg").unlink(missing_ok=True)
            depo.kamera_sil(kod)
            shutil.rmtree(yollar.CIKTI / kod, ignore_errors=True)
            return self._json({"tamam": True})
        elif yol == "/api/klasor":
            if hasattr(os, "startfile"):
                os.startfile(str(yollar.VERI))  # noqa: S606 - yalnızca kendi veri klasörümüz
            return self._json({"tamam": True})
        elif yol == "/api/kapat":
            self._json({"tamam": True})
            if AKTIF is not None:
                AKTIF.dur.set()
            threading.Thread(target=kapat, args=(self.server,), daemon=True).start()
            return None
        else:
            return self._json({"hata": "Bilinmeyen istek."}, 404)
        if not ok:
            return self._json({"hata": m}, 409)
        if yol in ("/api/is/test", "/api/is/izle", "/api/is/video") and AKTIF is not None:
            AKTIF.kod = kod
        return self._json({"tamam": True, "is": AKTIF.ozet() if AKTIF else None})


def kapanis_temizligi(is_bekle_sn: float = 20.0) -> None:
    """Program kapanırken: süren işi durdurur ve (sınırlı süre) bitmesini bekler; iş sahnesini durdurup kuyruğun son
    kayıtlarını alabilsin ve açık olayları kapatabilsin. Sonra arkada kalan arayüzsüz Studio süreçlerini kapatır. İlk andan
    itibaren yeni iş kabul edilmez (iş beklenirken sunucu istekleri yanıtlamayı sürdürebilir)."""
    with IS_KILIDI:
        KAPANIYOR.set()
        is_ = AKTIF
    if is_ is not None and is_.durum == "calisiyor":
        is_.dur.set()
        son = time.monotonic() + is_bekle_sn
        while is_.durum == "calisiyor" and time.monotonic() < son:
            time.sleep(0.3)
    try:
        import studio

        studio.durdur_hepsi()  # arayüzsüz Studio süreçleri arkada kalmasın
    except Exception:
        pass


def kapat(sunucu) -> None:
    time.sleep(0.4)
    print("Yangın Kamera kapatılıyor.", flush=True)
    kapanis_temizligi()
    sunucu.shutdown()


# ---------------------------------------------------------------- başlatma


def calisiyor_mu(port: int) -> bool:
    """Bu portta zaten bir Yangın Kamera çalışıyor mu?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/durum", timeout=2) as r:
            return json.loads(r.read().decode("utf-8")).get("uygulama") == yollar.UYGULAMA
    except Exception:
        return False


def splash_kapat() -> None:
    try:
        import pyi_splash  # yalnızca exe'de var

        pyi_splash.close()
    except Exception:
        pass


def isin() -> None:
    """Ağır kütüphaneleri arka planda yükle; ilk iş daha çabuk başlasın."""
    try:
        import kamera  # noqa: F401
        import kuyruk  # noqa: F401
    except Exception:
        traceback.print_exc(file=sys.__stderr__)


def main() -> None:
    ap = argparse.ArgumentParser(prog=yollar.UYGULAMA, description="Yangın ve duman kamera alarmı: yerel sunucu")
    ap.add_argument("--port", type=int, default=VARSAYILAN_PORT)
    ap.add_argument("--tarayici-yok", action="store_true", help="tarayıcıyı açma")
    a = ap.parse_args()

    if calisiyor_mu(a.port):
        splash_kapat()
        url = f"http://127.0.0.1:{a.port}/"
        print(f"Yangın Kamera zaten çalışıyor: {url}")
        if not a.tarayici_yok:
            webbrowser.open(url)
        time.sleep(2)
        return

    sys.stdout, sys.stderr = YON_OUT, YON_ERR
    print(f"Yangın Kamera {yollar.SURUM}")
    if yollar.hazirla():
        print("İlk kurulum: veri klasörü hazırlandı.")
    if yollar.DONDURULMUS:  # algılama modeli arka planda bir kez SHA-256 ile doğrulanır; yoksa ya da bozuksa indirilir
        import studio_kurulum

        studio_kurulum.model_indirmeyi_baslat()
    import depo

    depo.vt()

    ag = bool(depo.genel().get("ag_erisimi")) and len(depo.genel().get("api_anahtari") or "") >= 20
    dinle = "0.0.0.0" if ag else "127.0.0.1"
    sunucu = None
    for port in [a.port] + list(range(a.port + 1, a.port + 25)):
        try:
            sunucu = Sunucu((dinle, port), Istek)
            break
        except OSError:
            if calisiyor_mu(port):
                splash_kapat()
                print(f"Yangın Kamera zaten çalışıyor: http://127.0.0.1:{port}/")
                if not a.tarayici_yok:
                    webbrowser.open(f"http://127.0.0.1:{port}/")
                time.sleep(2)
                return
    if sunucu is None:
        splash_kapat()
        print("Boş port bulunamadı.")
        time.sleep(5)
        raise SystemExit(1)
    port = sunucu.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    DINLENEN.update(adres=dinle, port=port)
    if ag:
        try:
            DINLENEN["ag"] = sorted({b[4][0] for b in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET) if not b[4][0].startswith("127.")})
        except OSError:
            pass
        print("  Ağ erişimi AÇIK: ağdaki sistemler API anahtarıyla /api/v1/... adreslerini okuyabilir (arayüz yine yalnızca bu bilgisayardan).")
    print(f"  Adres   : {url}")
    print(f"  Veriler : {yollar.VERI}")
    print("Kapatmak için bu pencereyi kapatın (ya da Ayarlar sayfasındaki Kapat düğmesine basın).\n", flush=True)
    threading.Thread(target=isin, daemon=True).start()
    import kuyruk

    kuyruk_dur = threading.Event()
    threading.Thread(target=kuyruk.surekli, args=(kuyruk_dur, _bildir), name="kuyruk", daemon=True).start()
    splash_kapat()
    if not a.tarayici_yok:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        sunucu.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        sunucu.server_close()
    kapanis_temizligi()  # süren iş durdurulup beklenir, arayüzsüz Studio süreçleri kapatılır


if __name__ == "__main__":
    main()
