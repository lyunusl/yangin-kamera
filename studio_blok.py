"""Yangın Kamera'nın AugeLab Studio'ya kaydettiği özel bloklar.

Studio her bloğun dosyasını bu tanımlardan kendisi üretir (node.custom.create). Bloklar incedir: asıl iş, Studio'nun özel
blok klasörünün yanına konan "yangin_engine" klasöründeki yangin_motor paketindedir (model ve onnxruntime de orada).
Studio'nun kendi ortamına hiçbir paket kurulmaz; motorun ek kütüphaneleri sys.path'in SONUNA eklenir.
"""
from __future__ import annotations

MOTOR_KLASORU = "yangin_engine"  # Studio'nun custom_blocks klasörünün kardeşi
VIDEO_OP = "YanginVideo"
VIDEO_BASLIK = "Yangın Video"
ALGILA_OP = "YanginAlgilama"
ALGILA_BASLIK = "Yangın Algılama"
KURALLAR_OP = "YanginKurallar"
KURALLAR_BASLIK = "Yangın Kurallar"

# Üç blokta da aynı: motoru bul, sürümü değiştiyse yeniden yükle.
_YUKLE = """\
klasor = state.get('klasor')
if klasor is None:
    here = globals().get('__file__')
    if here:
        klasor = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(here))), 'yangin_engine')
    else:
        klasor = os.path.join(os.environ.get('APPDATA', ''), 'AugeLab Studio', 'marketplace', 'yangin_engine')
    if not os.path.isdir(os.path.join(klasor, 'yangin_motor')):
        outputs['Durum'] = 'hata: motor bulunamadi (Yangin Kamera panelini bir kez acin)'
        return
    for p in (klasor, os.path.join(klasor, 'deps')):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)
    state['klasor'] = klasor
try:
    damga = os.path.getmtime(os.path.join(klasor, 'surum.txt'))
except OSError:
    damga = 0
if state.get('blok') is None or state.get('damga') != damga:
    imza = ''
    try:
        with open(os.path.join(klasor, 'surum.txt'), encoding='ascii') as f:
            imza = f.read()
    except OSError:
        pass
    eski = sys.modules.get('yangin_motor')
    if eski is not None and getattr(eski, '_imza', None) != imza:
        for ad in [m for m in sys.modules if m == 'yangin_motor' or m.startswith('yangin_motor.')]:
            del sys.modules[ad]
    try:
        state['blok'] = importlib.import_module('yangin_motor.blok')
        sys.modules['yangin_motor']._imza = imza
    except Exception as exc:
        state['blok'] = None
        outputs['Durum'] = 'hata: motor yuklenemedi: %s: %s' % (type(exc).__name__, exc)
        return
    state['damga'] = damga
    state['durum'] = {}
blok = state['blok']
"""

VIDEO_KODU = """\
outputs['Image'] = None
outputs['Zaman'] = 0
outputs['Bitti'] = False
outputs['Durum'] = ''
""" + _YUKLE + """\
try:
    goruntu, zaman, bitti, durum = blok.video(state['durum'], inputs['Kamera'] or '')
except Exception as exc:
    outputs['Durum'] = 'hata: %s: %s' % (type(exc).__name__, exc)
    return
outputs['Image'] = goruntu
outputs['Zaman'] = zaman
outputs['Bitti'] = bitti
outputs['Durum'] = durum
"""

# Tespitler çıkışı varsayılan olarak "hata" değeridir (boş liste "alev ve duman yok" demektir): motor yüklenemezse ya da
# blok beklenmedik bir hata verirse Yangın Kurallar bunu görür, kural değerlendirmez ve panele hata bırakır.
ALGILA_KODU = """\
outputs['Tespitler'] = '{"hata": "Yangin Algilama calismadi"}'
outputs['Durum'] = ''
""" + _YUKLE + """\
try:
    tespitler, durum = blok.algila(state['durum'], inputs['Image'], inputs['Kamera'] or '', inputs['Zaman'])
except Exception as exc:
    outputs['Tespitler'] = '{"hata": "Yangin Algilama: %s"}' % type(exc).__name__
    outputs['Durum'] = 'hata: %s: %s' % (type(exc).__name__, exc)
    return
outputs['Tespitler'] = tespitler
outputs['Durum'] = durum
"""

