"""Alev ve duman tespiti (ONNX): yalnızca numpy, OpenCV ve onnxruntime kullanır.

AugeLab Studio'nun içinde (Yangın Algılama bloğu) ve Studio dışındaki sınamalarda aynı kod çalışır.

Model: girdi `goruntu` float32 [1, 3, 512, 512] (RGB, 0-1; kare 512×512'ye doğrudan, oranı korunmadan küçültülür),
çıktı `tespit` float32 [1, 16128, 7] = cx, cy, w, h (kareye göre 0-1), nesnellik, alev puanı, duman puanı.
Tespitin güveni = nesnellik × sınıf puanı. Sınıf başına NMS (IoU 0,45) uygulanır; eni ya da boyu 6 pikselden küçük
kutular atılır (model sıfır boyutlu, %40 güvenli sahte kutular üretebiliyor).
"""
from __future__ import annotations

import os

import cv2
import numpy as np

SINIFLAR = ("alev", "duman")
GIRDI = 512
NMS_IOU = 0.45
EN_AZ_KENAR = 6.0        # piksel (kare ölçüsünde)
VARSAYILAN_ESIK = {"alev": 0.30, "duman": 0.20}  # katalog.HASSASIYET["orta"] ile aynı


def saglayicilar() -> list[str]:
    """Varsa ekran kartı (DirectML ya da CUDA), yoksa işlemci."""
    import onnxruntime as ort

    var = ort.get_available_providers()
    return [p for p in ("DmlExecutionProvider", "CUDAExecutionProvider") if p in var] + ["CPUExecutionProvider"]


def on_isle(bgr: np.ndarray) -> np.ndarray:
    """Kare → model girdisi."""
    kucuk = cv2.resize(bgr, (GIRDI, GIRDI), interpolation=cv2.INTER_LINEAR)
    return np.ascontiguousarray(kucuk[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0)


def son_isle(y: np.ndarray, W: int, H: int, esik: dict[str, float] | None = None) -> list[dict]:
    """Model çıktısı (aday, 7) → [{"s": "alev" | "duman", "b": [x1, y1, x2, y2], "p": güven}] (kare pikseli)."""
    esik = {**VARSAYILAN_ESIK, **(esik or {})}
    puan = y[:, 5:5 + len(SINIFLAR)] * y[:, 4:5]
    sinif = puan.argmax(1)
    p = puan[np.arange(len(sinif)), sinif]
    out: list[dict] = []
    for i, ad in enumerate(SINIFLAR):
        sec = (sinif == i) & (p >= esik[ad])
        if not sec.any():
            continue
        w, h = y[sec, 2] * W, y[sec, 3] * H
        kutu = np.stack(((y[sec, 0] * W - w / 2), (y[sec, 1] * H - h / 2), w, h), 1)
        guven = p[sec]
        buyuk = (w >= EN_AZ_KENAR) & (h >= EN_AZ_KENAR)
        kutu, guven = kutu[buyuk], guven[buyuk]
        if not len(kutu):
            continue
        kalan = cv2.dnn.NMSBoxes(kutu.tolist(), guven.tolist(), float(esik[ad]), NMS_IOU)
        for j in np.array(kalan).reshape(-1):
            x1, y1, bw, bh = (float(v) for v in kutu[j])
            x2, y2 = min(float(W), x1 + bw), min(float(H), y1 + bh)
            x1, y1 = max(0.0, x1), max(0.0, y1)
            if x2 - x1 < EN_AZ_KENAR or y2 - y1 < EN_AZ_KENAR:  # kare dışına taşan kutunun görünen kısmı çok küçük
                continue
            out.append({"s": ad, "b": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)], "p": round(float(guven[j]), 3)})
    out.sort(key=lambda d: -d["p"])
    return out


class Algilayici:
    """Yangın modelini yükler ve kareleri çalıştırır."""

    def __init__(self, yol: str, veri: str | None = None):
        """`yol`: modelin düz adı (…/yangin-duman-512.onnx); korumalı pakette yanındaki paket girdisi açılır."""
        import onnxruntime as ort

        from .katalog import model_var
        from .model_oturumu import oturum_ac

        if not model_var(yol):
            raise RuntimeError(f"model dosyası yok: {os.path.basename(yol)}")
        self.ad = os.path.basename(yol)
        secenek = ort.SessionOptions()
        secenek.log_severity_level = 3
        secenek.add_session_config_entry("session.intra_op.allow_spinning", "0")  # boştayken işlemciyi meşgul etmesin
        self.oturum = oturum_ac(yol, veri, secenek, saglayicilar(), cpu_yedek=True)
        self.saglayici = self.oturum.get_providers()[0]
        self.girdi = self.oturum.get_inputs()[0].name

    def calistir(self, bgr: np.ndarray, esik: dict[str, float] | None = None) -> list[dict]:
        """Dönüş: [{"s": sınıf, "b": [x1, y1, x2, y2], "p": güven}] (kare pikseli), güveni yüksek olan önce."""
        H, W = bgr.shape[:2]
        y = self.oturum.run(None, {self.girdi: on_isle(bgr)})[0][0]
        return son_isle(y, W, H, esik)

    def ozet(self) -> str:
        return f"{self.ad} ({self.saglayici.replace('ExecutionProvider', '')})"
