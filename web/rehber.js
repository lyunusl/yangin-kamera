'use strict';
/* Tanıtım turu: ilk açılışta kendiliğinden başlar, sol şeritteki "Tur" düğmesiyle yeniden açılır.
   Her adım bir ekrana gider, ilgili öğeyi vurgular ve ne işe yaradığını anlatır. Tur açıkken sayfaya tıklanamaz:
   hiçbir ayar değişmez, hiçbir analiz başlamaz. uyg.js'teki S, IS, konum, git ve h kullanılır. */

const REHBER_ANAHTARI = 'yangin-rehber-goruldu';
const R = { acik: false, i: 0, hedef: null, kaydirildi: false, zamanlayici: null, oncekiOdak: null };
const REHBER_ARKA = ['#ray', '#sayfa', '#katman'];  // tur açıkken etkisiz kılınan bölümler (tıklama ve odak almaz)

/* Tur, varsa ilk kameranın ayar sayfasını gösterir (bölgeler ve kurallar dolu görünsün); kamera yoksa boş "Kamera ekle" formunu. */
const rehberKamera = () => 'kamera/' + ((S.durum?.kameralar || [])[0]?.kod || 'yeni');

/* yol: gidilecek ekran (yazılmazsa bulunulan ekran) · hedef: vurgulanacak öğe: seçici ya da öğeyi veren işlev
   (sırayla denenir; hiçbiri yoksa kart ortada durur) */
const REHBER_ADIMLARI = [
  { baslik: 'Yangın Kamera\'ya hoş geldiniz',
    metin: 'Yangın Kamera, kamera görüntüsünde alev ve duman arar ve görünce uyarır. Kamerayla çalışan bir erken uyarı yardımcısıdır; onaylı yangın algılama sisteminin yerini tutmaz. Tur sırasında hiçbir ayar değişmez.' },
  { yol: '', hedef: ['#sayfa .kameralar', '#sayfa .bos-durum', '#sayfa .ust'], baslik: 'Kontrol Odası',
    metin: 'Her karo bir kameranın son işaretli karesidir. Alev ya da duman sürerken karo "Alarm" olur.' },
  { hedef: ['#ray a[data-is="ses"]'], baslik: 'Siren',
    metin: 'Panel açıkken yeni bir kritik uyarı gelirse siren çalar. Bu düğme sireni kapatır ve açar.' },
  { yol: 'uyarilar', hedef: ['#sayfa .uyari', '#sayfa .liste', '#sayfa .ust'], baslik: 'Uyarılar',
    metin: 'Her uyarı klibi, karesi ve risk puanıyla gelir. Üstlenebilir, çözüldü ya da yanlış alarm diye işaretleyebilirsiniz.' },
  { yol: 'analitik', hedef: ['#sayfa .sahne', '#sayfa .ust'], baslik: 'Görsel Analitik',
    metin: 'Isı haritası, alevin ve dumanın görüntüde en çok nerede görüldüğünü gösterir.' },
  { yol: 'ayarlar', hedef: ['button[data-is="ornek"]', 'a[href="#/kamera/yeni"]', '#a-kameralar'], baslik: 'Başlamak',
    metin: 'Örnek analiz, programla gelen kısa klipleri işler. Kendi kameranız için "Kamera ekle"ye basın: IP kamera, kayıt cihazı (ONVIF ya da RTSP) ya da video dosyası.' },
  { yol: rehberKamera, hedef: ['#cizim-alani', '#k-bolgeler'], baslik: 'Bölgeler',
    metin: 'İki tür bölge çizilir. Kritik bölgede (elektrik odası, kimyasal deposu) uyarı daha çabuk çıkar. İzinli ateş bölgesindeki (kaynak tezgâhı, fırın, ocak) alev ve duman sayılmaz.' },
  { yol: rehberKamera, hedef: ['#k-kurallar'], baslik: 'Kurallar ve hassasiyet',
    metin: 'Kurallar her kamera için ayrı seçilir. "süre", alevin ya da dumanın kaç saniye görülünce uyarı vereceğidir. Hassasiyet yükseldikçe uyarı erken gelir, yanlış alarm artar.' },
  { yol: 'ayarlar', hedef: ['#a-kameralar tr', '#a-kameralar'], baslik: 'Analizi başlatma',
    metin: '"Bağlantıyı dene" kameradan bir kare alır. "İzlemeyi başlat" canlı kamerayı durdurulana kadar izler; video dosyasında "Videoyu analiz et" kullanılır. Görüntü AugeLab Studio\'da, arka planda işlenir.' },
  { yol: '', baslik: 'Hazırsınız',
    metin: 'Bu turu sol alttaki "Tur" düğmesiyle yeniden açabilirsiniz.' },
];

