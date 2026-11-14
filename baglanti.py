"""Dış bağlantılar: yeni olayları kullanıcının tanımladığı sistemlere iletir.

genel.json içinde "baglantilar" listesi; her bağlantının türü ve süzgeçleri vardır:

  {"ad": "...", "tur": "...", "acik": true, "en_az_puan": 9, "yalniz_ciddi": false,
   "kameralar": ["depo1"], "kategoriler": ["alev"], "kurallar": ["alev_duman"], ...türe özel alanlar}
  (yalniz_ciddi: yalnızca düzeyi kritik olan olaylar)

Türler ve alanları:
  webhook   adres, basliklar? ({"Ad": "değer"})                olayın tamamı JSON olarak POST edilir
  slack     adres (gelen webhook)                                kısa metin
  teams     adres (gelen webhook)                                kısa metin
  mqtt      sunucu, port (1883), konu, qos (0|1), kalici?,       olayın tamamı JSON olarak yayımlanır
            kullanici?, sifre_degiskeni?
  modbus    sunucu, port (502), birim (1), hedef ("bobin"|"yazmac"), adres, deger (1), darbe_sn (0 = açık bırak)
            Modbus TCP ile PLC'ye yazar: bobin (işlev 5) ya da tutma yazmacı (işlev 6)
  opcua     adres (opc.tcp://...), dugum ("ns=2;s=Alarm"), deger (true), darbe_sn, kullanici?, sifre_degiskeni?
  eposta    sunucu, port (587), tls (true), gonderen, alicilar [..], kullanici?, sifre_degiskeni?

Şifreler ayar dosyasına YAZILMAZ: "sifre_degiskeni" alanında adı verilen ortam değişkeninden okunur.
Görüntü gönderilmez; yalnızca olayın metin bilgileri gider. Veri yalnızca kullanıcının yazdığı adreslere gider.

ÖNEMLİ: çıkışlar, panel olayı AugeLab Studio'dan aldığında tetiklenir (kuralın süresi + bir-iki saniye). Bu çıkışlar ikaz
lambası, siren, kayıt ve bildirim içindir; onaylı yangın algılama sisteminin ya da emniyet durdurmasının yerine KULLANILAMAZ.
"""
from __future__ import annotations

import json
import os
import socket
import struct
import threading
import urllib.request

import depo

TURLER = {
    "webhook": "Webhook (JSON)", "slack": "Slack", "teams": "Microsoft Teams", "mqtt": "MQTT", "modbus": "Modbus TCP (PLC)",
    "opcua": "OPC UA (PLC / SCADA)", "eposta": "E-posta (SMTP)",
}
ALANLAR = ("id", "zaman", "kamera", "kamera_ad", "kural", "kural_ad", "kategori", "duzey", "bolge", "onem", "olasilik", "puan", "ciddi",
           "sure_sn", "aciklama", "klip", "kare")
ORNEK_OLAY = {"id": 0, "zaman": "2026-01-01T12:00:00", "kamera": "deneme", "kamera_ad": "Deneme kamerası", "kural": "alev",
              "kural_ad": "Alev algılandı", "kategori": "alev", "duzey": "kritik", "bolge": "Kazan dairesi", "onem": 5, "olasilik": 3, "puan": 15,
              "ciddi": 1, "sure_sn": 4.0, "aciklama": "Bu bir deneme iletisidir.", "klip": None, "kare": None}


def _sifre(b: dict) -> str | None:
    ad = b.get("sifre_degiskeni")
    return os.environ.get(ad) if ad else None


def metin(o: dict) -> str:
    yer = f"{o['kamera_ad']}" + (f" · {o['bolge']}" if o.get("bolge") else "")
    return (f"{'KRİTİK · ' if o['ciddi'] else ''}{o['kural_ad']} — {yer}\n"
            f"{o['zaman'].replace('T', ' ')} · risk puanı {o['puan']}/25 · {o['sure_sn']:g} sn\n{o.get('aciklama') or ''}")


