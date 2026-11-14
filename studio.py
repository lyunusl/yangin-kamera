"""AugeLab Studio köprüsü: arayüzsüz koşu.

Yangın Kamera, Studio'nun kodunu içermez ve Studio penceresini hiç açmaz. Kullanıcının kurduğu Studio'nun kendi
Python'uyla her kamera için gizli bir süreç başlatır:

    "<Studio>/Python/python.exe" -m studio run yangin-kamera.pmod --json

yangin-kamera.pmod, programla gelen hazır sahnedir (Studio sahne dosyalarını şifreli kaydettiği için bir kez Studio'da
kurulup kaydedilmiştir: kurulum/sablon.py):

    Yangın Kamera Kodu ───┬────────────────────┬────────────────────┐
    Yangın Video ─(görüntü, zaman)─► Yangın Algılama ─(tespitler)─► Yangın Kurallar ─► olaylar, klipler, ölçümler
              └──────────────(görüntü, zaman, bitti)─────────────────────┘            (panelin kuyruğuna)

Sahne her kamera için aynıdır; hangi kamerayı işleyeceğini ortam değişkenlerinden öğrenir (yangin_motor.blok:
YANGIN_KAMERA "kod#koşu", YANGIN_KAMERA_ADRES canlı akış adresi, YANGIN_DUR durdurma dosyası). Panel önce bloklarını
Studio'nun özel blok klasörüne yazar ve motorunu (yangin_motor, modeller, onnxruntime) yanına koyar; Studio'nun ortamına
paket kurulmaz. Model yalnızca Studio'nun içinde açılır; panel süreci modeli hiç yüklemez.

Geliştirme için:  python studio.py durum | dene | calistir <kamera> [saniye]
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import studio_blok
import yollar

KAYNAK = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
MOTOR_KAYNAK = KAYNAK / "motor"
SABLON_KAYNAK = KAYNAK / "kurulum" / "sahne" / "yangin-kamera.pmod"
DURUM_DOSYASI = yollar.VERI / "studio.json"
LISANS_ISARETI = yollar.VERI / "studio-lisans.txt"  # kurulum dosyası lisans kodunu Studio'ya kaydedince bırakır (kodun kendisi değil)
KOSU_KLASORU = yollar.VERI / "studio"
PENCERESIZ = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
CANLI_TURLER = ("rtsp", "onvif", "http")


class StudioHatasi(RuntimeError):
    """Studio bir isteği reddetti ya da sahne çalışmadı."""


class StudioYok(StudioHatasi):
    """AugeLab Studio kurulu değil: beklenebilir, hata değil."""


# ---------------------------------------------------------------- Studio'nun yerleri


def kurulu_klasor() -> Path | None:
    import studio_kurulum

    exe = studio_kurulum.kurulu_studio()
    return exe.parent if exe else None


def studio_python() -> Path:
    """Studio'nun kendi Python yorumlayıcısı (arayüzsüz koşu bununla yapılır)."""
    klasor = kurulu_klasor()
    if klasor is None:
        raise StudioYok("AugeLab Studio kurulu değil. Kurulum sihirbazıyla kurun.")
    py = klasor / "Python" / "python.exe"
    if not py.is_file():
        raise StudioHatasi(f"AugeLab Studio'nun Python'u bulunamadı ({py}). Studio'yu resmî kurucuyla onarın.")
    return py


def marketplace() -> Path:
    """Studio'nun özel blok klasörünün bulunduğu yer (Studio bunu her kullanıcı için %APPDATA% altında tutar)."""
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "AugeLab Studio" / "marketplace"


def surum() -> str | None:
    """Kurulu Studio'nun sürümü (paket bilgisinden; Studio çalıştırılmaz)."""
    klasor = kurulu_klasor()
    if klasor is None:
        return None
    for bilgi in sorted((klasor / "Python" / "Lib" / "site-packages").glob("studio-*.dist-info")):
        return bilgi.name[len("studio-"):-len(".dist-info")]
    return None


# ---------------------------------------------------------------- motor klasörü


