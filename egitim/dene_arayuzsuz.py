"""Arayüzsüz Studio koşusunu (studio.py) gerçek Studio olmadan, sahte bir `python -m studio` ile sınar.

  python egitim/dene_arayuzsuz.py

Sahte Studio, gerçeğinin --json çıktısını taklit eder: lifecycle satırları, --step verilirse sonuç satırıyla çıkış; verilmezse
(sürekli kip) kendiliğinden bitmez. Denenenler: blok dosyalarının yazılması, deneme koşusu, kameranın ortam değişkenleriyle
verilmesi (adres komut satırına girmez), durdurma dosyası ve süreç ağacının kapatılması, Studio'nun reddettiği koşunun nedeni,
panelin modeli hiç yüklememesi ve bağlantı denemesinin Studio'yu çalıştırmaması. Ayrıca: stderr'in maskelenip günlüğe yazılması
(kısa şifre ve tek seferlik yerel adres dahil), koşu başına durdurma dosyası, iş nesnesine bağlama, "EOF" / işaretli çıkış kodu /
kullanıcı klasörü, bağlantı denemesinin geç durdurması ve yazılamayan kare.
"""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

kok = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(kok))
import studio  # noqa: E402
import studio_blok  # noqa: E402

SAHTE = r'''
import json, os, sys, time
arg = sys.argv[1:]
def yaz(**o):
    print(json.dumps(o), flush=True)
kayit = os.path.join(os.getcwd(), "sahte-ortam.json")
with open(kayit, "a", encoding="utf-8") as f:
    f.write(json.dumps({"arg": arg, "kamera": os.environ.get("YANGIN_KAMERA"), "adres": os.environ.get("YANGIN_KAMERA_ADRES"),
                        "dur": os.environ.get("YANGIN_DUR"), "cv_log": os.environ.get("OPENCV_LOG_LEVEL"),
                        "ff_log": os.environ.get("OPENCV_FFMPEG_LOGLEVEL")}) + "\n")
def hata(metin):
    sys.stderr.write(metin + "\n")
    sys.stderr.flush()
adres = os.environ.get("YANGIN_KAMERA_ADRES")
if adres:  # gerçek OpenCV/FFmpeg gibi adresi ve kimlik bilgisini stderr'e yazar
    from urllib.parse import urlsplit
    u = urlsplit(adres)
    hata(f"[ffmpeg] opening {adres} failed")
    hata(f"auth user={u.username} password={u.password}")
    hata(f"baglanti {u.username} {u.password} reddedildi")
for ad, deger in sorted(os.environ.items()):
    if ad.startswith("YANGIN_") and ad.endswith("_URL"):
        hata(f"fetching {deger} for masking")
kamera = os.environ.get("YANGIN_KAMERA", "")
if kamera.startswith("eof"):  # lisans kodu girilmemiş Studio: konsoldan kod ister, girdi gelmez
    hata("Traceback (most recent call last):")
    hata("EOFError: EOF when reading a line")
    sys.exit(1)
if kamera.startswith("cokus"):  # sonuç bildirmeden çöker; son satırında kullanıcı klasörü geçer
    hata("hazirlaniyor")
    hata("modul yuklenemedi: " + os.environ.get("USERPROFILE", "") + "\\x\\y.py")
    sys.exit(-1)
yaz(type="lifecycle", state="starting")
if os.environ.get("YANGIN_KAMERA", "").startswith("lisanssiz"):
    print("Verification code: ", end="", flush=True)
    yaz(type="result", success=False, exit_code=2, failure_type="license", error="License is not active")
    sys.exit(2)
yaz(type="lifecycle", state="started")
if "--step" in arg:
    sonuc = os.environ.get("YANGIN_DENEME_SONUC")
    if sonuc:  # motorun deneme koşusu: model açıldı mı (SAHTE_MODEL=lisans ise lisans hatası)
        hata = os.environ.get("SAHTE_MODEL", "")
        with open(sonuc, "w", encoding="utf-8") as f:
            json.dump({"ok": not hata, "hata": "lisans: Studio lisansı etkin değil" if hata == "lisans" else hata}, f)
    time.sleep(0.3)
    yaz(type="result", success=True, exit_code=0, duration_ms=300)
    sys.exit(0)
while True:  # gerçek Studio gibi sürekli kipte kendiliğinden bitmez (durdurma dosyasına bloklar bakar)
    time.sleep(0.2)
'''

sonuc = []


def denetle(ad, kosul):
    sonuc.append((ad, bool(kosul)))
    print(("  geçti  " if kosul else "  KALDI  ") + ad, flush=True)


