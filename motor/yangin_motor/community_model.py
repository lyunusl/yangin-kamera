"""Yangın Kamera'nın otomatik Studio lisansı ile açılan yerel model paketi."""
from __future__ import annotations

import ctypes
from functools import lru_cache
import json
import os
from pathlib import Path
import re

from .model_lisans import LisansHatasi

ISARET = "community-paket.json"
UZANTI = ".isgm"
SIHIR = b"ISGMOD\x01\x00"
BASLIK, ETIKET = 52, 16
SINIR = 512 * 1024 * 1024 + BASLIK + ETIKET

_MESAJ = {
    1: "Model dosyasının biçimi geçersiz. Yangın Kamera kurulumunu yeniden indirin.",
    2: "Model dosyası doğrulanamadı. Yangın Kamera kurulumunu yeniden indirin.",
    3: "AugeLab Studio lisans durumu doğrulanamadı. Analizi Studio üzerinden yeniden başlatın.",
    4: "AugeLab Studio'da arayüzsüz analize izin veren etkin bir lisans bulunamadı.",
}


class StudioLisansOkumaHatasi(LisansHatasi):
    """Studio lisans durumunu döndüremedi."""


def isaretli(klasor) -> bool:
    return (Path(klasor) / ISARET).is_file()


def model_mi(yol) -> bool:
    return isaretli(Path(yol).parent) or Path(str(yol) + UZANTI).is_file()


def _kimlik(klasor: Path) -> bytes:
    try:
        with (klasor / ISARET).open("rb") as f:
            veri = json.loads(f.read(512))
        kimlik = veri["id"]
        if not isinstance(kimlik, str) or not re.fullmatch("[a-f0-9]{32}", kimlik):
            raise ValueError
        return bytes.fromhex(kimlik)
    except (OSError, ValueError, TypeError, KeyError) as e:
        raise LisansHatasi(_MESAJ[1]) from e


@lru_cache(maxsize=8)
def _kutuphane(yol: Path):
    if os.name != "nt":
        raise LisansHatasi("Bu model paketi Windows x64 gerektirir.")
    try:
        # Search only the module folder and System32 for dependencies.
        dll = ctypes.CDLL(str(yol), winmode=0x100 | 0x800)
        dll.layout_stride.argtypes = ()
        dll.layout_stride.restype = ctypes.c_int
        dll.frame_color.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t)
        dll.frame_color.restype = ctypes.c_int
    except (OSError, AttributeError) as e:
        raise LisansHatasi("Model bileşeni açılamadı. Yangın Kamera kurulumunu yeniden indirin.") from e
    return dll


def _dosya(klasor: Path, kimlik: bytes) -> Path:
    return (klasor / f"goruntu-{kimlik.hex()}.dll").absolute()


def _denetle(kod: int) -> None:
    if kod == 3:
        raise StudioLisansOkumaHatasi(_MESAJ[kod])
    if kod:
        raise LisansHatasi(_MESAJ.get(kod, _MESAJ[1]))


def yetki(dll_yolu: Path) -> None:
    _denetle(_kutuphane(dll_yolu).layout_stride())


def durum(klasor, dosyalar) -> dict:
    sonuc = {"sifreli": True, "community": True}
    klasor = Path(klasor)
    try:
        kimlik = _kimlik(klasor)
        for ad in dosyalar:
            with (klasor / (ad + UZANTI)).open("rb") as f:
                if f.read(24) != SIHIR + kimlik:
                    raise LisansHatasi(_MESAJ[1])
        if not _dosya(klasor, kimlik).is_file():
            raise LisansHatasi(_MESAJ[1])
    except (OSError, LisansHatasi) as e:
        return dict(sonuc, durum="bozuk",
                    mesaj=str(e) if isinstance(e, LisansHatasi) else _MESAJ[1])
    # Panel süreci Studio değildir. Lisans model açılırken DLL tarafından doğrulanır.
    return dict(sonuc, durum="studio_kosusunda_dogrulanir")


def ac(yol) -> tuple[bytes, Path]:
    """DLL yetkiyi kendisi kontrol eder; şifre çözme için yazılabilir bellek dışında hedef yoktur."""
    yol = Path(yol)
    kimlik = _kimlik(yol.parent)
    dll_yolu = _dosya(yol.parent, kimlik)
    try:
        ad = yol.name.encode("ascii")
        with Path(str(yol) + UZANTI).open("rb") as f:
            boyut = os.fstat(f.fileno()).st_size
            if not BASLIK + ETIKET < boyut <= SINIR:
                raise LisansHatasi(_MESAJ[1])
            veri = bytearray(boyut)
            if f.readinto(veri) != boyut or f.read(1) or veri[:24] != SIHIR + kimlik:
                raise LisansHatasi(_MESAJ[1])
    except (OSError, UnicodeError) as e:
        raise LisansHatasi(_MESAJ[1]) from e
    buf = (ctypes.c_ubyte * len(veri)).from_buffer(veri)
    adres = ctypes.addressof(buf)
    try:
        _denetle(_kutuphane(dll_yolu).frame_color(adres, boyut, ad, len(ad)))
        # ORT's Python API requires bytes. Its in-memory copy lives only with the inference session.
        return ctypes.string_at(adres + BASLIK, boyut - BASLIK - ETIKET), dll_yolu
    finally:
        ctypes.memset(adres, 0, boyut)
