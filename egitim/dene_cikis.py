"""Çıkışların sınanması: baglanti.py, bağımsız kütüphanelerin yerel sunucularına karşı çalıştırılır.

  Modbus TCP  → pymodbus sunucusu (bobin ve tutma yazmacı; darbe sonrası sıfırlanma; geçersiz adres hatası)
  MQTT        → amqtt sunucusu + amqtt abonesi (QoS 0 ve 1)
  OPC UA      → asyncua sunucusu (Boolean ve Int32 düğüm; darbe)
  e-posta     → aiosmtpd sunucusu
  webhook     → http.server

Çalıştırma: .venv\\Scripts\\python egitim\\dene_cikis.py   (requirements-gelistirme.txt kurulu olmalı)
"""
import asyncio
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import baglanti  # noqa: E402

SONUC = []
OLAY = dict(baglanti.ORNEK_OLAY, id=7, zaman="2026-11-11T10:00:00")


def kontrol(ad, kosul, ek=""):
    SONUC.append((ad, bool(kosul)))
    print(("TAMAM  " if kosul else "HATA   ") + ad + (f"  [{ek}]" if ek else ""), flush=True)


# ---------------------------------------------------------------- Modbus
def modbus():
    from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
    from pymodbus.server import StartAsyncTcpServer

    cihaz = ModbusDeviceContext(co=ModbusSequentialDataBlock(1, [0] * 20), hr=ModbusSequentialDataBlock(1, [0] * 20),
                                di=ModbusSequentialDataBlock(1, [0] * 20), ir=ModbusSequentialDataBlock(1, [0] * 20))
    baglam = ModbusServerContext(devices={1: cihaz}, single=False)
    dongu = asyncio.new_event_loop()
    threading.Thread(target=lambda: (asyncio.set_event_loop(dongu), dongu.run_until_complete(StartAsyncTcpServer(context=baglam, address=("127.0.0.1", 5020)))), daemon=True).start()
    time.sleep(1.0)

    from pymodbus.client import ModbusTcpClient

    okuyan = ModbusTcpClient("127.0.0.1", port=5020)
    okuyan.connect()

    def bobin(a):
        return int(okuyan.read_coils(a, count=1, device_id=1).bits[0])

    def yazmac(a):
        return okuyan.read_holding_registers(a, count=1, device_id=1).registers[0]

    b = {"tur": "modbus", "sunucu": "127.0.0.1", "port": 5020, "birim": 1, "hedef": "bobin", "adres": 3, "deger": 1, "darbe_sn": 1}
    baglanti.ilet(b, OLAY)
    time.sleep(0.2)
    kontrol("Modbus: bobin 3 açıldı", bobin(3) == 1, f"bobin={bobin(3)}")
    time.sleep(1.3)
    kontrol("Modbus: bobin 3 darbe süresi sonunda kapandı", bobin(3) == 0, f"bobin={bobin(3)}")
    baglanti.ilet({**b, "hedef": "yazmac", "adres": 5, "deger": 1234, "darbe_sn": 0}, OLAY)
    time.sleep(0.2)
    kontrol("Modbus: tutma yazmacı 5 = 1234 (sıfırlanmadı)", yazmac(5) == 1234, f"yazmaç={yazmac(5)}")
    kontrol("Modbus: komşu adresler değişmedi", bobin(2) == 0 and bobin(4) == 0 and yazmac(4) == 0 and yazmac(6) == 0)
    tamam, mesaj = baglanti.dene({**b, "adres": 500, "darbe_sn": 0})
    kontrol("Modbus: geçersiz adreste anlaşılır hata", not tamam and "adres" in mesaj, mesaj)
    tamam, mesaj = baglanti.dene({**b, "port": 5999})
    kontrol("Modbus: ulaşılamayan PLC'de hata", not tamam, mesaj)


# ---------------------------------------------------------------- MQTT
def mqtt():
    from amqtt.broker import Broker
    from amqtt.client import MQTTClient

    gelen = []
    hazir = threading.Event()

    async def calis():
        sunucu = Broker({"listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:18830"}}, "sys_interval": 0,
                         "auth": {"allow-anonymous": True}, "topic-check": {"enabled": False}})
        await sunucu.start()
        abone = MQTTClient()
        await abone.connect("mqtt://127.0.0.1:18830/")
        await abone.subscribe([("yangin/#", 1)])
        hazir.set()
        try:
            while True:
                m = await abone.deliver_message(timeout_duration=8)
                gelen.append((m.topic, bytes(m.data)))
        except Exception:
            pass

    threading.Thread(target=lambda: asyncio.run(calis()), daemon=True).start()
    hazir.wait(10)
    time.sleep(0.3)
    b = {"tur": "mqtt", "sunucu": "127.0.0.1", "port": 18830, "konu": "yangin/olay", "qos": 0}
    baglanti.ilet(b, OLAY)
    baglanti.ilet({**b, "konu": "yangin/tesis/depo", "qos": 1}, OLAY)
    time.sleep(1.5)
    konular = [k for k, _ in gelen]
    kontrol("MQTT: QoS 0 ileti aboneye ulaştı", "yangin/olay" in konular, str(konular))
    kontrol("MQTT: QoS 1 ileti aboneye ulaştı (sunucu onayladı)", "yangin/tesis/depo" in konular)
    if gelen:
        veri = json.loads(gelen[0][1].decode("utf-8"))
        kontrol("MQTT: ileti olayın JSON'u (Türkçe karakterler bozulmadı)", veri["olay"]["kural_ad"] == OLAY["kural_ad"] and veri["olay"]["puan"] == 15, veri["olay"]["kural_ad"])


