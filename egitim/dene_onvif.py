"""ONVIF istemcisini (onvif_istemci.py) ve kameranın ONVIF bağlantısını, bu bilgisayarda çalışan sahte bir cihaza karşı sınar.

  python egitim/dene_onvif.py
  python egitim/dene_onvif.py sun [port]     sahte cihazı açık tutar: kamera ayarındaki ONVIF alanlarını elle denemek için

Sahte cihaz iki kanallı bir kayıt cihazı gibi davranır (kanal başına ana ve alt akış profili), saati bir saat ileridedir,
servis ve akış adreslerinde başka bir sunucu adı bildirir ve WS-Security özetini denetler. İstendiğinde profilleri ters
sırayla bildirir, bir profili ya da kaynağı "kaybeder", gövdeyi çok yavaş gönderir ya da HTTP Digest ister.
Gerçek bir kamera ya da kayıt cihazıyla yapılmış bir sınama değildir. Kamera ayarları geçici bir veri klasörüne yazılır.
"""
import base64
import datetime as dt
import hashlib
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kok = Path(__file__).resolve().parent.parent
os.environ["YANGIN_KAMERA_VERI"] = tempfile.mkdtemp(prefix="yangin_onvif_")  # panelin veri klasörü yerine geçici klasör
sys.path.insert(0, str(kok))

import kamera  # noqa: E402
import onvif_istemci as onvif  # noqa: E402
import uygulama  # noqa: E402

KULLANICI, SIFRE = "izleyici", "deneme-şifresi 1/2"  # yalnızca bu sınamadaki sahte cihazın şifresi
BASKA_SUNUCU = "192.0.2.77"  # cihazın "kendi adresi" diye bildirdiği, bu bilgisayarda olmayan adres (belgelere ayrılmış aralık)
SAAT_FARKI = dt.timedelta(hours=1)
sonuc: list[tuple[str, bool]] = []
gorulen = {"sunucular": set(), "ozetsiz": 0, "digest": False}
cihaz_durumu = {"ters": False, "eksik": set()}  # sınama sırasında değiştirilir: profil sırası, kaybolan profiller


def zarf(govde: str) -> bytes:
    return ('<?xml version="1.0" encoding="UTF-8"?><SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" '
            'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" '
            f'xmlns:tt="http://www.onvif.org/ver10/schema"><SOAP-ENV:Body>{govde}</SOAP-ENV:Body></SOAP-ENV:Envelope>').encode("utf-8")


def profil(belirtec, ad, kaynak, en, boy):
    return (f'<trt:Profiles token="{belirtec}" fixed="true"><tt:Name>{ad}</tt:Name><tt:VideoSourceConfiguration token="vsc_{kaynak}">'
            f'<tt:SourceToken>{kaynak}</tt:SourceToken></tt:VideoSourceConfiguration><tt:VideoEncoderConfiguration token="vec_{belirtec}">'
            f'<tt:Encoding>H264</tt:Encoding><tt:Resolution><tt:Width>{en}</tt:Width><tt:Height>{boy}</tt:Height></tt:Resolution>'
            '</tt:VideoEncoderConfiguration></trt:Profiles>')


PROFIL_PARCALARI = [("Profile_101", profil("Profile_101", "Kanal1 Ana", "VideoSource_1", 2560, 1440)),
                    ("Profile_102", profil("Profile_102", "Kanal1 Alt", "VideoSource_1", 640, 360)),
                    ("Profile_ses", '<trt:Profiles token="Profile_ses"><tt:Name>Yalnız ses</tt:Name></trt:Profiles>'),
                    ("Profile_201", profil("Profile_201", "Kanal2 Ana", "VideoSource_2", 1920, 1080)),
                    ("Profile_202", profil("Profile_202", "Kanal2 Alt", "VideoSource_2", 704, 576))]


def profil_listesi() -> str:
    parcalar = [x for b, x in PROFIL_PARCALARI if b not in cihaz_durumu["eksik"]]
    return "".join(reversed(parcalar) if cihaz_durumu["ters"] else parcalar)


