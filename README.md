# Yangın Kamera

Yangın Kamera, güvenlik kameralarının ve video kayıtlarının görüntüsünde alev ve duman arar. Gördüğünde uyarı verir; uyarıları, işaretli kareleri ve olay kliplerini bir panelde toplar.

Kamerayla çalışan bir **erken uyarı yardımcısıdır; onaylı yangın algılama ve ihbar sisteminin yerini tutmaz.** Duman dedektörünüzü, yangın ihbar sisteminizi ve söndürme sisteminizi olduğu gibi kullanmaya devam edin.

<p align="center">
  <a href="https://github.com/lyunusl/yangin-kamera/releases/latest/download/YanginKamera-Kurulum-0.1.0.exe">
    <img src="https://img.shields.io/badge/Windows%20i%C3%A7in%20indir-Yang%C4%B1n%20Kamera-C62828?style=for-the-badge&logo=windows&logoColor=white" alt="Windows için Yangın Kamera'yı indir" height="56">
  </a>
  <br>
  <sub>Windows 10/11 (64 bit) · <a href="https://github.com/lyunusl/yangin-kamera/releases/latest">Sürüm notları</a></sub>
</p>

<!-- TODO ekran görüntüsü: Kontrol Odası (kamera karoları ve açık uyarılar). -->

## Neler yapabilirsiniz?

- **Kamera veya video ekleyin.** IP kamera, kayıt cihazı (RTSP ya da ONVIF), HTTP akışı veya video dosyasıyla çalışın.
- **Bölgeleri çizin.** Kritik bölgede (elektrik odası, kimyasal deposu) uyarı daha çabuk çıkar. İzinli ateş bölgesindeki (kaynak tezgâhı, fırın, ocak) alev ve duman sayılmaz.
- **Kuralları ve hassasiyeti seçin.** Her kamera için kuralları açıp kapatın, sürelerini ve hassasiyeti ayarlayın.
- **Uyarıları inceleyin.** Her uyarı işaretli karesi, klibi ve risk puanıyla gelir. Panel açıkken yeni bir kritik uyarıda siren çalar.
- **Takip ve raporlama yapın.** Uyarılardan görev açın, ısı haritasını inceleyin, Excel raporu alın.
- **Çıkışları yapılandırın.** Modbus TCP, OPC UA, MQTT, webhook, Slack / Teams ve e-posta ile uyarıları başka sistemlere iletin.

<!-- TODO ekran görüntüsü: Uyarılar listesi ve bir uyarının klibi. -->

## Neleri algılar?

| Kural | Düzey | Ne zaman uyarır |
|---|---|---|
| Alev algılandı | Kritik | Son 2 saniyede analiz edilen karelerin en az %60'ında alev var |
| Duman algılandı | Yüksek | Son 4 saniyede analiz edilen karelerin en az %60'ında duman var |
| Alev ve duman birlikte | Kritik | Aynı 4 saniyede hem alev hem duman için koşul sağlanıyor (en yüksek risk puanı) |
| Alev büyüyor | Kritik | Alev kutularının toplam alanı 10 saniye içinde en az iki katına çıktı |
| Duman yayılıyor | Yüksek | Duman kutularının toplam alanı 15 saniye içinde en az iki katına çıktı |
| Kritik bölgede alev ya da duman | Kritik | Tespitin merkezi kritik bölgenin içinde; 1 saniyelik pencereyle daha çabuk uyarır |

Kurallar kayan bir zaman penceresinde değerlendirilir: tek bir gürültülü kare uyarı başlatmaz. Koşul sağlanınca olay başlar, birkaç saniye boyunca sağlanmayınca kapanır. Süreler her kamera için değiştirilebilir.

<!-- TODO ekran görüntüsü: Kurallar ekranı. -->

## Nasıl çalışır?

