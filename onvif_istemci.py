"""ONVIF istemcisi (yalnızca standart kitaplık): ağda cihaz keşfi, kanal ve profil listesi, görüntü akışının adresi.

ONVIF, IP kameraların ve kayıt cihazlarının (NVR/DVR) ortak yönetim arayüzüdür. Burada yalnızca okuma yapılır:

  kesfet()                 ağdaki ONVIF cihazlarını bulur (WS-Discovery; şifre gerekmez)
  Cihaz(ip, port, k, s)    .bilgi()  .profiller()  .sec(profil, kanal, akis)  .akis_adresi(belirtec)

Kayıt cihazında her kanal ayrı bir görüntü kaynağıdır; profiller kaynağa göre kanallara ayrılır (1'den başlar).
Şifre hiçbir yere yazılmaz; her istekte WS-Security "UsernameToken" (özet) olarak gönderilir, cihaz isterse HTTP Digest de denenir.

Güvenlik: cihazın bildirdiği servis ve akış adreslerindeki sunucu adı kullanılmaz; istekler ve akış her zaman kullanıcının
yazdığı IP adresine gider (yalnızca yol ve port alınır). Böylece kullanıcı adı ve şifre başka bir adrese gönderilemez.
Yönlendirmeler izlenmez.

Komut satırı:
  python onvif_istemci.py kesfet
  python onvif_istemci.py profiller <ip> [port] [kullanıcı]      (şifre sorulur, ekranda görünmez)
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import http.client
import os
import re
import select
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

KESIF_ADRESI = ("239.255.255.250", 3702)
SIK_PORTLAR = "80, 8000, 8080 ya da 8899"
EN_COK_YANIT = 2 * 1024 * 1024  # cihazdan okunacak en büyük yanıt (bayt): kanal listesi bunun çok altındadır
SURE_DOLDU = "Cihaz yanıtını süresinde tamamlamadı."

_ZARF = ('<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
         'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" '
         'xmlns:tt="http://www.onvif.org/ver10/schema"><s:Header>{baslik}</s:Header><s:Body>{govde}</s:Body></s:Envelope>')
_GUVENLIK = ('<wsse:Security s:mustUnderstand="1" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" '
             'xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"><wsse:UsernameToken>'
             '<wsse:Username>{k}</wsse:Username>'
             '<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{ozet}</wsse:Password>'
             '<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce}</wsse:Nonce>'
             '<wsu:Created>{zaman}</wsu:Created></wsse:UsernameToken></wsse:Security>')
_KESIF = ('<?xml version="1.0" encoding="UTF-8"?><e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
          'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
          'xmlns:dn="http://www.onvif.org/ver10/network/wsdl"><e:Header><w:MessageID>uuid:{kimlik}</w:MessageID>'
          '<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
          '<w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action></e:Header>'
          '<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body></e:Envelope>')


class OnvifHatasi(Exception):
    """Kullanıcıya gösterilecek ileti taşır."""


class _YonlendirmeYok(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # kullanıcı adı ve şifre başka bir adrese taşınmasın
        return None


def _ayristir(veri: bytes) -> ET.Element:
    """Cihazdan gelen XML'i ayrıştırır. Belge türü ve varlık tanımı içeren yanıt reddedilir (iç içe varlıklarla bellek şişirme)."""
    if b"<!DOCTYPE" in veri or b"<!ENTITY" in veri:
        raise ET.ParseError("belge türü tanımı kabul edilmez")
    return ET.fromstring(veri)


def _soket(akim):
    """Yanıtın altındaki soket (başarılı yanıtta akim.fp.raw._sock, HTTP hatasında bir kat içeride); bulunamazsa None."""
    for e in (akim, getattr(akim, "fp", None)):
        s = getattr(getattr(getattr(e, "fp", None), "raw", None), "_sock", None)
        if s is not None:
            return s
    return None