AKISLAR = {"Profile_101": "/Streaming/Channels/101", "Profile_102": "/Streaming/Channels/102?transportmode=unicast",
           "Profile_201": "/Streaming/Channels/201", "Profile_202": "/Streaming/Channels/202"}


class SahteCihaz(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _yanit(self, kod, govde: bytes):
        self.send_response(kod)
        self.send_header("Content-Type", "application/soap+xml; charset=utf-8")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def _yavas(self, kod):
        """Başlıkları hemen, gövdeyi altı saniyeye yayarak gönderir (her 0,2 saniyede 20 bayt)."""
        self.send_response(kod)
        self.send_header("Content-Type", "application/soap+xml; charset=utf-8")
        self.send_header("Content-Length", "600")
        self.end_headers()
        try:
            for _ in range(60):
                self.wfile.write(b"<a>................</a>"[:10])
                self.wfile.flush()
                time.sleep(0.1)
        except OSError:
            gorulen["kapandi"] = time.monotonic()  # istemci süresi dolunca bağlantıyı kapattı

    def _yavas_baslik(self):
        """Durum satırını hemen, başlıkları altı saniyeye yayarak gönderir; gövdeye hiç gelmez."""
        self.close_connection = True
        try:
            self.wfile.write(b"HTTP/1.1 200 OK\r\n")
            for _ in range(60):
                self.wfile.write(b"X-Yavas: 1\r\n")
                self.wfile.flush()
                time.sleep(0.1)
        except OSError:
            gorulen["kapandi"] = time.monotonic()

    def _digest(self):
        if self.headers.get("Authorization"):
            gorulen["digest"] = True
            return self._yavas(200)
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Digest realm="onvif", nonce="4f6e766966", qop="auth", algorithm=MD5')
        if not self.path.endswith("yavas401"):
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        self.send_header("Content-Length", "600")
        self.end_headers()
        try:
            for _ in range(60):
                self.wfile.write(b"x" * 10)
                self.wfile.flush()
                time.sleep(0.1)
        except OSError:
            gorulen["kapandi"] = time.monotonic()
        return None

    def _kimlik(self, kok_) -> bool:
        ad = lambda e: e.tag.rsplit("}", 1)[-1]  # noqa: E731
        al = lambda a: next(((e.text or "") for e in kok_.iter() if ad(e) == a), None)  # noqa: E731
        k, ozet, nonce, zaman = al("Username"), al("Password"), al("Nonce"), al("Created")
        if None in (k, ozet, nonce, zaman):
            gorulen["ozetsiz"] += 1
            return False
        try:
            t = dt.datetime.strptime(zaman[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return False
        if abs((dt.datetime.now(dt.timezone.utc) + SAAT_FARKI - t).total_seconds()) > 15:  # cihazın saatine göre
            return False
        beklenen = base64.b64encode(hashlib.sha1(base64.b64decode(nonce) + zaman.encode() + SIFRE.encode("utf-8")).digest()).decode()
        return k == KULLANICI and ozet == beklenen

    def do_POST(self):
        gorulen["sunucular"].add(self.headers.get("Host", ""))
        govde = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        kok_ = ET.fromstring(govde)
        istek = next(e.tag.rsplit("}", 1)[-1] for e in kok_.iter() if e.tag.rsplit("}", 1)[-1].startswith("Get"))
        port = self.server.server_address[1]
        if istek == "GetSystemDateAndTime":
            t = dt.datetime.now(dt.timezone.utc) + SAAT_FARKI
            return self._yanit(200, zarf(f"<tds:GetSystemDateAndTimeResponse><tds:SystemDateAndTime><tt:UTCDateTime><tt:Time><tt:Hour>{t.hour}</tt:Hour>"
                                         f"<tt:Minute>{t.minute}</tt:Minute><tt:Second>{t.second}</tt:Second></tt:Time><tt:Date><tt:Year>{t.year}</tt:Year>"
                                         f"<tt:Month>{t.month}</tt:Month><tt:Day>{t.day}</tt:Day></tt:Date></tt:UTCDateTime></tds:SystemDateAndTime>"
                                         "</tds:GetSystemDateAndTimeResponse>"))
        if self.path.startswith("/onvif/digest"):  # yalnızca HTTP Digest isteyen cihaz: ilk yanıt 401, kimlikli tekrar yavaş
            return self._digest()
        if not self._kimlik(kok_):
            return self._yanit(400, zarf('<SOAP-ENV:Fault><SOAP-ENV:Code><SOAP-ENV:Value>SOAP-ENV:Sender</SOAP-ENV:Value><SOAP-ENV:Subcode>'
                                         '<SOAP-ENV:Value>ter:NotAuthorized</SOAP-ENV:Value></SOAP-ENV:Subcode></SOAP-ENV:Code><SOAP-ENV:Reason>'
                                         '<SOAP-ENV:Text xml:lang="en">Sender not Authorized</SOAP-ENV:Text></SOAP-ENV:Reason></SOAP-ENV:Fault>'))
        if self.path == "/onvif/yavas-baslik":
            return self._yavas_baslik()
        if self.path == "/onvif/yavas200":
            return self._yavas(200)
        if self.path == "/onvif/yavas500":
            return self._yavas(500)
        if self.path == "/onvif/buyuk":  # sınırın üstünde yanıt
            return self._yanit(200, b"<a>" + b"x" * (onvif.EN_COK_YANIT + 1000) + b"</a>")
        if self.path == "/onvif/varlik":  # belge türü ve varlık tanımı içeren yanıt
            return self._yanit(200, b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY b "bbbbbbbbbb">]><a>&b;</a>')
        if self.path == "/onvif/hata":  # cihazın hata metni güvenilmezdir
            return self._yanit(500, zarf('<SOAP-ENV:Fault><SOAP-ENV:Reason><SOAP-ENV:Text>&lt;script&gt;alert(1)&lt;/script&gt; ' + "uzun " * 80
                                         + '</SOAP-ENV:Text></SOAP-ENV:Reason></SOAP-ENV:Fault>'))
        if istek == "GetCapabilities":  # servis adresinde başka bir sunucu adı bildirir
            return self._yanit(200, zarf(f"<tds:GetCapabilitiesResponse><tds:Capabilities><tt:Media><tt:XAddr>http://{BASKA_SUNUCU}:{port}/onvif/medya2</tt:XAddr>"
                                         "</tt:Media></tds:Capabilities></tds:GetCapabilitiesResponse>"))
        if istek == "GetDeviceInformation":
            return self._yanit(200, zarf("<tds:GetDeviceInformationResponse><tds:Manufacturer>Sahte</tds:Manufacturer><tds:Model>NVR-2K</tds:Model>"
                                         "<tds:FirmwareVersion>1.0</tds:FirmwareVersion></tds:GetDeviceInformationResponse>"))
        if istek == "GetProfiles" and self.path == "/onvif/medya2":
            return self._yanit(200, zarf(f"<trt:GetProfilesResponse>{profil_listesi()}</trt:GetProfilesResponse>"))
        if istek == "GetStreamUri" and self.path == "/onvif/medya2":
            belirtec = next((e.text for e in kok_.iter() if e.tag.endswith("ProfileToken")), "")
            if belirtec not in AKISLAR:
                return self._yanit(400, zarf("<SOAP-ENV:Fault><SOAP-ENV:Reason><SOAP-ENV:Text>NoProfile</SOAP-ENV:Text></SOAP-ENV:Reason></SOAP-ENV:Fault>"))
            return self._yanit(200, zarf(f"<trt:GetStreamUriResponse><trt:MediaUri><tt:Uri>rtsp://baskasi:gizli@{BASKA_SUNUCU}:8554{AKISLAR[belirtec].replace('&', '&amp;')}</tt:Uri>"
                                         "</trt:MediaUri></trt:GetStreamUriResponse>"))
        return self._yanit(404, b"yok")


def kesif_yanitlayici(port: int, dur: threading.Event, hazir: threading.Event):
    """WS-Discovery sorgusuna yanıt veren sahte cihaz (çoklu yayın grubuna katılır)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", 3702))
        for ip in onvif._yerel_adresler() + ["127.0.0.1"]:
            try:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, struct.pack("4s4s", socket.inet_aton("239.255.255.250"), socket.inet_aton(ip or "0.0.0.0")))
            except OSError:
                pass
        s.settimeout(0.3)
    except OSError:
        hazir.set()
        return
    hazir.set()
    while not dur.is_set():
        try:
            veri, kimden = s.recvfrom(65535)
        except OSError:
            continue
        if b"Probe" not in veri:
            continue
        yanit = ('<?xml version="1.0" encoding="UTF-8"?><e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
                 'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"><e:Body><d:ProbeMatches>'
                 '<d:ProbeMatch><d:Scopes>onvif://www.onvif.org/name/Bozuk</d:Scopes><d:XAddrs>http://192.0.2.9:kapi/onvif/device_service</d:XAddrs></d:ProbeMatch>'
                 '<d:ProbeMatch><d:Scopes>onvif://www.onvif.org/name/Sahte%20NVR onvif://www.onvif.org/hardware/NVR-2K</d:Scopes>'
                 f'<d:XAddrs>http://{kimden[0]}:{port}/onvif/device_service</d:XAddrs></d:ProbeMatch></d:ProbeMatches></e:Body></e:Envelope>')
        s.sendto(yanit.encode("utf-8"), kimden)
    s.close()


def denetle(ad, kosul):
    sonuc.append((ad, bool(kosul)))
    print(("  geçti  " if kosul else "  KALDI  ") + ad, flush=True)


def hata(islev) -> str:
    try:
        islev()
        return ""
    except (onvif.OnvifHatasi, uygulama.AyarHatasi, SystemExit) as e:
        return str(e)


SUN = len(sys.argv) > 1 and sys.argv[1] == "sun"
sunucu = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[2]) if SUN and len(sys.argv) > 2 else 0), SahteCihaz)
PORT = sunucu.server_address[1]
threading.Thread(target=sunucu.serve_forever, daemon=True).start()
if SUN:  # elle deneme: kamera ayarında IP 127.0.0.1, ONVIF portu aşağıdaki port; kullanıcı ve şifre bu dosyanın başındaki sınama değerleri
    SAAT_FARKI = dt.timedelta(0)
    threading.Thread(target=kesif_yanitlayici, args=(PORT, threading.Event(), threading.Event()), daemon=True).start()
    print(f"Sahte ONVIF cihazı 127.0.0.1:{PORT} adresinde çalışıyor (kullanıcı: {KULLANICI}). Durdurmak için Ctrl+C.", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        sys.exit(0)

print("Kanallar ve profiller")
c = onvif.Cihaz("127.0.0.1", PORT, KULLANICI, SIFRE)
p = c.profiller()
denetle("dört görüntü profili, ses profili sayılmaz", [x["belirtec"] for x in p] == ["Profile_101", "Profile_102", "Profile_201", "Profile_202"])
denetle("profiller görüntü kaynağına göre iki kanala ayrılır", [x["kanal"] for x in p] == [1, 1, 2, 2])
denetle("çözünürlük ve kodlama okunur", (p[0]["en"], p[0]["boy"], p[0]["kodlama"]) == (2560, 1440, "H264"))
denetle("cihaz bilgisi okunur", c.bilgi() == {"uretici": "Sahte", "model": "NVR-2K", "yazilim": "1.0"})
denetle("cihazın saati bir saat ileride: özet cihaz saatine göre kabul edildi", abs(c._fark - 3600) < 5)

print("Profil seçimi")
denetle("kaynak belirteciyle alt akış: o kaynağın en düşük çözünürlüğü", c.sec(None, 9, "alt", kaynak="VideoSource_1")["belirtec"] == "Profile_102")
denetle("kaynak belirteciyle ana akış: o kaynağın en yüksek çözünürlüğü", c.sec(None, 9, "ana", kaynak="VideoSource_2")["belirtec"] == "Profile_201")
denetle("kayıtlı profil belirteci kanal numarasına ve akışa üstün gelir", c.sec("Profile_201", 1, "alt")["belirtec"] == "Profile_201")
denetle("cihazda bulunmayan kayıtlı profil hata verir, başka kanala düşülmez", "başka bir kanala geçilmedi" in hata(lambda: c.sec("Profile_999")))
denetle("çok kanallı cihazda yalnızca kanal numarası belirsizdir: bağlanılmaz, profil seçimi istenir",
        all("yalnızca kanal numarasıyla" in hata(lambda n=n: c.sec(None, n, "alt")) for n in (1, 2)))
cihaz_durumu["eksik"] = {"Profile_201", "Profile_202"}  # tek görüntü kaynağı: tek kanallı kamera gibi
tek = onvif.Cihaz("127.0.0.1", PORT, KULLANICI, SIFRE)
denetle("tek kanallı kamerada belirteçsiz kayıt çalışır: alt ve ana akış", (tek.sec(None, 1, "alt")["belirtec"], tek.sec(None, 1, "ana")["belirtec"]) == ("Profile_102", "Profile_101"))
denetle("tek kanallı kamerada olmayan kanal anlaşılır hata verir", "3. kanal yok" in hata(lambda: tek.sec(None, 3, "alt")))
cihaz_durumu["eksik"] = set()

print("Akış adresi ve adres sabitleme")
adres = c.akis_adresi("Profile_102")
denetle("RTSP adresi yolu ve sorgusuyla alınır", adres == "rtsp://127.0.0.1:8554/Streaming/Channels/102?transportmode=unicast")
denetle("akış adresinde cihazın bildirdiği başka sunucu ve kimlik kullanılmaz", BASKA_SUNUCU not in adres and "gizli" not in adres)
denetle("bütün istekler yazılan adrese gitti (bildirilen servis adresine değil)", gorulen["sunucular"] == {f"127.0.0.1:{PORT}"})

print("Kimlik ve hata iletileri")
m = hata(lambda: onvif.Cihaz("127.0.0.1", PORT, KULLANICI, "yanlış").profiller())
denetle("yanlış şifre: anlaşılır ileti, şifre iletide yok", "kabul etmedi" in m and "yanlış" not in m)
denetle("yanlış kullanıcı reddedilir", "kabul etmedi" in hata(lambda: onvif.Cihaz("127.0.0.1", PORT, "baska", SIFRE).profiller()))
kapali = socket.socket()
kapali.bind(("127.0.0.1", 0))
bos_port = kapali.getsockname()[1]
kapali.close()
m = hata(lambda: onvif.Cihaz("127.0.0.1", bos_port, KULLANICI, SIFRE, zaman_asimi=6).profiller())  # Windows kapalı porta ret yanıtını ~2 sn sonra verir
denetle("ulaşılamayan cihaz: port önerisiyle ileti", "ulaşılamadı" in m and "8899" in m)
denetle("geçersiz IP adresi istek atılmadan reddedilir", "geçersiz" in hata(lambda: onvif.Cihaz("127.0.0.1/../x", 80)))

print("Güvenilmeyen cihaz yanıtları")
for yol, beklenen, ad in (("/onvif/buyuk", "çok büyük", "sınırın üstündeki yanıt okunmaz"),
                          ("/onvif/varlik", "ONVIF yanıtı vermedi", "belge türü tanımı içeren yanıt ayrıştırılmaz")):
    k = onvif.Cihaz("127.0.0.1", PORT, KULLANICI, SIFRE)
    k._saat()
    k._medya = f"http://127.0.0.1:{PORT}{yol}"
    denetle(ad, beklenen in hata(k.profiller))
k = onvif.Cihaz("127.0.0.1", PORT, KULLANICI, SIFRE)
k._saat()
k._medya = f"http://127.0.0.1:{PORT}/onvif/hata"
m = hata(k.profiller)
denetle("cihazın serbest hata metni iletiye taşınmaz (yalnızca HTTP kodu)", m == "Cihaz isteği reddetti (HTTP 500).")
ayar_hata = {"kod": "x", "kamera": {"tur": "onvif", "ip": "127.0.0.1", "port": PORT, "kullanici": KULLANICI}}
gercek_medya = onvif.Cihaz._medya_adresi
onvif.Cihaz._medya_adresi = lambda self: (self._saat(), f"http://127.0.0.1:{PORT}/onvif/hata")[1]
m = hata(lambda: kamera.kaynak(ayar_hata, SIFRE))
onvif.Cihaz._medya_adresi = gercek_medya
denetle("iş hatasına da taşınmaz (kamera bağlantısı)", m == "ONVIF: Cihaz isteği reddetti (HTTP 500)." and "script" not in m and "uzun" not in m)

print("Toplam süre sınırı ve iptal (başlığını ya da gövdesini yavaş gönderen cihaz, sınır 1,0 sn)")
for yol, ad in (("/onvif/yavas-baslik", "yavaş başlıklar"), ("/onvif/yavas200", "yavaş HTTP 200 gövdesi"), ("/onvif/yavas500", "yavaş HTTP 500 gövdesi"),
                ("/onvif/digest", "HTTP Digest tekrarından sonra yavaş gövde"), ("/onvif/digest-yavas401", "HTTP 401 gövdesi yavaş (Digest isteği)")):
    k = onvif.Cihaz("127.0.0.1", PORT, KULLANICI, "digest-icin-ascii" if "digest" in yol else SIFRE)
    k._saat()
    k.zaman_asimi = 1.0
    k._medya = f"http://127.0.0.1:{PORT}{yol}"
    gorulen.pop("kapandi", None)
    t0 = time.monotonic()
    m = hata(k.profiller)
    gecen = time.monotonic() - t0
    isciler = [t for t in threading.enumerate() if t.name == "onvif-istek" and t.is_alive()]  # hata döndüğü anda
    denetle(f"{ad}: {gecen:.2f} sn içinde süre hatası", m == onvif.SURE_DOLDU and gecen <= 1.15)
    time.sleep(0.5)  # sahte cihaz, kapanan bağlantıyı bir sonraki yazışında fark eder
    kapandi = gorulen.get("kapandi")
    denetle(f"{ad}: hata döndüğünde işçi bitmiş, bağlantı kapatılmış" + (f" (cihaz {kapandi - t0:.2f} sn'de gördü)" if kapandi else ""),
            not isciler and kapandi is not None and kapandi - t0 <= 1.5)
denetle("Digest tekrarı gerçekten yapıldı (kimlikli istek cihaza ulaştı)", gorulen["digest"])
k = onvif.Cihaz("127.0.0.1", PORT, KULLANICI, SIFRE)  # ASCII dışı karakterli şifre
k._saat()
k._medya = f"http://127.0.0.1:{PORT}/onvif/digest"
denetle("Digest isteyen cihazda ASCII dışı şifre: çökme yerine anlaşılır hata", "ASCII dışı" in hata(k.profiller))
k = onvif.Cihaz("127.0.0.1", PORT, KULLANICI, SIFRE)
t0 = time.monotonic()
k.profiller()
denetle(f"olağan cihazda dört istek süre sınırına takılmaz ({time.monotonic() - t0:.2f} sn)", time.monotonic() - t0 < 2.0)

print("Kalıcı kanal eşlemesi (profil ve kaynak belirteci)")
duz = onvif.Cihaz("127.0.0.1", PORT, KULLANICI, SIFRE).profiller()
cihaz_durumu["ters"] = True
ters = onvif.Cihaz("127.0.0.1", PORT, KULLANICI, SIFRE).profiller()
denetle("cihaz profilleri ters sırayla bildirince kanal numaraları ve liste sırası değişmez", duz == ters and [x["kanal"] for x in ters] == [1, 1, 2, 2])
cihaz_durumu["ters"] = False
taban = {"kod": "nvr", "ad": "Kayıt cihazı", "kurallar": [{"kod": "alev"}], "bolgeler": [{"ad": "x", "tur": "kritik", "poly": [[0, 0], [1, 0], [1, 1]]}],
         "kamera": {"tur": "onvif", "ip": "127.0.0.1", "port": PORT, "kullanici": KULLANICI, "akis": "alt", "sifre": SIFRE}}
uygulama.kameralari_olustur(uygulama.kanal_ayarlari(taban, [1, 2], duz))
k1, k2 = uygulama.ayar_oku("nvr-k1"), uygulama.ayar_oku("nvr-k2")
denetle("toplu kayıt her kanalın profil ve kaynak belirtecini yazar",
        (k1["kamera"]["profil"], k1["kamera"]["kaynak"], k2["kamera"]["profil"], k2["kamera"]["kaynak"]) == ("Profile_102", "VideoSource_1", "Profile_202", "VideoSource_2"))
denetle("toplu kayıtta şifre yazılmaz, bölgeler boş başlar, kurallar kopyalanır",
        SIFRE not in (uygulama.ayar_yolu("nvr-k1").read_text(encoding="utf-8") + uygulama.ayar_yolu("nvr-k2").read_text(encoding="utf-8"))
        and k2["bolgeler"] == [] and k2["kurallar"] == [{"kod": "alev"}] and k2["ad"] == "Kayıt cihazı · Kanal 2")
yol = lambda ayar: kamera.kaynak(ayar, SIFRE)[0].split("8554", 1)[1]  # noqa: E731
denetle("kayıtlı kamera kendi kanalına bağlanır", (yol(k1), yol(k2)) == ("/Streaming/Channels/102?transportmode=unicast", "/Streaming/Channels/202"))
cihaz_durumu["ters"] = True
denetle("profil sırası değişince de aynı fiziksel kanal", (yol(k1), yol(k2)) == ("/Streaming/Channels/102?transportmode=unicast", "/Streaming/Channels/202"))
yalniz_kanal = {"kod": "y", "kamera": {"tur": "onvif", "ip": "127.0.0.1", "port": PORT, "kullanici": KULLANICI, "kanal": 2, "akis": "alt"}}
m_ters = hata(lambda: kamera.kaynak(yalniz_kanal, SIFRE))
cihaz_durumu["ters"] = False
m_duz = hata(lambda: kamera.kaynak(yalniz_kanal, SIFRE))
cihaz_durumu["ters"] = True
denetle("eski, belirteçsiz çok kanallı kayıt hiçbir sırada bağlanmaz: yeniden profil seçimi istenir",
        all(m.startswith("ONVIF: ") and "profili seçin" in m for m in (m_ters, m_duz)))
yeniden = {"kod": "y", "kamera": {**yalniz_kanal["kamera"], "profil": "Profile_202", "kaynak": "VideoSource_2"}}
denetle("profil yeniden seçilince aynı kayıt kanalına bağlanır", yol(yeniden) == "/Streaming/Channels/202")
cihaz_durumu["eksik"] = {"Profile_202"}
denetle("profil belirteci kaybolunca aynı kaynağın öteki profili kullanılır, başka kanala düşülmez", yol(k2) == "/Streaming/Channels/201")
cihaz_durumu["eksik"] = {"Profile_201", "Profile_202"}
m = hata(lambda: kamera.kaynak(k2, SIFRE))
denetle("profil ve kaynak birlikte kaybolunca hata: kanal 1'e geçilmez", "başka bir kanala geçilmedi" in m)
cihaz_durumu.update(ters=False, eksik=set())
tasinmis = {"kod": "t", "kamera": {**k2["kamera"], "profil": "Profile_101"}}  # belirteç artık başka kaynağın profili
denetle("profil belirteci başka kaynağa aitse kayıtlı kaynak esas alınır", yol(tasinmis) == "/Streaming/Channels/202")
m = hata_ayar = ""
try:
    uygulama.kanal_ayarlari({**taban, "kod": "nvr2"}, [1, 2, 3], duz)
except uygulama.AyarHatasi as e:
    m = str(e)
denetle("cihazın bildirmediği kanal istenirse toplu kayıt yapılmaz", "3. kanal yok" in m and not uygulama.ayar_yolu("nvr2-k1").exists())
m = [hata(lambda pr=pr: uygulama.kameralari_olustur(uygulama.kanal_ayarlari({**taban, "kod": "nvr3"}, [1, 2], pr))) for pr in (None, [])]
denetle("ONVIF'te profil listesi gönderilmezse sunucu reddeder: belirteçsiz ayar yazılmaz",
        all("listelenmeli" in x for x in m) and not list(uygulama.yollar.AYAR.glob("nvr3-*")))
marka = {"kod": "dvr", "ad": "DVR", "kamera": {"tur": "rtsp", "marka": "hikvision", "ip": "192.0.2.20", "port": 554, "kullanici": "admin", "akis": "alt"}}
uygulama.kameralari_olustur(uygulama.kanal_ayarlari(marka, [1, 2, 3], None))
denetle("markaya göre RTSP kayıt cihazında kanallar profil listesi olmadan eklenir (kanal adresin içinde)",
        [uygulama.ayar_oku(f"dvr-k{n}")["kamera"].get("kanal") for n in (1, 2, 3)] == [1, 2, 3] and "profil" not in uygulama.ayar_oku("dvr-k1")["kamera"])

print("Kamera ayarı (kamera.kaynak)")
ayar = {"kod": "nvr1-k2", "kamera": {"tur": "onvif", "ip": "127.0.0.1", "port": PORT, "kullanici": KULLANICI, "kanal": 2, "akis": "alt",
                                    "profil": "Profile_202", "kaynak": "VideoSource_2"}}
url, goster = kamera.kaynak(ayar, SIFRE)
denetle("kanal 2 alt akışın adresi kullanıcı adı ve şifreyle kurulur", url == f"rtsp://{KULLANICI}:deneme-%C5%9Fifresi%201%2F2@127.0.0.1:8554/Streaming/Channels/202")
denetle("ekranda gösterilen adreste şifre gizli", "****" in goster and "deneme" not in goster)
denetle("ONVIF kamerada şifre kutusu istenir", kamera.sifre_gerekli(ayar))
ayar["kamera"].update(profil="Profile_101", kaynak="VideoSource_1")
denetle("kayıtlı profil kullanılır", kamera.kaynak(ayar, SIFRE)[0].endswith("/Streaming/Channels/101"))
denetle("yanlış şifreyle bağlantı hatası ONVIF iletisiyle biter", hata(lambda: kamera.kaynak(ayar, "yanlış")).startswith("ONVIF: "))

print("Ağda keşif (WS-Discovery)")
dur, hazir = threading.Event(), threading.Event()
threading.Thread(target=kesif_yanitlayici, args=(PORT, dur, hazir), daemon=True).start()
hazir.wait(3)
bulunan = onvif.kesfet(2.0, arayuzler=onvif._yerel_adresler() + ["127.0.0.1"])
dur.set()
biz = [x for x in bulunan if x["port"] == PORT]
if biz:
    denetle("sahte cihaz keşifte bulundu; adı ve modeli okundu", biz[0]["ad"] == "Sahte NVR" and biz[0]["model"] == "NVR-2K")
    denetle("aynı yanıttaki bozuk adresli kayıt atlandı, arama kesilmedi", not [x for x in bulunan if x["ad"] == "Bozuk"])
else:
    print("  atlandı  bu bilgisayarda çoklu yayın (multicast) yanıtı alınamadı: keşif sınanamadı", flush=True)
if [x for x in bulunan if x["port"] != PORT]:
    print(f"  not: ağda {len([x for x in bulunan if x['port'] != PORT])} gerçek ONVIF cihazı da yanıt verdi (ayrıntı yazılmadı)", flush=True)

sunucu.shutdown()
kalan = [ad for ad, ok in sonuc if not ok]
print(f"\n{len(sonuc) - len(kalan)}/{len(sonuc)} denetim geçti" + (f" · kalanlar: {kalan}" if kalan else ""))
sys.exit(1 if kalan else 0)
