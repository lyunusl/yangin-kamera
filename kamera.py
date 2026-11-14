"""Kamera bağlantısı: bağlantıyı dene, bölge çizmek için kare al, kayıt al (Yangın Kamera).

Ayar dosyasındaki "kamera" alanı:

  {"tur": "rtsp", "marka": "hikvision", "ip": "<kamera IP>", "port": 554,
   "kullanici": "admin", "kanal": 1, "akis": "alt"}
  {"tur": "rtsp", "adres": "rtsp://{kullanici}:{sifre}@<kamera IP>:554/stream1", "kullanici": "admin"}
  {"tur": "onvif", "ip": "<cihaz IP>", "port": 80, "kullanici": "admin", "kanal": 1, "akis": "alt"}     # adres cihazdan öğrenilir
  {"tur": "onvif", "ip": "<cihaz IP>", "port": 80, "kullanici": "admin", "profil": "<profil belirteci>", "kaynak": "<görüntü kaynağı belirteci>"}
  {"tur": "http", "adres": "http://<kamera IP>:8080/video"}
  {"tur": "dosya", "yol": "videolar/salon.mp4"}

Şifre ayar dosyasına YAZILMAZ. Sırasıyla şuradan alınır:
  1) programın ekranında yazılan şifre (yalnızca bellekte tutulur)
  2) "sifre_degiskeni" alanında adı verilen ortam değişkeni (varsayılan KAMERA_SIFRE)
  3) komut satırında çalışırken sorulur (ekranda görünmez)

Kaynak koddan kullanım:
  python kamera.py markalar
  python kamera.py test   veri/ayar/salon.json            # bağlan, bir kare al: ayar/_kare_<kamera>.jpg
  python kamera.py kaydet veri/ayar/salon.json --dakika 15
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

import yollar

_GIZLI = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}

# {k}=kullanıcı, {s}=şifre, {ip}, {port}, {kanal}; ana/alt akış ayrı şablon
MARKALAR = {
    "hikvision": {"ad": "Hikvision / HiLook", "ana": "rtsp://{k}:{s}@{ip}:{port}/Streaming/Channels/{kanal}01", "alt": "rtsp://{k}:{s}@{ip}:{port}/Streaming/Channels/{kanal}02"},
    "dahua": {"ad": "Dahua / Imou / IMOU NVR", "ana": "rtsp://{k}:{s}@{ip}:{port}/cam/realmonitor?channel={kanal}&subtype=0", "alt": "rtsp://{k}:{s}@{ip}:{port}/cam/realmonitor?channel={kanal}&subtype=1"},
    "uniview": {"ad": "Uniview (UNV)", "ana": "rtsp://{k}:{s}@{ip}:{port}/unicast/c{kanal}/s0/live", "alt": "rtsp://{k}:{s}@{ip}:{port}/unicast/c{kanal}/s1/live"},
    "reolink": {"ad": "Reolink", "ana": "rtsp://{k}:{s}@{ip}:{port}/h264Preview_{kanal:02d}_main", "alt": "rtsp://{k}:{s}@{ip}:{port}/h264Preview_{kanal:02d}_sub"},
    "tapo": {"ad": "TP-Link Tapo / VIGI", "ana": "rtsp://{k}:{s}@{ip}:{port}/stream1", "alt": "rtsp://{k}:{s}@{ip}:{port}/stream2"},
    "axis": {"ad": "Axis", "ana": "rtsp://{k}:{s}@{ip}:{port}/axis-media/media.amp", "alt": "rtsp://{k}:{s}@{ip}:{port}/axis-media/media.amp?resolution=640x360"},
    "ezviz": {"ad": "EZVIZ (kullanıcı admin, şifre cihaz altındaki doğrulama kodu)", "ana": "rtsp://{k}:{s}@{ip}:{port}/H.264", "alt": "rtsp://{k}:{s}@{ip}:{port}/H.264"},
}


def maskele(url: str) -> str:
    """Adresi ekrana yazarken şifreyi gizler."""
    return re.sub(r"(://[^:/@]+:)[^@]*@", r"\1****@", url)


def sifre_gerekli(ayar: dict) -> bool:
    """Bu kamera için şifre sorulacak mı (ekrandaki şifre kutusunu göstermek için)."""
    k = ayar.get("kamera") or {}
    tur = k.get("tur", "rtsp")
    if tur == "onvif":
        return True
    if tur == "rtsp":
        return "{sifre}" in k["adres"] if k.get("adres") else True
    if tur == "http":
        return "{sifre}" in k.get("adres", "")
    return False


def sifre_al(k: dict, sifre: str | None = None) -> str:
    if sifre is not None:  # programın ekranından geldi (boş olabilir: şifresiz kamera)
        return sifre
    degisken = k.get("sifre_degiskeni", "KAMERA_SIFRE")
    s = os.environ.get(degisken)
    if s is None:
        if sys.stdin is None or not sys.stdin.isatty():
            raise SystemExit(f"Kamera şifresi girilmedi. Şifre kutusuna yazın (ya da {degisken} ortam değişkenini ayarlayın).")
        s = getpass.getpass(f"Kamera şifresi ({k.get('kullanici', 'admin')}): ")
    return s


def kaynak(ayar: dict, sifre: str | None = None) -> tuple[str, str]:
    """(OpenCV/ffmpeg'e verilecek kaynak, ekranda gösterilecek hali)."""
    k = ayar.get("kamera")
    if not k:
        raise SystemExit('Ayar dosyasında "kamera" alanı yok. Ayar sayfasında bağlantı türünü seçip kaydedin.')
    tur = k.get("tur", "rtsp")
    if tur == "dosya":
        if not k.get("yol"):
            raise SystemExit("Video dosyasının yolu yazılmamış.")
        yol = str((yollar.VERI / k["yol"]).resolve()) if not Path(k["yol"]).is_absolute() else k["yol"]
        if not Path(yol).exists():
            raise SystemExit(f"Video dosyası bulunamadı: {k['yol']}")
        return yol, Path(yol).name
    kul = k.get("kullanici", "admin")
    if tur == "http":
        sablon = k.get("adres", "")
        if not sablon:
            raise SystemExit("HTTP akış adresi yazılmamış.")
        url = sablon.replace("{kullanici}", quote(kul, safe="")).replace("{sifre}", quote(sifre_al(k, sifre), safe="") if "{sifre}" in sablon else "")
        return url, maskele(url)
    if tur == "onvif":  # ONVIF kamera ya da kayıt cihazı: akışın adresi her bağlanışta cihazdan sorulur
        import onvif_istemci

        s = sifre_al(k, sifre)
        try:
            adres, profil = onvif_istemci.akis(k.get("ip", ""), int(k.get("port") or 80), kul, s, profil=k.get("profil") or None,
                                               kanal=int(k.get("kanal") or 1), akis=k.get("akis", "alt"), kaynak=k.get("kaynak") or None)
        except onvif_istemci.OnvifHatasi as e:
            raise SystemExit(f"ONVIF: {e}")
        print(f"ONVIF profili: kanal {profil['kanal']} · {profil['ad'] or profil['belirtec']} · {profil['kodlama']} {profil['en']}x{profil['boy']}", flush=True)
        url = adres.replace("rtsp://", f"rtsp://{quote(kul, safe='')}:{quote(s, safe='')}@", 1) if kul else adres
        return url, maskele(url)
    if tur != "rtsp":
        raise SystemExit(f"Bilinmeyen kamera türü: {tur} (rtsp, onvif, http, dosya)")
    if k.get("adres"):
        sablon = k["adres"]
        gerek = "{sifre}" in sablon
        url = sablon.replace("{kullanici}", quote(kul, safe="")).replace("{sifre}", quote(sifre_al(k, sifre), safe="") if gerek else "")
        return url, maskele(url)
    marka = k.get("marka", "hikvision").lower()
    if marka not in MARKALAR:
        raise SystemExit(f"Bilinmeyen marka: {marka}. Tam adresi \"adres\" alanına yazın ya da şunlardan birini seçin: {', '.join(MARKALAR)}")
    if not k.get("ip"):
        raise SystemExit("Kameranın IP adresi yazılmamış. Ayar sayfasında IP adresini girip kaydedin.")
    sablon = MARKALAR[marka]["alt" if k.get("akis", "alt") == "alt" else "ana"]
    url = sablon.format(k=quote(kul, safe=""), s=quote(sifre_al(k, sifre), safe=""), ip=k["ip"], port=k.get("port", 554), kanal=int(k.get("kanal", 1)))
    return url, maskele(url)


def kod(ayar: dict, ayar_yol: Path) -> str:
    return ayar.get("kod") or ayar_yol.stem


def ac(src):
    import cv2

    if src.startswith("rtsp"):
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")  # TCP daha kararlı
    # 8 sn içinde yanıt yoksa vazgeç (OpenCV varsayılanı 30 sn)
    return cv2.VideoCapture(src, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000])