def _oku(akim, son: float) -> bytes:
    """Yanıt gövdesini okur; EN_COK_YANIT baytı ya da `son` anını (time.monotonic) aşarsa OnvifHatasi.

    Her okuma tek bir soket okumasıdır (read1) ve soketin süre sınırı o anda kalan süreye indirilir: yavaş yavaş gövde
    gönderen bir cihaz, okumayı toplam sürenin ötesine taşıyamaz."""
    parcalar, toplam = [], 0
    soket = _soket(akim)
    oku = getattr(akim, "read1", None) or akim.read
    while True:
        kalan = son - time.monotonic()
        if kalan <= 0:
            raise OnvifHatasi(SURE_DOLDU)
        if soket is not None:
            try:
                soket.settimeout(kalan)
            except OSError:
                pass
        try:
            parca = oku(65536)
        except TimeoutError:
            raise OnvifHatasi(SURE_DOLDU) from None
        if not parca:
            return b"".join(parcalar)
        toplam += len(parca)
        if toplam > EN_COK_YANIT:
            raise OnvifHatasi("Cihazın yanıtı beklenenden çok büyük; okunmadı.")
        parcalar.append(parca)


def _dogal(metin: str) -> list:
    """Doğal sıralama anahtarı: "VideoSource_10", "VideoSource_2"den sonra gelir."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", metin)]


def _temiz(metin: str) -> str:
    """Cihazın yazdığı hata metni güvenilir değildir: yalnızca harf, rakam ve yalın noktalama, en çok 120 karakter gösterilir."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w .,:;()/\-]", " ", metin or "")).strip()[:120]


def _soketi_kapat(s) -> None:
    try:
        s.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        s.close()
    except OSError:
        pass


class _Isleyici(urllib.request.HTTPHandler):
    """İsteğin açtığı her bağlantının soketini `soketler` listesine yazar: süre dolunca çağıran bu soketleri kapatarak
    isteği iptal eder. `iptal` işaretlendikten sonra yeni bağlantı açılmaz."""

    def __init__(self, soketler: list, iptal: threading.Event):
        super().__init__()
        self._soketler, self._iptal = soketler, iptal

    def http_open(self, req):
        soketler, iptal = self._soketler, self._iptal

        class Baglanti(http.client.HTTPConnection):
            def connect(self):
                if iptal.is_set():
                    raise OSError("istek iptal edildi")
                super().connect()
                soketler.append(self.sock)
                if iptal.is_set():  # bağlanırken süre doldu
                    _soketi_kapat(self.sock)
                    raise OSError("istek iptal edildi")

        return self.do_open(Baglanti, req)


class _Digest(urllib.request.HTTPDigestAuthHandler):
    def http_error_401(self, req, fp, code, msg, headers):
        fp.close()  # kimlik isteyen ilk yanıtın bağlantısı, kimlikli tekrar gönderilmeden kapatılır
        return super().http_error_401(req, fp, code, msg, headers)


def _ad(e: ET.Element) -> str:
    return e.tag.rsplit("}", 1)[-1]


def _bul(kok: ET.Element, *adlar: str) -> ET.Element | None:
    """Ad alanına bakmadan, verilen ad zincirini izleyen ilk öğe (her adım alt ağaçta aranır)."""
    e = kok
    for ad in adlar:
        e = next((x for x in e.iter() if x is not e and _ad(x) == ad), None)
        if e is None:
            return None
    return e


def _metin(kok: ET.Element, *adlar: str) -> str:
    e = _bul(kok, *adlar)
    return (e.text or "").strip() if e is not None else ""


def _yerel_adresler() -> list[str]:
    adresler = []
    try:
        for bilgi in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = bilgi[4][0]
            if ip not in adresler:
                adresler.append(ip)
    except OSError:
        pass
    return adresler or [""]


