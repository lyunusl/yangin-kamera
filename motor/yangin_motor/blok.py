"""AugeLab Studio bloklarının çağırdığı işlevler.

Bloklar incedir: görüntüyü ve kamera kodunu bu işlevlere verir. Motor klasörü (yangin_engine) Studio'nun özel blok
klasörünün yanındadır ve şunları içerir:

  yangin_motor/   bu paket
  modeller/       model dosyası ya da korumalı paket girdileri
  deps/           Studio'da olmayan kütüphaneler (onnxruntime)
  ayar.json       {"veri": "<panelin veri klasörü>"}  (kamera ayarları, kuyruk ve klipler orada)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time

import cv2
import numpy as np

from . import katalog, model_lisans
from .algila import Algilayici
from .kayit import Kayitci, ciz, kuyruga_birak
from .kural import Motor

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_YOLU = os.path.join(KOK, "modeller", katalog.MODEL_DOSYASI)
# Arayüzsüz koşu (python -m studio run): panel her kamera için sahne şablonunu ayrı bir süreçte çalıştırır ve kameranın
# kimliğini bu ortam değişkenleriyle verir. Şablondaki "Yangın Kamera Kodu" girişi o zaman yok sayılır.
ORTAM_KAMERA = "YANGIN_KAMERA"        # "kod#koşu"
ORTAM_ADRES = "YANGIN_KAMERA_ADRES"   # canlı kameranın akış adresi (şifre içerebilir: dosyaya yazılmaz)
ORTAM_DUR = "YANGIN_DUR"              # bu dosya oluşunca akış biter: açık olaylar kapanış kaydı bırakır
ORTAM_DENEME_SONUC = "YANGIN_DENEME_SONUC"  # deneme koşusunda modelin açılıp açılmadığı bu dosyaya yazılır
DENEME_KOD = "_deneme"                # panelin lisans kontrolü: kamera yok, siyah kare ile model (ve lisans) sınanır
ANALIZ_ARALIGI = 0.5   # saniye: kareler en çok bu sıklıkla analiz edilir (işlemcide bir analiz yaklaşık 0,25 sn sürer)
ANALIZ_DINLENME = 0.1  # saniye: canlı akışta bir analiz bittikten sonra en az bu kadar beklenir (yavaş bilgisayar kilitlenmesin)
OLCUM_ARALIGI = 30.0   # saniye: ısı haritası ve sayılar bu aralıkla panele bırakılır
CANLI_KLIP_HIZI = 8.0  # canlı akışta klibin saniyedeki kare sayısı


def _hata_json(neden: str) -> str:
    """Tespit çalışmadığında "tespitler" yerine verilen değer. Boş liste "alev ve duman yok" demektir; bu ise "bilinmiyor"
    demektir: Yangın Kurallar bu karede kural değerlendirmez, olay kaydetmez ve panele hata bırakır."""
    return json.dumps({"hata": neden}, ensure_ascii=False)


def _tespit_json(sira: int, tespitler: list) -> str:
    """`sira`: analizin sıra numarası. Aradaki (analiz edilmeyen) karelerde aynı değer yinelenir; Yangın Kurallar
    numara değişmediyse kuralları yeniden değerlendirmez."""
    return json.dumps({"sira": sira, "tespitler": tespitler})


def kod_ve_kosu(kamera_kod) -> tuple[str, str]:
    """Kamera girişi "kod" ya da "kod#koşu" biçimindedir; koşu değişince bloklar baştan başlar.
    Arayüzsüz koşuda kamera ortam değişkeninden gelir ve girişteki değerin yerini alır."""
    kamera_kod = os.environ.get(ORTAM_KAMERA) or kamera_kod
    kod, _, kosu = str(kamera_kod or "").strip().partition("#")
    return kod.strip(), kosu


def veri_klasoru() -> str:
    with open(os.path.join(KOK, "ayar.json"), encoding="utf-8") as f:
        return json.load(f)["veri"]


def kamera_ayari(kod: str) -> tuple[dict, float]:
    yol = os.path.join(veri_klasoru(), "ayar", f"{kod}.json")
    with open(yol, encoding="utf-8") as f:
        return json.load(f), os.path.getmtime(yol)


def _goruntu(image) -> np.ndarray | None:
    if image is None:
        return None
    a = np.asarray(image)
    if a.ndim == 2:
        a = cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)
    elif a.ndim == 3 and a.shape[2] == 4:
        a = a[:, :, :3]
    return np.ascontiguousarray(a) if a.ndim == 3 and a.size else None


def _saniye(zaman) -> float | None:
    """Zaman girişi: saniye (video dosyası) ya da None (canlı akış: -1, boş ya da bağlı değil)."""
    try:
        t = float(zaman) if zaman is not None and str(zaman) != "" else None
    except (TypeError, ValueError):
        t = None
    return t if t is not None and t >= 0 else None


def _bos_kare(state: dict, sinir: int = 10) -> bool:
    """Arka arkaya `sinir` kez görüntü gelmediyse True (bir kez): akış bitmiş sayılır, blok modelini bellekten bırakır."""
    state["bos"] = state.get("bos", 0) + 1
    return state["bos"] == sinir


class _CanliOkuyucu:
    """Canlı akışı arka planda okur ve yalnızca son kareyi tutar: kareler kuyrukta birikmez, analiz hep en yeni kareyle
    yapılır. Bağlantı koparsa birkaç saniyede bir yeniden bağlanır."""

    def __init__(self, adres: str):
        import threading

        self.adres, self.kare, self.sira, self.durum = adres, None, 0, "bekliyor: kameraya bağlanılıyor"
        self._dur = threading.Event()
        self._kilit = threading.Lock()
        threading.Thread(target=self._oku, name="yangin-canli", daemon=True).start()

    def _oku(self) -> None:
        bekle = 1.0
        while not self._dur.is_set():
            cap = cv2.VideoCapture(self.adres, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap.release()
                self.durum = "bekliyor: kameraya bağlanılamadı, yeniden deneniyor"
                self._dur.wait(bekle)
                bekle = min(10.0, bekle * 2)
                continue
            bekle = 1.0
            while not self._dur.is_set():
                ok, fr = cap.read()
                if not ok:
                    self.durum = "bekliyor: görüntü kesildi, yeniden bağlanılıyor"
                    break
                with self._kilit:
                    self.kare, self.sira = fr, self.sira + 1
            cap.release()

    def son(self):
        with self._kilit:
            return self.kare, self.sira

    def kapat(self) -> None:
        self._dur.set()


def _durduruldu() -> bool:
    """Panel arayüzsüz koşuyu durdururken önce bu dosyayı oluşturur: akış "bitti" olur, açık olaylar kapanır."""
    dur = os.environ.get(ORTAM_DUR)
    return bool(dur) and os.path.exists(dur)


def _video_ac(state: dict, kod: str, kosu: str) -> str | None:
    """Kaynağı açar. Dönüş: hata durumu ya da None."""
    state["kosu"] = kosu
    try:
        ayar, _ = kamera_ayari(kod)
    except Exception as e:
        return f"hata: kamera ayarı okunamadı ({kod}): {e}"
    kamera = ayar.get("kamera") or {}
    if kamera.get("tur") in ("rtsp", "onvif", "http"):
        adres = os.environ.get(ORTAM_ADRES, "")
        if not adres:
            return "hata: kameranın akış adresi verilmedi (sahneyi Yangın Kamera paneli başlatır)"
        state.update(kod=kod, canli=_CanliOkuyucu(adres), sira=0, n=0, bitti=False)
        return None
    if kamera.get("tur") != "dosya":
        return "hata: bu kamera türü Yangın Video ile okunamıyor"
    yol = kamera.get("yol", "")
    yol = yol if os.path.isabs(yol) else os.path.join(veri_klasoru(), yol)
    cap = cv2.VideoCapture(yol)
    if not cap.isOpened():
        return f"hata: video açılamadı: {os.path.basename(yol)}"
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    state.update(kod=kod, cap=cap, fps=fps if 1 <= fps <= 120 else 25.0, n=0, toplam=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), bitti=False)
    return None


def _video_kapat(state: dict) -> None:
    if state.get("cap") is not None:
        state["cap"].release()
    if state.get("canli") is not None:
        state["canli"].kapat()
    state.clear()


def video(state: dict, kamera_kod: str):
    """Yangın Video bloğu: kameranın ayarındaki video dosyasını kare kare okur. Arayüzsüz koşuda canlı kameranın akışını da
    okur (adres ortam değişkeninden gelir).
    Dönüş: (görüntü | None, zaman (sn; canlı akışta -1: duvar saati kullanılır), bitti, durum). Dosya bitince ya da panel
    durdurunca bir kez bitti=True döner, sonra görüntü vermez."""
    kod, kosu = kod_ve_kosu(kamera_kod)
    if kod == DENEME_KOD:  # deneme koşusu: modeli sınamak için siyah bir kare yeter
        return np.zeros((360, 640, 3), np.uint8), -1.0, False, "ok deneme karesi"
    if state.get("kod") != kod or state.get("kosu") != kosu:
        _video_kapat(state)
        hata = _video_ac(state, kod, kosu)
        if hata:
            return None, 0.0, False, hata
    canli = state.get("canli")
    if state["bitti"]:
        return None, -1.0 if canli else state["n"] / state["fps"], False, f"bitti: {state['n']} kare"
    if _durduruldu():
        state["bitti"] = True
        if canli:
            canli.kapat()
        else:
            state["cap"].release()
        return None, -1.0 if canli else state["n"] / state["fps"], True, f"bitti: durduruldu, {state['n']} kare"
    if canli:
        kare, sira = canli.son()
        if kare is None or sira == state["sira"]:
            return None, -1.0, False, canli.durum if kare is None else "ok: yeni kare bekleniyor"
        state["sira"] = sira
        state["n"] += 1
        return kare, -1.0, False, f"ok {state['n']} kare"
    ok, fr = state["cap"].read()
    if not ok:
        state["bitti"] = True
        state["cap"].release()
        return None, state["n"] / state["fps"], True, f"bitti: {state['n']} kare"
    t = state["n"] / state["fps"]
    state["n"] += 1
    return fr, t, False, f"ok {state['n']}" + (f" / {state['toplam']}" if state["toplam"] > 0 else "") + " kare"


def algila(state: dict, image, kamera_kod: str, zaman=None) -> tuple[str, str]:
    """Yangın Algılama bloğu. Kareleri en çok ANALIZ_ARALIGI sıklıkla analiz eder (video dosyasında videonun zamanına,
    canlı akışta duvar saatine göre); aradaki karelerde son tespitleri yineler. Dönüş: (tespitler JSON, durum)."""
    fr = _goruntu(image)
    if fr is None:
        if _bos_kare(state):
            state.pop("algilayici", None)  # akış bitti: model bellekten bırakılır, görüntü yeniden gelirse baştan yüklenir
        return state.get("son_json") or _tespit_json(0, []), "bekliyor: görüntü yok"
    state["bos"] = 0
    kod, kosu = kod_ve_kosu(kamera_kod)
    if kod == DENEME_KOD:
        return _model_deneme(state, fr)
    try:
        ayar, _ = kamera_ayari(kod)
    except Exception as e:
        return _hata_json(f"kamera ayarı okunamadı ({kod})"), f"hata: kamera ayarı okunamadı ({kod}): {e}"
    if state.get("kosu") != kosu:  # yeni çalıştırma: analiz sayacı ve zamanlaması baştan
        state.update(kosu=kosu, sira=0, son_analiz=None, son_bitis=None, son_json=None)
    t = _saniye(zaman)
    canli = t is None
    if canli:
        t = time.monotonic()
    son = state.get("son_analiz")
    if state.get("son_json") is not None and son is not None and 0 <= t - son < ANALIZ_ARALIGI - 1e-3:
        return state["son_json"], state.get("son_durum", "ok")
    if canli and state.get("son_json") is not None and state.get("son_bitis") is not None and 0 <= t - state["son_bitis"] < ANALIZ_DINLENME:
        return state["son_json"], state.get("son_durum", "ok")
    if state.get("algilayici") is None:
        try:
            state["algilayici"] = Algilayici(MODEL_YOLU, veri_klasoru())
        except model_lisans.LisansHatasi as e:
            return _hata_json(str(e)), f"hata: {e}"
        except Exception as e:
            return _hata_json(f"model yüklenemedi: {e}"), f"hata: model yüklenemedi: {type(e).__name__}: {e}"
    t0 = time.perf_counter()
    try:
        tespitler = state["algilayici"].calistir(fr, katalog.esikler(ayar))
    except model_lisans.LisansHatasi as e:
        state.pop("algilayici", None)
        return _hata_json(str(e)), f"hata: {e}"
    except Exception as e:
        return _hata_json(f"tespit çalışmadı: {type(e).__name__}"), f"hata: tespit çalışmadı: {type(e).__name__}: {e}"
    state["sira"] = state.get("sira", 0) + 1
    state["son_analiz"] = t
    state["son_bitis"] = time.monotonic()
    state["son_json"] = _tespit_json(state["sira"], tespitler)
    alev = sum(1 for d in tespitler if d["s"] == "alev")
    state["son_durum"] = (f"ok {alev} alev, {len(tespitler) - alev} duman · {1000 * (time.perf_counter() - t0):.0f} ms · "
                          f"{state['algilayici'].ozet()}")
    return state["son_json"], state["son_durum"]


def _model_deneme(state: dict, fr) -> tuple[str, str]:
    """Lisans kontrolü: modeli açıp bir kare çalıştırır (korumalı pakette AugeLab Studio lisansı burada doğrulanır) ve
    sonucu ORTAM_DENEME_SONUC dosyasına bir kez yazar. Kamera ayarı gerekmez."""
    if state.get("deneme_yazildi"):
        return _tespit_json(0, []), state.get("deneme_durum", "deneme bitti")
    sonuc = {"ok": False, "hata": ""}
    try:
        algilayici = Algilayici(MODEL_YOLU, veri_klasoru())
        algilayici.calistir(fr)
        sonuc = {"ok": True, "ozet": algilayici.ozet()}
    except model_lisans.LisansHatasi as e:
        sonuc["hata"] = f"lisans: {e}"
    except Exception as e:  # model dosyası yok, paket açılamadı, onnxruntime yüklenemedi...
        sonuc["hata"] = f"{type(e).__name__}: {e}"
    yol = os.environ.get(ORTAM_DENEME_SONUC)
    if yol:
        try:
            with open(yol, "w", encoding="utf-8") as f:
                json.dump(sonuc, f, ensure_ascii=False)
        except OSError:
            pass
    state["deneme_yazildi"] = True
    state["deneme_durum"] = "ok model açıldı" if sonuc["ok"] else f"hata: {sonuc['hata']}"
    return _tespit_json(0, []), state["deneme_durum"]


def _kur(state: dict, kod: str, ayar: dict, degisim: float, W: int, H: int) -> None:
    kamera = ayar.get("kamera") or {}
    bas = dt.datetime.now().replace(microsecond=0)
    if kamera.get("tur") == "dosya" and kamera.get("baslangic"):
        try:
            bas = dt.datetime.fromisoformat(kamera["baslangic"])
        except ValueError:
            pass
    kayitci = Kayitci(veri_klasoru(), kod, ayar.get("ad", kod), W, H, CANLI_KLIP_HIZI)
    kayitci.kosu = state.get("kosu") or ""
    state.update(kod=kod, degisim=degisim, boyut=(W, H), n=0, t0=time.monotonic(), son_t=None, son_olcum=0.0, son_cizili=None,
                 son_sira=None, motor=Motor(ayar, W, H, bas), kayitci=kayitci, ayar=ayar)


def _bitir(state: dict, isaret: bool = True) -> None:
    motor, kayitci = state.get("motor"), state.get("kayitci")
    if motor is None:
        return
    if kayitci is not None:
        kayitci.bitir(motor.kapat(), isaret)
        if state.get("son_cizili") is not None:
            kayitci.son_kare(state["son_cizili"], zorla=True)
        o = motor.olcum()
        if o is not None:
            kayitci.olcum(o)
    state["motor"] = None


def kurallar(state: dict, image, tespit_json: str, kamera_kod: str, zaman=None, bitti: bool = False):
    """Yangın Kurallar bloğu. `zaman`: görüntünün saniye cinsinden zamanı (video dosyasında Yangın Video bloğundan gelir;
    canlı akışta duvar saati kullanılır). `bitti`: akış bitti, açık olayları kapat.
    Dönüş: (işaretli görüntü, alarm, risk puanı, başlayan olaylar JSON, durum, yeni olay var mı, alarm yazılsın mı).
    "alarm yazılsın mı": alarm durumu değiştiğinde ve beş saniyede bir True olur; Studio'da bir yazma bloğunun Enable
    girişine bağlanırsa çıkışa her karede değil yalnızca gerektiğinde yazılır."""
    if bitti:  # akış bitti: motor henüz kurulmamış olsa da görüntü çıkışı boş kalır
        if state.get("motor") is None:
            return None, False, 0, "[]", "bitti: akış kapandı", False, False
        _bitir(state)
        state["son_alarm"] = False
        return None, False, 0, "[]", "bitti: akış kapandı", False, True  # alarm kapalı olarak bir kez yazılır
    fr = _goruntu(image)
    if fr is None:
        return image, False, 0, "[]", "bekliyor: görüntü yok", False, False
    kod, kosu = kod_ve_kosu(kamera_kod)
    if kod == DENEME_KOD:
        return fr, False, 0, "[]", "ok deneme", False, False
    if state.get("kosu") != kosu:  # yeni çalıştırma: önceki akıştan kalanı kapat, baştan başla
        _bitir(state, isaret=False)
        state["kosu"] = kosu
    try:
        ayar, degisim = kamera_ayari(kod)
    except Exception as e:
        return fr, False, 0, "[]", f"hata: kamera ayarı okunamadı ({kod}): {e}", False, False
    H, W = fr.shape[:2]
    if state.get("motor") is None or state.get("kod") != kod or state.get("degisim") != degisim or state.get("boyut") != (W, H):
        _bitir(state, isaret=False)
        _kur(state, kod, ayar, degisim, W, H)
    motor, kayitci = state["motor"], state["kayitci"]
    try:
        veri = json.loads(tespit_json) if tespit_json else []
    except ValueError:
        veri = {"hata": "tespitler okunamadı"}
    if isinstance(veri, dict) and isinstance(veri.get("tespitler"), list):
        tespitler, sira = veri["tespitler"], veri.get("sira")
    elif isinstance(veri, list):  # sıra numarası yok: her kare yeni analiz sayılır
        tespitler, sira = veri, None
    else:
        # Tespit çalışmıyor (model dosyası yok, yüklenemedi, lisans yok). Bu "alev ve duman yok" sayılmaz: kural
        # değerlendirilmez, olay kaydedilmez; panel işi hatayla durdurur.
        neden = str(veri.get("hata") or "bilinmiyor") if isinstance(veri, dict) else "tespitler okunamadı"
        if time.monotonic() - state.get("hata_kaydi", 0.0) >= 5.0:
            state["hata_kaydi"] = time.monotonic()
            try:
                kuyruga_birak(veri_klasoru(), kod, {"tur": "hata", "kamera": kod, "kosu": kosu, "metin": neden})
            except OSError:
                pass
        return fr, False, 0, "[]", f"hata: tespit çalışmıyor: {neden}", False, False
    yeni = sira is None or sira != state["son_sira"]
    state["son_sira"] = sira
    t = _saniye(zaman)
    canli = t is None
    if canli:  # canlı akış (Yangın Video -1 verir) ya da zaman girişi bağlı değil: duvar saati
        t = time.monotonic() - state["t0"]
    if state["son_t"] is not None and t > state["son_t"]:  # gerçek kare aralığının yumuşatılmış ortalaması
        aralik = min(1.0, max(0.02, t - state["son_t"]))
        motor.aralik = aralik if state["n"] == 1 else 0.9 * motor.aralik + 0.1 * aralik
        if state["n"] == 1 and not canli:  # video dosyası: klip, videonun kendi hızında yazılır
            kayitci.hiz_ayarla(1.0 / aralik)
    state["son_t"] = t
    state["n"] += 1
    if time.monotonic() - state.get("nabiz", 0.0) >= 5.0:  # panel, sahnenin çalıştığını bu kayıttan anlar
        state["nabiz"] = time.monotonic()
        kayitci._birak({"tur": "nabiz", "kamera": kod, "kare": state["n"]})
    sonuc = motor.adim(t, tespitler, yeni)
    an = (motor.bas_zaman + dt.timedelta(seconds=t)).strftime("%d.%m.%Y %H:%M:%S")
    acik = sonuc["acik"]
    ust = " · ".join(dict.fromkeys(o["k"]["ad"] for o in acik))
    cizili = ciz(fr.copy(), sonuc, motor.bolgeler, ust, f"{ayar.get('ad', kod)} · {an}")
    kayitci.kare(t, cizili, sonuc)
    state["son_cizili"] = cizili
    if t - state["son_olcum"] >= OLCUM_ARALIGI:
        state["son_olcum"] = t
        o = motor.olcum()
        if o is not None:
            kayitci.olcum(o)
    # Alarm, önemi eşiğin üstünde bir olay sürdüğü sürece açıktır (olay başlar başlamaz); risk puanı süreyle büyür.
    esik = int(ayar.get("alarm_en_az_onem", 4))
    risk = max((o["puan"] for o in sonuc["suren"]), default=0)
    alarm = any(o["onem"] >= esik for o in sonuc["suren"])
    gecerli = [d for d in sonuc["tespitler"] if not d.get("izinli")]
    alev = sum(1 for d in gecerli if d["s"] == "alev")
    durum = f"ok {alev} alev, {len(gecerli) - alev} duman, {len(acik)} açık olay · {an}"
    simdi = time.monotonic()
    yaz = bool(alarm) != bool(state.get("son_alarm")) or simdi - state.get("son_yazma", 0.0) >= 5.0
    if yaz:
        state["son_alarm"], state["son_yazma"] = bool(alarm), simdi
    return cizili, bool(alarm), int(risk), json.dumps(sonuc["baslayan"], ensure_ascii=False), durum, bool(sonuc["baslayan"]), yaz


def kapat(state: dict) -> None:
    """Sahne durdurulurken çağrılabilir: açık olayları ve sayıları kuyruğa bırakır."""
    _bitir(state)
