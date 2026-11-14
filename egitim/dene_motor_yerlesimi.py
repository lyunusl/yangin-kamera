"""Motorun Studio klasörüne yerleştirilmesini (studio.motoru_yerlestir) Studio olmadan, geçici klasörlerde sınar.

  python egitim/dene_motor_yerlesimi.py

Denetlenenler:
  - imza dosya tarihine bağlı değildir: yalnızca tarihi değişen kaynak (exe'nin her açılışta yeniden açtığı dosyalar) kopyalanmaz
  - yalnızca içeriği değişen dosya kopyalanır; kaynakta artık olmayan dosya silinir
  - Studio'nun kullandığı (kilitli) bir dosya değişmediyse sorun çıkmaz; değiştiyse anlaşılır hata verilir
  - kaynak koddan modeller motor/modeller'den alınır; indirilen model gelince imza değişir, yarım indirmeler girmez
  - exe benzetimi: işaret ve DLL yalnızca programla gelen kopyadan; veri klasöründeki değiştirilmiş ya da fazladan dosyalar
    motora girmez; model yalnızca bu süreçte SHA-256 ile doğrulanmışsa girer, sonradan değişirse çıkarılır
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kok = Path(__file__).resolve().parent.parent
os.environ["YANGIN_KAMERA_VERI"] = tempfile.mkdtemp(prefix="yangin_yerlesim_veri_")
sys.path.insert(0, str(kok))

import studio  # noqa: E402

sonuc: list[tuple[str, bool]] = []


def denetle(ad, kosul):
    sonuc.append((ad, bool(kosul)))
    print(("  geçti  " if kosul else "  KALDI  ") + ad, flush=True)


kaynak = Path(tempfile.mkdtemp(prefix="yangin_yerlesim_kaynak_"))
hedef = Path(tempfile.mkdtemp(prefix="yangin_yerlesim_hedef_")) / "yangin_engine"
for ad, dosyalar in {"yangin_motor": {"__init__.py": b"", "blok.py": b"x = 1\n", "alt/kural.py": b"y = 2\n"},
                     "modeller": {"buyuk.onnx": os.urandom(1_300_000), "kucuk.onnx": os.urandom(4000)},
                     "deps": {"onnxruntime/capi/kitaplik.pyd": os.urandom(50_000), "onnxruntime/__init__.py": b"# ort\n"}}.items():
    for goreli, icerik in dosyalar.items():
        yol = kaynak / ad / goreli
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_bytes(icerik)
studio.MOTOR_KAYNAK = kaynak
ASIL_MODELLER, ASIL_MODEL, ASIL_PAKET = studio.yollar.MODELLER, studio.yollar.MODEL, studio.yollar.PAKET_MODELLER
studio.yollar.MODELLER =kaynak / "modeller"  # modeller, programın etkin model klasöründen alınır (aşağıda ayrıca sınanır)

kopyalar: list[str] = []
gercek_kopya = studio.shutil.copyfile


def sayan_kopya(a, b, *k, **kw):
    kopyalar.append(Path(a).name)
    return gercek_kopya(a, b, *k, **kw)


studio.shutil.copyfile = sayan_kopya


def yerlestir():
    kopyalar.clear()
    studio.motoru_yerlestir(hedef)
    return sorted(kopyalar)


def surum():
    return (hedef / "surum.txt").read_text(encoding="ascii"), (hedef / "surum.txt").stat().st_mtime_ns


print("İlk yerleştirme ve tarih değişikliği")
denetle("ilk çalıştırmada yedi dosyanın hepsi kopyalanır", len(yerlestir()) == 7 and (hedef / "deps/onnxruntime/capi/kitaplik.pyd").is_file())
s1 = surum()
denetle("hiçbir şey değişmediyse kopya yok, surum.txt yeniden yazılmaz", yerlestir() == [] and surum() == s1)
ileri = time.time() + 86400
for p in kaynak.rglob("*"):
    if p.is_file():
        os.utime(p, (ileri, ileri))  # exe'nin dosyalarını yeni tarihle açması gibi
denetle("yalnızca dosya tarihleri değişince kopya yok, surum.txt aynı kalır", yerlestir() == [] and surum() == s1)

print("İçerik değişikliği")
(kaynak / "yangin_motor/blok.py").write_bytes(b"x = 2\n")  # aynı boyut, farklı içerik
denetle("aynı boyutta ama içeriği değişen dosya kopyalanır", yerlestir() == ["blok.py"] and (hedef / "yangin_motor/blok.py").read_bytes() == b"x = 2\n")
denetle("içerik değişince surum.txt değişir (bloklar motoru yeniden yükler)", surum()[0] != s1[0])
buyuk = bytearray((kaynak / "modeller/buyuk.onnx").read_bytes())
buyuk[-10] ^= 0xFF
(kaynak / "modeller/buyuk.onnx").write_bytes(bytes(buyuk))
denetle("büyük dosyanın sonu değişince kopyalanır", yerlestir() == ["buyuk.onnx"])
buyuk_yol = kaynak / "modeller/buyuk.onnx"
onceki_surumu = surum()[0]
onceki_tarih = buyuk_yol.stat()
orta = len(buyuk) // 2
buyuk[orta:orta + 10] = bytes(b ^ 0xFF for b in buyuk[orta:orta + 10])
buyuk_yol.write_bytes(buyuk)
os.utime(buyuk_yol, ns=(onceki_tarih.st_atime_ns, onceki_tarih.st_mtime_ns))
denetle("büyük modelin yalnız ortası değişince aynı boyut ve tarihte bile kopyalanır",
        yerlestir() == ["buyuk.onnx"] and (hedef / "modeller/buyuk.onnx").read_bytes() == buyuk and surum()[0] != onceki_surumu)
(kaynak / "yangin_motor/alt/kural.py").unlink()
(kaynak / "yangin_motor/yeni.py").write_bytes(b"z = 3\n")
k = yerlestir()
denetle("kaynaktan silinen dosya hedeften de silinir, yeni dosya eklenir", k == ["yeni.py"] and not (hedef / "yangin_motor/alt/kural.py").exists())
(hedef / "yangin_motor/__pycache__").mkdir()
(hedef / "yangin_motor/__pycache__/blok.cpython-312.pyc").write_bytes(b"pyc")
denetle("Studio'nun yazdığı __pycache__ dosyalarına dokunulmaz", yerlestir() == [] and (hedef / "yangin_motor/__pycache__/blok.cpython-312.pyc").exists())

print("Eski biçimli işaret (dosya tarihine bağlı imza)")
(hedef / "deps.surum").write_text("2:50006:1794383544", encoding="ascii")
denetle("işaret eski biçimdeyse dosyalar karşılaştırılır; aynı olan kitaplık kopyalanmaz", yerlestir() == [] and ":" in (hedef / "deps.surum").read_text(encoding="ascii"))

print("Kullanımdaki (kilitli) dosya")
if os.name == "nt":
    kilitli = hedef / "deps/onnxruntime/capi/kitaplik.pyd"
    with open(kilitli, "rb"):  # Studio'nun yüklediği kitaplık gibi: açık dosya okunur ama üstüne yazılamaz
        (hedef / "deps.surum").write_text("eski", encoding="ascii")
        denetle("kilitli dosya değişmediyse yerleştirme sorunsuz geçer", yerlestir() == [])
        (kaynak / "deps/onnxruntime/capi/kitaplik.pyd").write_bytes(os.urandom(50_000))
        try:
            yerlestir()
            m = ""
        except studio.StudioHatasi as e:
            m = str(e)
        denetle("kilitli dosya değiştiyse anlaşılır hata verilir", "kullanımda olabilir" in m and "kitaplik.pyd" in m)
    denetle("kilit kalkınca aynı yerleştirme tamamlanır", yerlestir() == ["kitaplik.pyd"] and not list(hedef.rglob("*.yeni")))
else:
    print("  atlandı  dosya kilidi sınaması yalnızca Windows'ta çalışır", flush=True)

print("Kaynak koddan: modeller motor/modeller gibi tek klasörden (yollar.MODELLER)")
etkin = Path(tempfile.mkdtemp(prefix="yangin_yerlesim_modeller_"))
(etkin / "community-paket.json").write_bytes(b'{"id": "00"}')
(etkin / "goruntu-00.dll").write_bytes(os.urandom(3000))
studio.yollar.MODELLER = studio.yollar.PAKET_MODELLER = etkin
k = yerlestir()
denetle("modeller yollar.MODELLER'den alınır",
        k == ["community-paket.json", "goruntu-00.dll"] and sorted(p.name for p in (hedef / "modeller").iterdir()) == ["community-paket.json", "goruntu-00.dll"])
s2 = (hedef / "modeller.surum").read_text(encoding="ascii")
(etkin / "yangin-duman-512.onnx.isgm.1234.indiriliyor").write_bytes(os.urandom(5000))  # süren indirme
(etkin / "yangin-duman-512.onnx.isgm.yeni").write_bytes(os.urandom(5000))  # kurulum dosyasının yarım indirmesi
denetle("yarım indirmeler (.indiriliyor, .yeni) motora girmez, imza değişmez",
        yerlestir() == [] and (hedef / "modeller.surum").read_text(encoding="ascii") == s2)
(etkin / "yangin-duman-512.onnx.isgm.1234.indiriliyor").replace(etkin / "yangin-duman-512.onnx.isgm")
s3 = surum()[0]
denetle("indirilen model gelince imza değişir ve model kopyalanır",
        yerlestir() == ["yangin-duman-512.onnx.isgm"] and (hedef / "modeller.surum").read_text(encoding="ascii") != s2
        and surum()[0] != s3 and (hedef / "modeller/yangin-duman-512.onnx.isgm").is_file())

print("Exe (benzetim): paket dosyaları programla gelen kopyadan, veri klasöründen yalnızca doğrulanmış model")
import hashlib  # noqa: E402

import studio_kurulum  # noqa: E402

guvenilir = Path(tempfile.mkdtemp(prefix="yangin_paket_"))
veri = Path(tempfile.mkdtemp(prefix="yangin_veri_")) / "modeller"
veri.mkdir()
DLL = "goruntu-" + "ab" * 16 + ".dll"
guvenilir_json, guvenilir_dll = b'{"id": "' + b"ab" * 16 + b'", "fixture": false}', os.urandom(4000)
(guvenilir / "community-paket.json").write_bytes(guvenilir_json)
(guvenilir / DLL).write_bytes(guvenilir_dll)
(guvenilir / "RUST-NOTICES.txt").write_bytes(b"bildirimler")
model = b"ISGMOD\x01\x00" + bytes.fromhex("ab" * 16) + os.urandom(3000)
# veri klasörü kullanıcının yazabildiği yerdir: değiştirilmiş işaret ve DLL, fazladan DLL, yarım indirmeler
(veri / "community-paket.json").write_bytes(b'{"id": "' + b"cd" * 16 + b'", "fixture": false}')
(veri / DLL).write_bytes(os.urandom(4000))
(veri / ("goruntu-" + "cd" * 16 + ".dll")).write_bytes(os.urandom(4000))
(veri / "baska.dll").write_bytes(os.urandom(100))
(veri / (studio_kurulum.MODEL_ADI + ".99.indiriliyor")).write_bytes(model[:100])
(veri / (studio_kurulum.MODEL_ADI + ".yeni")).write_bytes(model[:100])
(veri / studio_kurulum.MODEL_ADI).write_bytes(model)
studio.yollar.DONDURULMUS = True
studio.yollar.PAKET_MODELLER, studio.yollar.MODELLER = guvenilir, veri
studio_kurulum.MODEL_BOYUT, studio_kurulum.MODEL_SHA256 = len(model), hashlib.sha256(model).hexdigest()
studio_kurulum._DOGRULANAN.update(yol=None, boyut=None, zaman=None)


def motordakiler():
    return {p.name: p.read_bytes() for p in (hedef / "modeller").iterdir()}


yerlestir()
m = motordakiler()
denetle("doğrulanmamış model motora girmez; paket dosyaları güvenilir kopyadan gelir",
        m == {"community-paket.json": guvenilir_json, DLL: guvenilir_dll, "RUST-NOTICES.txt": b"bildirimler"})
denetle("doğrulanmamış modelde panel modeli eksik sayar", studio_kurulum.model_durumu()["eksik"] and not studio_kurulum.model_hazir())
denetle("tam SHA-256 doğrulaması geçer", studio_kurulum.model_dogrula() and studio_kurulum.model_dogrulandi())
okunan = []
gercek_ac = Path.open


def sayan_ac(self, *a, **kw):
    okunan.append(self.name)
    return gercek_ac(self, *a, **kw)


Path.open = sayan_ac
try:
    k = yerlestir()
finally:
    Path.open = gercek_ac
m = motordakiler()
denetle("doğrulanmış model girer; veri klasöründeki değiştirilmiş işaret/DLL, fazladan DLL ve yarım dosyalar girmez",
        k == [studio_kurulum.MODEL_ADI] and m == {"community-paket.json": guvenilir_json, DLL: guvenilir_dll,
                                                  "RUST-NOTICES.txt": b"bildirimler", studio_kurulum.MODEL_ADI: model})
denetle("imza için doğrulanmış model yeniden okunmaz (özeti bilinir)",
        studio_kurulum.MODEL_ADI not in okunan)
s4 = surum()[0]
denetle("değişmeyince yeniden kopya yok", yerlestir() == [] and surum()[0] == s4)
bozuk = bytearray(model)
bozuk[-5] ^= 0xFF
(veri / studio_kurulum.MODEL_ADI).write_bytes(bytes(bozuk))  # doğrulamadan sonra aynı boyutta değişti
os.utime(veri / studio_kurulum.MODEL_ADI, ns=(1, 1))
yerlestir()
denetle("doğrulamadan sonra değişen model kullanılmaz (motordan çıkarılır)",
        not studio_kurulum.model_dogrulandi() and studio_kurulum.MODEL_ADI not in motordakiler())
denetle("aynı boyutta bozuk model doğrulamada yakalanır ve silinir",
        not studio_kurulum.model_dogrula() and not (veri / studio_kurulum.MODEL_ADI).exists())
studio.yollar.DONDURULMUS = False

print("yollar: model klasörleri")
import subprocess  # noqa: E402

import yollar  # noqa: E402

betik = ("import sys; sys.frozen = True; import yollar; "
         "print(yollar.MODELLER == yollar.VERI / 'modeller', yollar.MODEL.parent == yollar.MODELLER, "
         "yollar.PAKET_MODELLER == yollar.MOTOR / 'modeller', hasattr(yollar, 'modelleri_hazirla'))")
ortam = dict(os.environ, YANGIN_KAMERA_VERI=str(veri.parent))
cikti = subprocess.run([sys.executable, "-c", betik], cwd=str(kok), env=ortam, capture_output=True, text=True).stdout.split()
denetle("exe'de indirilen model veri klasöründe, paket dosyaları programla gelen klasörde; veri klasörüne paket kopyalanmaz",
        cikti == ["True", "True", "True", "False"])
denetle("kaynak koddan çalışırken model klasörü motor/modeller'dir",
        ASIL_MODELLER == ASIL_PAKET == yollar.MOTOR / "modeller" == kok / "motor" / "modeller" and ASIL_MODEL.parent == ASIL_MODELLER)

kalan = [ad for ad, ok in sonuc if not ok]
print(f"\n{len(sonuc) - len(kalan)}/{len(sonuc)} denetim geçti" + (f" · kalanlar: {kalan}" if kalan else ""))
sys.exit(1 if kalan else 0)