def test(ayar: dict, ayar_yol: Path, sifre: str | None = None) -> int:
    import cv2

    src, goster = kaynak(ayar, sifre)
    print("Bağlanılıyor:", goster, flush=True)
    t0 = time.time()
    cap = ac(src)
    if not cap.isOpened():
        print(f"BAĞLANAMADI ({time.time() - t0:.1f} sn). Kontrol edin: IP ve port doğru mu, bilgisayar kamerayla aynı ağda mı,", flush=True)
        print("kullanıcı/şifre doğru mu, kamerada RTSP açık mı, marka şablonu bu modele uyuyor mu.", flush=True)
        return 1
    kare = None
    for _ in range(30):  # ilk kareler bozuk gelebilir
        ok, fr = cap.read()
        if ok and fr is not None:
            kare = fr
            break
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if kare is None:
        print("Bağlandı ama görüntü gelmedi. Alt akışı (\"akis\": \"alt\") ya da başka kanalı deneyin.", flush=True)
        return 1
    H, W = kare.shape[:2]
    print(f"BAĞLANDI: {W}x{H}, {fps:.0f} fps, {time.time() - t0:.1f} sn.", flush=True)
    yol = yollar.AYAR / f"_kare_{kod(ayar, ayar_yol)}.jpg"
    yol.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(yol), kare)  # bölge çizmek için
    print("Kare kaydedildi.", flush=True)
    if W > 1920:
        print("Not: çözünürlük yüksek; analiz için alt akış (720p) yeterli ve çok daha hızlı.", flush=True)
    return 0