def kesfet(sure: float = 3.0, arayuzler: list[str] | None = None) -> list[dict]:
    """Ağdaki ONVIF cihazları: [{"ip", "port", "ad", "model", "adres"}]. Yalnızca bu bilgisayarın bağlı olduğu ağ(lar)da arar;
    yönlendiricinin ardındaki cihazlar bulunmaz (IP adresi elle yazılır)."""
    istek = _KESIF.format(kimlik=uuid.uuid4()).encode("utf-8")
    soketler = []
    for ip in arayuzler if arayuzler is not None else _yerel_adresler():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            if ip:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
            s.bind((ip, 0))
            s.sendto(istek, KESIF_ADRESI)
            soketler.append(s)
        except OSError:
            continue
    bulunan: dict[tuple[str, int], dict] = {}
    son = dt.datetime.now() + dt.timedelta(seconds=sure)
    try:
        while soketler:
            kalan = (son - dt.datetime.now()).total_seconds()
            if kalan <= 0:
                break
            hazir, _, _ = select.select(soketler, [], [], min(kalan, 0.5))
            for s in hazir:
                try:
                    veri, (gonderen, _) = s.recvfrom(65535)
                    kok = _ayristir(veri)
                except (OSError, ET.ParseError):
                    continue
                for eslesme in (x for x in kok.iter() if _ad(x) == "ProbeMatch"):
                    try:  # bozuk bir yanıt (geçersiz adres ya da port) yalnızca atlanır, arama sürer
                        adres = next((a for a in _metin(eslesme, "XAddrs").split()
                                      if urlsplit(a).scheme == "http" and re.fullmatch(r"[\d.]+", urlsplit(a).hostname or "") and (urlsplit(a).port or 80)), None)
                        if adres is None:
                            continue
                        kapsamlar = _metin(eslesme, "Scopes").split()
                        al = lambda on: _temiz(next((urllib.request.unquote(k.rsplit("/", 1)[-1]) for k in kapsamlar if f"/{on}/" in k), ""))[:60]  # noqa: E731
                        port = urlsplit(adres).port or 80
                        bulunan.setdefault((gonderen, port), {"ip": gonderen, "port": port, "ad": al("name"), "model": al("hardware"), "adres": adres})
                    except ValueError:
                        continue
    finally:
        for s in soketler:
            s.close()
    return sorted(bulunan.values(), key=lambda c: tuple(int(p) for p in c["ip"].split(".")))


