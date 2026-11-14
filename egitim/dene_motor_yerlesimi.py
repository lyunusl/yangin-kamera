"""Motorun Studio klasörüne yerleştirilmesini (studio.motoru_yerlestir) Studio olmadan, geçici klasörlerde sınar.

  python egitim/dene_motor_yerlesimi.py

Denetlenenler:
  - imza dosya tarihine bağlı değildir: yalnızca tarihi değişen kaynak (exe'nin her açılışta yeniden açtığı dosyalar) kopyalanmaz
  - yalnızca içeriği değişen dosya kopyalanır; kaynakta artık olmayan dosya silinir
  - Studio'nun kullandığı (kilitli) bir dosya değişmediyse sorun çıkmaz; değiştiyse anlaşılır hata verilir
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

kalan = [ad for ad, ok in sonuc if not ok]
print(f"\n{len(sonuc) - len(kalan)}/{len(sonuc)} denetim geçti" + (f" · kalanlar: {kalan}" if kalan else ""))
sys.exit(1 if kalan else 0)
