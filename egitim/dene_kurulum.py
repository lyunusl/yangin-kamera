"""Studio kurulum sözleşmesini gerçek kurucu çalıştırmadan sınar.

  python egitim/dene_kurulum.py

Akış: resmî kurucuyu indir ve SHA-256 ile doğrula → Visual C++ yoksa Microsoft'tan indir, imzasını
doğrula, kur → Studio'yu sessizce kur, olmazsa resmî kurulum penceresini aç. Studio penceresi açılmaz (Yangın Kamera Studio'yu
arayüzsüz kullanır); lisans kodu Studio'nun kendi komutuyla (studio verify) arayüzsüz kaydedilir.
Algılama modeli: kurulum dosyası ve panel aynı adres ve özetle indirir; indirme yerel bir HTTP sunucusuyla sınanır
(doğru dosya, özeti tutmayan dosya, HTML sayfası, yarım kalan indirme).
"""
import hashlib
import io
import os
import ssl
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from urllib.error import URLError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import studio_kurulum as kurulum


def yanit(icerik: bytes):
    """urlopen yanıtı gibi: okunur, bağlam yöneticisidir ve başlık taşır."""
    y = io.BytesIO(icerik)
    y.headers = {"Content-Length": str(len(icerik))}
    return y


@unittest.skipUnless(os.name == "nt", "Windows kurulum senaryosu")
class StudioKurulumTesti(unittest.TestCase):
    def setUp(self):
        gecici = self.enterContext(tempfile.TemporaryDirectory())
        self.veri = Path(gecici) / "veri"
        self.hedef = Path(gecici) / "Programlar" / "Studio"
        self.studio = self.hedef / kurulum.EXE
        self.is_ = SimpleNamespace(dur=threading.Event())
        self.enterContext(patch.dict(os.environ, {"PROCESSOR_ARCHITEW6432": "AMD64"}))
        self.enterContext(patch.object(kurulum.yollar, "VERI", self.veri))
        self.enterContext(patch.object(kurulum, "varsayilan_klasor", return_value=self.hedef))
        self.enterContext(patch.object(kurulum, "kurulu_studio", side_effect=self._bul))
        self.enterContext(patch.object(kurulum, "_kurulumu_bekle", side_effect=lambda *a: self._bul()))
        self.enterContext(patch.object(kurulum.time, "sleep"))
        self.enterContext(patch.object(kurulum, "studio_calisiyor", return_value=False))
        self.vc_var = True
        self.enterContext(patch.object(kurulum, "vc_kurulu", side_effect=lambda: self.vc_var))
        self.imza = self.enterContext(patch.object(kurulum, "microsoft_imzali", return_value=True))
        self.indir = self.enterContext(patch.object(kurulum.urllib.request, "urlopen"))
        self.calistir = self.enterContext(patch.object(kurulum, "_harici_program"))
        self.izinle = self.enterContext(patch.object(kurulum, "_izinle_calistir"))
        self.icerik = b"MZ test icin kurulum paketi"
        self.vc_icerik = b"MZ test icin visual c++ paketi"
        self.gercek_sha = kurulum.KURULUM_SHA256
        self.enterContext(patch.object(kurulum, "KURULUM_SHA256", hashlib.sha256(self.icerik).hexdigest()))
        self.indir.side_effect = lambda istek, **kw: yanit(self.vc_icerik if istek.full_url == kurulum.VC_URL else self.icerik)
        kurulum.DURUM.update(asama="bos", hata="")

    def _bul(self):
        return kurulum._studio_exe(self.hedef)

    def _studio_olustur(self, *_a, **_kw):
        self.hedef.mkdir(parents=True, exist_ok=True)
        self.studio.touch()
        python = self.hedef / "Python"
        paket = python / "Lib" / "site-packages" / "studio"
        paket.mkdir(parents=True, exist_ok=True)
        (python / "pythonw.exe").touch()
        (paket / "__init__.py").touch()
        return 0

    def _indirilenler(self):
        return [c.args[0].full_url for c in self.indir.call_args_list]

    def test_var_olan_kurulum_korunur(self):
        self._studio_olustur()
        self.assertEqual(kurulum.kur(self.is_), {"kurulu": True})
        self.indir.assert_not_called()
        self.izinle.assert_not_called()
        self.calistir.assert_not_called()  # Studio penceresi açılmaz

    def test_ilk_kurulum_sessiz_ve_pencere_acmaz(self):
        self.izinle.side_effect = self._studio_olustur
        self.assertEqual(kurulum.kur(self.is_), {"kurulu": True})
        self.assertEqual(self._indirilenler(), [kurulum.KURULUM_URL])
        tls = self.indir.call_args.kwargs["context"]
        self.assertTrue(tls.check_hostname)
        self.assertEqual(tls.verify_mode, ssl.CERT_REQUIRED)
        kurucu, parametre = self.izinle.call_args.args[:2]
        self.assertEqual(kurucu.parent, self.veri / "kurulum")
        self.assertIn("--silent", parametre)
        self.assertIn(f'--install-dir "{self.hedef}"', parametre)
        self.calistir.assert_not_called()  # ne kurulum penceresi ne Studio penceresi açıldı
        self.assertEqual(kurulum.DURUM["asama"], "bos")
        self.assertFalse(hasattr(kurulum, "ac"))

    def test_sessiz_kurulum_olmazsa_resmi_pencere_acilir(self):
        self.izinle.return_value = 1603
        pencere = MagicMock()
        pencere.__enter__.return_value = pencere
        pencere.wait.side_effect = self._studio_olustur
        self.calistir.return_value = pencere
        self.assertEqual(kurulum.kur(self.is_), {"kurulu": True})
        cagrilar = self.calistir.call_args_list
        self.assertEqual(len(cagrilar), 1)  # yalnızca resmî kurulum penceresi; Studio başlatılmadı
        self.assertEqual(cagrilar[0].kwargs, {"cwd": self.veri / "kurulum"})

    def test_visual_cpp_yoksa_imzasi_dogrulanip_kurulur(self):
        self.vc_var = False

        def calistir(program, parametre="", **kw):
            if program.name == "vc_redist.x64.exe":
                self.assertEqual(parametre, "/install /passive /norestart")
                self.vc_var = True
                return 3010  # yeniden başlatma gerekebilir: başarı sayılır
            return self._studio_olustur()

        self.izinle.side_effect = calistir
        self.assertEqual(kurulum.kur(self.is_), {"kurulu": True})
        self.assertEqual(self._indirilenler(), [kurulum.KURULUM_URL, kurulum.VC_URL])
        self.imza.assert_called_once()
        self.assertEqual([c.args[0].name for c in self.izinle.call_args_list][0], "vc_redist.x64.exe")

    def test_imzasi_dogrulanmayan_visual_cpp_calistirilmaz(self):
        self.vc_var = False
        self.imza.return_value = False
        with self.assertRaisesRegex(SystemExit, "Microsoft imzası doğrulanamadı"):
            kurulum.kur(self.is_)
        self.izinle.assert_not_called()
        self.calistir.assert_not_called()
        self.assertFalse((self.veri / "kurulum" / "vc_redist.x64.exe").exists())
        self.assertEqual(kurulum.DURUM["asama"], "hata")

    def test_windows_izni_verilmezse_anlasilir_hata(self):
        self.vc_var = False
        self.izinle.side_effect = OSError(None, "iptal", None, 1223)
        with self.assertRaisesRegex(SystemExit, "Windows izni verilmedi"):
            kurulum.kur(self.is_)

    def test_eksik_kurulumun_uzerine_yazilmaz(self):
        self.hedef.mkdir(parents=True)
        self.studio.touch()
        (self.hedef / "korunacak.txt").touch()
        with self.assertRaisesRegex(SystemExit, "klasörü dolu"):
            kurulum.kur(self.is_)
        self.indir.assert_not_called()
        self.calistir.assert_not_called()

    def test_dogrulanmamis_paket_calistirilmaz(self):
        self.indir.side_effect = lambda *a, **kw: yanit(b"MZ gecersiz")
        with self.assertRaisesRegex(SystemExit, "doğrulaması başarısız"):
            kurulum.kur(self.is_)
        self.izinle.assert_not_called()
        self.calistir.assert_not_called()
        self.assertFalse(list((self.veri / "kurulum").iterdir()))

    def test_exe_olmayan_indirme_calistirilmaz(self):
        self.indir.side_effect = lambda *a, **kw: yanit(b"<html>hata sayfasi</html>")
        with self.assertRaisesRegex(SystemExit, "eksik ya da bozuk"):
            kurulum.kur(self.is_)
        self.izinle.assert_not_called()

    def test_kurucu_basari_donse_bile_studio_yoksa_hata(self):
        self.izinle.return_value = 0
        self.calistir.return_value.__enter__.return_value.wait.return_value = 0
        with self.assertRaisesRegex(SystemExit, "kurulumu tamamlanmadı veya bulunamadı"):
            kurulum.kur(self.is_)
        self.calistir.assert_called_once()  # sessiz kurulum Studio bırakmadı: resmî pencere açıldı, yine yok
        self.assertEqual(kurulum.DURUM["asama"], "hata")

    def test_gecersiz_tls_ile_kurucu_calistirilmaz(self):
        self.indir.side_effect = URLError(ssl.SSLCertVerificationError("sertifika"))
        with self.assertRaisesRegex(SystemExit, "TLS sertifikası doğrulanamadı"):
            kurulum.kur(self.is_)
        self.izinle.assert_not_called()
        self.calistir.assert_not_called()

    def test_kurulumdan_sonra_acilan_studio_kapatilir(self):
        self.izinle.side_effect = self._studio_olustur
        kurulum.studio_calisiyor.return_value = True
        with patch.object(kurulum.subprocess, "run") as calistir:
            self.assertEqual(kurulum.kur(self.is_), {"kurulu": True})
        self.assertEqual(calistir.call_args.args[0][:3], ["taskkill", "/IM", kurulum.EXE])

    def test_lisans_kodu_arayuzsuz_kaydedilir_ve_saklanmaz(self):
        self._studio_olustur()
        kod = "ABCD-1234-EFGH-5678"
        with patch.object(kurulum.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")) as calistir:
            kurulum.lisans_kaydet(" " + kod + "\n")
        komut = calistir.call_args.args[0]
        self.assertEqual(komut[0], str(self.hedef / "Python" / "python.exe"))
        self.assertEqual(komut[1:], ["-c", kurulum.VERIFY])
        self.assertNotIn(kod, " ".join(komut))  # kod komut satırında görünmez
        self.assertEqual(calistir.call_args.kwargs["env"]["YANGIN_LISANS_KODU"], kod)
        self.assertNotIn(kod, "".join(str(p) for p in self.veri.rglob("*")) if self.veri.exists() else "")

    def test_reddedilen_lisans_kodu_hata_metninde_gorunmez(self):
        self._studio_olustur()
        kod = "GECERSIZ-KOD-9999"
        cikti = SimpleNamespace(returncode=1, stdout="", stderr=f"Verification failed for {kod}: invalid code")
        with patch.object(kurulum.subprocess, "run", return_value=cikti):
            with self.assertRaises(SystemExit) as h:
                kurulum.lisans_kaydet(kod)
        self.assertNotIn(kod, str(h.exception.code))
        self.assertIn("kaydedilemedi", str(h.exception.code))

    def test_bicimsiz_lisans_kodu_studioya_verilmez(self):
        self._studio_olustur()
        with patch.object(kurulum.subprocess, "run") as calistir:
            for kod in ("", "kisa", "iki kelime kod", "--help"):
                with self.assertRaisesRegex(SystemExit, "geçersiz"):
                    kurulum.lisans_kaydet(kod)
        calistir.assert_not_called()

    def test_kurulum_dosyasi_ayni_studio_kurucusunu_kullanir(self):
        import re

        iss = (Path(__file__).resolve().parent.parent / "kurulum" / "YanginKamera.iss").read_text(encoding="utf-8")
        tanim = dict(re.findall(r'^#define (\w+) "([^"]*)"', iss, flags=re.M))
        self.assertEqual(tanim["StudioUrl"], kurulum.KURULUM_URL)
        self.assertEqual(tanim["StudioSha256"], self.gercek_sha)
        self.assertEqual(tanim["VcUrl"], kurulum.VC_URL)
        self.assertEqual(tanim["HesapUrl"], kurulum.HESAP_URL)
        self.assertEqual(tanim["StudioExe"], kurulum.EXE)

    def test_durum_paneli_icin(self):
        d = kurulum.durum()
        self.assertEqual(set(d), {"asama", "ne", "indirilen", "toplam", "hata", "gecen", "calisiyor"})


KOK = Path(__file__).resolve().parent.parent


class ModelSozlesmesiTesti(unittest.TestCase):
    """Kurulum dosyası ve panel aynı model dosyasını, aynı adresten, aynı doğrulamayla indirir."""

    def test_kurulum_dosyasi_ayni_modeli_indirir(self):
        import re

        iss = (KOK / "kurulum" / "YanginKamera.iss").read_text(encoding="utf-8")
        tanim = dict(re.findall(r'^#define (\w+) "([^"]*)"\s*$', iss, flags=re.M))
        self.assertEqual(tanim["ModelAdi"], kurulum.MODEL_ADI)
        self.assertEqual(int(tanim["ModelBoyut"]), kurulum.MODEL_BOYUT)
        self.assertEqual(tanim["ModelSha256"], kurulum.MODEL_SHA256)
        self.assertEqual(tanim["ModelDriveKimligi"], kurulum.MODEL_DRIVE_KIMLIGI)
        # ModelUrl ISPP ifadesidir ("..." + ModelDriveKimligi + "..."): parçaları birleştirilir
        ifade = re.search(r"^#define ModelUrl (.+)$", iss, flags=re.M).group(1)
        parcalar = [p.strip() for p in ifade.split("+")]
        url = "".join(p[1:-1] if p.startswith('"') else tanim[p] for p in parcalar)
        self.assertEqual(url, kurulum.MODEL_URL)
        self.assertEqual(kurulum.MODEL_URL, "https://drive.usercontent.google.com/download?id="
                         f"{kurulum.MODEL_DRIVE_KIMLIGI}&export=download&confirm=t")
        self.assertEqual(iss.count(f'"{kurulum.MODEL_DRIVE_KIMLIGI}"'), 1)  # kimlik .iss'te tek yerde
        self.assertRegex(kurulum.MODEL_SHA256, r"^[0-9a-f]{64}$")

    def test_sabitler_yerel_model_dosyasina_uyar(self):
        dosyalar = sorted((KOK / "kurulum" / "community-modeller").glob("*.isgm"))
        if not dosyalar:
            self.skipTest("yerel model paketi yok (kurulum/community-modeller)")
        dosya = KOK / "kurulum" / "community-modeller" / kurulum.MODEL_ADI
        self.assertTrue(dosya.is_file(), f"{kurulum.MODEL_ADI} yok")
        self.assertEqual(dosya.stat().st_size, kurulum.MODEL_BOYUT)
        with dosya.open("rb") as f:
            self.assertEqual(hashlib.file_digest(f, "sha256").hexdigest(), kurulum.MODEL_SHA256)

    def test_paket_exe_ye_buyuk_modeli_koymaz(self):
        spec = (KOK / "kurulum" / "YanginKamera.spec").read_text(encoding="utf-8")
        self.assertIn("[isaret, dll]]", spec)
        self.assertNotIn("[isaret, dll, *modeller]", spec)
        self.assertIn('"__pycache__" not in ad', spec)


class Sunucu:
    """Yerel HTTP sunucusu: her istekte `self.govde` döner; `self.kes` verilirse o kadar bayttan sonra bağlantıyı keser."""

    def __init__(self):
        import http.server

        dis = self

        class Isleyici(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                dis.istekler.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", dis.tur)
                if dis.uzunluk is not False:
                    self.send_header("Content-Length", str(len(dis.govde) if dis.uzunluk is None else dis.uzunluk))
                self.end_headers()
                self.wfile.write(dis.govde if dis.kes is None else dis.govde[:dis.kes])
                self.wfile.flush()
                self.close_connection = True

            def log_message(self, *a):
                pass

        self.govde, self.tur, self.kes, self.uzunluk, self.istekler = b"", "application/octet-stream", None, None, []
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Isleyici)
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.sunucu.server_address[1]}/download?id=DENEME&export=download&confirm=t"

    def kapat(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()


class ModelIndirmeTesti(unittest.TestCase):
    """studio_kurulum.model_indir: yerel sunucudan indirme, boyut ve SHA-256 doğrulaması, yarım dosya bırakmama."""

    def setUp(self):
        self.klasor = Path(self.enterContext(tempfile.TemporaryDirectory())) / "modeller"
        self.icerik = os.urandom(700_000)  # birkaç parçalık (256 KB) gerçek akış
        self.sunucu = Sunucu()
        self.addCleanup(self.sunucu.kapat)
        self.sunucu.govde = self.icerik
        self.enterContext(patch.object(kurulum.yollar, "MODELLER", self.klasor))
        self.enterContext(patch.object(kurulum, "MODEL_URL", self.sunucu.url))
        self.enterContext(patch.object(kurulum, "MODEL_BOYUT", len(self.icerik)))
        self.enterContext(patch.object(kurulum, "MODEL_SHA256", hashlib.sha256(self.icerik).hexdigest()))
        kurulum.MODEL_DURUM.update(asama="bos", indirilen=0, toplam=0, hata="")
        self.hedef = self.klasor / kurulum.MODEL_ADI

    def _kalanlar(self):
        return sorted(p.name for p in self.klasor.iterdir()) if self.klasor.exists() else []

    def test_dogru_dosya_indirilir_ve_yerine_konur(self):
        self.assertTrue(kurulum.model_indir())
        self.assertEqual(self.hedef.read_bytes(), self.icerik)
        self.assertEqual(self._kalanlar(), [kurulum.MODEL_ADI])  # .yeni kalmaz
        self.assertEqual(kurulum.MODEL_DURUM["indirilen"], len(self.icerik))
        self.assertEqual(kurulum.MODEL_DURUM["asama"], "bos")
        self.assertTrue(kurulum.model_indirildi())
        self.assertEqual(self.sunucu.istekler, ["/download?id=DENEME&export=download&confirm=t"])

    def test_ozeti_tutmayan_dosya_reddedilir(self):
        bozuk = bytearray(self.icerik)
        bozuk[len(bozuk) // 2] ^= 0xFF  # aynı boyut, farklı içerik
        self.sunucu.govde = bytes(bozuk)
        with self.assertRaisesRegex(SystemExit, "SHA-256"):
            kurulum.model_indir()
        self.assertEqual(self._kalanlar(), [])

    def test_html_sayfasi_reddedilir(self):
        self.sunucu.govde, self.sunucu.tur = b"<!DOCTYPE html><html><body>Google Drive - kota asildi</body></html>", "text/html"
        with self.assertRaisesRegex(SystemExit, "uyarı sayfası"):
            kurulum.model_indir()
        self.assertEqual(self._kalanlar(), [])
        self.sunucu.uzunluk = False  # boyut başlığı olmadan da: içerik boyutu ve özeti tutmaz
        with self.assertRaisesRegex(SystemExit, "uyarı sayfası"):
            kurulum.model_indir()
        self.assertEqual(self._kalanlar(), [])

    def test_yarim_kalan_indirme_reddedilir_ve_eski_dosya_korunur(self):
        self.klasor.mkdir(parents=True)
        self.hedef.write_bytes(b"onceki")  # boyutu yanlış eski dosya: indirme başarısızsa yerinde kalır
        self.sunucu.kes = len(self.icerik) // 3  # başlık tam boyutu söyler, bağlantı erken kapanır
        with self.assertRaises(SystemExit):
            kurulum.model_indir()
        self.assertEqual(self.hedef.read_bytes(), b"onceki")
        self.assertEqual(self._kalanlar(), [kurulum.MODEL_ADI])
        self.assertFalse(kurulum.model_indirildi())

    def test_durdurulan_indirme_dosya_birakmaz(self):
        dur = threading.Event()
        dur.set()
        self.assertFalse(kurulum.model_indir(dur))
        self.assertEqual(self._kalanlar(), [])

    def test_panel_indirmeyi_arka_planda_baslatir_ve_hatayi_gosterir(self):
        self.klasor.mkdir(parents=True)
        self.assertEqual(kurulum.model_indirmeyi_baslat(), (False, "Algılama modeli zaten yerinde."))  # işaret yok: düz model
        (self.klasor / kurulum.MODEL_ISARETI).write_text("{}", encoding="ascii")
        self.assertTrue(kurulum.model_durumu()["eksik"])
        self.sunucu.govde = b"<html>yok</html>"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(kurulum.model_indirmeyi_baslat()[0], True)
            self._bekle()
        d = kurulum.model_durumu()
        self.assertEqual((d["asama"], d["eksik"]), ("hata", True))
        self.assertIn("uyarı sayfası", d["hata"])
        self.sunucu.govde = self.icerik  # Yeniden dene
        with redirect_stdout(io.StringIO()):
            self.assertEqual(kurulum.model_indirmeyi_baslat(), (True, ""))
            self._bekle()
        self.assertEqual((kurulum.model_durumu()["asama"], kurulum.model_durumu()["eksik"]), ("bos", False))
        self.assertEqual(kurulum.model_indirmeyi_baslat(), (False, "Algılama modeli zaten yerinde."))

    def _bekle(self):
        for t in threading.enumerate():
            if t.name == "model-indirme":
                t.join(30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