function rehberGoruldu() { try { return localStorage.getItem(REHBER_ANAHTARI) === '1'; } catch (x) { return true; } }
function rehberIsaretle() { try { localStorage.setItem(REHBER_ANAHTARI, '1'); } catch (x) { /* depolama kapalı: tur yalnızca bu oturumda görünmüş sayılır */ } }

function rehberAc(i = 0) {
  if (!document.getElementById('rehber')) {
    const d = document.createElement('div');
    d.id = 'rehber';
    d.setAttribute('role', 'dialog');
    d.setAttribute('aria-modal', 'true');
    d.setAttribute('aria-label', 'Tanıtım turu');
    d.innerHTML = '<div class="rehber-isik yok"></div><div class="rehber-kart"></div>';
    document.body.appendChild(d);
  }
  $('#katman').innerHTML = '';
  if (!R.acik) R.oncekiOdak = document.activeElement;
  REHBER_ARKA.forEach(s => { const e = document.querySelector(s); if (e) e.inert = true; });
  R.acik = true;
  clearInterval(R.zamanlayici);
  R.zamanlayici = setInterval(rehberYerlestir, 200);  // sayfa yeniden çizilebilir: hedef her seferinde yeniden bulunur
  rehberGoster(i);
}

function rehberKapat() {
  R.acik = false;
  clearInterval(R.zamanlayici);
  document.getElementById('rehber')?.remove();
  REHBER_ARKA.forEach(s => { const e = document.querySelector(s); if (e) e.inert = false; });
  // odak, turdan önceki yerine döner; o öğe yeniden çizildiyse soldaki Tur düğmesine
  (R.oncekiOdak && document.contains(R.oncekiOdak) ? R.oncekiOdak : document.querySelector('#ray a[data-is="rehber"]'))?.focus({ preventScroll: true });
  R.oncekiOdak = null;
  rehberIsaretle();
}

function rehberGoster(i) {
  R.i = Math.max(0, Math.min(REHBER_ADIMLARI.length - 1, i));
  R.hedef = null;
  R.kaydirildi = false;
  const a = REHBER_ADIMLARI[R.i], son = R.i === REHBER_ADIMLARI.length - 1;
  const yol = typeof a.yol === 'function' ? a.yol() : a.yol;
  if (yol != null && konum().yol !== yol) git(yol);
  $('#rehber .rehber-kart').innerHTML = `<button class="rehber-kapat" data-is="rehber-kapat" title="Turu kapat (Esc)" aria-label="Turu kapat">×</button>
    <h3>${h(a.baslik)}</h3><p>${h(a.metin)}</p>
    <div class="rehber-alt"><span class="rehber-say">${R.i + 1} / ${REHBER_ADIMLARI.length}</span>
      ${R.i ? '<button class="dug kucuk" data-is="rehber-geri">Geri</button>' : '<button class="dug kucuk" data-is="rehber-kapat">Turu geç</button>'}
      <button class="dug kucuk ana" data-is="${son ? 'rehber-kapat' : 'rehber-ileri'}" id="rehber-ileri">${son ? 'Bitir' : 'İleri'}</button></div>`;
  $('#rehber-ileri').focus({ preventScroll: true });
  rehberYerlestir();
}

function rehberHedefi() {
  const a = REHBER_ADIMLARI[R.i];
  const yol = typeof a.yol === 'function' ? a.yol() : a.yol;
  if (yol != null && konum().yol !== yol) return null;  // ekran henüz değişmedi
  for (const s of a.hedef || []) {
    const e = typeof s === 'function' ? s() : document.querySelector(s);
    if (e && e.getClientRects().length) return e;
  }
  return null;
}

