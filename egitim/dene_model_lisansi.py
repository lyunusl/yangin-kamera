"""Korumalı model paketinin oturum mantığını (motor/yangin_motor/model_oturumu.py) gerçek paket ve Studio olmadan sınar.

  python egitim/dene_model_lisansi.py

Paketin kendisi (şifreli model ve bileşeni) yalnızca AugeLab Studio'nun içinde, etkin lisansla açılır; burada bileşen
sahte işlevlerle değiştirilir. Denetlenenler: lisansın oturum açıkken düzenli aralıkla yeniden denetlenmesi, geçici okuma
hatasının bir süre hoş görülmesi, lisans yoksa oturumun kapanması, klasördeki paket işaretinin düz modele üstün gelmesi.
"""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

KOK = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(KOK), str(KOK / "motor")]
from yangin_motor import community_model, katalog, model_lisans as ml, model_oturumu as mo


class ModelLisansTest(unittest.TestCase):
    def test_community_denetimi_ve_gecici_lisans_okuma_hatasi(self):
        kutuphane = Path("goruntu-test.dll")
        simdi = 0.0
        hata_kodu = 0

        def yetki(_):
            mo.community_model._denetle(hata_kodu)

        class Model:
            def run(self):
                return "tespit"

        with (patch.object(mo.time, "monotonic", side_effect=lambda: simdi),
              patch.object(mo._LisansliOturum, "_zamanla"),
              patch.object(mo.community_model, "model_mi", return_value=True),
              patch.object(mo.community_model, "ac", return_value=(b"model", kutuphane)) as ac,
              patch.object(mo.community_model, "yetki", side_effect=yetki) as kontrol,
              patch.object(mo, "_onnx", return_value=Model())):
            oturum = mo.oturum_ac("model.onnx", None, None, [])
            ac.assert_called_once()
            for simdi in range(60):
                self.assertEqual(oturum.run(), "tespit")
            kontrol.assert_not_called()

            hata_kodu = 3
            for simdi in (60.0, 61.0, 64.0):
                self.assertEqual(oturum.run(), "tespit")
            kontrol.assert_called_once_with(kutuphane)
            hata_kodu, simdi = 0, 65.0
            self.assertEqual(oturum.run(), "tespit")
            simdi = 124.0
            self.assertEqual(oturum.run(), "tespit")
            self.assertEqual(kontrol.call_count, 2)

            hata_kodu = 3
            for simdi in (125.0, 130.0, 135.0, 139.0):
                self.assertEqual(oturum.run(), "tespit")
            simdi = 140.0
            with self.assertRaises(mo.community_model.StudioLisansOkumaHatasi):
                oturum.run()
            self.assertIsNone(oturum._oturum)

            self.assertEqual(oturum.run(), "tespit")
            self.assertEqual(ac.call_count, 2)  # Yeni model yüklenirken DLL yetkiyi yeniden denetler.
            hata_kodu, simdi = 4, 200.0
            with self.assertRaisesRegex(ml.LisansHatasi, "etkin bir lisans"):
                oturum.run()
            self.assertIsNone(oturum._oturum)

    def test_paket_isareti_duz_modele_ustun_gelir(self):
        with TemporaryDirectory(prefix="yangin-paket-sinama-") as gecici:
            klasor = Path(gecici)
            yol = klasor / katalog.MODEL_DOSYASI
            self.assertFalse(katalog.model_var(str(yol)))
            self.assertEqual(katalog.model_kilidi(str(klasor)), {"sifreli": False, "durum": "duz"})
            yol.write_bytes(b"duz model")
            self.assertTrue(katalog.model_var(str(yol)))
            self.assertFalse(community_model.model_mi(yol))
            # paket işareti varsa düz dosya sayılmaz: paket girdisi aranır, yoksa paket "bozuk" görünür
            (klasor / community_model.ISARET).write_text('{"id": "' + "ab" * 16 + '", "fixture": true}', encoding="ascii")
            self.assertTrue(community_model.model_mi(yol))
            self.assertFalse(katalog.model_var(str(yol)))
            self.assertEqual(katalog.model_kilidi(str(klasor))["durum"], "bozuk")
            with self.assertRaises(ml.LisansHatasi):  # girdi yok: düz modele dönülmez
                mo.oturum_ac(str(yol), None, None, [])

    def test_paket_boyut_siniri(self):
        self.assertEqual(community_model.SINIR, 512 * 1024 * 1024 + community_model.BASLIK + community_model.ETIKET)


if __name__ == "__main__":
    unittest.main()