gecici = Path(tempfile.mkdtemp(prefix="yangin-arayuzsuz-"))
studio.KOSU_KLASORU = gecici / "veri" / "studio"
studio.DURUM_DOSYASI = gecici / "veri" / "studio.json"
studio.SABLON_KAYNAK = gecici / "yangin-kamera.pmod"
studio.SABLON_KAYNAK.write_bytes(b"sahte sahne")
studio.MOTOR_KAYNAK = gecici / "motor"
(studio.MOTOR_KAYNAK / "yangin_motor").mkdir(parents=True)
(studio.MOTOR_KAYNAK / "yangin_motor" / "__init__.py").write_text("", encoding="utf-8")
studio.marketplace = lambda: gecici / "marketplace"
studio.studio_python = lambda: Path(sys.executable)
baglanan = []  # iş nesnesine bağlanan süreçler
_gercek_bagla = studio.yollar.cocuk_bagla
studio.yollar.cocuk_bagla = lambda s: (baglanan.append(s.pid), _gercek_bagla(s))
paket = studio.KOSU_KLASORU / "studio"
paket.mkdir(parents=True)
(paket / "__init__.py").write_text("", encoding="utf-8")
(paket / "__main__.py").write_text(SAHTE, encoding="utf-8")


def ortamlar():
    yol = studio.KOSU_KLASORU / "sahte-ortam.json"
    return [json.loads(s) for s in yol.read_text(encoding="utf-8").splitlines()] if yol.exists() else []


print("Blok dosyaları")
motor = studio.bloklari_kur()
bloklar = gecici / "marketplace" / "custom_blocks"
dosyalar = sorted(p.name for p in bloklar.glob("*.py"))
denetle("üç blok dosyası yazıldı", dosyalar == sorted(t["opCode"] + ".py" for t in studio_blok.TANIMLAR))
ham = (bloklar / "YanginVideo.py").read_bytes()
denetle("Studio'nun ürettiği gibi CRLF satır sonu", b"\r\n" in ham and b"\n" not in ham.replace(b"\r\n", b""))
denetle("motor yanına yerleşti, veri klasörü yazıldı", (motor / "yangin_motor" / "__init__.py").exists() and (motor / "ayar.json").exists())
damgalar = {p.name: p.stat().st_mtime_ns for p in bloklar.glob("*.py")}
time.sleep(0.05)
studio.bloklari_kur()
denetle("değişmeyen blok dosyalarına dokunulmaz", damgalar == {p.name: p.stat().st_mtime_ns for p in bloklar.glob("*.py")})
for t in studio_blok.TANIMLAR:
    compile(studio_blok.dosya_metni(t), t["opCode"], "exec")
denetle("üretilen blok dosyaları derlenebilir", True)

print("Deneme koşusu")
d = studio.dene(30)
denetle("deneme geçti, hazır kaydedildi", d["hazir"] and json.loads(studio.DURUM_DOSYASI.read_text())["hazir"] is True)
denetle("deneme --step ile sınırlı", "--step" in ortamlar()[-1]["arg"])
os.environ["SAHTE_MODEL"] = "lisans"
try:
    studio.dene(30)
    denetle("model lisans yüzünden açılmazsa deneme geçmez", False)
except studio.StudioHatasi as e:
    denetle("model lisans yüzünden açılmazsa deneme geçmez", "lisans" in str(e).lower())
denetle("başarısız deneme hazır=False ve nedenini kaydeder", json.loads(studio.DURUM_DOSYASI.read_text())["hazir"] is False and "lisans" in json.loads(studio.DURUM_DOSYASI.read_text())["hata"].lower())
del os.environ["SAHTE_MODEL"]
studio.dene(30)
denetle("lisans gelince deneme yeniden geçer", json.loads(studio.DURUM_DOSYASI.read_text())["hazir"] is True)

print("Panel modeli yüklemez")
import cv2  # noqa: E402
import numpy as np  # noqa: E402

import kamera  # noqa: E402
import kurallar  # noqa: E402,F401
import rapor  # noqa: E402,F401
import uygulama  # noqa: E402,F401

denetle("panelin modülleri onnxruntime yüklemez", "onnxruntime" not in sys.modules and "yangin_motor.algila" not in sys.modules)
kamera.yollar.AYAR = gecici / "veri" / "ayar"
video = gecici / "deneme.mp4"
yazici = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
for i in range(10):
    yazici.write(np.full((48, 64, 3), 20 * i, np.uint8))
yazici.release()
onceki = len(ortamlar())
ayar = {"kod": "dnm", "kamera": {"tur": "dosya", "yol": str(video)}}
kod = kamera.test(ayar, kamera.yollar.AYAR / "dnm.json")
kare = cv2.imread(str(kamera.yollar.AYAR / "_kare_dnm.jpg"))
denetle("bağlantı denemesi bir kare alır ve kaydeder", kod == 0 and kare is not None and kare.shape[:2] == (48, 64))
denetle("bağlantı denemesi Studio'yu çalıştırmaz, modeli yüklemez", len(ortamlar()) == onceki and "onnxruntime" not in sys.modules)