def kaydet(ayar: dict, ayar_yol: Path, dakika: float, hedef: Path | None = None, sifre: str | None = None,
           dur: threading.Event | None = None) -> Path:
    """Kamera görüntüsünü 720p kaydeder. `dur` işaretlenirse kayıt erken bitirilir (o ana kadarki kısım saklanır)."""
    src, goster = kaynak(ayar, sifre)
    an = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    hedef = hedef or yollar.VIDEOLAR / f"{kod(ayar, ayar_yol)}_{an}.mp4"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    sn = max(5, int(dakika * 60))
    print(f"Kayıt: {goster} → {hedef.name} ({sn} sn)", flush=True)
    if str(src).startswith("rtsp"):
        giris = ["-rtsp_transport", "tcp", "-timeout", "8000000"]
    elif (ayar.get("kamera") or {}).get("tur") == "dosya":
        giris = ["-re"]  # video dosyası canlı kamera gibi gerçek hızda okunsun
    else:
        giris = []
    # 720p'ye indir, sesi at; her kamerada aynı biçim çıksın diye yeniden kodla
    komut = [yollar.ffmpeg(), "-y", "-loglevel", "error", *giris, "-i", str(src), "-t", str(sn), "-an",
             "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", str(hedef)]
    p = subprocess.Popen(komut, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **_GIZLI)
    yollar.cocuk_bagla(p)  # program kapanırsa kayıt da dursun
    hata = []
    okuyucu = threading.Thread(target=lambda: hata.extend(p.stderr.read().decode("utf-8", "replace").splitlines()), daemon=True)
    okuyucu.start()
    while p.poll() is None:
        if dur is not None and dur.is_set():
            try:  # ffmpeg'e "q": dosyayı düzgün kapatıp çıkar
                p.stdin.write(b"q")
                p.stdin.flush()
            except OSError:
                pass
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()
            break
        time.sleep(0.3)
    okuyucu.join(timeout=5)
    durduruldu = dur is not None and dur.is_set()
    if not hedef.exists() or hedef.stat().st_size < 10_000 or (p.returncode not in (0, None) and not durduruldu):
        son = maskele(hata[-1]) if hata else "bilinmeyen hata"
        raise SystemExit(f"Kayıt alınamadı: {son}")
    return hedef


def main() -> None:
    ap = argparse.ArgumentParser(description="Kamera bağlantısı")
    alt = ap.add_subparsers(dest="komut", required=True)
    alt.add_parser("markalar", help="hazır marka şablonlarını listele")
    for ad in ("test", "kaydet"):
        p = alt.add_parser(ad)
        p.add_argument("ayar")
        if ad != "test":
            p.add_argument("--dakika", type=float, default=15)
    a = ap.parse_args()
    if a.komut == "markalar":
        for k, v in MARKALAR.items():
            print(f"{k:<10} {v['ad']}\n           {maskele(v['alt'].replace('{k}', 'admin').replace('{s}', 'x'))}")
        print("Listede olmayan marka: tam adresi \"adres\" alanına yazın, şifre yerine {sifre} bırakın.")
        return
    yollar.hazirla()
    ayar_yol = Path(a.ayar)
    ayar = json.loads(ayar_yol.read_text(encoding="utf-8"))
    if a.komut == "test":
        raise SystemExit(test(ayar, ayar_yol))
    print("Kaydedildi:", kaydet(ayar, ayar_yol, a.dakika))


if __name__ == "__main__":
    main()