1. Kamera akışını veya video dosyasını ekleyin.
2. İsterseniz görüntü üzerinde kritik ve izinli ateş bölgelerini çizin.
3. Analizi başlatın. Görüntüyü bilgisayarınızdaki **AugeLab Studio** arka planda işler; Studio penceresi açılmaz.
4. Uyarıları, klipleri ve raporları Yangın Kamera panelinde inceleyin.

Programda dört kısa örnek video ve hazır kamera ayarları bulunur. Önce **Ayarlar → Örnek analizi çalıştır** ile paneli deneyebilirsiniz.

## Kurulum

Yukarıdaki **Windows için indir** düğmesiyle kurulum dosyasını indirip çalıştırın. Kurulum adım adım ilerler:

1. **Yangın Kamera** bu kullanıcı için kurulur (yönetici izni gerekmez).
2. **AugeLab Studio** kurulu değilse resmî kurulum dosyası indirilir, doğrulanır ve sessizce kurulur. Visual C++ bileşeni eksikse Microsoft'tan kurulur; Windows izin sorabilir.
3. **AugeLab hesabı**: hesabınız yoksa düğmeyle tarayıcıda oluşturun.
4. **Lisans kodu**: hesabınızdaki lisans kodunu yapıştırın. Kod, Studio penceresi açılmadan Studio'ya kaydedilir; Yangın Kamera onu saklamaz.

Kurulum bitince Yangın Kamera açılır ve panel tarayıcınızda görünür (`http://127.0.0.1:8790`). Studio'nun hazır olduğu kısa bir arka plan denemesiyle doğrulanır. Bir adımı atladıysanız paneldeki kurulum sihirbazı aynı adımları gösterir.

Analiz, arayüzsüz kullanıma izin veren etkin bir AugeLab Studio lisansıyla çalışır. Programla gelen model paketi korumalıdır: yalnızca AugeLab Studio'nun içinde, etkin lisansla açılır. İlk kurulum ve lisans etkinleştirme için internet gerekir.

## Kamera ve veri

ONVIF destekli cihazlar ağda aranabilir, kayıt cihazlarındaki kanallar ayrı kameralar olarak eklenebilir. RTSP adresi elle de girilebilir. Kamera şifresi ayar dosyasına kaydedilmez.

Analiz bilgisayarınızda yapılır; görüntü internete gönderilmez. Olay kareleri ve klipleri bu bilgisayarda saklanır. **Görüntülerde kişiler gizlenmez**: kareler ve klipler kamerada ne görünüyorsa onu içerir. Tanımladığınız çıkışlara yalnızca olayın metin bilgileri gider, görüntü gitmez. Ağ erişimini açarsanız, API anahtarını bilen sistemler olay karelerini ve kliplerini de okuyabilir.

## Sınırlar ve test durumu

- **Onaylı yangın algılama sisteminin yerini tutmaz.** Kamera görmediğini algılayamaz: görüş alanı dışındaki, bir engelin arkasındaki ya da çok küçük görünen alev ve duman kaçar. Güneş yansıması, sıcak lamba, buhar, toz ve sis yanlış uyarı verebilir.
- Model gerçek fabrikalarda çalışıyor; gerçek alev ve dumanla test edildi. Bu depodaki sınama görselleri ve dört örnek klip ise yapay zekâ ile üretildi; modelin bu uygulamada kullanılan ONNX çevirisi yalnızca bunlarla karşılaştırıldı. Kendi kameranızda birkaç gün izleyip yanlış ve kaçan uyarıları kontrol edin.
- Kurallar yapay tespit dizileriyle sınandı. "Alev büyüyor" ve "Duman yayılıyor" deneyseldir: modelin kutu alanı gerçek görüntüde ölçülmedi.
- Analiz işlemcide saniyede yaklaşık **iki kare** yapılır (hızlı bir masaüstünde kare başına yaklaşık 0,25 saniye). Uyarı, alev ya da duman göründükten en erken bir-iki saniye sonra çıkar.
- Model, alevi bazen sıfır boyutlu kutularla bildirir; bunlar atılır. Böyle karelerde alev sayılmayabilir.
- Aynı anda bir kamera izlenir. USB kamera desteklenmez.
- Gerçek IP kamera, ONVIF cihazı ve kayıt cihazıyla uçtan uca test yapılmadı; ONVIF akışı yerel bir test cihazıyla sınandı. Kurulum temiz bir Windows ortamında (Windows Sandbox) iki durumda denendi: AugeLab Studio kurulu değilken ve önceden kuruluyken. İkisinde de lisans kabul edildi, panel açıldı ve dört örnek klip Studio penceresi açılmadan analiz edildi.
- Bildirim ve kontrol çıkışları ikaz ve entegrasyon içindir. Emniyet durdurması ya da söndürme tetiklemesi olarak kullanılmaz.