class Cihaz:
    """Bir ONVIF cihazı (kamera ya da kayıt cihazı). Bütün istekler `ip` adresine gider."""

    def __init__(self, ip: str, port: int = 80, kullanici: str = "admin", sifre: str = "", zaman_asimi: float = 6.0):
        if not re.fullmatch(r"[A-Za-z0-9.\-]+", ip or ""):
            raise OnvifHatasi("Cihazın IP adresi yazılmamış ya da geçersiz.")
        self.ip, self.port, self.kullanici, self.sifre, self.zaman_asimi = ip, int(port or 80), kullanici or "", sifre or "", zaman_asimi
        self._fark: float | None = None  # cihaz saati - bu bilgisayarın saati (sn): özet, cihazın saatine göre hazırlanır
        self._medya: str | None = None

    # --- adresler
    def _sabitle(self, adres: str, varsayilan_yol: str) -> str:
        """Cihazın bildirdiği adresten yalnızca yolu (ve cihazın kendi adresiyse portu) alır; sunucu her zaman self.ip'dir."""
        p = urlsplit(adres or "")
        port = p.port if p.hostname == self.ip and p.port else self.port
        return f"http://{self.ip}:{port}{p.path or varsayilan_yol}"

    @property
    def _aygit(self) -> str:
        return f"http://{self.ip}:{self.port}/onvif/device_service"

    # --- istek
    def _baslik(self) -> str:
        if not self.kullanici:
            return ""
        nonce = os.urandom(16)
        zaman = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=self._fark or 0.0)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        ozet = base64.b64encode(hashlib.sha1(nonce + zaman.encode("ascii") + self.sifre.encode("utf-8")).digest()).decode("ascii")
        return _GUVENLIK.format(k=escape(self.kullanici), ozet=ozet, nonce=base64.b64encode(nonce).decode("ascii"), zaman=zaman)

    def _istek(self, adres: str, govde: str, kimlikli: bool = True) -> ET.Element:
        """Tek SOAP isteği. Bağlantı, başlıklar, gövdenin okunması ve gerekirse HTTP Digest tekrarı BİRLİKTE en çok
        self.zaman_asimi saniye sürer (monotonik saatle). İstek ayrı bir iş parçacığında yürür; süre dolduğunda istek
        İPTAL edilir: açtığı bağlantıların soketleri kapatılır, yeni bağlantı açması engellenir ve iş parçacığının bittiği
        beklenir. Böylece hata döndükten sonra cihaza açık bağlantı ya da çalışan işçi kalmaz."""
        son = time.monotonic() + self.zaman_asimi
        sonuc: list = []
        soketler: list = []
        iptal = threading.Event()

        def calis():
            try:
                sonuc.append((True, self._istek_ic(adres, govde, kimlikli, son, soketler, iptal)))
            except BaseException as e:  # noqa: BLE001  (çağırana aktarılır)
                sonuc.append((False, e))

        is_parcacigi = threading.Thread(target=calis, daemon=True, name="onvif-istek")
        is_parcacigi.start()
        is_parcacigi.join(max(0.0, son - time.monotonic()))
        if is_parcacigi.is_alive():
            iptal.set()
            for s in list(soketler):
                _soketi_kapat(s)
            is_parcacigi.join(1.0)  # soketi kapanan okuma hemen hata verir
            raise OnvifHatasi(SURE_DOLDU)
        if not sonuc:
            raise OnvifHatasi(SURE_DOLDU)
        tamam, deger = sonuc[0]
        if tamam:
            return deger
        if isinstance(deger, OnvifHatasi):
            raise deger
        if isinstance(deger, UnicodeError):  # urllib'in HTTP Digest kodu şifreyi ASCII olarak işler
            raise OnvifHatasi("Cihaz HTTP Digest kimliği istiyor; bu yöntem ASCII dışı karakter içeren kullanıcı adı ya da şifreyle kullanılamıyor.") from None
        raise OnvifHatasi(f"ONVIF isteği tamamlanamadı ({type(deger).__name__}).") from None

    def _istek_ic(self, adres: str, govde: str, kimlikli: bool, son: float, soketler: list, iptal: threading.Event) -> ET.Element:
        veri = _ZARF.format(baslik=self._baslik() if kimlikli else "", govde=govde).encode("utf-8")
        istek = urllib.request.Request(adres, data=veri, headers={"Content-Type": "application/soap+xml; charset=utf-8"})
        acici = urllib.request.build_opener(urllib.request.ProxyHandler({}), _YonlendirmeYok(), _Isleyici(soketler, iptal))
        for deneme in (1, 2):
            kalan = son - time.monotonic()
            if kalan <= 0:
                raise OnvifHatasi(SURE_DOLDU)
            try:
                with acici.open(istek, timeout=kalan) as r:
                    return _ayristir(_oku(r, son))
            except urllib.error.HTTPError as e:
                try:
                    icerik = _oku(e, son)
                finally:
                    e.close()  # hata yanıtının bağlantısı her çıkışta (süre hatası dahil) kapatılır
                if e.code == 401 and deneme == 1 and kimlikli and "digest" in (e.headers.get("WWW-Authenticate") or "").lower():
                    sifreler = urllib.request.HTTPPasswordMgrWithDefaultRealm()  # cihaz HTTP Digest istiyor
                    sifreler.add_password(None, adres, self.kullanici, self.sifre)
                    acici = urllib.request.build_opener(urllib.request.ProxyHandler({}), _YonlendirmeYok(), _Isleyici(soketler, iptal), _Digest(sifreler))
                    continue
                # Cihazın yazdığı serbest hata metni yalnızca hatanın türünü anlamak için okunur; iletiye, panele ya da iş
                # kaydına taşınmaz (güvenilir değildir). Kullanıcıya yalnızca HTTP kodu ve bizim iletimiz gösterilir.
                try:
                    hata = _ayristir(icerik)
                    tur = " ".join((x.text or "") for x in hata.iter() if _ad(x) in ("Value", "Text", "faultstring"))
                except ET.ParseError:
                    tur = ""
                if e.code in (401, 403) or re.search(r"NotAuthorized|Unauthorized|FailedAuthentication|not authorized", tur, re.I):
                    raise OnvifHatasi("Cihaz kullanıcı adını ya da şifreyi kabul etmedi. Cihazda bu kullanıcı için ONVIF erişimi açık olmalı.") from None
                if 300 <= e.code < 400:
                    raise OnvifHatasi("Cihaz başka bir adrese yönlendirdi; yönlendirme izlenmez.") from None
                raise OnvifHatasi(f"Cihaz isteği reddetti (HTTP {e.code}).") from None
            except (urllib.error.URLError, OSError) as e:
                raise OnvifHatasi(f"Cihaza ulaşılamadı ({self.ip}:{self.port}): {getattr(e, 'reason', e)}. ONVIF portu çoğunlukla {SIK_PORTLAR}'dur; "
                                  "cihazda ONVIF açık olmalı.") from None
            except ET.ParseError:
                raise OnvifHatasi(f"{self.ip}:{self.port} adresindeki cihaz ONVIF yanıtı vermedi. ONVIF portunu denetleyin ({SIK_PORTLAR}).") from None
        raise OnvifHatasi("Cihaz kullanıcı adını ya da şifreyi kabul etmedi.")

    def _saat(self) -> None:
        """Cihazın saatini okur (kimlik gerekmez): özet, cihazın saatine yakın bir zaman damgasıyla kabul edilir."""
        if self._fark is not None:
            return
        self._fark = 0.0
        try:
            yanit = self._istek(self._aygit, "<tds:GetSystemDateAndTime/>", kimlikli=False)
            u = _bul(yanit, "UTCDateTime")
            if u is not None:
                sayi = lambda *yol: int(_metin(u, *yol))  # noqa: E731
                cihaz = dt.datetime(sayi("Date", "Year"), sayi("Date", "Month"), sayi("Date", "Day"), sayi("Time", "Hour"), sayi("Time", "Minute"),
                                    sayi("Time", "Second"), tzinfo=dt.timezone.utc)
                self._fark = (cihaz - dt.datetime.now(dt.timezone.utc)).total_seconds()
        except OnvifHatasi as e:
            if "ulaşılamadı" in str(e):
                raise  # cihaz yok: sonraki istekler de zaman aşımına kadar bekletmesin
        except ValueError:
            pass  # saat okunamadı: bu bilgisayarın saatiyle denenir

    def _medya_adresi(self) -> str:
        if self._medya is None:
            self._saat()
            try:
                yanit = self._istek(self._aygit, "<tds:GetCapabilities><tds:Category>Media</tds:Category></tds:GetCapabilities>")
                self._medya = self._sabitle(_metin(yanit, "Media", "XAddr"), "/onvif/Media")
            except OnvifHatasi as e:
                if "kabul etmedi" in str(e) or "ulaşılamadı" in str(e) or "ONVIF yanıtı" in str(e):
                    raise
                self._medya = f"http://{self.ip}:{self.port}/onvif/Media"  # yetenek listesi vermeyen cihaz: yaygın yol
        return self._medya

    # --- okuma
    def bilgi(self) -> dict:
        """{"uretici", "model", "yazilim"}; okunamazsa boş sözlük."""
        self._saat()
        try:
            y = self._istek(self._aygit, "<tds:GetDeviceInformation/>")
        except OnvifHatasi:
            return {}
        return {"uretici": _temiz(_metin(y, "Manufacturer"))[:60], "model": _temiz(_metin(y, "Model"))[:60], "yazilim": _temiz(_metin(y, "FirmwareVersion"))[:60]}

    def profiller(self) -> list[dict]:
        """Görüntü profilleri: [{"belirtec", "ad", "kanal", "kaynak", "kodlama", "en", "boy"}], kanala göre sıralı.

        `kaynak` görüntü kaynağının (fiziksel kanalın) belirtecidir. `kanal` numarası, kaynak belirteçlerinin doğal sırasıdır
        (1'den): cihaz profilleri hangi sırayla bildirirse bildirsin aynı kaynak aynı numarayı alır."""
        yanit = self._istek(self._medya_adresi(), "<trt:GetProfiles/>")
        out = []
        for p in (x for x in yanit.iter() if _ad(x) == "Profiles"):
            if _bul(p, "VideoEncoderConfiguration") is None:
                continue  # ses ya da üstveri profili
            sayi = lambda *yol: int(_metin(p, *yol) or 0)  # noqa: E731
            out.append({"belirtec": p.get("token") or "", "ad": _temiz(_metin(p, "Name"))[:60], "kanal": 0,
                        "kaynak": _metin(p, "VideoSourceConfiguration", "SourceToken") or "-",
                        "kodlama": _temiz(_metin(p, "VideoEncoderConfiguration", "Encoding"))[:20],
                        "en": sayi("VideoEncoderConfiguration", "Resolution", "Width"), "boy": sayi("VideoEncoderConfiguration", "Resolution", "Height")})
        if not out:
            raise OnvifHatasi("Cihaz görüntü profili bildirmedi.")
        kaynaklar = sorted({p["kaynak"] for p in out}, key=_dogal)
        for p in out:
            p["kanal"] = kaynaklar.index(p["kaynak"]) + 1
        return sorted(out, key=lambda p: (p["kanal"], -p["en"] * p["boy"], _dogal(p["belirtec"])))

    def sec(self, profil: str | None = None, kanal: int = 1, akis: str = "alt", profiller: list[dict] | None = None, kaynak: str | None = None) -> dict:
        """Kullanılacak profil.

        Kayıtlı belirteçler kanal numarasından önce gelir ve kamerayı fiziksel kanala bağlar:
          - `profil` belirteci cihazda varsa (ve `kaynak` kayıtlıysa aynı kaynağa aitse) o profil;
          - profil belirteci kaybolduysa ama `kaynak` cihazda duruyorsa, AYNI kaynağın alt ya da ana akış profili;
          - ikisi de bulunamazsa hata: başka bir kanala düşülmez.
        Hiç belirteç kayıtlı değilse: cihaz tek kanallıysa (tek görüntü kaynağı) o kaynağın alt ya da ana akış profili.
        Çok kanallı cihazda yalnızca kanal numarasıyla kaydedilmiş kamera BELİRSİZDİR (numara, cihazın profilleri bildirme
        sırasına ya da sıralama kuralına göre başka bir fiziksel kanala denk gelebilir): bağlanılmaz, profilin yeniden
        seçilmesi istenir."""
        hepsi = profiller if profiller is not None else self.profiller()
        uc = max if akis == "ana" else min
        if profil or kaynak:
            p = next((x for x in hepsi if x["belirtec"] == profil), None) if profil else None
            if p is not None and (not kaynak or p["kaynak"] == kaynak):
                return p
            ayni_kaynak = [x for x in hepsi if x["kaynak"] == kaynak] if kaynak else []
            if ayni_kaynak:
                return uc(ayni_kaynak, key=lambda x: x["en"] * x["boy"])
            raise OnvifHatasi("Kayıtlı profil ya da görüntü kaynağı cihazda bulunamadı; başka bir kanala geçilmedi. "
                              "Kamera ayarında kanalları yeniden listeleyip profili seçin.")
        if len({x["kaynak"] for x in hepsi}) > 1:
            raise OnvifHatasi("Bu kamera çok kanallı bir cihazda yalnızca kanal numarasıyla kaydedilmiş; hangi fiziksel kanal olduğu kesin değil. "
                              "Kamera ayarında \"Kanalları ve profilleri listele\"ye basıp profili seçin ve kaydedin.")
        adaylar = [x for x in hepsi if x["kanal"] == int(kanal or 1)]
        if not adaylar:
            raise OnvifHatasi(f"Cihazda {kanal}. kanal yok ({max(x['kanal'] for x in hepsi)} kanal bildirdi).")
        return uc(adaylar, key=lambda x: x["en"] * x["boy"])

    def akis_adresi(self, belirtec: str) -> str:
        """Profilin RTSP adresi (kullanıcı adı ve şifre içermez). Sunucu adı her zaman self.ip'dir."""
        yanit = self._istek(self._medya_adresi(), "<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport>"
                            f"<tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup><trt:ProfileToken>{escape(belirtec)}</trt:ProfileToken></trt:GetStreamUri>")
        uri = _metin(yanit, "MediaUri", "Uri") or _metin(yanit, "Uri")
        p = urlsplit(uri)
        if p.scheme != "rtsp":
            raise OnvifHatasi("Cihaz bu profil için RTSP adresi vermedi.")
        return f"rtsp://{self.ip}:{p.port or 554}{p.path}{'?' + p.query if p.query else ''}"