print("Kamera koşusu")
bilgi = asyncio.run(studio.sahne_kur("kapi", {"kamera": {"tur": "rtsp"}}))
asyncio.run(studio.yeni_kosu(bilgi, "kapi"))
gizli = "rtsp://kullanici:GIZLI-sifre@10.0.0.9/akis"
asyncio.run(studio.kamera_adresi(bilgi, gizli))
onceki = len(ortamlar())
asyncio.run(studio.calistir(bilgi))
for _ in range(50):
    if len(ortamlar()) > onceki:
        break
    time.sleep(0.1)
o = ortamlar()[-1]
denetle("kamera kodu ve koşu ortamdan verilir", o["kamera"] == f"kapi#{bilgi['kosu']}")
denetle("akış adresi yalnızca sürecin ortamında", o["adres"] == gizli and gizli not in " ".join(o["arg"]))
denetle("canlı akışta Studio çökünce yeniden başlatır", "--on-fail" in o["arg"] and "restart" in o["arg"])
denetle("koşu sürerken sorun yok", studio.kosu_sorunu(bilgi) is None and bilgi["surec"].calisiyor())
bas = time.monotonic()
asyncio.run(studio.durdur(bilgi))
denetle("durdurulunca süreç kapandı (kendiliğinden bitmeyen sürekli kip)", not bilgi["surec"].calisiyor())
denetle("durdurma dosyası temizlendi", not Path(o["dur"]).exists())
denetle("adres hiçbir dosyaya yazılmadı", not any("GIZLI" in p.read_text(encoding="utf-8", errors="ignore")
                                                  for p in (gecici / "veri").rglob("*") if p.is_file() and p.name != "sahte-ortam.json"))
denetle("koşu listesi boşaldı", "kapi" not in studio.KOSULAR)
denetle("canlı adreste OpenCV/FFmpeg günlüğü kapalı", o["cv_log"] == "SILENT" and o["ff_log"] == "-8")
denetle("koşunun kendi durdurma dosyası (<kod>-<koşu>.dur)", Path(o["dur"]).name == f"kapi-{bilgi['kosu']}.dur")
denetle("Studio süreci programın iş nesnesine bağlandı", bilgi["surec"].surec.pid in baglanan)


def gunluk_metni(kod, aranan, sn=5.0):
    """Studio'nun stderr'i arka planda okunur: aranan satır günlüğe düşene kadar bekler."""
    yol = studio.KOSU_KLASORU / f"{kod}.log"
    son = time.monotonic() + sn
    while time.monotonic() < son:
        metin = yol.read_text(encoding="utf-8") if yol.exists() else ""
        if aranan in metin:
            return metin
        time.sleep(0.1)
    return yol.read_text(encoding="utf-8") if yol.exists() else ""


metin = gunluk_metni("kapi", "reddedildi")
denetle("stderr maskelenip günlüğe yazıldı (adres, kullanıcı, şifre yok)", "reddedildi" in metin and "GIZLI" not in metin
        and "kullanici" not in metin and "10.0.0.9" not in metin)

print("Kısa kullanıcı adı ve şifre")
bilgi = asyncio.run(studio.sahne_kur("kisa", {"kamera": {"tur": "rtsp"}}))
asyncio.run(studio.yeni_kosu(bilgi, "kisa"))
asyncio.run(studio.kamera_adresi(bilgi, "rtsp://yo:z9@10.0.0.7/akis"))
asyncio.run(studio.calistir(bilgi))
ilk_kosu, ilk_dur = bilgi["kosu"], bilgi["surec"].dur
metin = gunluk_metni("kisa", "reddedildi")
denetle("iki karakterlik kullanıcı ve şifre de maskelenir", "reddedildi" in metin and "z9" not in metin and " yo " not in metin
        and "user=****" in metin and "password=****" in metin and "10.0.0.7" not in metin)
asyncio.run(studio.yeni_kosu(bilgi, "kisa"))
asyncio.run(studio.calistir(bilgi))  # aynı kameranın yeni koşusu: önceki kapatılır
ikinci = bilgi["surec"]
try:
    ilk_dur.touch()  # önceki koşu için geç gelen durdurma
except OSError:
    pass
time.sleep(0.5)
denetle("önceki koşunun geç durdurması yeni koşuya dokunmaz", ikinci.dur != ilk_dur and ikinci.calisiyor()
        and ikinci.dur.name == f"kisa-{bilgi['kosu']}.dur" and bilgi["kosu"] != ilk_kosu)