## Kaynak koddan geliştirme

Python 3.12 ve Windows x64 üzerinde, proje klasöründe ortamı hazırlayın.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install --target motor\deps --no-deps onnxruntime==1.31.1
New-Item -ItemType Directory -Force motor\modeller | Out-Null
Invoke-WebRequest https://github.com/lyunusl/yangin-kamera/releases/latest/download/yangin-duman-512.onnx.isgm -OutFile kurulum\community-modeller\yangin-duman-512.onnx.isgm
Copy-Item kurulum\community-modeller\* motor\modeller\
.venv\Scripts\python uygulama.py
```

Panel `http://127.0.0.1:8790` adresinde açılır. AugeLab Studio kurulu ve lisanslı olmalıdır; panel Studio'yu açmaz, her kamera için `python -m studio run` ile arka planda çalıştırır. Korumalı model paketi `kurulum\community-modeller` klasöründedir; şifreli model dosyası (`yangin-duman-512.onnx.isgm`, 210 MB) GitHub'ın dosya sınırını aştığı için depoda değil, sürüm dosyaları arasındadır ve yukarıdaki komutla indirilir. Panel modeli hiç yüklemez; model yalnızca Studio'nun içinde, etkin lisansla açılır.

Çalıştırılan hazır sahne (`kurulum\sahne\yangin-kamera.pmod`) depoda yoktur, çünkü Studio sahne dosyalarını şifreli kaydeder ve kaydetme yalnızca Studio penceresinden yapılır. Bir kez üretilir:

1. Studio'yu açın. MCP `127.0.0.1:8765` adresinde açık olmalıdır.
2. `.venv\Scripts\python kurulum\sablon.py` çalıştırın. Yangın bloklarını Studio'ya kaydeder ve sahneyi yeni bir sekmede kurar: Yangın Video → Yangın Algılama → Yangın Kurallar.
3. Studio'da açılan sekmeyi **Dosya → Farklı Kaydet** ile `kurulum\sahne\yangin-kamera.pmod` olarak kaydedin.

Sınamalar `egitim` klasöründedir (`requirements-gelistirme.txt` gerekir) ve Studio olmadan çalışır:

```powershell
.venv\Scripts\python -m pip install -r requirements-gelistirme.txt
.venv\Scripts\python egitim\dene_kurallar.py
```

`dene_model.py` ve `dene_ornekler.py` düz modeli ister. EXE ve Windows kurulum dosyası PyInstaller ve Inno Setup ile `kurulum\derle.cmd` çalıştırılarak oluşturulur; hazır sahne ya da korumalı model paketi yoksa derleme durur.

## Lisans ve kaynaklar

Yangın Kamera'nın kodu GNU AGPL-3.0 lisanslıdır. AugeLab Studio ayrı lisanslı bir üründür. Alev ve duman modeli: AugeLab Marketplace "Fire & Smoke Detection AI Model" (YOLOv4-CSP). [Uygulama lisansı](LICENSE) · [Atıflar](ATIFLAR.md)
