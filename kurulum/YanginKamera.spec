import json
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
# Hazır sahne: Studio sahneleri şifreli kaydettiği için bir kez Studio'da kurulup kaydedilir (kurulum/sablon.py).
# Depoda tutulmaz (.gitignore: *.pmod); exe'ye girer ve panel onu arayüzsüz çalıştırır.
sahne = root / "kurulum" / "sahne" / "yangin-kamera.pmod"
if not sahne.is_file():
    raise SystemExit(f"Hazır sahne yok: {sahne}. kurulum/sablon.py ile üretip Studio'da Farklı Kaydet ile kaydedin.")
MODEL = "yangin-duman-512.onnx"
data = [
    (str(sahne), "kurulum/sahne"),
    (str(root / "web"), "web"),
    (str(root / "motor" / "yangin_motor"), "motor/yangin_motor"),
    (str(root / "motor" / "deps"), "motor/deps"),
    (str(root / "LICENSE"), "."),
    (str(root / "ATIFLAR.md"), "."),
]
if (root / "ornekler").is_dir():  # örnek videolar ve ayarları (yoksa program örneksiz açılır)
    data.append((str(root / "ornekler"), "ornekler"))
kip = os.environ.get("YANGIN_MODEL_PAKETI", "").strip().lower()
if kip == "community":
    # Korumalı paket: model yalnızca AugeLab Studio'nun içinde, etkin lisansla açılır. Düz model exe'ye girmez.
    paket = Path(os.environ.get("YANGIN_COMMUNITY_MODEL_KLASORU") or root / "kurulum" / "community-modeller")
    isaret = paket / "community-paket.json"
    try:
        bildirim = json.loads(isaret.read_text(encoding="ascii"))
        kimlik = bytes.fromhex(bildirim["id"])
        if len(kimlik) != 16 or bildirim["fixture"] is not False:
            raise ValueError("Test paketi dağıtımda kullanılamaz.")
        dll = paket / f"goruntu-{kimlik.hex()}.dll"
        if not dll.is_file():
            raise ValueError("Rust model bileşeni eksik.")
        bildirimler = paket / "RUST-NOTICES.txt"
        if not bildirimler.is_file() or not bildirimler.stat().st_size:
            raise ValueError("Rust bağımlılık bildirimleri eksik.")
        modeller = [paket / (MODEL + ".isgm")]
        for m in modeller:
            with m.open("rb") as f:
                if f.read(24) != b"ISGMOD\x01\x00" + kimlik or m.stat().st_size <= 68:
                    raise ValueError(f"Paket başlığı geçersiz: {m.name}")
    except (OSError, ValueError, TypeError, KeyError) as e:
        raise SystemExit(f"Community model paketi eksik veya geçersiz: {e}") from e
    data += [(str(m), "motor/modeller") for m in [isaret, dll, *modeller]]
    data.append((str(bildirimler), "."))
elif kip == "":
    duz = root / "motor" / "modeller" / MODEL  # geliştirme derlemesi: düz model
    if not duz.is_file():
        raise SystemExit(f"Model dosyası yok: {duz}")
    data.append((str(duz), "motor/modeller"))
else:
    raise SystemExit(f"Bilinmeyen YANGIN_MODEL_PAKETI: {kip} (community ya da boş)")

a = Analysis(
    [str(root / "uygulama.py")],
    pathex=[str(root), str(root / "motor")],
    datas=data,
    hiddenimports=(
        collect_submodules("yangin_motor")
    ),
    excludes=["torch", "tensorflow", "matplotlib", "pytest"],
)
if kip == "community":
    # ONNX Runtime'ın örnek grafikleri Community kurulumunda kullanılmaz.
    a.datas = [(ad, yol, tur) for ad, yol, tur in a.datas if not ad.lower().endswith(".onnx")]
# Visual C++ çalışma kitaplıkları Windows'un kendi klasöründen alınır. PyInstaller bunları PATH'te ilk bulduğu yerden
# toplar; PATH'teki başka bir programın eski msvcp140.dll dosyası pakete girerse onnxruntime modeli yüklerken
# erişim ihlaliyle (0xC0000005) kapanır.
_sistem = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"
_crt = {"msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll",
        "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll", "vcomp140.dll"}
a.binaries = [(ad, str(_sistem / ad), tur) if ad.lower() in _crt and (_sistem / ad).is_file() else (ad, yol, tur) for ad, yol, tur in a.binaries]
for _ad, _yol, _tur in a.binaries:
    if _ad.lower() == "msvcp140.dll":
        import ctypes, ctypes.wintypes

        _boy = ctypes.windll.version.GetFileVersionInfoSizeW(_yol, None)
        _veri = ctypes.create_string_buffer(_boy)
        ctypes.windll.version.GetFileVersionInfoW(_yol, 0, _boy, _veri)
        _bilgi, _n = ctypes.c_void_p(), ctypes.wintypes.UINT()
        ctypes.windll.version.VerQueryValueW(_veri, "\\", ctypes.byref(_bilgi), ctypes.byref(_n))
        _ms = ctypes.cast(_bilgi, ctypes.POINTER(ctypes.wintypes.DWORD * 4)).contents[2]  # dwFileVersionMS
        if (_ms >> 16, _ms & 0xFFFF) < (14, 40):
            raise SystemExit(f"msvcp140.dll eski ({_ms >> 16}.{_ms & 0xFFFF}, kaynak: {_yol}); güncel Visual C++ 2015-2022 Redistributable (x64) kurun.")

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="YanginKamera-community" if kip == "community" else "YanginKamera",
    console=True,
    upx=False,
    icon=str(root / "kurulum" / "yangin-kamera.ico"),  # kurulum/simge.py çizer
)