def akis(ip: str, port: int, kullanici: str, sifre: str, profil: str | None = None, kanal: int = 1, akis: str = "alt",
         kaynak: str | None = None) -> tuple[str, dict]:
    """(RTSP adresi, seçilen profil). Adres kullanıcı adı ve şifre içermez."""
    c = Cihaz(ip, port, kullanici, sifre)
    p = c.sec(profil, kanal, akis, kaynak=kaynak)
    return c.akis_adresi(p["belirtec"]), p


if __name__ == "__main__":
    import getpass
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 2 and sys.argv[1] == "kesfet":
        for c in kesfet() or [{"ip": "cihaz bulunamadı", "port": "", "ad": "", "model": ""}]:
            print(c["ip"], c["port"], c["ad"], c["model"])
    elif len(sys.argv) >= 3 and sys.argv[1] == "profiller":
        kul = sys.argv[4] if len(sys.argv) > 4 else "admin"
        try:
            c = Cihaz(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 80, kul, getpass.getpass(f"Şifre ({kul}): "))
            print(c.bilgi())
            for p in c.profiller():
                print(f"kanal {p['kanal']}  {p['belirtec']:<18} {p['ad']:<24} {p['kodlama']} {p['en']}x{p['boy']}")
        except OnvifHatasi as e:
            raise SystemExit(str(e))
    else:
        raise SystemExit(__doc__)
