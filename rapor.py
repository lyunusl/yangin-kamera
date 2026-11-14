"""Veritabanından ekranlar için özetler: Kontrol Odası, Uyarılar, Görsel Analitik, Raporlar, Excel."""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import depo
import kurallar
import yollar


def aralik(q: dict) -> tuple[str, str]:
    """İstekten zaman aralığı: bas/bit (YYYY-AA-GG) ya da son `gun` gün."""
    simdi = dt.datetime.now()
    if q.get("bas") and q.get("bit"):
        return q["bas"][:10] + "T00:00:00", q["bit"][:10] + "T23:59:59"
    try:
        gun = max(1, min(730, int(q.get("gun", 7))))
    except (TypeError, ValueError):
        gun = 7
    bas = (simdi - dt.timedelta(days=gun - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return bas.isoformat(), simdi.replace(microsecond=0).isoformat()


def _olaylar(bas: str, bit: str, kamera: str | None = None, yanlislar: bool = False) -> list[dict]:
    sql, p = "SELECT * FROM olay WHERE zaman >= ? AND zaman <= ?", [bas, bit]
    if kamera:
        sql += " AND kamera = ?"
        p.append(kamera)
    if not yanlislar:
        sql += " AND durum != 'yanlis'"
    out = depo.sor(sql + " ORDER BY zaman DESC, id DESC", *p)
    vs = depo.genel()["vardiyalar"]
    for o in out:
        o["vardiya"] = depo.vardiya(o["zaman"], vs)
    return out


def _olcumler(bas: str, bit: str, kamera: str | None = None, tam: bool = False) -> list[dict]:
    alanlar = "*" if tam else "id, kamera, kamera_ad, bas, sure_sn, analiz, alev_sn, duman_sn, son_kare"
    sql, p = f"SELECT {alanlar} FROM olcum WHERE bas >= ? AND bas <= ?", [bas, bit]
    if kamera:
        sql += " AND kamera = ?"
        p.append(kamera)
    return depo.sor(sql + " ORDER BY bas", *p)


def son_kritik() -> int:
    """En son kritik olayın numarası (panel yeni kritik olayda siren çalar)."""
    return depo.sor("SELECT COALESCE(MAX(id), 0) AS n FROM olay WHERE duzey = 'kritik'")[0]["n"]


def kameralar() -> list[dict]:
    """Ayar dosyası olan kameralar ve son durumları."""
    out = []
    son = {r["kamera"]: r["bas"] for r in depo.sor("SELECT kamera, MAX(bas) AS bas FROM olcum GROUP BY kamera")}
    acik = {r["kamera"]: r for r in depo.sor(
        "SELECT kamera, COUNT(*) AS n, SUM(ciddi) AS ciddi, MAX(puan) AS puan, SUM(suruyor) AS suruyor FROM olay WHERE durum = 'acik' GROUP BY kamera")}
    for yol in sorted(yollar.AYAR.glob("*.json")):
        if yol.stem.startswith("_"):
            continue
        try:
            a = json.loads(yol.read_text(encoding="utf-8"))
        except Exception:
            continue
        kod = a.get("kod") or yol.stem
        ac = acik.get(kod, {})
        kare = yollar.AYAR / f"_kare_{kod}.jpg"
        son_kare = yollar.CIKTI / kod / "son_kare.jpg"  # motor, çalışırken saniyede bir yeniler
        out.append({
            "kod": kod, "ad": a.get("ad", kod), "tur": (a.get("kamera") or {}).get("tur", "rtsp"),
            "bolge": len(a.get("bolgeler") or []), "kural": len(kurallar.coz(a)),
            "son_analiz": son.get(kod), "son_kare": f"/cikti/{kod}/son_kare.jpg?t={son_kare.stat().st_mtime_ns // 1_000_000}" if son_kare.exists() else None,
            "ayar_karesi": f"/ayar/{kare.name}?t={int(kare.stat().st_mtime)}" if kare.exists() else None,
            "acik": ac.get("n", 0), "acik_kritik": ac.get("ciddi") or 0, "suruyor": ac.get("suruyor") or 0, "en_yuksek_puan": ac.get("puan") or 0,
            "ornek": kod in yollar.ORNEK_ADLARI,
        })
    return out


def _gunler(bas: str, bit: str) -> list[str]:
    a, b = dt.date.fromisoformat(bas[:10]), dt.date.fromisoformat(bit[:10])
    return [(a + dt.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def ozet(q: dict) -> dict:
    """Kontrol Odası."""
    bas, bit = aralik(q)
    olaylar, olcumler = _olaylar(bas, bit), _olcumler(bas, bit)
    gunluk = {g: {"gun": g, "olay": 0, "kritik": 0, "izlenen_sn": 0.0, "tespit_sn": 0.0} for g in _gunler(bas, bit)}
    for m in olcumler:
        g = gunluk.get(m["bas"][:10])
        if g:
            g["izlenen_sn"] += m["sure_sn"]
            g["tespit_sn"] += max(m["alev_sn"], m["duman_sn"])
    for o in olaylar:
        g = gunluk.get(o["zaman"][:10])
        if g:
            g["olay"] += 1
            g["kritik"] += o["ciddi"]
    aciklar = sorted((o for o in olaylar if o["durum"] == "acik"), key=lambda o: (-o["suruyor"], -o["puan"], o["zaman"]))
    return {
        "bas": bas, "bit": bit, "tesis": depo.genel()["tesis"],
        "izlenen_sn": round(sum(m["sure_sn"] for m in olcumler)), "olay": len(olaylar),
        "kritik": sum(o["ciddi"] for o in olaylar), "acik": len(aciklar), "suruyor": sum(o["suruyor"] for o in aciklar),
        "seri": [{**g, "izlenen_sn": round(g["izlenen_sn"]), "tespit_sn": round(g["tespit_sn"])} for g in gunluk.values()],
        "kameralar": kameralar(), "canli": aciklar[:12],
    }


def olaylar(q: dict) -> dict:
    """Uyarılar listesi (süzgeçli)."""
    bas, bit = aralik({"gun": q.get("gun", 30), **q})
    liste = _olaylar(bas, bit, q.get("kamera") or None, yanlislar=True)
    for alan in ("kategori", "durum", "duzey", "vardiya", "kural"):
        if q.get(alan):
            liste = [o for o in liste if str(o[alan]) == q[alan]]
    if q.get("ciddi") == "1":
        liste = [o for o in liste if o["ciddi"]]
    if q.get("sirala") == "puan":
        liste.sort(key=lambda o: (-o["puan"], o["zaman"]))
    try:
        sinir = max(1, min(1000, int(q.get("sinir", 200))))
    except (TypeError, ValueError):
        sinir = 200
    gorevler = defaultdict(list)
    for r in depo.sor("SELECT gorev, olay FROM gorev_olay"):
        gorevler[r["olay"]].append(r["gorev"])
    for o in liste:
        o["gorevler"] = gorevler.get(o["id"], [])
    return {"toplam": len(liste), "olaylar": liste[:sinir]}


def analitik(q: dict) -> dict:
    """Görsel Analitik: bir kamerada alevin ve dumanın görüldüğü yerler (ısı haritası) ve olayların zamana dağılımı."""
    bas, bit = aralik({"gun": q.get("gun", 7), **q})
    kamera = q.get("kamera") or None
    olcumler = _olcumler(bas, bit, kamera, tam=True)
    olaylar_ = _olaylar(bas, bit, kamera)
    if q.get("kategori"):
        olaylar_ = [o for o in olaylar_ if o["kategori"] == q["kategori"]]
    if q.get("kural"):
        olaylar_ = [o for o in olaylar_ if o["kural"] == q["kural"]]
    if q.get("ciddi") == "1":
        olaylar_ = [o for o in olaylar_ if o["ciddi"]]
    gen = yuk = 0
    alev = duman = None
    saatlik = [{"saat": h, "tespit_sn": 0.0, "olay": 0} for h in range(24)]
    for m in olcumler:
        iz = json.loads(m["izgara"])
        if alev is None:
            gen, yuk = iz["gen"], iz["yuk"]
            alev = [[0.0] * gen for _ in range(yuk)]
            duman = [[0.0] * gen for _ in range(yuk)]
        if iz["gen"] == gen and iz["yuk"] == yuk:
            for y in range(yuk):
                for x in range(gen):
                    alev[y][x] += iz["alev"][y][x]
                    duman[y][x] += iz["duman"][y][x]
        saatlik[int(m["bas"][11:13])]["tespit_sn"] += max(m["alev_sn"], m["duman_sn"])
    for o in olaylar_:
        saatlik[int(o["zaman"][11:13])]["olay"] += 1
    olay_izgara = [[0] * gen for _ in range(yuk)] if gen else []
    for o in olaylar_:
        if gen and o["x"] is not None:
            olay_izgara[min(yuk - 1, max(0, int(o["y"] * yuk)))][min(gen - 1, max(0, int(o["x"] * gen)))] += o["puan"]
    yogun = max(saatlik, key=lambda s: (s["olay"], s["tespit_sn"])) if olaylar_ or olcumler else None
    ayar = {}
    if kamera and (yollar.AYAR / f"{kamera}.json").exists():
        ayar = json.loads((yollar.AYAR / f"{kamera}.json").read_text(encoding="utf-8"))
    kural_say = defaultdict(int)
    for o in olaylar_:
        kural_say[(o["kural"], o["kural_ad"])] += 1
    son_kare = yollar.CIKTI / kamera / "son_kare.jpg" if kamera else None
    # en riskli hücrenin payı ("bir köşe riskin %X'i")
    toplam_risk = sum(sum(s) for s in olay_izgara) if gen else 0
    en_hucre = max((v for s in olay_izgara for v in s), default=0) if gen else 0
    return {
        "bas": bas, "bit": bit, "kamera": kamera, "parca": len(olcumler),
        "son_kare": f"/cikti/{kamera}/son_kare.jpg?t={son_kare.stat().st_mtime_ns // 1_000_000}" if son_kare is not None and son_kare.exists() else None,
        "izgara": {"gen": gen, "yuk": yuk, "alev": alev or [], "duman": duman or [], "olay": olay_izgara},
        "bolgeler": ayar.get("bolgeler") or [],
        "noktalar": [{"x": o["x"], "y": o["y"], "puan": o["puan"], "kural_ad": o["kural_ad"], "id": o["id"]} for o in olaylar_ if o["x"] is not None][:500],
        "sayilar": {
            "alev_sn": round(sum(m["alev_sn"] for m in olcumler)), "duman_sn": round(sum(m["duman_sn"] for m in olcumler)),
            "olay": len(olaylar_), "kritik": sum(o["ciddi"] for o in olaylar_), "izlenen_sn": round(sum(m["sure_sn"] for m in olcumler)),
            "yogun_saat": f"{yogun['saat']:02d}:00" if yogun and (yogun["olay"] or yogun["tespit_sn"] > 0) else None,
            "en_riskli_pay": round(100 * en_hucre / toplam_risk) if toplam_risk else None,
        },
        "saatlik": [{"saat": s["saat"], "tespit_sn": round(s["tespit_sn"]), "olay": s["olay"]} for s in saatlik],
        "kurallar": sorted(({"kod": k, "ad": ad, "n": n} for (k, ad), n in kural_say.items()), key=lambda r: -r["n"]),
    }


def rapor(q: dict) -> dict:
    """Raporlar: olay eğilimi ve kural / kamera / vardiya / bölge kırılımları."""
    bas, bit = aralik({"gun": q.get("gun", 30), **q})
    olaylar_, olcumler = _olaylar(bas, bit), _olcumler(bas, bit)
    gunler = _gunler(bas, bit)
    haftalik = len(gunler) > 62

    def kova(tarih: str) -> str:
        if not haftalik:
            return tarih
        d = dt.date.fromisoformat(tarih)
        return (d - dt.timedelta(days=d.weekday())).isoformat()

    egilim = {}
    for g in gunler:
        egilim.setdefault(kova(g), {"d": kova(g), "olay": 0, "kritik": 0, "risk": 0})
    for o in olaylar_:
        e = egilim.get(kova(o["zaman"][:10]))
        if e:
            e["olay"] += 1
            e["kritik"] += o["ciddi"]
            e["risk"] += o["puan"]

    def kirilim(alan: str, ad_alani: str | None = None) -> list[dict]:
        g = defaultdict(lambda: {"n": 0, "kritik": 0, "risk": 0, "sure_sn": 0.0})
        for o in olaylar_:
            x = g[(o[alan], o[ad_alani] if ad_alani else o[alan])]
            x["n"] += 1
            x["kritik"] += o["ciddi"]
            x["risk"] += o["puan"]
            x["sure_sn"] += o["sure_sn"]
        return sorted(({"kod": k, "ad": ad, **{a: (round(v, 1) if isinstance(v, float) else v) for a, v in x.items()}}
                       for (k, ad), x in g.items()), key=lambda r: -r["risk"])

    yanit = []
    for o in olaylar_:
        if o["durum_zamani"] and o["durum"] != "acik":
            try:
                yanit.append((dt.datetime.fromisoformat(o["durum_zamani"]) - dt.datetime.fromisoformat(o["zaman"])).total_seconds() / 60)
            except ValueError:
                pass
    # önceki eşit uzunluktaki dönemle karşılaştırma
    uzun = dt.datetime.fromisoformat(bit) - dt.datetime.fromisoformat(bas)
    obas = (dt.datetime.fromisoformat(bas) - uzun - dt.timedelta(seconds=1)).isoformat()
    obit = (dt.datetime.fromisoformat(bas) - dt.timedelta(seconds=1)).isoformat()
    gorevler = depo.sor("SELECT durum, COUNT(*) AS n FROM gorev GROUP BY durum")
    kategori = kirilim("kategori")
    for r in kategori:
        r["ad"] = kurallar.KATEGORILER.get(r["kod"], r["kod"])
    return {
        "bas": bas, "bit": bit, "tesis": depo.genel()["tesis"], "haftalik": haftalik,
        "olay": len(olaylar_), "onceki_olay": len(_olaylar(obas, obit)), "kritik": sum(o["ciddi"] for o in olaylar_),
        "risk": sum(o["puan"] for o in olaylar_),
        "acik": sum(1 for o in olaylar_ if o["durum"] == "acik"), "cozulen": sum(1 for o in olaylar_ if o["durum"] == "cozuldu"),
        "yanlis": depo.sor("SELECT COUNT(*) AS n FROM olay WHERE zaman >= ? AND zaman <= ? AND durum = 'yanlis'", bas, bit)[0]["n"],
        "izlenen_sn": round(sum(m["sure_sn"] for m in olcumler)),
        "ort_yanit_dk": round(sum(yanit) / len(yanit), 1) if yanit else None,
        "egilim": list(egilim.values()),
        "kurallar": kirilim("kural", "kural_ad"), "kameralar": kirilim("kamera", "kamera_ad"), "vardiyalar": kirilim("vardiya"),
        "kategoriler": kategori, "bolgeler": [r for r in kirilim("bolge") if r["kod"]],
        "gorevler": {r["durum"]: r["n"] for r in gorevler},
    }


def gorevler() -> list[dict]:
    """Görevler; her biri için bağlı olaylar ve kapanış sonrası doğrulama."""
    liste = depo.sor("SELECT * FROM gorev ORDER BY (durum = 'kapandi'), COALESCE(son_tarih, '9999'), id DESC")
    bugun = dt.date.today().isoformat()
    for g in liste:
        bagli = depo.sor("SELECT o.id, o.zaman, o.kural, o.kural_ad, o.kamera, o.kamera_ad, o.bolge, o.puan, o.kare, o.klip FROM gorev_olay b "
                         "JOIN olay o ON o.id = b.olay WHERE b.gorev = ? ORDER BY o.zaman DESC", g["id"])
        g["olaylar"] = bagli
        g["gecikti"] = bool(g["son_tarih"] and g["durum"] != "kapandi" and g["son_tarih"] < bugun)
        # aynı kamera + kural (+ bölge) için haftalık olay sayısı: önlem işe yaradı mı?
        kamera = g["kamera"] or (bagli[0]["kamera"] if bagli else None)
        kural = g["kural"] or (bagli[0]["kural"] if bagli else None)
        g["haftalar"], g["dogrulama"] = [], None
        if kamera and kural:
            sql, p = "SELECT zaman, puan FROM olay WHERE kamera = ? AND kural = ? AND durum != 'yanlis'", [kamera, kural]
            if g["bolge"]:
                sql += " AND bolge = ?"
                p.append(g["bolge"])
            hafta = defaultdict(int)
            for o in depo.sor(sql, *p):
                d = dt.date.fromisoformat(o["zaman"][:10])
                hafta[(d - dt.timedelta(days=d.weekday())).isoformat()] += 1
            g["haftalar"] = [{"hafta": h, "n": n} for h, n in sorted(hafta.items())][-10:]
            if g["durum"] == "kapandi" and g["kapanma"]:
                sonra = depo.sor(sql + " AND zaman > ?", *p, g["kapanma"])
                izleme = depo.sor("SELECT COUNT(*) AS n FROM olcum WHERE kamera = ? AND bas > ?", kamera, g["kapanma"])[0]["n"]
                g["dogrulama"] = {"sonra_olay": len(sonra), "sonra_parca": izleme,
                                  "durum": "bekliyor" if izleme == 0 else ("tekrarladi" if sonra else "dogrulandi")}
    return liste


def excel() -> Path:
    """Son 30 günün raporunu cikti/rapor.xlsx olarak yazar."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    r = rapor({"gun": 30})
    duzey = {"kritik": "kritik", "yuksek": "yüksek"}
    kitap = Workbook()
    s = kitap.active
    s.title = "Özet"
    for satir in (["Tesis", r["tesis"]], ["Dönem", f"{r['bas'][:10]} – {r['bit'][:10]}"], ["Olay", r["olay"]],
                  ["Önceki dönemde olay", r["onceki_olay"]], ["Kritik olay", r["kritik"]], ["Açık olay", r["acik"]],
                  ["Çözülen olay", r["cozulen"]], ["Yanlış alarm", r["yanlis"]], ["İzlenen süre (saat)", round(r["izlenen_sn"] / 3600, 2)],
                  ["Ortalama yanıt süresi (dk)", r["ort_yanit_dk"]]):
        s.append(satir)
    for ad, baslik, liste in (("Kurallar", "Kural", r["kurallar"]), ("Kameralar", "Kamera", r["kameralar"]),
                              ("Vardiyalar", "Vardiya", r["vardiyalar"]), ("Bölgeler", "Bölge", r["bolgeler"])):
        s = kitap.create_sheet(ad)
        s.append([baslik, "Olay", "Kritik", "Risk puanı toplamı", "Toplam süre (sn)"])
        for x in liste:
            s.append([x["ad"], x["n"], x["kritik"], x["risk"], x["sure_sn"]])
    s = kitap.create_sheet("Olaylar")
    s.append(["No", "Zaman", "Kamera", "Kural", "Kategori", "Düzey", "Bölge", "Vardiya", "Önem", "Olasılık", "Risk puanı", "Süre (sn)", "Durum", "Üstlenen", "Not"])
    for o in _olaylar(r["bas"], r["bit"], yanlislar=True):
        s.append([o["id"], o["zaman"].replace("T", " "), o["kamera_ad"], o["kural_ad"], kurallar.KATEGORILER.get(o["kategori"], o["kategori"]),
                  duzey.get(o["duzey"], o["duzey"]), o["bolge"], o["vardiya"], o["onem"], o["olasilik"], o["puan"], o["sure_sn"],
                  {"acik": "açık", "ustlenildi": "üstlenildi", "cozuldu": "çözüldü", "yanlis": "yanlış alarm"}.get(o["durum"], o["durum"]),
                  o["ustlenen"], o["notlar"]])
    s = kitap.create_sheet("Görevler")
    s.append(["No", "Başlık", "Sorumlu", "Son tarih", "Durum", "Bağlı olay", "Oluşturma", "Kapanma", "Doğrulama"])
    for g in gorevler():
        s.append([g["id"], g["baslik"], g["sorumlu"], g["son_tarih"], {"acik": "açık", "suruyor": "sürüyor", "kapandi": "kapandı"}.get(g["durum"]),
                  len(g["olaylar"]), g["olusturma"].replace("T", " "), (g["kapanma"] or "").replace("T", " "),
                  {"dogrulandi": "kamera doğruladı", "tekrarladi": "tekrarladı", "bekliyor": "izleme bekleniyor"}.get((g["dogrulama"] or {}).get("durum"), "")])
    for s in kitap.worksheets:
        for h in s[1]:
            h.font = Font(bold=True)
        for sutun in s.columns:
            s.column_dimensions[sutun[0].column_letter].width = min(48, max(12, max(len(str(h.value or "")) for h in sutun) + 2))
    yollar.CIKTI.mkdir(parents=True, exist_ok=True)
    hedef = yollar.CIKTI / "rapor.xlsx"
    kitap.save(hedef)
    return hedef