# ---------------------------------------------------------------- OPC UA
def opcua():
    from asyncua import ua
    from asyncua.sync import Client, Server

    sunucu = Server()
    sunucu.set_endpoint("opc.tcp://127.0.0.1:48400/yangin/")
    ns = sunucu.register_namespace("yangin-deneme")
    nesne = sunucu.nodes.objects.add_object(ns, "Hat")
    alarm = nesne.add_variable(ua.NodeId("YanginAlarm", ns), "YanginAlarm", False)
    seviye = nesne.add_variable(ua.NodeId("YanginRisk", ns), "YanginRisk", ua.Variant(0, ua.VariantType.Int32))
    alarm.set_writable()
    seviye.set_writable()
    sunucu.start()
    try:
        b = {"tur": "opcua", "adres": "opc.tcp://127.0.0.1:48400/yangin/", "dugum": f"ns={ns};s=YanginAlarm", "deger": "true", "darbe_sn": 1}
        baglanti.ilet(b, OLAY)
        okuyan = Client("opc.tcp://127.0.0.1:48400/yangin/")
        okuyan.connect()
        try:
            kontrol("OPC UA: Boolean düğüm true oldu", okuyan.get_node(b["dugum"]).read_value() is True)
            time.sleep(2.5)
            kontrol("OPC UA: darbe süresi sonunda false oldu", okuyan.get_node(b["dugum"]).read_value() is False)
            baglanti.ilet({**b, "dugum": f"ns={ns};s=YanginRisk", "deger": 15, "darbe_sn": 0}, OLAY)
            kontrol("OPC UA: Int32 düğüm = 15", okuyan.get_node(f"ns={ns};s=YanginRisk").read_value() == 15)
        finally:
            okuyan.disconnect()
        tamam, mesaj = baglanti.dene({**b, "dugum": f"ns={ns};s=Yok", "darbe_sn": 0})
        kontrol("OPC UA: olmayan düğümde hata", not tamam, mesaj)
    finally:
        sunucu.stop()


# ---------------------------------------------------------------- e-posta
def eposta():
    from aiosmtpd.controller import Controller

    gelen = []

    class Tutucu:
        async def handle_DATA(self, sunucu, oturum, zarf):
            gelen.append((zarf.mail_from, zarf.rcpt_tos, zarf.content.decode("utf-8", "replace")))
            return "250 OK"

    denetci = Controller(Tutucu(), hostname="127.0.0.1", port=8025)
    denetci.start()
    try:
        baglanti.ilet({"tur": "eposta", "sunucu": "127.0.0.1", "port": 8025, "tls": False, "gonderen": "yangin@ornek.test", "alicilar": ["amir@ornek.test", "guvenlik@ornek.test"]}, OLAY)
        time.sleep(0.3)
        kontrol("E-posta: sunucu iletiyi aldı, iki alıcı", len(gelen) == 1 and len(gelen[0][1]) == 2, str(gelen[0][:2]) if gelen else "")
        kontrol("E-posta: konu satırında kural ve kamera", bool(gelen) and "Subject:" in gelen[0][2])
        tamam, mesaj = baglanti.dene({"tur": "eposta", "sunucu": "127.0.0.1", "port": 8025, "tls": False, "alicilar": ["a@ornek.test"], "kullanici": "x", "sifre_degiskeni": "YANGIN_YOK_BOYLE_DEGISKEN"})
        kontrol("E-posta: şifre değişkeni yoksa gönderilmez", not tamam and "YANGIN_YOK_BOYLE_DEGISKEN" in mesaj, mesaj)
    finally:
        denetci.stop()


# ---------------------------------------------------------------- webhook
def webhook():
    gelen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            gelen.append((self.path, dict(self.headers), self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    s = HTTPServer(("127.0.0.1", 8799), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    baglanti.ilet({"tur": "webhook", "adres": "http://127.0.0.1:8799/olay", "basliklar": {"X-Kaynak": "yangin"}}, OLAY)
    baglanti.ilet({"tur": "teams", "adres": "http://127.0.0.1:8799/teams"}, OLAY)
    kontrol("Webhook: JSON ve özel başlık ulaştı", len(gelen) == 2 and json.loads(gelen[0][2])["olay"]["id"] == 7 and gelen[0][1].get("X-Kaynak") == "yangin")
    kontrol("Teams/Slack biçimi: kısa metin", "KRİTİK" in json.loads(gelen[1][2])["text"] and "Alev algılandı" in json.loads(gelen[1][2])["text"])
    kontrol("Süzgeç: risk puanı düşük olay iletilmez", not baglanti.uygun({"en_az_puan": 20}, OLAY) and baglanti.uygun({"en_az_puan": 15, "kategoriler": ["alev"]}, OLAY)
            and not baglanti.uygun({"kategoriler": ["duman"]}, OLAY) and baglanti.uygun({"yalniz_ciddi": True}, OLAY)
            and not baglanti.uygun({"yalniz_ciddi": True}, dict(OLAY, ciddi=0)) and not baglanti.uygun({"kameralar": ["baska"]}, OLAY))
    s.shutdown()


for ad, fn in (("Modbus", modbus), ("MQTT", mqtt), ("OPC UA", opcua), ("e-posta", eposta), ("webhook", webhook)):
    try:
        fn()
    except Exception as e:
        import traceback

        traceback.print_exc()
        kontrol(f"{ad}: sınama çalışmadı", False, repr(e)[:200])
basarili = sum(1 for _, k in SONUC if k)
print(f"\n{basarili}/{len(SONUC)} kontrol geçti")
sys.exit(0 if basarili == len(SONUC) else 1)
