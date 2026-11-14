"""Örnek klipleri motorun kendi yolundan geçirir: Yangın Video → Yangın Algılama → Yangın Kurallar (Studio olmadan),
sonra kuyruğu panelin koduyla içeri alır.

  python egitim/dene_ornekler.py

motor/modeller/yangin-duman-512.onnx (düz model) ve ornekler/videolar/*.mp4 gerekir. Klipler yapay zekâ ile üretilmiştir;
bu sınama modelin gerçek kamera görüntüsündeki başarısını ölçmez. Veri klasörü geçicidir.
Denetlenenler: varsayılan ayarlarla depo ve açık saha kliplerinde "alev", duman klibinde "duman" uyarısı başlar; depo
ve açık sahada ilk saniyede hiçbir uyarı başlamaz; analiz saniyede en çok iki kare yapılır; her olayın karesi ve klibi
yazılır; panel kayıtları veritabanına alır ve klipleri tarayıcıda oynayan biçime çevirir.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kok = Path(__file__).resolve().parent.parent
veri = Path(tempfile.mkdtemp(prefix="yangin_ornekler_"))
os.environ["YANGIN_KAMERA_VERI"] = str(veri)
sys.path.insert(0, str(kok))
sys.path.insert(0, str(kok / "motor"))

import cv2  # noqa: E402

import depo  # noqa: E402
import kuyruk  # noqa: E402
import rapor  # noqa: E402
import yollar  # noqa: E402
from yangin_motor import blok, katalog  # noqa: E402

if not (kok / "motor" / "modeller" / katalog.MODEL_DOSYASI).is_file():
    raise SystemExit("Düz model dosyası yok: motor/modeller/" + katalog.MODEL_DOSYASI)
BEKLENEN = {"depo": "alev", "acik": "alev", "duman": "duman"}  # klip → başlaması gereken kural
kodlar = yollar.ornek_kodlar()
eksik = [k for k in BEKLENEN if k not in kodlar]
if eksik:
    raise SystemExit(f"Örnek video yok: {', '.join(eksik)} (ornekler/videolar)")
yollar.hazirla()
blok.veri_klasoru = lambda: str(veri)  # motor, panelin veri klasörünü Studio'da ayar.json'dan okur
sonuc: list[tuple[str, bool]] = []


def denetle(ad, kosul):
    sonuc.append((ad, bool(kosul)))
    print(("  geçti  " if kosul else "  KALDI  ") + ad, flush=True)


def kos(kod):
    """Klibi blokların sırasıyla işler. Dönüş: (başlayan olaylar [(videodaki an, kayıt)], kare sayısı, analiz sayısı, süre)."""
    vid, algi, kural = {}, {}, {}
    kamera = f"{kod}#sinama"
    baslayan, kare, analizler, t0 = [], 0, set(), time.perf_counter()
    while True:
        fr, zaman, bitti, _ = blok.video(vid, kamera)
        tespit, durum = blok.algila(algi, fr, kamera, zaman)
        cizili, alarm, risk, olaylar, kdurum, yeni, _ = blok.kurallar(kural, fr, tespit, kamera, zaman, bitti)
        if bitti:
            break
        assert not durum.startswith("hata") and not kdurum.startswith("hata"), (durum, kdurum)
        assert cizili is not None and cizili.shape == fr.shape
        analizler.add(json.loads(tespit)["sira"])
        baslayan += [(zaman, o) for o in json.loads(olaylar)]
        assert bool(json.loads(olaylar)) == yeni and (not yeni or alarm)
        kare += 1
    return baslayan, kare, len(analizler), time.perf_counter() - t0


ozetler = {}
for kod in kodlar:
    ayar = json.loads((yollar.AYAR / f"{kod}.json").read_text(encoding="utf-8"))
    print(f"{ayar['ad']} ({kod})")
    baslayan, kare, analiz, sure = kos(kod)
    cap = cv2.VideoCapture(str(yollar.VIDEOLAR / f"{kod}.mp4"))
    uzunluk = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 25)
    cap.release()
    for an, o in baslayan:
        print(f"  {an:5.2f} sn  {o['kural_ad']} (ilk görülme {o['bas']:.1f} sn, risk {o['puan']})")
    print(f"  {kare} kare, {analiz} analiz, {sure:.1f} sn sürdü")
    kurallar_ = {o["kural"] for _, o in baslayan}
    ozetler[kod] = kurallar_
    if kod in BEKLENEN:
        denetle(f"{kod}: \"{katalog.KURAL[BEKLENEN[kod]]['ad']}\" başlar", BEKLENEN[kod] in kurallar_)
    if kod in ("depo", "acik"):
        denetle(f"{kod}: ilk saniyede hiçbir uyarı başlamaz (ne başlangıcı ne ilk görülmesi)", all(an >= 1.0 and o["bas"] >= 1.0 for an, o in baslayan))
    denetle(f"{kod}: saniyede en çok iki kare analiz edilir", analiz <= 2 * uzunluk + 1 and analiz >= uzunluk)

print("Panel: kuyruğun içeri alınması")
yeni = kuyruk.al()
olaylar = depo.sor("SELECT * FROM olay ORDER BY id")
denetle("kuyruk boşaldı, başlayan her olay veritabanında", not list(kuyruk.KLASOR.glob("*.json")) and len(yeni) == len(olaylar) > 0)
denetle("akış bitince bütün olaylar kapandı", all(o["suruyor"] == 0 for o in olaylar) and all(kuyruk.kosu_bitti(k, "sinama") for k in kodlar))
denetle("her olayın karesi yazıldı", all(o["kare"] and (yollar.CIKTI / o["kare"]).is_file() for o in olaylar))
denetle("her olayın klibi tarayıcıda oynayan biçime çevrildi", all(o["klip"] and o["klip"].endswith(".mp4") and not o["klip"].endswith(".ham.mp4")
                                                                    and (yollar.CIKTI / o["klip"]).stat().st_size > 10_000 for o in olaylar))
denetle("yarım (ham) klip kalmadı", not list(yollar.CIKTI.rglob("*.ham.mp4")))
ornek = next(o for o in olaylar if o["kamera"] == "depo" and o["kural"] == "alev")
klip = cv2.VideoCapture(str(yollar.CIKTI / ornek["klip"]))
klip_sn = klip.get(cv2.CAP_PROP_FRAME_COUNT) / (klip.get(cv2.CAP_PROP_FPS) or 1)
klip.release()
denetle(f"depo klibi gerçek hızında (olay {ornek['sure_sn']:.1f} sn, klip {klip_sn:.1f} sn)", ornek["sure_sn"] - 1.5 <= klip_sn <= ornek["sure_sn"] + 4.5)
denetle("olay kaydı: düzey, risk puanı ve örnek işareti", ornek["duzey"] == "kritik" and ornek["ciddi"] == 1 and ornek["puan"] >= 15 and ornek["ornek"] == 1
        and 0 <= ornek["x"] <= 1 and 0 <= ornek["y"] <= 1)
denetle("duman olayı yüksek düzeyde", any(o["kamera"] == "duman" and o["kural"] == "duman" and o["duzey"] == "yuksek" for o in olaylar))
denetle("her kameranın son işaretli karesi var", all((yollar.CIKTI / k / "son_kare.jpg").is_file() for k in kodlar))
ozet = rapor.ozet({"gun": 3650})
analitik = rapor.analitik({"kamera": "depo", "gun": 3650})
denetle("Kontrol Odası özeti olayları sayar", ozet["olay"] == len(olaylar) and ozet["kritik"] == sum(o["ciddi"] for o in olaylar) and ozet["suruyor"] == 0)
denetle("Görsel Analitik: depo için alev ısı haritası dolu", analitik["sayilar"]["alev_sn"] > 0 and sum(map(sum, analitik["izgara"]["alev"])) > 0
        and analitik["son_kare"] and analitik["sayilar"]["olay"] >= 1)
denetle("panel yeni kritik olayı görür (siren)", rapor.son_kritik() == max(o["id"] for o in olaylar if o["duzey"] == "kritik"))
excel = rapor.excel()
denetle("Excel raporu yazılır", excel.is_file() and excel.stat().st_size > 3000)
depo.kapat()

kalan = [ad for ad, ok in sonuc if not ok]
print(f"\n{len(sonuc) - len(kalan)}/{len(sonuc)} denetim geçti" + (f" · kalanlar: {kalan}" if kalan else ""))
sys.exit(1 if kalan else 0)