def yuk(o: dict) -> dict:
    return {"olay": {a: o.get(a) for a in ALANLAR}}


# ---------------------------------------------------------------- HTTP


def _http(adres: str, govde: dict, basliklar: dict | None = None) -> None:
    if not str(adres).startswith(("http://", "https://")):
        raise ValueError("adres http:// ya da https:// ile başlamalı")
    istek = urllib.request.Request(adres, data=json.dumps(govde, ensure_ascii=False).encode("utf-8"), method="POST",
                                   headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "YanginKamera", **(basliklar or {})})
    with urllib.request.urlopen(istek, timeout=8) as r:
        r.read()


# ---------------------------------------------------------------- MQTT 3.1.1 (yalnızca yayımlama)


def _mqtt_dizi(s: bytes) -> bytes:
    return struct.pack("!H", len(s)) + s


def _mqtt_uzunluk(n: int) -> bytes:
    out = bytearray()
    while True:
        b, n = n % 128, n // 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _oku(s: socket.socket, n: int) -> bytes:
    veri = b""
    while len(veri) < n:
        parca = s.recv(n - len(veri))
        if not parca:
            raise ConnectionError("bağlantı kapandı")
        veri += parca
    return veri


def mqtt_yayimla(sunucu: str, port: int, konu: str, ileti: bytes, qos: int = 0, kalici: bool = False,
                 kullanici: str | None = None, sifre: str | None = None, istemci: str = "yangin-kamera") -> None:
    bayrak = 0x02  # temiz oturum
    yuk_ = _mqtt_dizi(istemci.encode())
    if kullanici:
        bayrak |= 0x80
        yuk_ += _mqtt_dizi(kullanici.encode())
        if sifre is not None:
            bayrak |= 0x40
            yuk_ += _mqtt_dizi(sifre.encode())
    degisken = _mqtt_dizi(b"MQTT") + bytes([0x04, bayrak]) + struct.pack("!H", 30)
    with socket.create_connection((sunucu, int(port)), timeout=8) as s:
        s.settimeout(8)
        s.sendall(bytes([0x10]) + _mqtt_uzunluk(len(degisken) + len(yuk_)) + degisken + yuk_)
        yanit = _oku(s, 4)
        if yanit[0] != 0x20 or yanit[3] != 0:
            raise ConnectionError(f"MQTT sunucusu bağlantıyı reddetti (kod {yanit[3]})")
        qos = 1 if int(qos) == 1 else 0
        govde = _mqtt_dizi(konu.encode()) + (struct.pack("!H", 1) if qos else b"") + ileti
        s.sendall(bytes([0x30 | (qos << 1) | (1 if kalici else 0)]) + _mqtt_uzunluk(len(govde)) + govde)
        if qos:
            onay = _oku(s, 4)
            if onay[0] != 0x40:
                raise ConnectionError("MQTT sunucusu iletiyi onaylamadı")
        s.sendall(bytes([0xE0, 0x00]))


# ---------------------------------------------------------------- Modbus TCP


def modbus_yaz(sunucu: str, port: int, birim: int, hedef: str, adres: int, deger: int) -> None:
    """Tek bobin (işlev 5) ya da tek tutma yazmacı (işlev 6) yazar. `adres` sıfırdan başlar (40001 → 0)."""
    if hedef == "bobin":
        islev, veri = 5, 0xFF00 if deger else 0x0000
    else:
        islev, veri = 6, int(deger) & 0xFFFF
    pdu = struct.pack("!BHH", islev, int(adres) & 0xFFFF, veri)
    cerceve = struct.pack("!HHHB", 1, 0, len(pdu) + 1, int(birim) & 0xFF) + pdu
    with socket.create_connection((sunucu, int(port)), timeout=5) as s:
        s.settimeout(5)
        s.sendall(cerceve)
        bas = _oku(s, 7)
        uzunluk = struct.unpack("!H", bas[4:6])[0]
        yanit = _oku(s, uzunluk - 1)
        if yanit[0] & 0x80:
            kod = yanit[1] if len(yanit) > 1 else 0
            raise ConnectionError(f"PLC yazmayı reddetti (Modbus hata kodu {kod}: "
                                  f"{ {1: 'işlev desteklenmiyor', 2: 'adres geçersiz', 3: 'değer geçersiz', 4: 'cihaz hatası'}.get(kod, 'bilinmeyen') })")
        if yanit[0] != islev:
            raise ConnectionError("PLC'den beklenmeyen yanıt")