KURALLAR_KODU = """\
outputs['Image'] = None
outputs['Alarm'] = False
outputs['Risk'] = 0
outputs['Olaylar'] = '[]'
outputs['Durum'] = ''
outputs['Yeni Olay'] = False
outputs['Alarm Yaz'] = False
""" + _YUKLE + """\
try:
    goruntu, alarm, risk, olaylar, durum, yeni, yaz = blok.kurallar(state['durum'], inputs['Image'], inputs['Tespitler'] or '[]', inputs['Kamera'] or '', inputs['Zaman'], bool(inputs['Bitti']))
except Exception as exc:
    outputs['Durum'] = 'hata: %s: %s' % (type(exc).__name__, exc)
    return
outputs['Image'] = goruntu
outputs['Alarm'] = alarm
outputs['Risk'] = risk
outputs['Olaylar'] = olaylar
outputs['Durum'] = durum
outputs['Yeni Olay'] = yeni
outputs['Alarm Yaz'] = yaz
"""

VIDEO = {
    "resolverKey": "yangin_video",
    "name": VIDEO_OP,
    "opCode": VIDEO_OP,
    "title": VIDEO_BASLIK,
    "kind": "computation",
    "description": (
        "Bir kameranın ayarındaki video dosyasını kare kare okur; arayüzsüz çalışmada canlı kameranın akışını da okur. "
        "'Kamera' girişi kamera kodudur. Çıkışlar: görüntü, görüntünün saniye cinsinden zamanı (canlı akışta -1), "
        "akış bittiğinde bir kez True olan Bitti ve durum."
    ),
    "imports": ["sys", "os", "importlib"],
    "inputs": [{"name": "Kamera", "type": "String"}],
    "outputs": [{"name": "Image", "type": "ImageAny"}, {"name": "Zaman", "type": "Number"}, {"name": "Bitti", "type": "Boolean"},
                {"name": "Durum", "type": "String"}],
    "parameters": [],
    "processCode": VIDEO_KODU,
}

ALGILA = {
    "resolverKey": "yangin_algilama",
    "name": ALGILA_OP,
    "opCode": ALGILA_OP,
    "title": ALGILA_BASLIK,
    "kind": "computation",
    "description": (
        "Alev ve duman tespiti. ONNX modelini marketplace/yangin_engine klasöründen çalıştırır; saniyede en çok iki kareyi "
        "analiz eder, aradaki karelerde son tespitleri yineler. Güven eşiğini 'Kamera' girişindeki kamera kodunun ayarı "
        "belirler; 'Zaman' Yangın Video'dan gelir. Çıkış: JSON {sira, tespitler: [{s: alev | duman, b: [x1, y1, x2, y2], "
        "p: güven}]} ve durum."
    ),
    "imports": ["sys", "os", "importlib"],
    "inputs": [{"name": "Image", "type": "ImageAny"}, {"name": "Kamera", "type": "String"}, {"name": "Zaman", "type": "Number"}],
    "outputs": [{"name": "Tespitler", "type": "String"}, {"name": "Durum", "type": "String"}],
    "parameters": [],
    "processCode": ALGILA_KODU,
}

