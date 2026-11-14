"""Veritabanı (SQLite, tek dosya: veri/yangin.db): olaylar, görevler, ölçüm parçaları.

Bütün zamanlar yerel saatle ISO biçiminde ("2026-11-11T09:30:00") tutulur.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading

import yollar

_KILIT = threading.RLock()

SEMA = """
CREATE TABLE IF NOT EXISTS olay (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kimlik TEXT,                    -- motorun verdiği kimlik (olay başlarken ve kapanırken aynı)
  suruyor INTEGER NOT NULL DEFAULT 0,  -- olay şu an sürüyor mu
  zaman TEXT NOT NULL,            -- alevin ya da dumanın ilk görüldüğü an
  kamera TEXT NOT NULL,           -- kamera kodu
  kamera_ad TEXT NOT NULL,
  kural TEXT NOT NULL,            -- kural kodu
  kural_ad TEXT NOT NULL,
  kategori TEXT NOT NULL,
  duzey TEXT NOT NULL,            -- kritik | yuksek
  bolge TEXT,                     -- bölge adı (varsa)
  onem INTEGER NOT NULL,          -- 1-5
  olasilik INTEGER NOT NULL,      -- 1-5
  puan INTEGER NOT NULL,          -- onem × olasilik
  ciddi INTEGER NOT NULL,         -- düzeyi kritik olan olay
  sure_sn REAL NOT NULL,
  x REAL, y REAL,                 -- görüntüdeki konum (0-1)
  klip TEXT, kare TEXT,           -- cikti/ altındaki göreli yollar
  aciklama TEXT,
  ornek INTEGER NOT NULL DEFAULT 0,
  durum TEXT NOT NULL DEFAULT 'acik',   -- acik | ustlenildi | cozuldu | yanlis
  ustlenen TEXT, notlar TEXT, durum_zamani TEXT
);
CREATE INDEX IF NOT EXISTS olay_zaman ON olay(zaman);
CREATE INDEX IF NOT EXISTS olay_kamera ON olay(kamera, zaman);
CREATE INDEX IF NOT EXISTS olay_kimlik ON olay(kimlik);

CREATE TABLE IF NOT EXISTS olcum (            -- izlenen her zaman dilimi (yaklaşık 30 sn)
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kamera TEXT NOT NULL, kamera_ad TEXT NOT NULL,
  bas TEXT NOT NULL, sure_sn REAL NOT NULL,
  analiz INTEGER NOT NULL,        -- analiz edilen kare sayısı
  alev_sn REAL NOT NULL,          -- alev görülen süre
  duman_sn REAL NOT NULL,         -- duman görülen süre
  izgara TEXT NOT NULL,           -- JSON: {"gen": 32, "yuk": 18, "alev": [...], "duman": [...]}
  son_kare TEXT,
  ornek INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS olcum_kamera ON olcum(kamera, bas);

CREATE TABLE IF NOT EXISTS gorev (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  baslik TEXT NOT NULL, aciklama TEXT,
  sorumlu TEXT, son_tarih TEXT,
  durum TEXT NOT NULL DEFAULT 'acik',   -- acik | suruyor | kapandi
  kamera TEXT, kural TEXT, bolge TEXT,
  olusturma TEXT NOT NULL, kapanma TEXT
);
CREATE TABLE IF NOT EXISTS gorev_olay (gorev INTEGER NOT NULL, olay INTEGER NOT NULL, PRIMARY KEY (gorev, olay));
"""


def baglan() -> sqlite3.Connection:
    yollar.VERI.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(yollar.VT), timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SEMA)
    return c


_VT: sqlite3.Connection | None = None


def vt() -> sqlite3.Connection:
    global _VT
    with _KILIT:
        if _VT is None:
            _VT = baglan()
        return _VT


def kapat() -> None:
    global _VT
    with _KILIT:
        if _VT is not None:
            _VT.close()
            _VT = None


def simdi() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def sor(sql: str, *p) -> list[dict]:
    with _KILIT:
        return [dict(r) for r in vt().execute(sql, p).fetchall()]


def yaz(sql: str, *p) -> int:
    with _KILIT:
        c = vt().execute(sql, p)
        vt().commit()
        return c.lastrowid


def ekle(tablo: str, kayit: dict) -> int:
    alanlar = list(kayit)
    return yaz(f"INSERT INTO {tablo} ({', '.join(alanlar)}) VALUES ({', '.join('?' * len(alanlar))})",
               *[json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for v in kayit.values()])


def kamera_sil(kod: str, yalniz_ornek: bool = False) -> None:
    ek = " AND ornek = 1" if yalniz_ornek else ""
    with _KILIT:
        vt().execute(f"DELETE FROM gorev_olay WHERE olay IN (SELECT id FROM olay WHERE kamera = ?{ek})", (kod,))
        vt().execute(f"DELETE FROM olay WHERE kamera = ?{ek}", (kod,))
        vt().execute(f"DELETE FROM olcum WHERE kamera = ?{ek}", (kod,))
        vt().commit()


# ---------------------------------------------------------------- genel ayarlar

VARSAYILAN_GENEL = {
    "tesis": "Tesis",
    "vardiyalar": [{"ad": "Gündüz", "bas": "08:00", "bit": "16:00"}, {"ad": "Akşam", "bas": "16:00", "bit": "00:00"},
                   {"ad": "Gece", "bas": "00:00", "bit": "08:00"}],
    "baglantilar": [],   # [{"ad": "...", "tur": "webhook", "adres": "https://...", "en_az_puan": 9}]
}


def genel() -> dict:
    try:
        g = json.loads(yollar.GENEL_AYAR.read_text(encoding="utf-8"))
    except Exception:
        g = {}
    return {**VARSAYILAN_GENEL, **g}


def genel_yaz(g: dict) -> None:
    yollar.VERI.mkdir(parents=True, exist_ok=True)
    yollar.GENEL_AYAR.write_text(json.dumps({**genel(), **g}, ensure_ascii=False, indent=1), encoding="utf-8")


def vardiya(zaman: str, vardiyalar: list[dict] | None = None) -> str:
    """Verilen anın düştüğü vardiyanın adı."""
    vardiyalar = vardiyalar or genel()["vardiyalar"]
    dk = int(zaman[11:13]) * 60 + int(zaman[14:16])
    for v in vardiyalar:
        a = int(v["bas"][:2]) * 60 + int(v["bas"][3:5])
        b = int(v["bit"][:2]) * 60 + int(v["bit"][3:5])
        if (a <= dk < b) if a < b else (dk >= a or dk < b):
            return v["ad"]
    return "–"