def _dosyalar(klasor: Path) -> list[Path]:
    return sorted(p for p in klasor.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def _dosya_ozeti(p: Path) -> bytes:
    """Dosyanın tüm içeriğinin SHA-256 özeti."""
    with p.open("rb") as dosya:
        return hashlib.file_digest(dosya, "sha256").digest()


def _parmak_izi(klasor: Path) -> str:
    """Klasörün içerik imzası: dosya adları ve içerik özetleri. Dosya tarihine bakılmaz: exe her açılışta dosyalarını
    geçici bir klasöre yeni tarihle açar; tarih imzaya girseydi motor her açılışta yeniden kopyalanırdı."""
    h = hashlib.sha256()
    dosyalar = _dosyalar(klasor)
    for p in dosyalar:
        h.update(p.relative_to(klasor).as_posix().encode("utf-8") + b"\0" + _dosya_ozeti(p))
    return f"{len(dosyalar)}:{h.hexdigest()[:40]}"


def _esitle(kaynak: Path, hedef: Path) -> int:
    """Hedef klasörü kaynağın aynısı yapar; yalnızca içeriği farklı olan dosyalara dokunur. Dönüş: kopyalanan dosya sayısı.

    Aynı kalan dosyalar yeniden yazılmaz: Studio açıkken yüklediği kitaplıklar (onnxruntime) kilitlidir ve üstlerine
    yazılamaz. Gerçekten değişmiş bir dosya kilitliyse anlaşılır bir hata verilir. Kaynakta artık olmayan dosyalar silinir;
    silinemeyen (kullanımda olan) eski dosya yerinde kalır."""
    hedef.mkdir(parents=True, exist_ok=True)
    kaynaklar = {p.relative_to(kaynak): p for p in _dosyalar(kaynak)}
    kopya = 0
    for goreli, p in kaynaklar.items():
        h = hedef / goreli
        try:
            ayni = h.is_file() and h.stat().st_size == p.stat().st_size and _dosya_ozeti(h) == _dosya_ozeti(p)
        except OSError:
            ayni = False  # hedef okunamadı: yeniden yazmayı dene
        if ayni:
            continue
        h.parent.mkdir(parents=True, exist_ok=True)
        gecici = h.with_name(h.name + ".yeni")
        try:
            shutil.copyfile(p, gecici)
            os.replace(gecici, h)
        except OSError:
            try:
                gecici.unlink(missing_ok=True)
            except OSError:
                pass
            raise StudioHatasi(f"Motor dosyası güncellenemedi ({goreli.as_posix()}): dosya kullanımda olabilir. "
                               "Süren analizleri durdurup tekrar deneyin.") from None
        kopya += 1
    for h in _dosyalar(hedef):
        if h.relative_to(hedef) not in kaynaklar:
            try:
                h.unlink()
            except OSError:
                pass
    return kopya


def motoru_yerlestir(hedef: Path) -> Path:
    """Motoru (yangin_motor, modeller, deps) Studio'nun özel blok klasörünün yanına kopyalar; değişmediyse dokunmaz."""
    if not (MOTOR_KAYNAK / "yangin_motor").is_dir():
        raise StudioHatasi(f"Motor kaynağı bulunamadı: {MOTOR_KAYNAK}")
    hedef.mkdir(parents=True, exist_ok=True)
    imzalar = []
    for ad in ("yangin_motor", "modeller", "deps"):
        kaynak = MOTOR_KAYNAK / ad
        if not kaynak.is_dir():
            continue
        imza = _parmak_izi(kaynak)
        imzalar.append(imza)
        isaret = hedef / f"{ad}.surum"
        if (hedef / ad).is_dir() and isaret.exists() and isaret.read_text(encoding="ascii") == imza:
            continue
        _esitle(kaynak, hedef / ad)
        isaret.write_text(imza, encoding="ascii")
    surum = hedef / "surum.txt"  # yalnızca değiştiyse yazılır: bloklar bu dosyanın tarihine bakarak motoru yeniden yükler
    if not surum.exists() or surum.read_text(encoding="ascii") != "|".join(imzalar):
        surum.write_text("|".join(imzalar), encoding="ascii")
    (hedef / "ayar.json").write_text(json.dumps({"veri": str(yollar.VERI)}), encoding="utf-8")
    return hedef


def bloklari_kur() -> Path:
    """Yangın bloklarını Studio'nun özel blok klasörüne yazar (yalnızca değiştiyse) ve motoru yanına yerleştirir.
    Dosyalar Studio'nun node.custom.create ile ürettiklerinin aynısıdır (studio_blok.dosya_metni). Dönüş: motor klasörü."""
    bloklar = marketplace() / "custom_blocks"
    bloklar.mkdir(parents=True, exist_ok=True)
    for tanim in studio_blok.TANIMLAR:
        hedef = bloklar / f"{tanim['opCode']}.py"
        metin = studio_blok.dosya_metni(tanim).replace("\n", "\r\n").encode("utf-8")
        try:
            if hedef.is_file() and hedef.read_bytes() == metin:
                continue
        except OSError:
            pass
        gecici = hedef.with_name(hedef.name + ".yeni")
        gecici.write_bytes(metin)
        os.replace(gecici, hedef)
    return motoru_yerlestir(marketplace() / studio_blok.MOTOR_KLASORU)


def sablon() -> Path:
    """Hazır sahnenin veri klasöründeki kopyası (exe her açılışta dosyalarını başka bir geçici klasöre açar)."""
    if not SABLON_KAYNAK.is_file():
        raise StudioHatasi(f"Hazır sahne bulunamadı: {SABLON_KAYNAK}")
    KOSU_KLASORU.mkdir(parents=True, exist_ok=True)
    hedef = KOSU_KLASORU / SABLON_KAYNAK.name
    if not hedef.is_file() or _dosya_ozeti(hedef) != _dosya_ozeti(SABLON_KAYNAK):
        shutil.copyfile(SABLON_KAYNAK, hedef)
    return hedef


# ---------------------------------------------------------------- arayüzsüz koşular


class Kosu:
    """Bir kameranın gizli `studio run` süreci."""

    def __init__(self, kod: str, kosu: str, surec: subprocess.Popen, dur: Path, gunluk: Path):
        self.kod, self.kosu, self.surec, self.dur, self.gunluk = kod, kosu, surec, dur, gunluk
        self.durum = "başlıyor"
        self.sonuc: dict | None = None
        self._okundu = threading.Event()
        threading.Thread(target=self._oku, name=f"studio-{kod}", daemon=True).start()

    def _oku(self) -> None:
        """Studio'nun --json olaylarını okur (lifecycle / result)."""
        try:
            for satir in self.surec.stdout:
                try:
                    olay = json.loads(satir)
                except ValueError:
                    # With no local license Studio's console prompt can precede
                    # the JSON result on the same line, even with stdin closed.
                    bas = satir.find('{"type":')
                    if bas < 0:
                        continue
                    try:
                        olay = json.loads(satir[bas:])
                    except ValueError:
                        continue
                if not isinstance(olay, dict):
                    continue
                if olay.get("type") == "lifecycle":
                    self.durum = olay.get("state") or self.durum
                elif olay.get("type") == "result":
                    self.sonuc = olay
        finally:
            self._okundu.set()

    def calisiyor(self) -> bool:
        return self.surec.poll() is None

    def sorun(self) -> str | None:
        """Süreç kendiliğinden bittiyse nedeni (lisans, eksik blok, çökme...), sürüyorsa None."""
        if self.calisiyor():
            return None
        self._okundu.wait(2)
        r = self.sonuc or {}
        if r.get("success"):
            return None
        neden = r.get("error") or r.get("failure_type") or f"çıkış kodu {self.surec.returncode}"
        return (f"AugeLab Studio sahneyi çalıştıramadı ({neden}). Studio lisansınızı kurulum sihirbazından kontrol edin; "
                f"ayrıntı: {self.gunluk}")

    def bitir(self, bekle_sn: float = 3.0) -> None:
        """Önce akışı bitirir (açık olaylar kapanış kaydı bırakır), sonra süreci kapatır."""
        try:
            self.dur.touch()
        except OSError:
            pass
        son = time.monotonic() + bekle_sn
        while self.calisiyor() and time.monotonic() < son:
            time.sleep(0.2)
        if self.calisiyor():
            # Studio sürekli çalışma kipinde kendiliğinden bitmez: süreç ağacı (denetleyici ve işçi) kapatılır
            subprocess.run(["taskkill", "/PID", str(self.surec.pid), "/T", "/F"], capture_output=True, creationflags=PENCERESIZ)
            try:
                self.surec.wait(10)
            except subprocess.TimeoutExpired:
                self.surec.kill()
        try:
            self.dur.unlink(missing_ok=True)
        except OSError:
            pass


KOSULAR: dict[str, Kosu] = {}
_KILIT = threading.Lock()


def baslat(kod: str, kosu: str, adres: str = "", canli: bool = False, adim: int | None = None, ek_ortam: dict | None = None) -> Kosu:
    """Kameranın sahnesini arayüzsüz başlatır. `canli`: süreç çökerse Studio onu yeniden başlatır."""
    py = studio_python()
    sahne = sablon()
    bloklari_kur()
    with _KILIT:
        eski = KOSULAR.pop(kod, None)
    if eski is not None:
        eski.bitir(0)
    KOSU_KLASORU.mkdir(parents=True, exist_ok=True)
    dur = KOSU_KLASORU / f"{kod}.dur"
    dur.unlink(missing_ok=True)
    gunluk = KOSU_KLASORU / f"{kod}.log"
    ortam = {k: v for k, v in os.environ.items() if not k.startswith(("YANGIN_", "PYTHON", "_MEI", "TCL_", "TK_"))}
    ortam.update(YANGIN_KAMERA=f"{kod}#{kosu}", YANGIN_DUR=str(dur), PYTHONIOENCODING="utf-8")
    if adres:
        ortam["YANGIN_KAMERA_ADRES"] = adres  # şifre içerebilir: yalnızca sürecin ortamında, dosyaya yazılmaz
    ortam.update(ek_ortam or {})
    komut = [str(py), "-m", "studio", "run", str(sahne), "--json", "--verbosity", "30"]
    if canli:
        komut += ["--on-fail", "restart", "--max-restarts", "1000", "--restart-delay", "5"]
    if adim:
        komut += ["--step", str(int(adim))]
    import studio_kurulum

    with gunluk.open("ab") as g, studio_kurulum._temiz_dll_dizini():  # Studio, paketlenmiş Python'un DLL dizinini devralmasın
        surec = subprocess.Popen(komut, cwd=str(KOSU_KLASORU), env=ortam, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=g, text=True, encoding="utf-8", errors="replace", creationflags=PENCERESIZ)
    k = Kosu(kod, kosu, surec, dur, gunluk)
    with _KILIT:
        KOSULAR[kod] = k
    return k


def durdur_hepsi() -> None:
    """Program kapanırken: süren bütün koşuları bitirir."""
    with _KILIT:
        kosular = list(KOSULAR.values())
        KOSULAR.clear()
    for k in kosular:
        k.bitir()


# ---------------------------------------------------------------- durum ve deneme


KONTROL_SURUMU = 1  # lisans kontrolünün sürümü: değişirse eski "hazır" kaydı geçersiz sayılır


def _kayitli() -> dict:
    try:
        return json.loads(DURUM_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def kaydet(**degerler) -> None:
    d = _kayitli()
    d.update(degerler)
    DURUM_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
    DURUM_DOSYASI.write_text(json.dumps(d), encoding="utf-8")


def _deneme_kosusu(sinir_sn: float) -> tuple["Kosu", str | None]:
    """Deneme sahnesini kısa bir koşuyla çalıştırır: motor modeli açıp siyah bir kare işler, sonucu bir dosyaya yazar.
    Dönüş: (koşu, sorun ya da None)."""
    KOSU_KLASORU.mkdir(parents=True, exist_ok=True)
    sonuc_yolu = KOSU_KLASORU / "deneme-sonuc.json"
    sonuc_yolu.unlink(missing_ok=True)
    k = baslat("_deneme", secrets.token_hex(4), adim=3, ek_ortam={"YANGIN_DENEME_SONUC": str(sonuc_yolu)})
    try:
        k.surec.wait(sinir_sn)
    except subprocess.TimeoutExpired:
        k.bitir(0)
        raise StudioHatasi("AugeLab Studio deneme sahnesini zamanında bitirmedi.") from None
    finally:
        with _KILIT:
            KOSULAR.pop("_deneme", None)
    sorun = k.sorun()
    if not sorun:
        try:
            model = json.loads(sonuc_yolu.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            model = {"ok": False, "hata": "motor sonuç bırakmadı (Yangın blokları Studio'da çalışmadı)"}
        if not model.get("ok"):
            hata = str(model.get("hata") or "bilinmiyor")
            sorun = ("Lisans kodunu kurulum sihirbazından girin." if hata.startswith("lisans") else f"Model açılamadı ({hata}).")
    return k, sorun


def dene(sinir_sn: float = 240.0) -> dict:
    """Studio'nun arayüzsüz çalışabildiğini (kurulu, bloklar yükleniyor) ve modelin açıldığını (korumalı pakette
    Studio lisansı dahil) kısa bir koşuyla dener: motor siyah bir kareyle modeli çalıştırıp sonucu bir dosyaya yazar."""
    k, sorun = _deneme_kosusu(sinir_sn)
    if sorun:
        kaydet(hazir=False, denendi=time.time(), hata=sorun[:300], kontrol=KONTROL_SURUMU)
        raise StudioHatasi(sorun)
    kaydet(hazir=True, denendi=time.time(), surum=surum(), hata=None, kontrol=KONTROL_SURUMU)
    return {"hazir": True, "sure_sn": round(((k.sonuc or {}).get("duration_ms") or 0) / 1000, 1)}


async def durum() -> dict:
    """Panelin gösterdiği Studio durumu. Studio'ya bağlanılmaz; kurulu mu, sahne denendi mi, koşan kamera var mı."""
    if kurulu_klasor() is None:
        raise StudioYok("AugeLab Studio kurulu değil.")
    studio_python()
    k = _kayitli()
    hazir = k.get("hazir") if k.get("kontrol") == KONTROL_SURUMU else None  # eski kayıt: yeniden kontrol edilir
    return {"surum": surum(), "arayuzsuz": True, "hazir": hazir, "denendi": k.get("denendi"), "hata": k.get("hata"),
            "lisans_kaydedildi": bool(k.get("lisans") or LISANS_ISARETI.is_file()),
            "motor_calisiyor": any(x.calisiyor() for x in list(KOSULAR.values()))}


# ---------------------------------------------------------------- panelin kullandığı işler


async def sahne_kur(kod: str, ayar: dict) -> dict:
    """Kameranın koşusunu hazırlar: Studio ve hazır sahne yerinde mi, bloklar ve motor güncel mi."""
    tur = (ayar.get("kamera") or {}).get("tur", "rtsp")
    if tur not in CANLI_TURLER + ("dosya",):
        raise StudioHatasi(f"Bu kamera türü desteklenmiyor ({tur}). Kamerayı IP kamera, ONVIF, HTTP akışı ya da video dosyası olarak ekleyin.")
    studio_python()
    sablon()
    bloklari_kur()
    return {"kod": kod, "tur": tur, "adres": "", "kosu": None}


async def yeni_kosu(bilgi: dict, kod: str) -> str:
    """Yeni bir koşu numarası verir: motorun kuyruğa bıraktığı kayıtlar bu numarayı taşır."""
    bilgi["kosu"] = secrets.token_hex(4)
    return bilgi["kosu"]


async def kamera_adresi(bilgi: dict, adres: str) -> None:
    """Canlı akış adresi koşunun ortamına verilir (dosyaya ya da sahneye yazılmaz)."""
    bilgi["adres"] = adres


async def calistir(bilgi: dict, sure_ms: int | None = None) -> dict:
    """Sahneyi arayüzsüz başlatır. `sure_ms` verilirse o kadar sonra akışı bitirir."""
    canli = bilgi["tur"] in CANLI_TURLER
    k = baslat(bilgi["kod"], bilgi["kosu"] or secrets.token_hex(4), bilgi.get("adres", ""), canli=canli)
    bilgi["surec"] = k
    if sure_ms:
        def zamanla():
            time.sleep(sure_ms / 1000)
            if k.calisiyor():
                k.dur.touch()
        threading.Thread(target=zamanla, daemon=True, name=f"studio-sure-{bilgi['kod']}").start()
    return {"pid": k.surec.pid}


async def durdur(bilgi: dict, dogrula_sn: float = 20.0) -> None:
    """Akışı bitirir ve süreci kapatır; kapandığı doğrulanamazsa StudioHatasi."""
    k = bilgi.get("surec") or KOSULAR.get(bilgi["kod"])
    if k is None:
        return
    k.bitir()
    with _KILIT:
        if KOSULAR.get(bilgi["kod"]) is k:
            KOSULAR.pop(bilgi["kod"])
    if k.calisiyor():
        raise StudioHatasi("Studio süreci kapatılamadı.")


def kosu_sorunu(bilgi: dict) -> str | None:
    """Koşu kendiliğinden bittiyse (lisans, eksik dosya, çökme) nedeni."""
    k = bilgi.get("surec")
    return k.sorun() if k is not None else None


# ---------------------------------------------------------------- geliştirme komutları


def _komut(arg: list[str]) -> None:
    yollar.hazirla()
    if arg[0] == "durum":
        print(asyncio.run(durum()))
    elif arg[0] == "dene":
        print(dene())
    elif arg[0] == "calistir":
        kod = arg[1]
        ayar = json.loads((yollar.AYAR / f"{kod}.json").read_text(encoding="utf-8"))
        bilgi = asyncio.run(sahne_kur(kod, ayar))
        asyncio.run(yeni_kosu(bilgi, kod))
        asyncio.run(calistir(bilgi))
        time.sleep(float(arg[2]) if len(arg) > 2 else 30)
        print("sorun:", kosu_sorunu(bilgi))
        asyncio.run(durdur(bilgi))
        print("durduruldu")


if __name__ == "__main__":
    _komut(sys.argv[1:])