# ---------------------------------------------------------------- OPC UA


def opcua_yaz(adres: str, dugum: str, deger, kullanici: str | None = None, sifre: str | None = None) -> None:
    try:
        from asyncua import ua
        from asyncua.sync import Client
    except ImportError as e:
        raise RuntimeError("OPC UA için asyncua paketi kurulu değil") from e
    istemci = Client(adres, timeout=6)
    if kullanici:
        istemci.set_user(kullanici)
        if sifre is not None:
            istemci.set_password(sifre)
    istemci.connect()
    try:
        d = istemci.get_node(dugum)
        tur = d.read_data_type_as_variant_type()
        if tur == ua.VariantType.Boolean:
            deger = bool(deger) if not isinstance(deger, str) else deger.lower() in ("1", "true", "evet", "açık", "acik")
        elif tur in (ua.VariantType.Float, ua.VariantType.Double):
            deger = float(deger)
        elif tur != ua.VariantType.String:
            deger = int(deger)
        else:
            deger = str(deger)
        d.write_value(ua.DataValue(ua.Variant(deger, tur)))
    finally:
        istemci.disconnect()


# ---------------------------------------------------------------- e-posta


def eposta_gonder(b: dict, konu: str, govde: str) -> None:
    import smtplib
    from email.message import EmailMessage

    alicilar = [a for a in b.get("alicilar") or [] if a]
    if not alicilar:
        raise ValueError("alıcı yazılmamış")
    ileti = EmailMessage()
    ileti["Subject"], ileti["From"], ileti["To"] = konu, b.get("gonderen") or b.get("kullanici") or "yangin-kamera@localhost", ", ".join(alicilar)
    ileti.set_content(govde)
    with smtplib.SMTP(b["sunucu"], int(b.get("port") or 587), timeout=10) as s:
        if b.get("tls", True):
            s.starttls()
        if b.get("kullanici"):
            sifre = _sifre(b)
            if sifre is None:
                raise ValueError(f"e-posta şifresi bulunamadı: {b.get('sifre_degiskeni') or 'sifre_degiskeni yazılmamış'} ortam değişkenini ayarlayın")
            s.login(b["kullanici"], sifre)
        s.send_message(ileti)


# ---------------------------------------------------------------- gönderim


def _darbe(b: dict, kapat) -> None:
    """Çıkış `darbe_sn` saniye sonra kapatılır (0 ise açık kalır; PLC tarafında sıfırlanır)."""
    try:
        sn = float(b.get("darbe_sn") or 0)
    except (TypeError, ValueError):
        sn = 0
    if sn > 0:
        z = threading.Timer(sn, lambda: _sessiz(kapat))
        z.daemon = True
        z.start()


def _sessiz(fn) -> None:
    try:
        fn()
    except Exception:
        pass


