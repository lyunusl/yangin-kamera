"""YOLOv4-CSP (darknet cfg + weights) -> ONNX. Kullanım: darknet_onnx.py <cfg> <weights> <cikti.onnx>

Giriş  "goruntu": float32 [1,3,H,W], RGB, 0..1 (kare H x W'ye doğrudan, oran korunmadan boyutlanır; darknet böyle yapar).
Çıkış  "tespit" : float32 [1,N,5+sınıf] = cx, cy, w, h (0..1, kareye oranlı), nesne puanı, sınıf puanları.
Toplu normalleştirme darknet'in çıkarım formülüyle (sqrt(var + 1e-5)) evrişime gömülür.
"""
import sys

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


def cfg_oku(yol):
    bloklar = []
    for satir in open(yol, encoding="utf-8"):
        satir = satir.split("#")[0].strip()
        if not satir:
            continue
        if satir.startswith("["):
            bloklar.append({"tur": satir[1:-1].strip()})
        else:
            k, v = satir.split("=", 1)
            bloklar[-1][k.strip()] = v.strip()
    return bloklar[0], bloklar[1:]


class Ag(nn.Module):
    def __init__(self, cfg, agirlik):
        super().__init__()
        self.net, self.bloklar = cfg_oku(cfg)
        self.W, self.H = int(self.net["width"]), int(self.net["height"])
        veri = np.fromfile(agirlik, dtype=np.uint8)
        maj, mino, _ = np.frombuffer(veri[:12], np.int32)
        bas = 12 + (8 if maj * 10 + mino >= 2 else 4)
        w = np.frombuffer(veri[bas:], np.float32)
        p = 0
        kanal = [int(self.net.get("channels", 3))]
        self.katman = nn.ModuleList()
        for i, b in enumerate(self.bloklar):
            t = b["tur"]
            m = nn.Identity()
            if t == "convolutional":
                n, k, s = int(b["filters"]), int(b["size"]), int(b["stride"])
                g = int(b.get("groups", 1))
                c = kanal[-1]
                m = nn.Conv2d(c, n, k, s, k // 2 if int(b.get("pad", 0)) else 0, groups=g, bias=True)
                bn = int(b.get("batch_normalize", 0))
                if bn:
                    beta, gama, ort, var = (w[p + j * n:p + (j + 1) * n] for j in range(4))
                    p += 4 * n
                else:
                    bias = w[p:p + n]
                    p += n
                adet = n * (c // g) * k * k
                cek = w[p:p + adet].reshape(n, c // g, k, k).astype(np.float64)
                p += adet
                if bn:
                    # darknet çıkarımda fuse_conv_batchnorm kullanır: scales / sqrt(var + 1e-5)
                    olcek = gama.astype(np.float64) / np.sqrt(var.astype(np.float64) + 1e-5)
                    cek = cek * olcek[:, None, None, None]
                    bias = beta.astype(np.float64) - ort.astype(np.float64) * olcek
                m.weight.data = torch.from_numpy(cek.astype(np.float32).copy())
                m.bias.data = torch.from_numpy(np.asarray(bias, np.float32).copy())
                cikis = n
            elif t == "shortcut":
                cikis = kanal[-1]
            elif t == "route":
                kat = [int(x) for x in b["layers"].split(",")]
                kat = [x if x >= 0 else i + x for x in kat]
                b["_kat"] = kat
                assert int(b.get("groups", 1)) == 1
                cikis = sum(kanal[x + 1] for x in kat)
            elif t == "maxpool":
                k, s = int(b["size"]), int(b["stride"])
                assert s == 1, "yalnızca SPP havuzu bekleniyor"
                m = nn.MaxPool2d(k, 1, k // 2)
                cikis = kanal[-1]
            elif t == "upsample":
                cikis = kanal[-1]
            elif t == "yolo":
                assert int(b.get("new_coords", 0)) == 1
                cikis = kanal[-1]
            else:
                raise ValueError(t)
            self.katman.append(m)
            kanal.append(cikis)
        assert p == len(w), (p, len(w))

    def forward(self, x):
        cikti, sonuc = [], []
        for i, (b, m) in enumerate(zip(self.bloklar, self.katman)):
            t = b["tur"]
            if t == "convolutional":
                x = m(x)
                a = b.get("activation", "linear")
                if a == "mish":
                    x = x * torch.tanh(F.softplus(x))
                elif a == "logistic":
                    x = torch.sigmoid(x)
                elif a == "leaky":
                    x = F.leaky_relu(x, 0.1)
                else:
                    assert a == "linear", a
            elif t == "shortcut":
                x = x + cikti[i + int(b["from"])]
            elif t == "route":
                x = torch.cat([cikti[k] for k in b["_kat"]], 1) if len(b["_kat"]) > 1 else cikti[b["_kat"][0]]
            elif t == "maxpool":
                x = m(x)
            elif t == "upsample":
                x = F.interpolate(x, scale_factor=int(b["stride"]), mode="nearest")
            elif t == "yolo":
                maske = [int(v) for v in b["mask"].split(",")]
                capa = np.array([float(v) for v in b["anchors"].split(",")], np.float32).reshape(-1, 2)[maske]
                sinif = int(b["classes"])
                olcek = float(b.get("scale_x_y", 1.0))
                B, _, gh, gw = x.shape
                y = x.view(B, len(maske), 5 + sinif, gh, gw).permute(0, 1, 3, 4, 2)
                gy, gx = torch.meshgrid(torch.arange(gh, dtype=torch.float32), torch.arange(gw, dtype=torch.float32), indexing="ij")
                izgara = torch.stack((gx, gy), -1).view(1, 1, gh, gw, 2)
                xy = (y[..., 0:2] * olcek - 0.5 * (olcek - 1) + izgara) / torch.tensor([gw, gh], dtype=torch.float32)
                c = torch.from_numpy(capa / np.array([self.W, self.H], np.float32)).view(1, len(maske), 1, 1, 2)
                wh = (y[..., 2:4] * 2) ** 2 * c
                sonuc.append(torch.cat((xy, wh, y[..., 4:]), -1).reshape(B, -1, 5 + sinif))
            cikti.append(x)
        return torch.cat(sonuc, 1)


if __name__ == "__main__":
    cfg, agirlik, hedef = sys.argv[1:4]
    ag = Ag(cfg, agirlik).eval()
    ornek = torch.zeros(1, 3, ag.H, ag.W)
    with torch.no_grad():
        print("çıkış", tuple(ag(ornek).shape))
    torch.onnx.export(ag, ornek, hedef, input_names=["goruntu"], output_names=["tespit"], opset_version=17,
                      do_constant_folding=True, dynamo=False)
    import onnx
    m = onnx.load(hedef)
    del m.metadata_props[:]
    m.producer_name, m.producer_version, m.doc_string = "", "", ""
    for ad, deger in (("siniflar", "alev,duman"), ("giris", f"{ag.W}x{ag.H} RGB 0..1")):
        e = m.metadata_props.add()
        e.key, e.value = ad, deger
    onnx.save(m, hedef)
    onnx.checker.check_model(hedef)
    print("yazıldı", hedef)