function rehberYerlestir() {
  const kok = document.getElementById('rehber');
  if (!R.acik || !kok) return;
  const isik = kok.querySelector('.rehber-isik'), kart = kok.querySelector('.rehber-kart');
  const W = window.innerWidth, H = window.innerHeight, pay = 12;
  const e = rehberHedefi();
  if (e && (e !== R.hedef || !R.kaydirildi)) {  // hedef ilk bulunduğunda görünür yere kaydırılır
    R.hedef = e;
    R.kaydirildi = true;
    const r0 = e.getBoundingClientRect();
    if (r0.top < 70 || r0.bottom > H - 20) e.scrollIntoView({ block: r0.height > H * 0.7 ? 'start' : 'center' });
  }
  let r = null;
  if (e) {
    const b = e.getBoundingClientRect();
    const x1 = Math.max(4, b.left - 6), y1 = Math.max(4, b.top - 6), x2 = Math.min(W - 4, b.right + 6), y2 = Math.min(H - 4, b.bottom + 6);
    if (x2 - x1 > 8 && y2 - y1 > 8) r = { x1, y1, x2, y2 };
  }
  const kw = kart.offsetWidth, kh = kart.offsetHeight;
  let kx, ky;
  if (!r) {  // vurgulanacak öğe yok: kart ortada, bütün sayfa karartılır
    isik.classList.add('yok');
    Object.assign(isik.style, { left: '0px', top: '0px', width: W + 'px', height: H + 'px' });
    kx = (W - kw) / 2;
    ky = (H - kh) / 2;
  } else {
    isik.classList.remove('yok');
    Object.assign(isik.style, { left: r.x1 + 'px', top: r.y1 + 'px', width: r.x2 - r.x1 + 'px', height: r.y2 - r.y1 + 'px' });
    const sinirla = (v, enAz, enCok) => Math.max(enAz, Math.min(enCok, v));
    if (r.y2 + pay + kh <= H - pay) [kx, ky] = [sinirla(r.x1, pay, W - kw - pay), r.y2 + pay];                       // altına
    else if (r.y1 - pay - kh >= pay) [kx, ky] = [sinirla(r.x1, pay, W - kw - pay), r.y1 - pay - kh];                // üstüne
    else if (r.x2 + pay + kw <= W - pay) [kx, ky] = [r.x2 + pay, sinirla(r.y1, pay, H - kh - pay)];                 // sağına
    else if (r.x1 - pay - kw >= pay) [kx, ky] = [r.x1 - pay - kw, sinirla(r.y1, pay, H - kh - pay)];                // soluna
    else [kx, ky] = [W - kw - pay - 8, H - kh - pay - 8];                                                           // sığmıyor: sağ alt köşe, öğenin üstünde
  }
  Object.assign(kart.style, { left: Math.round(kx) + 'px', top: Math.round(ky) + 'px' });
}

IS['rehber'] = () => rehberAc(0);
IS['rehber-ileri'] = () => rehberGoster(R.i + 1);
IS['rehber-geri'] = () => rehberGoster(R.i - 1);
IS['rehber-kapat'] = () => rehberKapat();

document.addEventListener('keydown', ev => {
  if (!R.acik) return;
  if (ev.key === 'Escape') rehberKapat();
  else if (ev.key === 'ArrowRight') { if (R.i < REHBER_ADIMLARI.length - 1) rehberGoster(R.i + 1); }
  else if (ev.key === 'ArrowLeft') { if (R.i > 0) rehberGoster(R.i - 1); }
  else if (ev.key === 'Tab') {  // odak turun dışına çıkmasın
    const d = [...document.querySelectorAll('#rehber button')];
    const sira = d.indexOf(document.activeElement);
    ev.preventDefault();
    d[(sira + (ev.shiftKey ? d.length - 1 : 1)) % d.length]?.focus();
  }
});
window.addEventListener('resize', rehberYerlestir);
window.addEventListener('scroll', rehberYerlestir, true);

/* İlk açılış: program hazır olunca (durum okununca) tur bir kez kendiliğinden başlar. */
(function ilkAcilis(deneme = 0) {
  if (rehberGoruldu()) return;
  if (S.durum && S.katalog) { rehberIsaretle(); return rehberAc(0); }  // gösterildiği an işaretlenir: sayfa yenilenirse yeniden başlamaz
  if (deneme < 100) setTimeout(() => ilkAcilis(deneme + 1), 150);
})();
