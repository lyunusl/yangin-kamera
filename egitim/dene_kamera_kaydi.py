"""Toplu kamera kaydını (kayıt cihazının kanalları) sınar: ya hepsi yazılır ya hiçbiri, var olan kamera ezilmez.

  python egitim/dene_kamera_kaydi.py

Veri klasörü geçicidir; Studio ya da kamera gerekmez. Denetlenenler (uygulama.kameralari_olustur, kanal_ayarlari ve
panelin /api/ayar, /api/ayar/kanallar uçları):
  - aynı anda gelen kayıtlardan yalnızca biri başarılı olur, dosyalar tek bir isteğe aittir
  - aynı kod, örnek kamera kodu ya da geçersiz kod varsa hiçbir dosya yazılmaz
  - yazarken hata çıkarsa oluşturulan dosyalar geri alınır; geri alınamayan kayıt iletide adıyla yazılır
"""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kok = Path(__file__).resolve().parent.parent
os.environ["YANGIN_KAMERA_VERI"] = tempfile.mkdtemp(prefix="yangin_kayit_")
sys.path.insert(0, str(kok))

import uygulama  # noqa: E402
import yollar  # noqa: E402

sonuc: list[tuple[str, bool]] = []


def denetle(ad, kosul):
    sonuc.append((ad, bool(kosul)))
    print(("  geçti  " if kosul else "  KALDI  ") + ad, flush=True)


def hata(islev) -> str:
    try:
        islev()
        return ""
    except uygulama.AyarHatasi as e:
        return str(e)


def kamera(kod, ad="Kamera", **ek):
    return {"kod": kod, "ad": ad, "kamera": {"tur": "rtsp", "marka": "hikvision", "ip": "192.0.2.10", "kanal": 1, **ek}, "bolgeler": []}


def dosyalar(on=""):
    return sorted(p.stem for p in yollar.AYAR.glob(f"{on}*.json")) if yollar.AYAR.is_dir() else []


print("Tek işlemde oluşturma")
r = uygulama.kameralari_olustur([kamera("a-k1", sifre="gizli-deneme"), kamera("a-k2"), kamera("a-k3")])
denetle("üç kamera birlikte yazılır", r["kodlar"] == ["a-k1", "a-k2", "a-k3"] and dosyalar("a-") == ["a-k1", "a-k2", "a-k3"])
denetle("şifre alanı dosyaya yazılmaz, not döner", "gizli-deneme" not in uygulama.ayar_yolu("a-k1").read_text(encoding="utf-8") and r["notlar"])
onceki = uygulama.ayar_yolu("a-k2").read_text(encoding="utf-8")
m = hata(lambda: uygulama.kameralari_olustur([kamera("b-k1"), kamera("a-k2", ad="EZEN"), kamera("b-k3")]))
denetle("listede var olan bir kod varsa hiçbiri yazılmaz, var olan değişmez",
        "a-k2" in m and "hiçbiri eklenmedi" in m and dosyalar("b-") == [] and uygulama.ayar_yolu("a-k2").read_text(encoding="utf-8") == onceki)
denetle("aynı kod listede iki kez geçerse hiçbiri yazılmaz", "birden çok" in hata(lambda: uygulama.kameralari_olustur([kamera("c-k1"), kamera("c-k1")])) and dosyalar("c-") == [])
denetle("geçersiz kod varsa hiçbiri yazılmaz", "Kısa kod" in hata(lambda: uygulama.kameralari_olustur([kamera("d-k1"), kamera("D K2")])) and dosyalar("d-") == [])
ornek = next(iter(yollar.ORNEK_ADLARI))  # örnek kodları, videoları gelmeden de ayrılmıştır
denetle("örnek kamera kodu reddedilir", "örnek" in hata(lambda: uygulama.kameralari_olustur([kamera("e-k1"), kamera(ornek)])) and dosyalar("e-") == [])
denetle("boş ya da 64'ten uzun liste reddedilir", all("1 ile 64" in hata(lambda x=x: uygulama.kameralari_olustur(x)) for x in ([], [kamera(f"f-k{i}") for i in range(65)], None)))

print("Yazma hatası")
gercek_yaz, gercek_sil = uygulama._ayar_metni_yaz, uygulama._ayar_sil