KURALLAR = {
    "resolverKey": "yangin_kurallar",
    "name": KURALLAR_OP,
    "opCode": KURALLAR_OP,
    "title": KURALLAR_BASLIK,
    "kind": "computation",
    "description": (
        "Yangın kuralları: alev ve duman tespitlerini kayan bir zaman penceresinde değerlendirir, kameranın bölgelerini ve "
        "kurallarını uygular. Çıkışlar: işaretli görüntü; Alarm (önemli olay sürerken True); Risk (0-25); başlayan olaylar "
        "(JSON); durum; Yeni Olay; Alarm Yaz (alarm değişince ve 5 sn'de bir True). Zaman ve Bitti, Yangın Video'dan gelir."
    ),
    "imports": ["sys", "os", "importlib"],
    "inputs": [{"name": "Image", "type": "ImageAny"}, {"name": "Tespitler", "type": "String"}, {"name": "Kamera", "type": "String"},
               {"name": "Zaman", "type": "Number"}, {"name": "Bitti", "type": "Boolean"}],
    "outputs": [{"name": "Image", "type": "ImageAny"}, {"name": "Alarm", "type": "Boolean"}, {"name": "Risk", "type": "Number"},
                {"name": "Olaylar", "type": "String"}, {"name": "Durum", "type": "String"}, {"name": "Yeni Olay", "type": "Boolean"},
                {"name": "Alarm Yaz", "type": "Boolean"}],
    "parameters": [],
    "processCode": KURALLAR_KODU,
}

TANIMLAR = [VIDEO, ALGILA, KURALLAR]


def imza() -> str:
    """Blok tanımlarının özeti: giriş ya da çıkışlar değiştiyse hazır sahnenin yeniden üretilmesi gerekir."""
    import hashlib
    import json

    return hashlib.sha1(json.dumps(TANIMLAR, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def dosya_metni(t: dict) -> str:
    """Bloğun Studio'nun özel blok klasörüne konacak dosyası: Studio'nun node.custom.create ile tanımdan ürettiği dosyanın
    aynısı. Arayüzsüz çalışmada (studio run) Studio açık olmadığından dosyayı panel kendisi yazar."""
    op = t["opCode"]
    girisler = ",\n".join(f"        SocketTypes.{g['type']}({g['name']!r}, multiple=False)" for g in t["inputs"])
    cikislar = ",\n".join(f"        SocketTypes.{c['type']}({c['name']!r}, multiple=False)" for c in t["outputs"])
    adlar = ", ".join(repr(c["name"]) for c in t["outputs"])
    if len(t["outputs"]) == 1:
        adlar += ","
    islem = "".join(("        " + s if s.strip() else "") + "\n" for s in t["processCode"].rstrip("\n").split("\n"))
    girdi = ",\n".join(f"            {g['name']!r}: self.input[{g['name']!r}].data" for g in t["inputs"])
    cikti = ",\n".join(f"            {c['name']!r}: None" for c in t["outputs"])
    ithal = "".join(f"import {m}\n" for m in t.get("imports") or [])
    return (
        "from studio.custom_block import (\n"
        "    Block, CheckBox, DropDown, Label, SocketTypes, TextInput, add_block,\n"
        ")\n\n"
        f"{ithal}\n"
        f"class {op}(Block):\n"
        f"    op_code = {op!r}\n"
        f"    input_sockets = [\n{girisler}\n    ]\n"
        f"    output_sockets = [\n{cikislar}\n    ]\n"
        "    _augelab_generated_spec_version = 1\n"
        f"    _augelab_output_names = ({adlar})\n\n"
        "    def init(self):\n"
        f"        self.op_title = {t['title']!r}\n"
        "        self.width = 280\n"
        "        self.height = 150\n"
        f"        self.tooltip = {t['description']!r}\n"
        "        pass\n"
        "        self._augelab_generated_state = {}\n\n"
        "    @staticmethod\n"
        "    def _process(inputs, parameters, state, outputs):\n"
        f"{islem}\n"
        "    def run(self):\n"
        f"        inputs = {{\n{girdi}\n        }}\n"
        "        parameters = {\n            \n        }\n"
        "        state = self._augelab_generated_state\n"
        f"        outputs = {{\n{cikti}\n        }}\n"
        "        self._process(inputs, parameters, state, outputs)\n"
        "        unknown = set(outputs).difference(self._augelab_output_names)\n"
        "        if unknown:\n"
        "            raise ValueError(f\"Undeclared generated outputs: {sorted(unknown)}\")\n"
        "        for output_name in self._augelab_output_names:\n"
        "            self.output[output_name].data = outputs[output_name]\n\n\n"
        f"add_block({op}.op_code, {op})\n"
    )