asyncio.run(studio.durdur(bilgi))
ilk_dur.unlink(missing_ok=True)

print("Tek seferlik yerel adres")
yerel = "http://127.0.0.1:50123/" + "A1b2C3d4E5f6G7h8"
k = studio.baslat("_yerel", "y1", adim=3, ek_ortam={"YANGIN_DENEME_KARE_URL": yerel})
k.surec.wait(20)
metin = gunluk_metni("_yerel", "for masking")
denetle("ortamla verilen *_URL adresi ve erişim anahtarı günlüğe gitmez", "fetching **** for masking" in metin
        and "127.0.0.1" not in metin and "A1b2C3d4" not in metin)
with studio._KILIT:
    studio.KOSULAR.pop("_yerel", None)

print("Studio reddederse")
bilgi = asyncio.run(studio.sahne_kur("lisanssiz", {"kamera": {"tur": "dosya"}}))
asyncio.run(studio.yeni_kosu(bilgi, "lisanssiz"))
asyncio.run(studio.calistir(bilgi))
bilgi["surec"].surec.wait(20)
neden = studio.kosu_sorunu(bilgi) or ""
denetle("kendiliğinden biten koşunun nedeni bildirilir", "License is not active" in neden)
denetle("video dosyasında yeniden başlatma yok", "--on-fail" not in ortamlar()[-1]["arg"])
try:
    asyncio.run(studio.sahne_kur("usb", {"kamera": {"tur": "usb"}}))
    denetle("desteklenmeyen kamera türü açıkça reddedilir", False)
except studio.StudioHatasi as e:
    denetle("desteklenmeyen kamera türü açıkça reddedilir", "desteklenmiyor" in str(e))


def kendiliginden_biten(kod):
    bilgi = asyncio.run(studio.sahne_kur(kod, {"kamera": {"tur": "dosya"}}))
    asyncio.run(studio.yeni_kosu(bilgi, kod))
    asyncio.run(studio.calistir(bilgi))
    bilgi["surec"].surec.wait(20)
    return studio.kosu_sorunu(bilgi) or ""


neden = kendiliginden_biten("eof")
denetle("\"EOF when reading a line\": Studio etkinleştirilmemiş, lisans kodu girilmemiş", "etkinleştirilmemiş" in neden
        and "lisans kodu" in neden and "sihirbaz" in neden and "EOF" not in neden)
neden = kendiliginden_biten("cokus")
denetle("işaretli çıkış kodu ve son satır bildirilir", "çıkış kodu -1" in neden and "modul yuklenemedi" in neden)
metin = gunluk_metni("cokus", "modul yuklenemedi")
kullanici = os.environ.get("USERPROFILE", "")
denetle("kullanıcı klasörü ne nedende ne günlükte geçer", bool(kullanici) and kullanici not in neden and kullanici not in metin
        and kullanici.replace("\\", "/") not in neden and "%USERPROFILE%" in metin)

print("Bağlantı denemesi ve durdurma")
gercek_ac = kamera.ac
gec = __import__("threading").Event()


def gec_ac(src):  # durdurma, kamera açılırken (kare yazılmadan önce) gelir
    gec.set()
    return gercek_ac(src)


kamera.ac = gec_ac
(kamera.yollar.AYAR / "_kare_gec.jpg").unlink(missing_ok=True)
r = kamera.test({"kod": "gec", "kamera": {"tur": "dosya", "yol": str(video)}}, kamera.yollar.AYAR / "gec.json", dur=gec)
kamera.ac = gercek_ac
denetle("kare yazılmadan önce durdurulan deneme kare kaydetmez", r == 2 and not (kamera.yollar.AYAR / "_kare_gec.jpg").exists())
gercek_yaz = cv2.imwrite
cv2.imwrite = lambda *a, **k: False  # kare yazılamıyor (disk dolu, klasör yazılamıyor)
r = kamera.test({"kod": "gec", "kamera": {"tur": "dosya", "yol": str(video)}}, kamera.yollar.AYAR / "gec.json")
cv2.imwrite = gercek_yaz
denetle("kaydedilemeyen kare denemeyi başarısız yapar", r == 1)
r = kamera.test({"kod": "gec", "kamera": {"tur": "dosya", "yol": str(video)}}, kamera.yollar.AYAR / "gec.json")
denetle("kaydedilen kare denemeyi geçirir", r == 0 and (kamera.yollar.AYAR / "_kare_gec.jpg").exists())

studio.durdur_hepsi()
kalan = [ad for ad, ok in sonuc if not ok]
print(f"\n{len(sonuc) - len(kalan)}/{len(sonuc)} denetim geçti" + (f" · kalanlar: {kalan}" if kalan else ""))
sys.exit(1 if kalan else 0)