def bozuk_yaz(dosya, ayar):
    if ayar["kod"] == "g-k3":
        dosya.write('{"yarım')  # yarım yazılmış dosya
        raise OSError("disk dolu")
    gercek_yaz(dosya, ayar)


uygulama._ayar_metni_yaz = bozuk_yaz
m = hata(lambda: uygulama.kameralari_olustur([kamera("g-k1"), kamera("g-k2"), kamera("g-k3"), kamera("g-k4")]))
denetle("üçüncü dosya yazılamazsa önceki ikisi ve yarım dosya geri alınır", "Hiçbiri eklenmedi" in m and dosyalar("g-") == [])


def bozuk_sil(kod):
    if kod == "h-k1":
        raise PermissionError("dosya kilitli")
    gercek_sil(kod)


uygulama._ayar_metni_yaz = lambda dosya, ayar: (_ for _ in ()).throw(OSError("disk dolu")) if ayar["kod"] == "h-k2" else gercek_yaz(dosya, ayar)
uygulama._ayar_sil = bozuk_sil
m = hata(lambda: uygulama.kameralari_olustur([kamera("h-k1"), kamera("h-k2")]))
denetle("geri alınamayan kayıt iletide adıyla yazılır", "Geri alınamayan kayıtlar kaldı: h-k1" in m and dosyalar("h-") == ["h-k1"])
uygulama._ayar_metni_yaz, uygulama._ayar_sil = gercek_yaz, gercek_sil
gercek_sil("h-k1")

print("Eşzamanlı kayıt")


def yaris(n, islev):
    """`islev(i)`yi n iş parçacığında aynı anda başlatır. Dönüş: [(i, hata iletisi ya da "")]."""
    bariyer, cikti = threading.Barrier(n), []

    def calis(i):
        bariyer.wait()
        cikti.append((i, hata(lambda: islev(i))))

    isler = [threading.Thread(target=calis, args=(i,)) for i in range(n)]
    for t in isler:
        t.start()
    for t in isler:
        t.join()
    return cikti


c = yaris(12, lambda i: uygulama.kameralari_olustur([kamera(f"y-k{n}", ad=f"istek {i}") for n in (1, 2, 3, 4)]))
kazanan = [i for i, m in c if not m]
adlar = {json.loads(uygulama.ayar_yolu(k).read_text(encoding="utf-8"))["ad"] for k in dosyalar("y-")}
denetle("aynı dört kodu yazan 12 eşzamanlı istekten yalnızca biri başarılı", len(kazanan) == 1 and all("zaten var" in m or "az önce" in m for i, m in c if m))
denetle("dört dosyanın hepsi kazanan isteğe ait (karışık kayıt yok)", dosyalar("y-") == ["y-k1", "y-k2", "y-k3", "y-k4"] and adlar == {f"istek {kazanan[0]}"})
c = yaris(12, lambda i: uygulama.kameralari_olustur([kamera("tek", ad=f"istek {i}")]))
denetle("aynı kodla 12 eşzamanlı tekli oluşturmadan yalnızca biri başarılı", sum(1 for _, m in c if not m) == 1)
c = yaris(8, lambda i: uygulama.kameralari_olustur([kamera(f"z{i}-k1"), kamera("ortak" if i % 2 else f"z{i}-k2")]))
kalan = dosyalar("z")
denetle("ortak koda çarpan isteklerin öteki dosyaları da kalmaz",
        sum(1 for i, m in c if not m and i % 2) == 1 and all(f"z{i}-k1" not in kalan for i, m in c if m) and "ortak" in dosyalar("ortak"))