def ilet(b: dict, o: dict) -> None:
    """Bir olayı bir bağlantıya iletir; başarısızsa hata fırlatır."""
    tur = b.get("tur", "webhook")
    if tur in ("slack", "teams"):
        _http(b.get("adres", ""), {"text": metin(o)})
    elif tur == "webhook":
        _http(b.get("adres", ""), yuk(o), b.get("basliklar") if isinstance(b.get("basliklar"), dict) else None)
    elif tur == "mqtt":
        mqtt_yayimla(b["sunucu"], b.get("port") or 1883, b.get("konu") or "yangin/olay", json.dumps(yuk(o), ensure_ascii=False).encode("utf-8"),
                     b.get("qos") or 0, bool(b.get("kalici")), b.get("kullanici") or None, _sifre(b))
    elif tur == "modbus":
        hedef = b.get("hedef", "bobin")
        arg = (b["sunucu"], b.get("port") or 502, b.get("birim") or 1, hedef, b.get("adres") or 0)
        modbus_yaz(*arg, b.get("deger") if b.get("deger") is not None else 1)
        _darbe(b, lambda: modbus_yaz(*arg, 0))
    elif tur == "opcua":
        deger = b.get("deger") if b.get("deger") is not None else True
        arg = (b.get("adres", ""), b.get("dugum", ""))
        opcua_yaz(*arg, deger, b.get("kullanici") or None, _sifre(b))
        _darbe(b, lambda: opcua_yaz(*arg, False if isinstance(deger, bool) or str(deger).lower() in ("true", "false") else 0, b.get("kullanici") or None, _sifre(b)))
    elif tur == "eposta":
        eposta_gonder(b, f"[Yangın Kamera] {o['kural_ad']} · {o['kamera_ad']}", metin(o))
    else:
        raise ValueError(f"bilinmeyen bağlantı türü: {tur}")


def uygun(b: dict, o: dict) -> bool:
    if not b.get("acik", True):
        return False
    if o["puan"] < int(b.get("en_az_puan") or 0) or (b.get("yalniz_ciddi") and not o["ciddi"]):
        return False
    for alan, olay_alani in (("kameralar", "kamera"), ("kategoriler", "kategori"), ("kurallar", "kural")):
        if b.get(alan) and o[olay_alani] not in b[alan]:
            return False
    return True


def _hata_metni(e: Exception) -> str:
    if isinstance(e, (TimeoutError, socket.timeout)) or "timed out" in str(e):
        return "karşı taraf yanıt vermedi (zaman aşımı); adres, port ve ağ bağlantısını kontrol edin"
    if isinstance(e, ConnectionRefusedError):
        return "bağlantı reddedildi; adres ve port doğru mu, karşıdaki hizmet açık mı"
    if isinstance(e, socket.gaierror):
        return "sunucu adı çözülemedi; adresi kontrol edin"
    return (str(e) or e.__class__.__name__)[:160]


def gonder(olay_kimlikleri: list[int]) -> list[str]:
    """Yeni olayları açık bağlantılara iletir. Dönüş: ekrana yazılacak kısa notlar (hata dahil)."""
    # Bütün çıkışları panel gönderir (Studio arayüzsüz, hazır sahneyle çalışır; sahnede çıkış bloğu yoktur)
    hedefler = [b for b in depo.genel().get("baglantilar") or [] if b.get("acik", True)]
    if not hedefler or not olay_kimlikleri:
        return []
    olaylar = depo.sor(f"SELECT * FROM olay WHERE id IN ({', '.join('?' * len(olay_kimlikleri))}) ORDER BY id", *olay_kimlikleri)
    notlar = []
    for b in hedefler:
        n, hatalar = 0, []
        secilen = [o for o in olaylar if uygun(b, o)]
        if b.get("tur") in ("modbus", "opcua") and secilen:
            secilen = [max(secilen, key=lambda o: o["puan"])]  # aynı anda başlayan olaylarda PLC çıkışı bir kez tetiklenir
        for o in secilen:
            try:
                ilet(b, o)
                n += 1
            except Exception as e:
                hatalar.append(_hata_metni(e))
        if n or hatalar:
            ad = b.get("ad") or TURLER.get(b.get("tur"), "bağlantı")
            notlar.append(f"Bağlantı \"{ad}\": {n} olay iletildi" + (f"; {len(hatalar)} iletilemedi ({hatalar[0]})" if hatalar else "") + ".")
    return notlar