print("Kanal ayarları")
taban = {"kod": "nvr", "ad": "NVR", "kurallar": [{"kod": "alev"}], "kamera": {"tur": "rtsp", "marka": "dahua", "ip": "192.0.2.30", "kanal": 7, "akis": "alt"}}
a = uygulama.kanal_ayarlari(taban, [1, 2, 3])
denetle("markaya göre RTSP: kanal başına ayrı kod, ad ve kanal numarası", [(x["kod"], x["ad"], x["kamera"]["kanal"]) for x in a] == [("nvr-k1", "NVR · Kanal 1", 1), ("nvr-k2", "NVR · Kanal 2", 2), ("nvr-k3", "NVR · Kanal 3", 3)])
denetle("yinelenen ya da geçersiz kanal listesi reddedilir", all(hata(lambda k=k: uygulama.kanal_ayarlari(taban, k)) for k in ([1, 1], [0, 1], [], ["x"], None)))
denetle("IP adresi ya da kısa kod yoksa reddedilir", "IP adresi" in hata(lambda: uygulama.kanal_ayarlari({**taban, "kamera": {"tur": "rtsp"}}, [1, 2])) and "kısa kodu" in hata(lambda: uygulama.kanal_ayarlari({**taban, "kod": ""}, [1, 2])))
onvif_taban = {**taban, "kod": "onv", "kamera": {"tur": "onvif", "ip": "192.0.2.31", "port": 80, "akis": "ana"}}
denetle("ONVIF'te profil listesi yoksa reddedilir (belirteçsiz ayar üretilmez)", all("listelenmeli" in hata(lambda p=p: uygulama.kanal_ayarlari(onvif_taban, [1, 2], p)) for p in (None, [], "x")))
pr = [{"belirtec": "p11", "kaynak": "s1", "kanal": 1, "en": 1920, "boy": 1080}, {"belirtec": "p12", "kaynak": "s1", "kanal": 1, "en": 640, "boy": 360},
      {"belirtec": "p21", "kaynak": "s2", "kanal": 2, "en": 1280, "boy": 720}, {"belirtec": "", "kaynak": "s3", "kanal": 3, "en": 1, "boy": 1}]
a = uygulama.kanal_ayarlari(onvif_taban, [1, 2], pr)
denetle("ONVIF: ana akışta en yüksek çözünürlüklü profilin ve kaynağın belirteci yazılır", [(x["kamera"]["profil"], x["kamera"]["kaynak"]) for x in a] == [("p11", "s1"), ("p21", "s2")])
denetle("belirteci boş profilden kanal üretilmez", "3. kanal yok" in hata(lambda: uygulama.kanal_ayarlari(onvif_taban, [1, 3], pr)))

print("Panelin uçları (yerel sunucu)")
sunucu = uygulama.Sunucu(("127.0.0.1", 0), uygulama.Istek)
port = sunucu.server_address[1]
threading.Thread(target=sunucu.serve_forever, daemon=True).start()


def gonder(yol, govde):
    istek = urllib.request.Request(f"http://127.0.0.1:{port}{yol}", data=json.dumps(govde).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(istek, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        with e:
            return e.code, json.loads(e.read().decode("utf-8"))


kod, y = gonder("/api/ayar/kanallar", {"taban": {**taban, "kod": "uc"}, "kanallar": [1, 2]})
denetle("/api/ayar/kanallar iki kamerayı oluşturur", kod == 200 and y.get("kodlar") == ["uc-k1", "uc-k2"] and dosyalar("uc-") == ["uc-k1", "uc-k2"])
kod, y = gonder("/api/ayar/kanallar", {"taban": {**taban, "kod": "uc"}, "kanallar": [2, 3]})
denetle("çakışan istek 400 döner, yeni kanal da yazılmaz", kod == 400 and "uc-k2" in y.get("hata", "") and dosyalar("uc-") == ["uc-k1", "uc-k2"])
kod, y = gonder("/api/ayar/kanallar", {"taban": onvif_taban, "kanallar": [1, 2]})
denetle("ONVIF için profil listesi gönderilmezse 400 döner", kod == 400 and "listelenmeli" in y.get("hata", "") and dosyalar("onv-") == [])
kod, y = gonder("/api/ayar", {"yeni": True, "ayar": kamera("uc-k1", ad="EZEN")})
denetle("/api/ayar yeni=true var olan kamerayı ezmez", kod == 400 and json.loads(uygulama.ayar_yolu("uc-k1").read_text(encoding="utf-8"))["ad"] == "NVR · Kanal 1")
kod, y = gonder("/api/ayar", {"ayar": kamera("uc-k1", ad="Düzenlendi")})
denetle("/api/ayar (düzenleme) var olan kamerayı günceller", kod == 200 and json.loads(uygulama.ayar_yolu("uc-k1").read_text(encoding="utf-8"))["ad"] == "Düzenlendi")
sunucu.shutdown()
sunucu.server_close()

kalan = [ad for ad, ok in sonuc if not ok]
print(f"\n{len(sonuc) - len(kalan)}/{len(sonuc)} denetim geçti" + (f" · kalanlar: {kalan}" if kalan else ""))
sys.exit(1 if kalan else 0)