def dene(b: dict) -> tuple[bool, str]:
    """Bağlantıya bir deneme iletisi yollar. Dönüş: (başarılı mı, kısa açıklama)."""
    try:
        ilet(b, dict(ORNEK_OLAY, zaman=depo.simdi()))
        return True, "Deneme iletisi gönderildi."
    except Exception as e:
        return False, _hata_metni(e)


def temizle(b: dict) -> dict:
    """Arayüzden gelen bağlantıyı doğrular ve yalnızca bilinen alanları saklar (şifre alanı saklanmaz)."""
    tur = b.get("tur") if b.get("tur") in TURLER else "webhook"
    def sayi(alan, varsayilan, en_az, en_cok):
        try:
            return max(en_az, min(en_cok, int(float(b.get(alan, varsayilan)))))
        except (TypeError, ValueError):
            return varsayilan
    def yazi(alan, uzunluk=300):
        return str(b.get(alan) or "").strip()[:uzunluk]
    def liste(alan):
        return [str(x)[:60] for x in (b.get(alan) or []) if x][:40] if isinstance(b.get(alan), list) else []
    out = {"ad": yazi("ad", 60) or TURLER[tur], "tur": tur, "acik": bool(b.get("acik", True)), "en_az_puan": sayi("en_az_puan", 0, 0, 25),
           "yalniz_ciddi": bool(b.get("yalniz_ciddi")), "kameralar": liste("kameralar"), "kategoriler": liste("kategoriler"), "kurallar": liste("kurallar")}
    if tur in ("webhook", "slack", "teams"):
        out["adres"] = yazi("adres", 500)
        if not out["adres"].startswith(("http://", "https://")):
            raise SystemExit("Bağlantı adresi http:// ya da https:// ile başlamalı.")
        if tur == "webhook" and isinstance(b.get("basliklar"), dict):
            out["basliklar"] = {str(k)[:60]: str(v)[:300] for k, v in list(b["basliklar"].items())[:8]}
    elif tur == "mqtt":
        out.update(sunucu=yazi("sunucu", 200), port=sayi("port", 1883, 1, 65535), konu=yazi("konu", 200) or "yangin/olay", qos=sayi("qos", 0, 0, 1),
                   kalici=bool(b.get("kalici")), kullanici=yazi("kullanici", 80), sifre_degiskeni=yazi("sifre_degiskeni", 60))
    elif tur == "modbus":
        out.update(sunucu=yazi("sunucu", 200), port=sayi("port", 502, 1, 65535), birim=sayi("birim", 1, 0, 255),
                   hedef="yazmac" if b.get("hedef") == "yazmac" else "bobin", adres=sayi("adres", 0, 0, 65535), deger=sayi("deger", 1, 0, 65535),
                   darbe_sn=sayi("darbe_sn", 5, 0, 3600))
    elif tur == "opcua":
        out.update(adres=yazi("adres", 300), dugum=yazi("dugum", 200), deger=b.get("deger") if isinstance(b.get("deger"), (bool, int, float)) else (yazi("deger", 60) or True),
                   darbe_sn=sayi("darbe_sn", 5, 0, 3600), kullanici=yazi("kullanici", 80), sifre_degiskeni=yazi("sifre_degiskeni", 60))
        if not out["adres"].startswith("opc.tcp://") or not out["dugum"]:
            raise SystemExit("OPC UA adresi opc.tcp:// ile başlamalı ve düğüm yazılmalı (ör. ns=2;s=Alarm).")
    elif tur == "eposta":
        out.update(sunucu=yazi("sunucu", 200), port=sayi("port", 587, 1, 65535), tls=bool(b.get("tls", True)), gonderen=yazi("gonderen", 120),
                   alicilar=[str(a).strip()[:120] for a in (b.get("alicilar") or []) if str(a).strip()][:20] if isinstance(b.get("alicilar"), list) else [],
                   kullanici=yazi("kullanici", 120), sifre_degiskeni=yazi("sifre_degiskeni", 60))
    if tur in ("mqtt", "modbus", "eposta") and not out.get("sunucu"):
        raise SystemExit("Sunucu adresi yazılmamış.")
    return out
