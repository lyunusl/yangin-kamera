'use strict';
/* Yangın Kamera arayüzü: tek sayfa, veriler /api/... adreslerinden gelir. */

const S = { durum: null, katalog: null, gun: 7, olaylar: {}, analitik: { katman: 'alev', kamera: '', kategori: '', karsilastir: false }, cizim: null, acikImza: null };
const $ = (s, k = document) => k.querySelector(s);
const h = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const AYLAR = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];
const DUZEY = { kritik: 'Kritik', yuksek: 'Yüksek' };
const DURUM = { acik: 'Açık', ustlenildi: 'Üstlenildi', cozuldu: 'Çözüldü', yanlis: 'Yanlış alarm' };
const GDURUM = { acik: 'Açık', suruyor: 'Sürüyor', kapandi: 'Kapandı' };

async function api(yol, govde) {
  const r = await fetch(yol, govde ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(govde) } : {});
  const j = await r.json().catch(() => ({ hata: 'Yanıt okunamadı.' }));
  if (!r.ok || j.hata) throw new Error(j.hata || 'İstek başarısız.');
  return j;
}
function tarih(iso, saniye) {
  if (!iso) return '–';
  const [g, s] = iso.split('T');
  const [, a, d] = g.split('-');
  return (yerelGun() === g ? 'Bugün' : `${+d} ${AYLAR[+a - 1]}`) + ' ' + (s || '').slice(0, saniye ? 8 : 5);
}
function yerelGun() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
function sure(sn) {
  sn = Math.round(sn || 0);
  if (sn < 60) return `${sn} sn`;
  if (sn < 3600) return `${Math.floor(sn / 60)} dk${sn % 60 ? ' ' + (sn % 60) + ' sn' : ''}`;
  return `${Math.floor(sn / 3600)} sa ${Math.floor(sn % 3600 / 60)} dk`;
}
function bildir(metin) {
  const e = document.createElement('div');
  e.className = 'bildirim'; e.textContent = metin; document.body.appendChild(e);
  setTimeout(() => e.remove(), 4200);
}
const ikon = d => `<svg viewBox="0 0 24 24">${d}</svg>`;
const IKON = {
  kontrol: ikon('<rect x="3" y="3" width="8" height="8" rx="2"/><rect x="13" y="3" width="8" height="5" rx="2"/><rect x="13" y="11" width="8" height="10" rx="2"/><rect x="3" y="14" width="8" height="7" rx="2"/>'),
  uyari: ikon('<path d="M6 9a6 6 0 0112 0c0 6 2.5 7 2.5 7h-17S6 15 6 9z"/><path d="M10 20a2 2 0 004 0"/>'),
  analitik: ikon('<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>'),
  aksiyon: ikon('<rect x="3" y="3" width="18" height="18" rx="4"/><path d="M8 12l3 3 5-6"/>'),
  rapor: ikon('<path d="M4 20V10M10 20V4M16 20v-7M21 20H3"/>'),
  kural: ikon('<path d="M12.3 3c.5 3.6 5.2 5.4 5.2 10.2a5.5 5.5 0 01-11 0c0-2.1.9-3.6 2.2-4.9.2 1.5.8 2.3 1.7 2.7-.5-2.9.2-5.7 1.9-8z"/>'),
  ses: ikon('<path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z"/><path d="M15.5 9a4.2 4.2 0 010 6M18 6.5a8 8 0 010 11"/>'),
  sessiz: ikon('<path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>'),
  yardim: ikon('<circle cx="12" cy="12" r="9"/><path d="M9.3 9.3a2.8 2.8 0 115 1.7c-.9 1-2.3 1.4-2.3 3"/><path d="M12 17.2v.1"/>'),
  ayar: ikon('<circle cx="12" cy="12" r="3"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8"/>'),
};
const SAYFALAR = [['', 'kontrol', 'Kontrol'], ['uyarilar', 'uyari', 'Uyarılar'], ['analitik', 'analitik', 'Analitik'], ['aksiyonlar', 'aksiyon', 'Aksiyon'],
  ['raporlar', 'rapor', 'Raporlar'], ['kurallar', 'kural', 'Kurallar']];
const MARKA = '<svg viewBox="0 0 32 32" width="26" height="26"><path d="M16.4 4.5c.6 4.6 6.6 7 6.6 13.3a7 7 0 01-14 0c0-2.7 1.2-4.7 2.9-6.3.2 1.9 1 3 2.1 3.5-.6-3.7.2-7.4 2.4-10.5z" fill="#e0260f"/><path d="M16 25.2a3.3 3.3 0 01-3.3-3.3c0-1.9 1.5-2.9 2.5-4.7.7 1.6 4.1 2.2 4.1 4.7a3.3 3.3 0 01-3.3 3.3z" fill="#ffa41f"/></svg>';

function rayCiz() {
  const yol = konum().yol;
  const acik = (S.durum?.kameralar || []).reduce((t, k) => t + (k.acik || 0), 0);
  $('#ray').innerHTML = `<div class="marka" title="Yangın Kamera">${MARKA}</div>`
    + SAYFALAR.map(([y, i, ad]) => `<a href="#/${y}" class="${yol === y ? 'secili' : ''}">${IKON[i]}${ad}${y === 'uyarilar' && acik ? `<span class="rozet">${acik > 99 ? '99+' : acik}</span>` : ''}</a>`).join('')
    + `<div class="bosluk"></div><a href="#" data-is="ses" title="${SES.kapali ? 'Siren kapalı: kritik uyarıda ses çalmaz' : 'Siren açık: yeni kritik uyarıda ses çalar'}">${IKON[SES.kapali ? 'sessiz' : 'ses']}Siren</a>`
    + `<a href="#" data-is="rehber" title="Tanıtım turu">${IKON.yardim}Tur</a><a href="#/ayarlar" class="${yol === 'ayarlar' || yol.startsWith('kamera') ? 'secili' : ''}">${IKON.ayar}Ayarlar${S.durum?.is?.durum === 'calisiyor' ? '<span class="rozet">•</span>' : ''}</a>`;
}
function konum() {
  const ham = location.hash.replace(/^#\/?/, '');
  const [yol, sorgu] = ham.split('?');
  return { yol: yol || '', q: Object.fromEntries(new URLSearchParams(sorgu || '')) };
}
function git(yol, q) { const s = new URLSearchParams(q || {}).toString(); location.hash = '#/' + yol + (s ? '?' + s : ''); }
const donemSec = () => `<select class="cip" data-degis="donem">${[[1, 'Bugün'], [7, 'Son 7 gün'], [30, 'Son 30 gün'], [90, 'Son 90 gün']].map(([g, a]) => `<option value="${g}" ${S.gun === g ? 'selected' : ''}>${a}</option>`).join('')}</select>`;
const ust = (baslik, alt, sag = '') => `<div class="ust"><h1>${h(baslik)}<small>${alt}</small></h1>${sag}</div>`;
const cubuklar = (degerler, renk, enCok) => {
  const m = enCok || Math.max(1, ...degerler.map(v => v || 0));
  return `<div class="cubuklar">${degerler.map(v => `<i style="${v ? `height:${Math.max(6, 100 * v / m)}%;background:${renk}` : ''}" title="${v ?? '–'}"></i>`).join('')}</div>`;
};
const duzeyRozet = o => `<span class="rozet ${o.duzey}">${DUZEY[o.duzey] || o.duzey}</span>${o.suruyor ? ' <span class="rozet ciddi">Sürüyor</span>' : ''}`;
function uyariSatiri(o, secili) {
  S.olaylar[o.id] = o;
  return `<div class="uyari ${secili ? 'secili' : ''}" data-is="olay-ac" data-id="${o.id}">${o.kare ? `<img src="/cikti/${h(o.kare)}" loading="lazy" alt="">` : '<div class="yok"></div>'}
    <div class="govde"><div>${duzeyRozet(o)} ${o.durum !== 'acik' ? `<span class="rozet gri">${DURUM[o.durum]}</span>` : ''}</div>
    <div class="bas">${h(o.kural_ad)}</div><div class="alt">${h(o.kamera_ad)}${o.bolge ? ' · ' + h(o.bolge) : ''} · ${tarih(o.zaman, true)} · ${sure(o.sure_sn)}</div></div>
    <div style="text-align:right"><div class="et">Risk</div><b style="font-size:18px">${o.puan}</b></div></div>`;
}

/* ------------------------------------------------------------ Siren (yeni kritik uyarıda; ses dosyası yok, WebAudio ile üretilir) */
const SES = { kapali: false, ctx: null, son: null };
try { SES.kapali = localStorage.getItem('yangin-siren') === '0'; } catch (x) { /* depolama kapalı: siren açık kalır */ }
function sesBaglami() {
  if (!SES.ctx) {
    const C = window.AudioContext || window.webkitAudioContext;
    if (!C) return null;
    SES.ctx = new C();
  }
  if (SES.ctx.state === 'suspended') SES.ctx.resume().catch(() => { /* tarayıcı sayfaya tıklanmadan ses açmaz */ });
  return SES.ctx;
}
function sirenCal(sn = 2.4) {
  if (SES.kapali) return;
  const c = sesBaglami();
  if (!c) return;
  const t0 = c.currentTime + 0.03, o = c.createOscillator(), g = c.createGain();
  o.type = 'sawtooth';
  for (let t = 0; t < sn; t += 0.6) {  // iki tonlu, inip çıkan siren
    o.frequency.setValueAtTime(620, t0 + t);
    o.frequency.linearRampToValueAtTime(1180, t0 + t + 0.3);
    o.frequency.linearRampToValueAtTime(620, t0 + t + 0.6);
  }
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(0.2, t0 + 0.05);
  g.gain.setValueAtTime(0.2, t0 + sn - 0.15);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + sn);
  o.connect(g); g.connect(c.destination);
  o.start(t0); o.stop(t0 + sn + 0.05);
}
// Tarayıcılar sesi ancak sayfaya bir kez tıklandıktan sonra açar: ilk tıklamada ses bağlamı hazırlanır.
document.addEventListener('pointerdown', () => { if (!SES.kapali) sesBaglami(); }, { capture: true });
async function kritikIzle() {
  const son = S.durum?.son_kritik || 0;
  if (SES.son == null) { SES.son = son; return; }
  if (son <= SES.son) return;
  SES.son = son;
  sirenCal();
  try { const o = await api('/api/olay/' + son); bildir(`Kritik uyarı · ${o.kural_ad} · ${o.kamera_ad}`); } catch (x) { bildir('Kritik uyarı'); }
}

/* ------------------------------------------------------------ Kontrol Odası */
function kameraHali(k) {
  const is = S.durum?.is;
  if (k.suruyor) return ['alarm', 'Alarm'];
  if (is?.durum === 'calisiyor' && is.kod === k.kod && is.tur !== 'test') return ['canli', is.tur === 'izle' ? 'İzleniyor' : 'Analiz'];
  return ['', 'Beklemede'];
}
function kameraKarosu(k) {
  const [sinif, ad] = kameraHali(k), kare = k.son_kare || k.ayar_karesi;
  return `<div class="kam ${sinif === 'alarm' ? 'alarm' : ''}" data-is="kamera-ac" data-kod="${h(k.kod)}">${kare ? `<img src="${h(kare)}" alt="">` : '<div class="bos">Henüz görüntü yok.<br>Ayarlar\'dan başlatın.</div>'}
    <div class="hal ${sinif}">${ad}</div>${k.acik ? `<div class="acik">${k.acik} açık</div>` : ''}<div class="ad"><span>${h(k.ad)}</span>${k.son_analiz ? `<span>${tarih(k.son_analiz)}</span>` : ''}</div></div>`;
}
function karolariYenile() {
  // Çalışan kameranın karesi saniyede bir yenilenir: karo, sayfa yeniden çizilmeden güncellenir.
  for (const k of S.durum?.kameralar || []) {
    const e = document.querySelector(`.kam[data-kod="${CSS.escape(k.kod)}"]`);
    if (!e) continue;
    const img = e.querySelector('img'), kare = k.son_kare || k.ayar_karesi, [sinif, ad] = kameraHali(k);
    if (!img && kare) { e.outerHTML = kameraKarosu(k); continue; }
    if (img && kare && img.getAttribute('src') !== kare) img.src = kare;
    const hal = e.querySelector('.hal');
    if (hal && hal.textContent !== ad) { hal.className = 'hal ' + sinif; hal.textContent = ad; e.classList.toggle('alarm', sinif === 'alarm'); }
  }
}
async function sayfaKontrol() {
  const d = await api(`/api/ozet?gun=${S.gun}`);
  const s = d.seri;
  let govde;
  if (!d.kameralar.length) govde = bosDurum();
  else {
    govde = `<div class="izgara dortlu" style="margin-bottom:14px">
      <div class="kart"><div class="et">Süren alarm</div><div class="sayi" style="${d.suruyor ? 'color:var(--kritik)' : ''}">${d.suruyor}<small>${d.acik} açık uyarı</small></div></div>
      <div class="kart"><div class="et">Kritik olay</div><div class="sayi">${d.kritik}<small>${d.olay} olayın içinde</small></div>${cubuklar(s.map(x => x.kritik), 'var(--kritik)')}</div>
      <div class="kart"><div class="et">Olay</div><div class="sayi">${d.olay}</div>${cubuklar(s.map(x => x.olay), 'var(--yuksek)')}</div>
      <div class="kart"><div class="et">İzlenen süre</div><div class="sayi">${sure(d.izlenen_sn)}</div>${cubuklar(s.map(x => x.izlenen_sn), '#f3b08a')}</div>
    </div>
    <div class="izgara iki">
      <div class="kart"><div style="display:flex;align-items:center;margin-bottom:12px"><div class="et" style="flex:1">Kameralar · ${d.kameralar.length}</div><a class="dug kucuk" href="#/ayarlar">Kamera ekle / ayarla</a></div>
        <div class="kameralar">${d.kameralar.map(kameraKarosu).join('')}</div>
        <div class="not" style="margin-top:10px">Her karo, kameranın son işaretli karesidir; çalışırken saniyede bir yenilenir.</div></div>
      <div class="kart"><div style="display:flex;align-items:center;margin-bottom:12px"><div class="et" style="flex:1"><span style="color:var(--vurgu)">●</span> Açık uyarılar · ${d.acik}</div><a class="dug kucuk" href="#/uyarilar">Tümü</a></div>
        <div class="liste">${d.canli.length ? d.canli.map(o => uyariSatiri(o)).join('') : '<div class="not">Bu dönemde açık uyarı yok.</div>'}</div></div>
    </div>`;
  }
  $('#sayfa').innerHTML = ust('Kontrol Odası', `${h(d.tesis)} · süren alarmlar üstte`, donemSec()) + modelUyarisi() + govde;
}
/* ------------------------------------------------------------ AugeLab Studio kurulum sihirbazı
   Adım adım: Studio'yu kur → AugeLab hesabı → lisans kodu → hazır. Studio penceresi hiç açılmaz:
   Yangın Kamera Studio'yu arayüzsüz kullanır (lisans kodu da Studio'nun kendi komutuyla arayüzsüz kaydedilir).
   Kurulum sürerken AugeLab hesap sayfası pencerenin içinde açılır (hesabı olmayan o sırada üye olur). Var olan hesapla
   girişi çerçevede yapmaz: Google/Microsoft girişi çerçevede çalışmaz, lisans kodu ayrı bir pencerede alınır. */
const SH = { kapatildi: false, cevrimdisi: 0, hesapVar: false, zamanlayici: null, kod: '', hata: '', otoDeneme: false };
try { SH.hesapVar = localStorage.getItem('yangin-augelab-hesap') === '1'; } catch (x) { /* depolama kapalı */ }
const SH_KURULUM = ['indiriliyor', 'vc', 'kuruluyor', 'pencere'];
const shMb = b => (b / 1048576).toFixed(1).replace('.', ',');
function shHesapUrl() { return S.durum?.hesap_url || 'https://account.augelab.com/'; }
function shDeniyor(d) { return d?.is?.tur === 'studio-dene' && d?.is?.durum === 'calisiyor'; }
function shAdim(d) {
  const k = d?.studio_kurulum || {};
  const kuruluyor = (d?.is?.tur === 'studio-kurulum' && d?.is?.durum === 'calisiyor') || SH_KURULUM.includes(k.asama);
  if (!d?.studio_kurulu || kuruluyor) return 0;
  if (d?.studio?.bagli && !shDeniyor(d)) return 3;
  if (!SH.hesapVar && !d?.studio?.lisans_kaydedildi && !shDeniyor(d)) return 1;
  return 2;
}
function shHesap(adim, d) {
  const k = d?.studio_kurulum || {};
  const goster = !SH.hesapVar && (adim === 1 || (adim === 0 && SH_KURULUM.includes(k.asama)));
  $('#sh-hesap').hidden = !goster;
  $('#sihirbaz').classList.toggle('genis', goster);
  if (!goster) return;
  const url = shHesapUrl() + '?p=signup';
  const cerceve = $('#sh-iframe');
  if (cerceve.dataset.url !== url) {
    cerceve.src = url; cerceve.dataset.url = url;
    $('#sh-cerceve').classList.remove('tam'); $('#sh-ust').textContent = 'Sayfanın üstünü göster';
    $('#sh-kaydir').classList.remove('gitti');
  }
  $('#sh-hesap-bag').href = url;
  $('#sh-hesap-yazi').innerHTML = adim === 0
    ? '<b>AugeLab hesabınız yoksa kurulum sürerken burada oluşturun.</b> Lisans kodu için gerekli.'
    : '<b>AugeLab hesabınızı burada oluşturun</b> (e-postanıza gelen bağlantıyla onaylayın). Hesabınız varsa “Hesabım var”a basın.';
}
function shSonDeneme(d) {
  // Son "Studio'yu dene" işi hatayla bittiyse nedeni (lisans yok, kurulum bozuk...).
  const is = d?.is;
  if (is?.tur !== 'studio-dene' || is.durum === 'calisiyor' || d?.studio?.bagli) return '';
  return is.durum === 'hata' ? (is.satirlar || []).slice(-1)[0] || 'Lisans bulunamadı.' : '';
}
function shCiz() {
  const d = S.durum;
  if (!d || !$('#sihirbaz').open) return;
  const k = d.studio_kurulum || {};
  const adim = shAdim(d);
  document.querySelectorAll('#sihirbaz .sh-adimlar li').forEach((li, i) => { li.className = i < adim ? 'bitti' : i === adim ? 'su' : ''; });
  let govde = '', eylem = '';
  if (adim === 0 && SH_KURULUM.includes(k.asama)) {
    // "Studio'yu kur" adımının alt adımları, bittikçe işaretlenir.
    const sira = { indiriliyor: 0, vc: 1, kuruluyor: 2, pencere: 2 }[k.asama];
    const yuzde = k.toplam ? Math.round(100 * k.indirilen / k.toplam) : 0;
    const indirme = k.toplam ? `<div class="sh-cubuk"><i style="width:${yuzde}%"></i></div><div class="sh-bekle">${h(k.ne)} · ${shMb(k.indirilen)} / ${shMb(k.toplam)} MB · %${yuzde}</div>` : '';
    const sure = `${Math.floor((k.gecen || 0) / 60)}:${String((k.gecen || 0) % 60).padStart(2, '0')}`;
    const satir = (i, yazi, ek = '') => `<li style="list-style:none;margin-left:-20px">${i < sira ? '✓' : i === sira ? '▶' : '○'} ${i === sira ? `<b>${yazi}</b>` : yazi}${i === sira ? ek : ''}</li>`;
    govde = `<h2>AugeLab Studio kuruluyor</h2><ol class="yap">
      ${satir(0, 'AugeLab kurulum dosyasını indir', k.asama === 'indiriliyor' ? indirme : '')}
      ${satir(1, 'Visual C++ bileşenini kur (Microsoft)', k.asama === 'vc' ? (indirme || '<div class="sh-bekle"><span class="sh-don"></span>Kuruluyor. Windows izin sorarsa <b>Evet</b> deyin.</div>') : '')}
      ${satir(2, k.asama === 'pencere' ? 'AugeLab Studio’yu kurulum penceresinde kur' : 'AugeLab Studio’yu kur (birkaç dakika sürer)',
        `<div class="sh-bekle"><span class="sh-don"></span>${k.asama === 'pencere' ? 'Kurulum penceresindeki adımları tamamlayın. ' : ''}${sure}</div>`)}
    </ol>`;
  } else if (adim === 0) {
    govde = `<h2>AugeLab Studio kurulu değil</h2><p>Yangın Kamera görüntüleri bu bilgisayardaki <b>AugeLab Studio</b> ile analiz eder; görüntüler internete gönderilmez. Studio arka planda çalışır, penceresi açılmaz.</p>
      <p>Yangın Kamera, AugeLab Studio’yu AugeLab’den indirip bu bilgisayara kuracak; Visual C++ bileşeni eksikse onu da Microsoft’tan kurar.</p>
      ${k.asama === 'hata' && k.hata ? `<p class="hata">${h(k.hata)}</p>` : ''}`;
    eylem = `<button class="dug ana" data-is="studio-kurulum" data-tur="kur"${d.is?.durum === 'calisiyor' ? ' disabled' : ''}>${k.asama === 'hata' ? 'Tekrar dene' : 'İndir ve kur'} →</button>`;
  } else if (adim === 1) {
    govde = '<h2>AugeLab hesabı</h2><p>AugeLab Studio kuruldu. Studio’yu etkinleştiren lisans kodu AugeLab hesabınızda görünür; ücretsiz Community planı yeterli.</p>';
    eylem = '<button class="dug ana" id="sh-hesap-tamam" type="button">Hesabım hazır →</button>';
  } else if (adim === 2) {
    const deniyor = shDeniyor(d);
    const hata = SH.hata || shSonDeneme(d);
    govde = `<h2>Lisans kodu</h2>
      <ol class="yap">
        <li>AugeLab hesabınıza giriş yapın (Google, Microsoft ya da e-posta) ve lisans kodunu kopyalayın.
          <div style="margin-top:8px"><button class="dug" data-is="hesap-ac">Lisans kodumu al ↗</button></div></li>
        <li>Kodu buraya yapıştırın. Yangın Kamera kodu yalnızca AugeLab Studio’ya verir; saklamaz.
          <div class="sh-kod"><input id="sh-kod" autocomplete="off" spellcheck="false" placeholder="Lisans kodu" value="${h(SH.kod)}"${deniyor ? ' disabled' : ''}></div></li>
      </ol>
      ${deniyor ? '<div class="sh-bekle"><span class="sh-don"></span>Lisans kontrol ediliyor…</div>' : ''}
      ${hata ? `<p class="hata">${h(hata)}</p>` : ''}
      ${d.studio?.lisans_kaydedildi || deniyor ? '' : '<p class="soluk" style="font-size:13px">Studio bu bilgisayarda zaten etkinse kod girmeden <a href="#" id="sh-dene">lisansı kontrol edin</a>.</p>'}`;
    eylem = `<button class="dug ana" id="sh-kaydet" type="button"${deniyor ? ' disabled' : ''}>Kaydet →</button>`;
  } else {
    govde = `<h2>Hazır</h2><p>AugeLab Studio ${h(d.studio?.surum || '')} arka planda çalışmaya hazır; penceresi açılmaz. Kameralarınızı ekleyip analizi başlatabilir ya da Ayarlar’dan örnek analizi çalıştırabilirsiniz.</p>`;
    eylem = '<button class="dug ana" data-is="sihirbaz-kapat">Bitir</button>';
  }
  const odak = document.activeElement?.id === 'sh-kod';
  $('#sh-govde').innerHTML = govde; $('#sh-eylem').innerHTML = eylem;
  const model = modelIndirme(d);  // Studio adımlarından bağımsız: algılama modeli indirmesi
  $('#sh-model').hidden = !model; $('#sh-model').innerHTML = model;
  if (adim === 2) {
    const girdi = $('#sh-kod');
    girdi.oninput = () => { SH.kod = girdi.value; SH.hata = ''; };
    girdi.onkeydown = e => { if (e.key === 'Enter') $('#sh-kaydet').click(); };
    if (odak) { girdi.focus(); girdi.setSelectionRange(girdi.value.length, girdi.value.length); }
    $('#sh-kaydet').onclick = shKaydet;
    const dene = $('#sh-dene');
    if (dene) dene.onclick = async e => { e.preventDefault(); SH.hata = ''; try { await api('/api/studio/dene', {}); } catch (x) { SH.hata = x.message; } await durumAl(); };
  }
  if (adim === 1) $('#sh-hesap-tamam').onclick = () => $('#sh-hesabim-var').click();
  // Lisans kodu kurulum dosyasında girildiyse Studio bir kez kendiliğinden denenir (pencere açılmaz).
  if (adim === 2 && d.studio?.lisans_kaydedildi && d.studio?.hazir !== true && !shDeniyor(d) && !SH.otoDeneme && d.is?.durum !== 'calisiyor' && !d.model_indirme?.eksik) {
    SH.otoDeneme = true;
    api('/api/studio/dene', {}).then(durumAl).catch(x => { SH.hata = x.message; shCiz(); });
  }
  shHesap(adim, d);
  $('#sh-sonra').style.visibility = adim === 3 ? 'hidden' : 'visible';
}
async function shKaydet() {
  const kod = (SH.kod || '').trim();
  if (!kod) { SH.hata = 'Lisans kodunu yapıştırın.'; shCiz(); return; }
  SH.hata = '';
  $('#sh-kaydet').disabled = true;
  try {
    await api('/api/studio/lisans', { kod });
    SH.kod = '';  // kod sayfada da tutulmaz
  } catch (x) {
    SH.hata = x.message;
  }
  await durumAl();
}
function sihirbazAc() {
  SH.kapatildi = false;
  if (!$('#sihirbaz').open) $('#sihirbaz').showModal();
  shCiz();
  clearInterval(SH.zamanlayici);
  SH.zamanlayici = setInterval(async () => { try { await durumAl(); } catch (x) { /* program kapanmış olabilir */ } }, 1500);
}
function sihirbazKapat() { $('#sihirbaz').close(); clearInterval(SH.zamanlayici); }
function sihirbazIzle() {
  // Studio hazır değilse (kurulu değil, lisans girilmedi, deneme geçmedi) sihirbaz kendiliğinden açılır (tanıtım turu açıkken beklenir).
  const bagli = !!S.durum?.studio?.bagli;
  SH.cevrimdisi = bagli ? 0 : SH.cevrimdisi + 1;
  if (!bagli && SH.cevrimdisi >= 2 && !SH.kapatildi && !$('#sihirbaz').open && !document.getElementById('rehber')) sihirbazAc();
  shCiz();
}
$('#sh-sonra').onclick = () => { SH.kapatildi = true; sihirbazKapat(); };
$('#sh-hesabim-var').onclick = () => { SH.hesapVar = true; try { localStorage.setItem('yangin-augelab-hesap', '1'); } catch (x) { /* depolama kapalı */ } shCiz(); };
$('#sh-ust').onclick = () => { const tam = $('#sh-cerceve').classList.toggle('tam'); $('#sh-ust').textContent = tam ? 'Formu öne getir' : 'Sayfanın üstünü göster'; };
$('#sh-cerceve').addEventListener('mouseenter', () => setTimeout(() => $('#sh-kaydir').classList.add('gitti'), 4000));
$('#sihirbaz').addEventListener('cancel', () => { SH.kapatildi = true; clearInterval(SH.zamanlayici); });

let otoDenemeYapildi = false;
function studioOtoDene(d) {
  // Studio kurulu ama henüz denenmemişse (ör. lisans kodu kurulum dosyasında girildi) deneme bir kez kendiliğinden başlar.
  // Deneme modeli açar: algılama modeli indirilene kadar beklenir.
  if (otoDenemeYapildi || !d?.studio_kurulu || d?.studio?.kurulu === false || d?.studio?.hazir != null || d?.is?.durum === 'calisiyor' || d?.model_indirme?.eksik) return;
  otoDenemeYapildi = true;
  api('/api/studio/dene', {}).then(durumAl).catch(() => { /* iş çalışıyor olabilir; sihirbazdan yeniden denenir */ });
}
function studioUyarisi() {
  // Studio bağlı değilken sayfanın üstünde kısa bir şerit: adımlar kurulum sihirbazında (yukarıda).
  const d = S.durum;
  if (d?.studio?.bagli) return '<div data-studio-kurulum hidden></div>';
  const kuruluyor = d?.is?.tur === 'studio-kurulum' && d?.is?.durum === 'calisiyor';
  const deniyor = d?.is?.tur === 'studio-dene' && d?.is?.durum === 'calisiyor';
  if (deniyor || (d?.studio_kurulu && d?.studio?.hazir == null && !kuruluyor)) {
    return '<div data-studio-kurulum class="uyari-seridi"><b>Lisans kontrol ediliyor</b> Lütfen bekleyin.</div>';
  }
  const baslik = kuruluyor ? 'AugeLab Studio kuruluyor' : d?.studio_kurulu ? 'Lisans bulunamadı' : 'AugeLab Studio kurulu değil';
  const ek = d?.studio_kurulu && d?.studio?.hata ? h(d.studio.hata) + ' ' : 'Analiz için AugeLab Studio gerekir (arka planda çalışır, penceresi açılmaz). ';
  return '<div data-studio-kurulum class="uyari-seridi"><b>' + baslik + '</b> ' + ek
    + '<button class="dug kucuk ana" data-is="sihirbaz-ac">Kurulum sihirbazı</button></div>';
}
function modelIndirme(d) {
  // Algılama modeli kurulumda indirilemediyse panel indirir: ilerleme, hata ve "Yeniden dene".
  const m = d?.model_indirme;
  if (!m?.eksik) return '';
  if (m.asama === 'dogrulaniyor') return '<b>Algılama modeli hazırlanıyor…</b> Dosya doğrulanıyor; birkaç saniye sürer.';
  if (m.asama === 'indiriliyor') {
    const yuzde = m.toplam ? Math.round(100 * m.indirilen / m.toplam) : 0;
    return `<b>Algılama modeli indiriliyor… %${yuzde}</b> ${shMb(m.indirilen)} / ${shMb(m.toplam)} MB. İndirme bitince analiz başlatılabilir.<div class="sh-cubuk"><i style="width:${yuzde}%"></i></div>`;
  }
  const dugme = `<button class="dug kucuk ana" data-is="model-indir">${m.asama === 'hata' ? 'Yeniden dene' : 'İndir'}</button>`;
  if (m.asama === 'hata') return `<b>Algılama modeli indirilemedi.</b> ${h(m.hata)} ${dugme}`;
  return `<b>Algılama modeli yok.</b> Alev ve duman aramak için indirilmesi gerekir (yaklaşık ${Math.round((m.boyut || 0) / 1e6)} MB). ${dugme}`;
}
function modelIndirmeSeridi() {
  const m = modelIndirme(S.durum);
  return m ? `<div data-model-indirme class="uyari-seridi">${m}</div>` : '<div data-model-indirme hidden></div>';
}
function modelUyarisi() {
  const d = S.durum, k = d?.model_kilidi;
  let model = '';
  if (d?.model_indirme?.eksik) model = modelIndirmeSeridi();
  else if (k?.sifreli && k.durum !== 'studio_kosusunda_dogrulanir') model ='<div class="uyari-seridi"><b>Model paketi</b> ' + h(k.mesaj || 'Model paketi açılamıyor.') + '</div>';
  else if (d && !d.model) model = '<div class="uyari-seridi"><b>Model dosyası yok.</b> Alev ve duman aranamaz; programı yeniden kurun.</div>';
  return studioUyarisi() + model;
}
function bosDurum() {
  return `<div class="bos-durum"><h3>Henüz kamera yok</h3><p>Bir IP kamera, kayıt cihazı ya da video dosyası ekleyin.</p>
    <p><a class="dug ana" href="#/kamera/yeni">Kamera ekle</a> ${S.durum?.ornek_var ? '<button class="dug" data-is="ornek">Örnek analizi çalıştır</button>' : ''}</p></div>`;
}

/* ------------------------------------------------------------ Uyarılar */
async function sayfaUyarilar(q) {
  const p = new URLSearchParams({ gun: S.gun });
  for (const a of ['kamera', 'kategori', 'duzey', 'durum', 'vardiya', 'sirala']) if (q[a]) p.set(a, q[a]);
  const d = await api('/api/olaylar?' + p);
  const sec = (ad, etiket, secenekler) => `<select class="cip" data-degis="suzgec" data-alan="${ad}"><option value="">${etiket}</option>${secenekler.map(([v, a]) => `<option value="${h(v)}" ${q[ad] === String(v) ? 'selected' : ''}>${h(a)}</option>`).join('')}</select>`;
  const suzgec = sec('kamera', 'Tüm kameralar', S.durum.kameralar.map(k => [k.kod, k.ad]))
    + sec('kategori', 'Tüm kategoriler', Object.entries(S.katalog.kategoriler))
    + sec('duzey', 'Tüm düzeyler', Object.entries(DUZEY)) + sec('durum', 'Tüm durumlar', Object.entries(DURUM))
    + sec('vardiya', 'Tüm vardiyalar', S.durum.genel.vardiyalar.map(v => [v.ad, v.ad]))
    + sec('sirala', 'Yeniden eskiye', [['puan', 'Riske göre']]) + donemSec();
  $('#sayfa').innerHTML = ust('Uyarılar', `${d.toplam} olay · klip, risk puanı ve konumla`, '')
    + `<div class="ust" style="margin-top:-6px">${suzgec}</div>`
    + (d.olaylar.length ? `<div class="liste">${d.olaylar.map(o => uyariSatiri(o, q.id == o.id)).join('')}</div>` : '<div class="bos-durum"><h3>Uyarı yok</h3><p>Bu süzgeçlere uyan olay bulunamadı.</p></div>');
  if (q.id && S.olaylar[q.id]) olayCekmecesi(S.olaylar[q.id]);
}
function olayCekmecesi(o) {
  $('#katman').innerHTML = `<div class="cekmece form"><div style="display:flex;gap:10px;align-items:flex-start;margin-bottom:12px"><div style="flex:1">
      <div>${duzeyRozet(o)} <span class="rozet gri">${DURUM[o.durum]}</span></div><h2 style="margin-top:6px">${h(o.kural_ad)}</h2>
      <div class="not">${h(o.kamera_ad)}${o.bolge ? ' · ' + h(o.bolge) : ''} · ${tarih(o.zaman, true)}${o.vardiya ? ' · ' + h(o.vardiya) + ' vardiyası' : ''}</div></div>
      <button class="dug kucuk" data-is="katman-kapat">Kapat</button></div>
    ${o.klip ? `<video src="/cikti/${h(o.klip)}" controls autoplay muted loop playsinline></video>` : (o.kare ? `<img class="buyuk" src="/cikti/${h(o.kare)}" alt="">` : '')}
    <div class="bilgi"><div><span class="et">Risk puanı</span><b>${o.puan} / 25</b><span class="not">önem ${o.onem} × olasılık ${o.olasilik}</span></div>
      <div><span class="et">Süre</span><b>${sure(o.sure_sn)}</b><span class="not">${o.suruyor ? 'sürüyor' : 'kapandı'}</span></div>
      <div><span class="et">Olay no</span><b>#${o.id}</b><span class="not">${S.katalog.kategoriler[o.kategori] || o.kategori}</span></div></div>
    <p>${h(o.aciklama || '')}</p>
    <label>Üstlenen</label><input id="o-ustlenen" value="${h(o.ustlenen || '')}" placeholder="ad ya da ekip">
    <label>Not</label><textarea id="o-not" placeholder="ne yapıldı, ne görüldü">${h(o.notlar || '')}</textarea>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
      <button class="dug" data-is="olay-durum" data-id="${o.id}" data-durum="ustlenildi">Üstlen</button>
      <button class="dug" data-is="olay-durum" data-id="${o.id}" data-durum="cozuldu">Çözüldü</button>
      <button class="dug" data-is="olay-durum" data-id="${o.id}" data-durum="yanlis">Yanlış alarm</button>
      ${o.durum !== 'acik' ? `<button class="dug" data-is="olay-durum" data-id="${o.id}" data-durum="acik">Yeniden aç</button>` : ''}
      <button class="dug ana" data-is="gorev-yeni" data-olay="${o.id}">Görev oluştur</button></div>
    ${(o.gorevler || []).length ? `<p class="not">Bu olay ${o.gorevler.map(g => `<a href="#/aksiyonlar">#${g} numaralı göreve</a>`).join(', ')} bağlı.</p>` : ''}
    <p class="not">"Yanlış alarm" işaretlenen olay raporlara girmez.</p></div>`;
}

/* ------------------------------------------------------------ Görsel Analitik */
function isiRengi(t) {
  const r = [[246, 211, 101], [255, 154, 31], [224, 38, 15]];
  const a = t < .5 ? 0 : 1, f = t < .5 ? t * 2 : (t - .5) * 2;
  return 'rgb(' + r[a].map((v, i) => Math.round(v + (r[a + 1][i] - v) * f)).join(',') + ')';
}
const bolgeRengi = tur => tur === 'izinli' ? '#7ad38a' : '#ffb01f';
function sahneCiz(d, katman) {
  if (!d.son_kare) return '<div class="sahne"><div class="bosyazi">Bu kameradan henüz işaretli görüntü yok.</div></div>';
  const g = d.izgara;
  let ic = '';
  if (g.gen) {
    const hucre = g[katman] || [];
    const m = Math.max(0, ...hucre.flat());
    const gw = 1000 / g.gen, gh = 1000 / g.yuk;
    if (m > 0) hucre.forEach((satir, y) => satir.forEach((v, x) => {
      if (v <= 0) return;
      const t = Math.pow(v / m, .55);
      ic += `<rect x="${x * gw}" y="${y * gh}" width="${gw}" height="${gh}" fill="${isiRengi(t)}" opacity="${(.25 + .55 * t).toFixed(2)}"><title>${katman === 'olay' ? 'risk puanı toplamı ' + v : sure(v)}</title></rect>`;
    }));
  }
  for (const b of d.bolgeler) ic += `<polygon points="${b.poly.map(p => `${p[0] * 1000},${p[1] * 1000}`).join(' ')}" fill="none" stroke="${bolgeRengi(b.tur)}" stroke-width="1.5" stroke-dasharray="6 5" vector-effect="non-scaling-stroke"><title>${h(b.ad)}</title></polygon>`;
  if (katman === 'olay') for (const n of d.noktalar) ic += `<line x1="${n.x * 1000}" y1="${n.y * 1000}" x2="${n.x * 1000}" y2="${n.y * 1000}" stroke="#fff" stroke-width="${6 + n.puan / 3}" stroke-opacity=".9" stroke-linecap="round" vector-effect="non-scaling-stroke"><title>${h(n.kural_ad)} · risk ${n.puan}</title></line>`;
  return `<div class="sahne"><img src="${h(d.son_kare)}" alt=""><svg viewBox="0 0 1000 1000" preserveAspectRatio="none">${ic}</svg></div>`;
}
function analitikSerit(d) {
  const s = d.sayilar;
  return `<div class="serit"><span class="et">Sayılar</span><span>Alev görülen süre<b>${sure(s.alev_sn)}</b></span><span>Duman görülen süre<b>${sure(s.duman_sn)}</b></span>
    <span>Olay<b>${s.olay}</b></span><span>Kritik<b style="color:${s.kritik ? 'var(--kritik)' : 'inherit'}">${s.kritik}</b></span>
    <span>Yoğun saat<b>${s.yogun_saat || '–'}</b></span><span>İzlenen<b>${sure(s.izlenen_sn)}</b></span><span class="olcek">AZ<i></i>ÇOK</span></div>`;
}
async function sayfaAnalitik(q) {
  const A = S.analitik;
  const kameralar = S.durum.kameralar;
  if (!kameralar.length) { $('#sayfa').innerHTML = ust('Görsel Analitik', 'alev ve duman ısı haritası') + bosDurum(); return; }
  if (q.kamera) A.kamera = q.kamera;
  if (!kameralar.some(k => k.kod === A.kamera)) A.kamera = (kameralar.find(k => k.son_analiz) || kameralar[0]).kod;
  const sorgu = ek => '/api/analitik?' + new URLSearchParams({ kamera: A.kamera, ...(A.kategori === 'kritik' ? { ciddi: 1 } : { kategori: A.kategori }), ...ek });
  const d = await api(sorgu({ gun: S.gun }));
  let once = null;
  if (A.karsilastir) {  // önceki eşit uzunluktaki dönem
    const gun = S.gun, bit = new Date(Date.now() - gun * 864e5), bas = new Date(Date.now() - (2 * gun - 1) * 864e5);
    const f = x => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
    once = await api(sorgu({ bas: f(bas), bit: f(bit) }));
  }
  const dugme = (deger, ad) => `<button class="${A.katman === deger ? 'secili' : ''}" data-is="analitik-sec" data-alan="katman" data-deger="${deger}">${ad}</button>`;
  const enCokSaat = Math.max(1, ...d.saatlik.map(x => x.olay));
  $('#sayfa').innerHTML = ust('Görsel Analitik', 'alev ve duman görüntüde nerede toplandı', donemSec())
    + `<div class="kart"><div class="ust" style="margin-bottom:10px">
        <select class="cip" data-degis="analitik-kamera">${kameralar.map(k => `<option value="${h(k.kod)}" ${k.kod === A.kamera ? 'selected' : ''}>${h(k.ad)}</option>`).join('')}</select>
        <select class="cip" data-degis="analitik-kategori"><option value="">Tüm uyarılar</option><option value="kritik" ${A.kategori === 'kritik' ? 'selected' : ''}>Kritik</option>${Object.entries(S.katalog.kategoriler).map(([k, a]) => `<option value="${k}" ${A.kategori === k ? 'selected' : ''}>${h(a)}</option>`).join('')}</select>
        <label class="cip" style="cursor:pointer"><input type="checkbox" data-degis="analitik-karsilastir" ${A.karsilastir ? 'checked' : ''}> Önceki dönemle karşılaştır</label></div>
      <div class="sekmeler"><span class="et" style="align-self:center;flex:1">Isı haritası</span>${dugme('alev', 'Alev')}${dugme('duman', 'Duman')}${dugme('olay', 'Olay riski')}</div>
      ${once ? `<div class="izgara" style="grid-template-columns:1fr 1fr"><div><div class="et" style="margin-bottom:6px">Önce · ${once.bas.slice(0, 10)} – ${once.bit.slice(0, 10)} · ${once.sayilar.olay} olay</div>${sahneCiz({ ...once, son_kare: once.son_kare || d.son_kare, bolgeler: d.bolgeler }, A.katman)}</div>
          <div><div class="et" style="margin-bottom:6px">Sonra · ${d.bas.slice(0, 10)} – ${d.bit.slice(0, 10)} · ${d.sayilar.olay} olay</div>${sahneCiz(d, A.katman)}</div></div>` : sahneCiz(d, A.katman)}
      ${analitikSerit(d)}
      ${d.sayilar.en_riskli_pay ? `<p class="not" style="margin:8px 2px 0">En riskli hücre, toplam olay riskinin <b>%${d.sayilar.en_riskli_pay}</b>'ini taşıyor.</p>` : ''}</div>
    <div class="izgara iki" style="margin-top:14px"><div class="kart"><div class="et">Saatlere göre olay</div>
        <div class="cubuklar" style="height:90px">${d.saatlik.map(x => `<i style="${x.olay ? `height:${Math.max(6, 100 * x.olay / enCokSaat)}%;background:var(--vurgu)` : (x.tespit_sn ? 'background:#f3b08a' : '')}" title="${String(x.saat).padStart(2, '0')}:00 · ${x.olay} olay · ${sure(x.tespit_sn)} tespit"></i>`).join('')}</div>
        <div style="display:flex;justify-content:space-between" class="et"><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div>
        <p class="not">Açık renkli çubuk: o saatte alev ya da duman görüldü ama uyarı çıkmadı.</p></div>
      <div class="kart"><div class="et" style="margin-bottom:6px">Bu kamerada kurallara göre olay</div>${d.kurallar.length ? `<table>${d.kurallar.map(k => `<tr><td>${h(k.ad)}</td><td class="s"><b>${k.n}</b></td></tr>`).join('')}</table>` : '<div class="not">Olay yok.</div>'}
        <p style="margin-top:12px"><button class="dug kucuk" data-is="gorev-yeni" data-kamera="${h(A.kamera)}">Bu kameradan görev oluştur</button></p></div></div>`;
}

/* ------------------------------------------------------------ Aksiyonlar */
async function sayfaAksiyonlar() {
  const d = await api('/api/gorevler');
  const kart = g => {
    const m = Math.max(1, ...g.haftalar.map(x => x.n));
    const dogrulama = g.dogrulama ? { dogrulandi: '<span class="rozet yesil">Kapanıştan beri tekrar yok</span>', tekrarladi: `<span class="rozet kirmizi">Kapanıştan sonra ${g.dogrulama.sonra_olay} kez tekrarladı</span>`, bekliyor: '<span class="rozet gri">Doğrulama için yeni görüntü bekleniyor</span>' }[g.dogrulama.durum] : '';
    return `<div class="gorev"><div style="display:flex;gap:10px;align-items:flex-start"><div style="flex:1"><h3>${h(g.baslik)}</h3>
        <div class="not">${g.sorumlu ? 'Sorumlu: ' + h(g.sorumlu) + ' · ' : ''}${g.olaylar.length} olaya bağlı · açıldı ${tarih(g.olusturma)}</div></div>
        ${g.son_tarih ? `<span class="rozet ${g.gecikti ? 'kritik' : 'sari'}">Son tarih ${g.son_tarih.slice(8, 10)}.${g.son_tarih.slice(5, 7)}</span>` : ''}
        <span class="rozet ${g.durum === 'kapandi' ? 'yesil' : g.durum === 'suruyor' ? 'sari' : 'gri'}">${GDURUM[g.durum]}</span></div>
      ${g.aciklama ? `<p style="margin:8px 0 0">${h(g.aciklama)}</p>` : ''}
      ${g.olaylar.length ? `<div style="display:flex;gap:6px;margin-top:10px;overflow:auto">${g.olaylar.slice(0, 6).map(o => o.kare ? `<img src="/cikti/${h(o.kare)}" style="height:54px;border-radius:7px;cursor:pointer" data-is="olay-git" data-id="${o.id}" title="${h(o.kural_ad)} · ${tarih(o.zaman)}">` : '').join('')}</div>` : ''}
      ${g.haftalar.length ? `<div class="et" style="margin-top:12px">Aynı kural · haftalık olay</div><div class="cubuklar" style="height:54px">${g.haftalar.map(x => `<i style="height:${Math.max(6, 100 * x.n / m)}%;background:${g.kapanma && x.hafta > g.kapanma.slice(0, 10) ? '#6fb89b' : 'var(--vurgu)'}" title="${x.hafta} haftası: ${x.n} olay"></i>`).join('')}</div>` : ''}
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:12px">${dogrulama}<span style="flex:1"></span>
        ${g.durum !== 'suruyor' && g.durum !== 'kapandi' ? `<button class="dug kucuk" data-is="gorev-durum" data-id="${g.id}" data-durum="suruyor">Başlat</button>` : ''}
        ${g.durum !== 'kapandi' ? `<button class="dug kucuk ana" data-is="gorev-durum" data-id="${g.id}" data-durum="kapandi">Kapat</button>` : `<button class="dug kucuk" data-is="gorev-durum" data-id="${g.id}" data-durum="acik">Yeniden aç</button>`}
        <button class="dug kucuk" data-is="gorev-duzenle" data-id="${g.id}">Düzenle</button><button class="dug kucuk tehlike" data-is="gorev-sil" data-id="${g.id}">Sil</button></div></div>`;
  };
  S.gorevler = Object.fromEntries(d.gorevler.map(g => [g.id, g]));
  $('#sayfa').innerHTML = ust('Aksiyonlar', 'uyarılardan açılan görevler: sorumlu ve son tarih', '<button class="dug ana" data-is="gorev-yeni">Yeni görev</button>')
    + (d.gorevler.length ? `<div class="liste" style="gap:12px">${d.gorevler.map(kart).join('')}</div>`
      : '<div class="bos-durum"><h3>Henüz görev yok</h3><p>Bir uyarıyı açıp <b>Görev oluştur</b>\'a basın ya da buradan yeni görev ekleyin.</p></div>');
}
function gorevPenceresi(g, olay) {
  const o = olay ? S.olaylar[olay] : null;
  g = g || { baslik: o ? `${o.kural_ad}${o.bolge ? ' · ' + o.bolge : ''}` : '', aciklama: '', sorumlu: '', son_tarih: '', durum: 'acik', kamera: o?.kamera || konum().q.kamera || '', kural: o?.kural || '', bolge: o?.bolge || '' };
  $('#katman').innerHTML = `<div class="perde"><div class="pencere form"><h2 style="margin:0 0 4px">${g.id ? 'Görevi düzenle' : 'Yeni görev'}</h2>
    ${o ? `<div class="not">Olay #${o.id} bu göreve bağlanır ve "üstlenildi" olur.</div>` : ''}
    <label>Başlık</label><input id="g-baslik" value="${h(g.baslik)}" placeholder="ör. Kaynak tezgâhının çevresini boşalt">
    <label>Açıklama</label><textarea id="g-aciklama">${h(g.aciklama || '')}</textarea>
    <div class="satir"><div><label>Sorumlu</label><input id="g-sorumlu" value="${h(g.sorumlu || '')}"></div><div><label>Son tarih</label><input id="g-tarih" type="date" value="${h(g.son_tarih || '')}"></div></div>
    <div class="satir"><div><label>Kamera</label><select id="g-kamera"><option value="">–</option>${S.durum.kameralar.map(k => `<option value="${h(k.kod)}" ${g.kamera === k.kod ? 'selected' : ''}>${h(k.ad)}</option>`).join('')}</select></div>
      <div><label>İzlenecek kural</label><select id="g-kural"><option value="">–</option>${S.katalog.kurallar.filter(k => k.durum !== 'yok').map(k => `<option value="${k.kod}" ${g.kural === k.kod ? 'selected' : ''}>${h(k.ad)}</option>`).join('')}</select></div></div>
    <p class="not">Kamera ve kural seçilirse, görev kapandıktan sonra o kural o kamerada yeniden görülürse görev "tekrarladı" olur.</p>
    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px"><button class="dug" data-is="katman-kapat">Vazgeç</button>
      <button class="dug ana" data-is="gorev-kaydet" data-id="${g.id || ''}" data-olay="${olay || ''}" data-durum="${g.durum}" data-bolge="${h(g.bolge || '')}">Kaydet</button></div></div></div>`;
  $('#g-baslik').focus();
}

/* ------------------------------------------------------------ Raporlar */
function cizgi(noktalar) {
  if (!noktalar.some(v => v)) return '<div class="not" style="padding:30px 0">Bu dönemde olay yok.</div>';
  const enCok = Math.max(4, ...noktalar);
  const n = Math.max(1, noktalar.length - 1), X = i => 28 + 952 * i / n, Y = v => 180 - 160 * v / enCok;
  const yol = noktalar.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ');
  return `<svg viewBox="0 0 1000 200" style="width:100%;height:190px">${[0, enCok / 2, enCok].map(v => `<line x1="28" x2="980" y1="${Y(v)}" y2="${Y(v)}" stroke="#eeeae0"/><text x="0" y="${Y(v) + 4}" font-size="11" fill="#9a9ea8">${Math.round(v)}</text>`).join('')}
    <path d="${yol}" fill="none" stroke="#e0260f" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>${noktalar.map((v, i) => v ? `<circle cx="${X(i)}" cy="${Y(v)}" r="${noktalar.length > 40 ? 2 : 4}" fill="#fff" stroke="#e0260f" stroke-width="2"><title>${v}</title></circle>` : '').join('')}</svg>`;
}
async function sayfaRaporlar() {
  const d = await api(`/api/rapor?gun=${Math.max(S.gun, 7)}`);
  const fark = d.olay - d.onceki_olay;
  const tablo = (baslik, satirlar) => `<div class="kart"><div class="et" style="margin-bottom:6px">${baslik}</div>${satirlar.length ? `<table><tr><th></th><th class="s">Olay</th><th class="s">Kritik</th><th class="s">Risk</th><th style="width:28%"></th></tr>
    ${satirlar.slice(0, 12).map(r => `<tr><td>${h(r.ad)}</td><td class="s">${r.n}</td><td class="s">${r.kritik || ''}</td><td class="s"><b>${r.risk}</b></td><td><div class="cubuk"><i style="width:${100 * r.risk / Math.max(1, satirlar[0].risk)}%"></i></div></td></tr>`).join('')}</table>` : '<div class="not">Olay yok.</div>'}</div>`;
  $('#sayfa').innerHTML = ust('Raporlar', `${h(d.tesis)} · ${d.bas.slice(0, 10)} – ${d.bit.slice(0, 10)}`, donemSec() + '<a class="dug" href="/api/rapor.xlsx">Excel raporu (30 gün)</a>')
    + `<div class="izgara iki" style="margin-bottom:14px"><div class="kart"><div class="et">Olay eğilimi${d.haftalik ? ' · haftalık' : ' · günlük'}</div>${cizgi(d.egilim.map(e => e.olay))}</div>
      <div class="kart"><div class="et">Olay</div><div class="sayi" style="font-size:54px">${d.olay}${d.olay || d.onceki_olay ? `<span class="fark ${fark > 0 ? 'kotu' : ''}">${fark > 0 ? '▲ +' : fark < 0 ? '▼ ' : ''}${fark} önceki döneme göre</span>` : ''}</div>
        <div class="bilgi" style="grid-template-columns:repeat(2,1fr)"><div><span class="et">Kritik</span><b>${d.kritik}</b><span class="not">risk toplamı ${d.risk}</span></div><div><span class="et">Açık / çözülen</span><b>${d.acik} / ${d.cozulen}</b><span class="not">${d.yanlis} yanlış alarm</span></div>
          <div><span class="et">İzlenen süre</span><b>${sure(d.izlenen_sn)}</b></div><div><span class="et">Ort. yanıt</span><b>${d.ort_yanit_dk == null ? '–' : String(d.ort_yanit_dk).replace('.', ',') + ' dk'}</b><span class="not">üstlenme ya da çözme</span></div></div></div></div>
    <div class="izgara" style="grid-template-columns:repeat(2,minmax(0,1fr))">${tablo('Kurala göre', d.kurallar)}${tablo('Kameraya göre', d.kameralar)}${tablo('Vardiyaya göre', d.vardiyalar)}${tablo('Bölgeye göre', d.bolgeler)}</div>`;
}

/* ------------------------------------------------------------ Kurallar */
const KURAL_DURUMU = { hazir: '<span class="rozet yesil">Sınandı</span>', deneysel: '<span class="rozet sari">Deneysel</span>', yok: '<span class="rozet gri">Kapalı</span>' };
async function sayfaKurallar() {
  const K = S.katalog;
  const sinama = k => k.sinama ? `<div class="not">${k.sinama.beklenen ? `${k.sinama.yakalanan}/${k.sinama.beklenen} yakalandı` : ''}${k.sinama.beklenen && k.sinama.denetim ? ' · ' : ''}${k.sinama.denetim ? `${k.sinama.yanlis}/${k.sinama.denetim} yanlış alarm` : ''}</div>` : '';
  const eksik = K.kurallar.filter(k => k.model_eksik);
  $('#sayfa').innerHTML = ust('Kurallar', `${K.kurallar.length} kural · saniyede yaklaşık iki kare analiz edilir`)
    + (eksik.length ? `<div class="uyari-seridi"><b>Kurallar çalışmıyor: model dosyası yok</b> (${h(eksik[0].model_eksik)}).</div>` : '')
    + '<div class="uyari-seridi">Kurallar yapay tespit dizileriyle sınandı; model yalnızca üretilmiş görüntülerle doğrulandı. <b>Gerçek kamera kaydıyla sınanmadı</b>: kendi kameranızda birkaç gün izleyip yanlış alarmları kontrol edin. Onaylı yangın algılama sisteminin yerini tutmaz.</div>'
    + `<div class="izgara" style="grid-template-columns:repeat(2,minmax(0,1fr))">${Object.entries(K.kategoriler).map(([kod, ad]) => `<div class="kart"><div class="et">${h(ad)} · ${K.kurallar.filter(k => k.kategori === kod).length}</div>
      ${K.kurallar.filter(k => k.kategori === kod).map(k => `<div class="kural"><div style="flex:1"><div class="ad">${h(k.ad)} <span class="rozet ${k.duzey}">${DUZEY[k.duzey]}</span></div><div class="ac">${k.bolge_turu ? 'Bölge: ' + h(K.bolge_turleri[k.bolge_turu]) + ' · ' : ''}${h(k.aciklama)}</div></div><div style="text-align:right;white-space:nowrap">${k.model_eksik ? '<span class="rozet kirmizi">Model dosyası yok</span>' : KURAL_DURUMU[k.durum]}<div class="not">süre ${String(k.sure_sn).replace('.', ',')} sn</div>${sinama(k)}</div></div>`).join('')}</div>`).join('')}</div>`;
}

/* ------------------------------------------------------------ Ayarlar */
function isKarti() {
  const i = S.durum.is;
  if (!i) return '<div class="not">Henüz bir iş çalıştırılmadı.</div>';
  const ad = { calisiyor: 'çalışıyor', bitti: 'bitti', hata: 'hata', durduruldu: 'durduruldu' }[i.durum];
  return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><b>${h(i.baslik)}</b><span class="rozet ${i.durum === 'calisiyor' ? 'sari' : i.durum === 'hata' ? 'kirmizi' : 'yesil'}">${ad}</span><span class="not">${sure(i.sure)}</span><span style="flex:1"></span>
    ${i.durum === 'calisiyor' ? `<button class="dug kucuk tehlike" data-is="is-durdur">${i.durduruluyor ? 'Durduruluyor…' : 'Durdur'}</button>` : ''}</div><div class="kayit" id="kayit">${h(i.satirlar.join('\n'))}</div>`;
}
async function sayfaAyarlar() {
  const d = S.durum, g = d.genel;
  const kam = k => `<tr><td><b>${h(k.ad)}</b><div class="not">${{ rtsp: 'IP kamera / kayıt cihazı', onvif: 'ONVIF', http: 'HTTP akışı', dosya: 'video dosyası' }[k.tur] || k.tur} · ${k.bolge} bölge · ${k.kural} kural${k.ornek ? ' · örnek' : ''}${k.son_analiz ? ' · son analiz ' + tarih(k.son_analiz) : ''}</div></td>
    <td style="white-space:nowrap;text-align:right">${k.sifre ? `<input type="password" placeholder="kamera şifresi" autocomplete="off" data-sifre="${h(k.kod)}" style="width:130px;border:1px solid var(--cizgi2);border-radius:8px;padding:5px 8px">` : ''}
      <button class="dug kucuk" data-is="is" data-tur="test" data-kod="${h(k.kod)}">Bağlantıyı dene</button>
      ${k.tur === 'dosya' ? `<button class="dug kucuk ana" data-is="is" data-tur="video" data-kod="${h(k.kod)}">Videoyu analiz et</button>` : `<button class="dug kucuk ana" data-is="is" data-tur="izle" data-kod="${h(k.kod)}">İzlemeyi başlat</button>`}
      <a class="dug kucuk" href="#/kamera/${h(k.kod)}">Düzenle</a><button class="dug kucuk tehlike" data-is="kamera-sil" data-kod="${h(k.kod)}" data-ad="${h(k.ad)}">Sil</button></td></tr>`;
  $('#sayfa').innerHTML = ust('Ayarlar', `Yangın Kamera ${h(d.surum)} · AugeLab Studio ${d.studio?.bagli ? h(d.studio.surum || '') + ' hazır (arka planda)' : 'hazır değil'} · her şey bu bilgisayarda çalışır`, '<button class="dug" data-is="klasor">Veri klasörü</button><button class="dug tehlike" data-is="kapat">Programı kapat</button>')
    + modelUyarisi()
    + `<div class="izgara iki"><div class="kart" id="a-kameralar"><div style="display:flex;align-items:center;margin-bottom:8px"><div class="et" style="flex:1">Kameralar</div>
        ${d.ornek_var ? '<button class="dug kucuk" data-is="ornek">Örnek analizi çalıştır</button> ' : ''}<a class="dug kucuk ana" href="#/kamera/yeni" style="margin-left:6px">Kamera ekle</a></div>
        ${d.kameralar.length ? `<table>${d.kameralar.map(kam).join('')}</table>` : '<div class="not">Henüz kamera yok.</div>'}
        <p class="not">Analiz AugeLab Studio'da, arka planda çalışır; uyarılar başladığı anda buraya düşer. <b>İzlemeyi başlat</b> canlı kamerayı durdurulana kadar izler. Aynı anda bir iş çalışır. Kamera şifresi kaydedilmez.</p></div>
      <div class="kart"><div class="et" style="margin-bottom:8px">İşlem</div><div id="is-karti">${isKarti()}</div></div></div>
    <div class="izgara iki" style="margin-top:14px"><div class="kart form"><div class="et">Tesis ve vardiyalar</div>
        <label>Tesis adı</label><input id="tesis" value="${h(g.tesis)}">
        <label>Vardiyalar (ad, başlangıç, bitiş)</label><div id="vardiyalar">${g.vardiyalar.map(v => `<div class="satir" style="margin-bottom:6px"><input value="${h(v.ad)}"><input type="time" value="${v.bas}"><input type="time" value="${v.bit}"></div>`).join('')}</div>
        <p><button class="dug ana" data-is="genel-kaydet">Kaydet</button></p></div>
      <div class="kart"><div style="display:flex;align-items:center;margin-bottom:6px"><div class="et" style="flex:1">Çıkışlar: PLC, haberleşme, bildirim</div><button class="dug kucuk ana" data-is="baglanti-pencere" data-i="-1">Çıkış ekle</button></div>
        ${g.baglantilar.length ? `<table>${g.baglantilar.map((b, i) => `<tr><td><b>${h(b.ad)}</b> ${b.acik === false ? '<span class="rozet gri">kapalı</span>' : ''}<div class="not">${h(S.katalog.baglanti_turleri[b.tur] || b.tur)} · ${h(baglantiOzeti(b))}</div></td>
          <td style="white-space:nowrap;text-align:right"><button class="dug kucuk" data-is="baglanti-dene" data-i="${i}">Dene</button> <button class="dug kucuk" data-is="baglanti-pencere" data-i="${i}">Düzenle</button> <button class="dug kucuk tehlike" data-is="baglanti-sil" data-i="${i}">Sil</button></td></tr>`).join('')}</table>` : '<div class="not">Henüz çıkış yok. Yeni uyarılar PLC\'ye (Modbus TCP, OPC UA), MQTT sunucusuna, webhook adresine, Slack / Teams kanalına ya da e-postaya iletilebilir.</div>'}
        <p class="not" style="margin-bottom:0">Çıkışlar uyarı başladığında tetiklenir. İkaz lambası, siren ve bildirim içindir; <b>onaylı yangın algılama sisteminin ya da emniyet durdurmasının yerine kullanılamaz</b>. Görüntü gönderilmez; şifreler kaydedilmez, ortam değişkeninden okunur.</p></div></div>
    <div class="kart" style="margin-top:14px"><div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px"><div class="et" style="flex:1">Dış sistemler için API (yalnızca okuma)</div>
        <label class="cip" style="cursor:pointer"><input type="checkbox" data-degis="ag-erisimi" ${g.ag_erisimi ? 'checked' : ''}> Ağdaki sistemler anahtarla okuyabilsin</label>
        ${g.api_anahtari ? '<button class="dug kucuk" data-is="anahtar-yenile">Anahtarı yenile</button>' : ''}</div>
      <table>${Object.entries(S.katalog.api).map(([u, a]) => `<tr><td style="font-family:var(--mono);font-size:12.5px;white-space:nowrap">GET ${h(u)}</td><td class="not">${h(a)}</td></tr>`).join('')}</table>
      <p class="not">Bu bilgisayardan anahtarsız okunur: <code>http://127.0.0.1:${d.dinlenen.port}/api/v1/olaylar</code>. ${g.ag_erisimi ? (d.dinlenen.adres === '0.0.0.0'
        ? `Ağdan: ${d.dinlenen.ag.map(ip => `<code>http://${h(ip)}:${d.dinlenen.port}/api/v1/…</code>`).join(', ') || 'bu bilgisayarın ağ adresi'} · her istekte <code>X-API-Key</code> başlığı gerekir. Ağdan yalnızca bu adresler okunur (olay klipleri ve kareleri dahil); arayüz ve ayarlar açılmaz. Bağlantı şifrelenmez (HTTP): yalnızca güvendiğiniz yerel ağda açın.`
        : '<b>Ağ erişimi kaydedildi; geçerli olması için programı kapatıp yeniden açın.</b>') : (d.dinlenen.adres === '0.0.0.0' ? '<b>Ağ erişimi kapatıldı:</b> ağdan gelen istekler reddediliyor; program yeniden açılana kadar ağ arayüzlerini dinlemeyi sürdürür.' : 'Ağ erişimi kapalı: program yalnızca bu bilgisayarı dinler.')}</p>
      ${g.ag_erisimi && g.api_anahtari ? `<div class="form"><label>API anahtarı (Power BI, Grafana, SCADA gibi sistemlere yazılır; başkasıyla paylaşmayın)</label><input readonly value="${h(g.api_anahtari)}" onfocus="this.select()" style="font-family:var(--mono)"></div>` : ''}</div>`;
  const k = $('#kayit'); if (k) k.scrollTop = k.scrollHeight;
}
const B_ORTAK = [['kullanici', 'Kullanıcı adı (gerekmiyorsa boş)', ''], ['sifre_degiskeni', 'Şifrenin okunacağı ortam değişkeninin adı', 'ör. YANGIN_SIFRE']];
const B_ALAN = {
  webhook: [['adres', 'Adres (olay JSON olarak POST edilir)', 'https://…']],
  slack: [['adres', 'Gelen webhook adresi', 'https://hooks.slack.com/…']],
  teams: [['adres', 'Gelen webhook adresi', 'https://…']],
  mqtt: [['sunucu', 'MQTT sunucusu', 'ör. 10.0.0.5'], ['port', 'Port', 1883, 'sayi'], ['konu', 'Konu', 'yangin/olay'], ['qos', 'QoS (0 ya da 1)', 0, 'sayi'], ...B_ORTAK],
  modbus: [['sunucu', 'PLC adresi', 'ör. 10.0.0.20'], ['port', 'Port', 502, 'sayi'], ['birim', 'Birim (slave) no', 1, 'sayi'],
    ['hedef', 'Yazılacak yer', 'bobin', 'secim', [['bobin', 'Bobin / coil (işlev 5)'], ['yazmac', 'Tutma yazmacı / holding register (işlev 6)']]],
    ['adres', 'Adres (0\'dan başlar; 40001 → 0)', 0, 'sayi'], ['deger', 'Yazılacak değer (bobinde 1 = açık)', 1, 'sayi'], ['darbe_sn', 'Kaç saniye sonra sıfırlansın (0 = sıfırlama)', 5, 'sayi']],
  opcua: [['adres', 'Sunucu adresi', 'opc.tcp://10.0.0.20:4840'], ['dugum', 'Düğüm (node)', 'ns=2;s=YanginAlarm'], ['deger', 'Yazılacak değer', 'true'], ['darbe_sn', 'Kaç saniye sonra sıfırlansın (0 = sıfırlama)', 5, 'sayi'], ...B_ORTAK],
  eposta: [['sunucu', 'SMTP sunucusu', 'smtp.ornek.com'], ['port', 'Port', 587, 'sayi'], ['gonderen', 'Gönderen adres', ''], ['alicilar', 'Alıcılar (virgülle ayırın)', '', 'liste'], ...B_ORTAK],
};
function baglantiOzeti(b) {
  const hedef = { webhook: b.adres, slack: b.adres, teams: b.adres, mqtt: `${b.sunucu}:${b.port} · ${b.konu}`, modbus: `${b.sunucu}:${b.port} · ${b.hedef === 'yazmac' ? 'yazmaç' : 'bobin'} ${b.adres}${b.darbe_sn ? ` · ${b.darbe_sn} sn darbe` : ''}`,
    opcua: `${b.adres} · ${b.dugum}`, eposta: `${b.sunucu} → ${(b.alicilar || []).join(', ')}` }[b.tur] || '';
  const suzgec = [b.en_az_puan ? `risk ≥ ${b.en_az_puan}` : '', b.yalniz_ciddi ? 'yalnız kritik' : '', (b.kategoriler || []).length ? b.kategoriler.map(k => S.katalog.kategoriler[k] || k).join(', ') : '',
    (b.kameralar || []).length ? `${b.kameralar.length} kamera` : ''].filter(Boolean).join(' · ');
  return hedef + (suzgec ? ' · ' + suzgec : ' · bütün olaylar');
}
function baglantiPenceresi(i, tur) {
  const eski = i >= 0 ? S.durum.genel.baglantilar[i] : null;
  const b = eski && (!tur || tur === eski.tur) ? eski : { tur: tur || 'modbus', ad: '', acik: true, en_az_puan: 0, yalniz_ciddi: false, kategoriler: [], kameralar: [] };
  const alan = ([ad, etiket, varsayilan, tip, secenekler]) => {
    const deger = b[ad] ?? (tip === 'sayi' || tip === 'secim' ? varsayilan : '');
    if (tip === 'secim') return `<div><label>${etiket}</label><select data-b="${ad}">${secenekler.map(([v, a]) => `<option value="${v}" ${deger === v ? 'selected' : ''}>${a}</option>`).join('')}</select></div>`;
    return `<div><label>${etiket}</label><input data-b="${ad}" data-tip="${tip || ''}" ${tip === 'sayi' ? 'type="number"' : ''} value="${h(Array.isArray(deger) ? deger.join(', ') : deger)}" placeholder="${h(tip === 'sayi' ? '' : varsayilan)}" autocomplete="off"></div>`;
  };
  const isaretler = (ad, secenekler) => `<div style="display:flex;gap:6px;flex-wrap:wrap">${secenekler.map(([v, a]) => `<label class="cip" style="cursor:pointer;margin:0"><input type="checkbox" data-b-liste="${ad}" value="${h(v)}" ${(b[ad] || []).includes(v) ? 'checked' : ''}>${h(a)}</label>`).join('')}</div>`;
  $('#katman').innerHTML = `<div class="perde"><div class="pencere form" style="width:min(640px,100%)"><h2 style="margin:0 0 4px">${eski ? 'Çıkışı düzenle' : 'Çıkış ekle'}</h2>
    <div class="satir"><div><label>Tür</label><select data-degis="baglanti-tur" data-i="${i}">${Object.entries(S.katalog.baglanti_turleri).map(([t, a]) => `<option value="${t}" ${b.tur === t ? 'selected' : ''}>${h(a)}</option>`).join('')}</select></div>
      <div><label>Ad</label><input data-b="ad" value="${h(b.ad || '')}" placeholder="ör. Depo ikaz sireni"></div></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 8px">${B_ALAN[b.tur].map(alan).join('')}</div>
    <div class="et" style="margin-top:14px">Hangi olaylar iletilsin</div>
    <div class="satir"><div><label>En az risk puanı (0-25)</label><input data-b="en_az_puan" data-tip="sayi" type="number" min="0" max="25" value="${b.en_az_puan ?? 0}"></div>
      <div><label>&nbsp;</label><label class="cip" style="cursor:pointer;margin:0"><input type="checkbox" data-b-kutu="yalniz_ciddi" ${b.yalniz_ciddi ? 'checked' : ''}> Yalnızca kritik</label></div>
      <div><label>&nbsp;</label><label class="cip" style="cursor:pointer;margin:0"><input type="checkbox" data-b-kutu="acik" ${b.acik !== false ? 'checked' : ''}> Açık</label></div></div>
    <label>Kategoriler (hiçbiri seçilmezse hepsi)</label>${isaretler('kategoriler', Object.entries(S.katalog.kategoriler))}
    <label>Kameralar (hiçbiri seçilmezse hepsi)</label>${isaretler('kameralar', S.durum.kameralar.map(k => [k.kod, k.ad])) || '<span class="not">Kamera yok.</span>'}
    ${b.tur === 'modbus' || b.tur === 'opcua' ? '<p class="not">Onaylı yangın algılama sisteminin ya da emniyet durdurmasının yerine kullanmayın.</p>' : ''}
    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px"><button class="dug" data-is="katman-kapat">Vazgeç</button><button class="dug" data-is="baglanti-dene" data-i="form">Deneme iletisi gönder</button>
      <button class="dug ana" data-is="baglanti-kaydet" data-i="${i}">Kaydet</button></div></div></div>`;
}
function baglantiFormu() {
  const b = { tur: $('[data-degis="baglanti-tur"]').value };
  document.querySelectorAll('[data-b]').forEach(e => { const tip = e.dataset.tip; b[e.dataset.b] = tip === 'sayi' ? (e.value === '' ? undefined : +e.value) : tip === 'liste' ? e.value.split(',').map(x => x.trim()).filter(Boolean) : e.value.trim(); });
  document.querySelectorAll('[data-b-kutu]').forEach(e => { b[e.dataset.bKutu] = e.checked; });
  for (const ad of ['kategoriler', 'kameralar']) b[ad] = [...document.querySelectorAll(`[data-b-liste="${ad}"]`)].filter(e => e.checked).map(e => e.value);
  return b;
}

/* ------------------------------------------------------------ Kamera düzenleme */
const KURAL_ALANLARI = { sure_sn: 'süre (sn)', kat: 'kat' };
function kuralAcikMi(k, ayar) {
  if (ayar.kurallar) return ayar.kurallar.some(x => x.kod === k.kod && !x.kapali);
  return !k.bolge_turu || (ayar.bolgeler || []).some(b => b.tur === k.bolge_turu);
}
async function sayfaKamera(kod) {
  const K = S.katalog;
  let ayar = { ad: '', kod: '', kamera: { tur: 'rtsp', marka: 'hikvision', port: 554, kanal: 1, akis: 'alt', kullanici: 'admin' }, bolgeler: [] };
  const yeni = kod === 'yeni';
  if (!yeni) ayar = await api('/api/ayar/' + encodeURIComponent(kod));
  ayar.bolgeler = ayar.bolgeler || [];
  const bilgi = S.durum.kameralar.find(k => k.kod === kod);
  S.cizim = { ayar, noktalar: [], kare: bilgi?.ayar_karesi || bilgi?.son_kare || null };
  const k = ayar.kamera || {};
  const kuralDegeri = (r, alan) => (ayar.kurallar || []).find(x => x.kod === r.kod)?.[alan] ?? r[alan];
  const hassasiyet = ayar.hassasiyet || K.varsayilan_hassasiyet;
  $('#sayfa').innerHTML = ust(yeni ? 'Kamera ekle' : ayar.ad || kod, 'bağlantı, bölgeler ve kurallar', '<a class="dug" href="#/ayarlar">← Ayarlar</a><button class="dug ana" data-is="kamera-kaydet">Kaydet</button>')
    + `<div class="izgara iki"><div><div class="kart" id="k-bolgeler"><div class="et" style="margin-bottom:8px">Bölgeler</div><div id="cizim-alani"></div>
        <div class="form"><div class="satir"><div><label>Çizilen bölgenin türü</label><select id="b-tur">${Object.entries(K.bolge_turleri).map(([t, a]) => `<option value="${t}">${h(a)}</option>`).join('')}</select></div>
          <div><label>Adı</label><input id="b-ad" placeholder="ör. Elektrik odası"></div></div>
          <p style="display:flex;gap:8px;flex-wrap:wrap"><button class="dug ana kucuk" data-is="bolge-kapat">Bölgeyi kapat</button><button class="dug kucuk" data-is="bolge-geri">Son noktayı sil</button>
            <label class="dug kucuk" style="cursor:pointer;margin:0">Görüntü seç<input type="file" accept="image/*" id="kare-dosya" hidden></label></p>
          <p class="not">Köşelere sırayla tıklayın, sonra <b>Bölgeyi kapat</b>. <b>Kritik bölge</b>: alev ya da duman daha çabuk uyarır (elektrik odası, kimyasal deposu). <b>İzinli ateş bölgesi</b>: buradaki alev ve duman sayılmaz (kaynak tezgâhı, fırın, ocak). Kare yoksa kamerayı kaydedip Ayarlar'da <b>Bağlantıyı dene</b>'ye basın.</p></div>
        <div id="bolge-listesi"></div></div></div>
      <div><div class="kart form" id="k-baglanti"><div class="et">Bağlantı</div>
        <div class="satir"><div><label>Kamera adı</label><input id="k-ad" value="${h(ayar.ad || '')}" placeholder="ör. Depo · Kapı 2"></div><div><label>Kısa kod</label><input id="k-kod" value="${h(ayar.kod || (yeni ? '' : kod))}" ${yeni ? '' : 'disabled'} placeholder="depo2"></div></div>
        <label>Bağlantı türü</label><select id="k-tur" data-degis="kamera-tur">${[['rtsp', 'IP kamera / kayıt cihazı – NVR, DVR (RTSP, markaya göre)'], ['onvif', 'ONVIF kamera / kayıt cihazı (adres cihazdan öğrenilir)'], ['http', 'HTTP akışı (MJPEG)'], ['dosya', 'Video dosyası']].map(([t, a]) => `<option value="${t}" ${k.tur === t ? 'selected' : ''}>${a}</option>`).join('')}</select>
        <div data-tur="rtsp"><label>Marka</label><select id="k-marka">${Object.entries(K.markalar).map(([m, a]) => `<option value="${m}" ${k.marka === m && !k.adres ? 'selected' : ''}>${h(a)}</option>`).join('')}<option value="" ${k.adres ? 'selected' : ''}>Diğer (tam adres)</option></select>
          <div class="satir"><div><label>IP adresi</label><input id="k-ip" value="${h(k.ip || '')}"></div><div style="flex:.5"><label>Port</label><input id="k-port" value="${h(k.port ?? 554)}"></div></div>
          <div class="satir"><div><label>Kanal</label><input id="k-kanal" value="${h(k.kanal ?? 1)}"></div><div><label>Akış</label><select id="k-akis"><option value="alt" ${k.akis !== 'ana' ? 'selected' : ''}>Alt akış (önerilen)</option><option value="ana" ${k.akis === 'ana' ? 'selected' : ''}>Ana akış</option></select></div></div>
          <p class="not" style="margin:6px 0 0">Kayıt cihazında (NVR / DVR) IP adresi cihazın adresidir; <b>kanal</b>, kameranın cihazdaki sırasıdır. Her kanal ayrı bir kamera olarak eklenir.</p>
          <div class="satir" style="align-items:flex-end"><div style="flex:.5"><label>Kayıt cihazındaki kanal sayısı</label><input id="k-kanal-sayisi" type="number" min="2" max="64" placeholder="ör. 8"></div>
            <div><button class="dug kucuk" data-is="nvr-kanallari-ekle">Kanalları ayrı kameralar olarak ekle</button></div></div></div>
        <div data-tur="rtsp http"><label>Tam adres (şifre yerine {sifre}; marka seçiliyse boş bırakın)</label><input id="k-adres" value="${h(k.adres || '')}" placeholder="rtsp://{kullanici}:{sifre}@IP:554/...">
          <label>Kullanıcı adı</label><input id="k-kullanici" value="${h(k.kullanici || 'admin')}" autocomplete="off"></div>
        <div data-tur="onvif"><div class="satir"><div><label>Cihazın IP adresi (kamera ya da kayıt cihazı)</label><input id="o-ip" value="${h(k.ip || '')}"></div><div style="flex:.5"><label>ONVIF portu</label><input id="o-port" value="${h(k.tur === 'onvif' ? k.port ?? 80 : 80)}" title="Çoğunlukla 80, 8000, 8080 ya da 8899"></div>
            <div style="flex:none;align-self:flex-end"><button class="dug kucuk" data-is="onvif-kesfet">Ağda ara</button></div></div>
          <div class="satir"><div><label>Kullanıcı adı</label><input id="o-kullanici" value="${h(k.kullanici || 'admin')}" autocomplete="off"></div>
            <div style="flex:.5"><label>Kanal</label><input id="o-kanal" type="number" min="1" value="${h(k.kanal ?? 1)}"></div>
            <div><label>Akış</label><select id="o-akis"><option value="alt" ${k.akis !== 'ana' ? 'selected' : ''}>Alt akış (önerilen)</option><option value="ana" ${k.akis === 'ana' ? 'selected' : ''}>Ana akış</option></select></div></div>
          <label>Profil</label><select id="o-profil"><option value="">Kendiliğinden (yalnızca tek kanallı kamera): seçilen akış</option>${k.tur === 'onvif' && k.profil ? `<option value="${h(k.profil)}" data-ad="${h(k.profil_ad || '')}" data-kaynak="${h(k.kaynak || '')}" selected>${h(k.profil_ad || k.profil)}</option>` : ''}</select>
          <div class="satir" style="align-items:flex-end;margin-top:8px"><div><label>Şifre (yalnızca listelemek için; kaydedilmez)</label><input id="o-sifre" type="password" autocomplete="off"></div>
            <div style="flex:none"><button class="dug kucuk" data-is="onvif-profiller">Kanalları ve profilleri listele</button></div></div>
          <div id="o-sonuc" style="margin-top:8px"></div>
          <p class="not">ONVIF'te akışın adresi cihazdan sorulur; marka seçmek gerekmez. Kayıt cihazında her kanal ayrı bir kamera olarak eklenir ve profili listeden seçmek zorunludur: kamera, seçilen profilin ve görüntü kaynağının belirteciyle hep aynı kanala bağlanır. Cihazda ONVIF açık ve bu kullanıcıya izin verilmiş olmalıdır.</p></div>
        <div data-tur="dosya"><label>Video dosyası (tam yol ya da veri klasörüne göre)</label><input id="k-yol" value="${h(k.yol || '')}" placeholder="videolar/kayit.mp4">
          <label>Kaydın başlangıç zamanı (isteğe bağlı)</label><input id="k-baslangic" type="datetime-local" value="${h((k.baslangic || '').slice(0, 16))}"></div>
        <p class="not">Şifre buraya yazılmaz ve kaydedilmez; bağlanırken Ayarlar sayfasındaki şifre kutusuna yazılır.</p></div>
      <div class="kart form" id="k-kurallar" style="margin-top:14px"><div class="et">Kurallar</div>
        <label>Hassasiyet</label><select id="k-hassasiyet">${Object.entries(K.hassasiyetler).map(([v, a]) => `<option value="${v}" ${hassasiyet === v ? 'selected' : ''}>${h(a)}</option>`).join('')}</select>
        ${Object.entries(K.kategoriler).map(([kat, ad]) => { const rs = K.kurallar.filter(r => r.kategori === kat && r.durum !== 'yok'); return rs.length ? `<div class="et" style="margin-top:14px">${h(ad)}</div>` + rs.map(r => `<div class="kural"><input type="checkbox" data-kural="${r.kod}" ${kuralAcikMi(r, ayar) ? 'checked' : ''} ${r.model_eksik ? 'disabled title="Model dosyası yok: bu kural değerlendirilmez"' : ''} style="margin-top:4px">
          <div style="flex:1"><div class="ad">${h(r.ad)} <span class="rozet ${r.duzey}">${DUZEY[r.duzey]}</span> ${r.model_eksik ? '<span class="rozet kirmizi">Model dosyası yok</span> ' : ''}${r.durum === 'deneysel' ? '<span class="rozet sari">Deneysel</span>' : ''}</div><div class="ac">${r.bolge_turu ? 'Bölge: ' + h(K.bolge_turleri[r.bolge_turu]) + ' · ' : ''}${h(r.aciklama)}</div>
          <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:4px">${Object.entries(KURAL_ALANLARI).filter(([a]) => r[a] != null).map(([a, e]) => `<span class="not">${e} <input type="number" step="any" min="0.5" data-kural-alan="${r.kod}:${a}" value="${kuralDegeri(r, a)}" style="width:64px;padding:2px 6px;border-radius:6px"></span>`).join('')}</div></div></div>`).join('') : ''; }).join('')}</div></div></div>`;
  kameraTuruGoster(); cizimCiz();
}
function kameraTuruGoster() {
  const t = $('#k-tur').value;
  document.querySelectorAll('[data-tur]').forEach(e => { if (e.tagName === 'DIV') e.style.display = e.dataset.tur.split(' ').includes(t) ? '' : 'none'; });
}
function cizimCiz() {
  const C = S.cizim, K = S.katalog;
  const poli = b => `<polygon points="${b.poly.map(p => `${p[0] * 1000},${p[1] * 1000}`).join(' ')}" fill="${b.tur === 'izinli' ? 'rgba(122,211,138,.16)' : 'rgba(255,176,31,.16)'}" stroke="${bolgeRengi(b.tur)}" stroke-width="2" vector-effect="non-scaling-stroke"><title>${h(b.ad)}</title></polygon>`;
  const acik = C.noktalar.length ? `<polyline points="${C.noktalar.map(p => `${p[0] * 1000},${p[1] * 1000}`).join(' ')}" fill="none" stroke="#e0260f" stroke-width="2.5" vector-effect="non-scaling-stroke"/>`
    + C.noktalar.map(p => `<line x1="${p[0] * 1000}" y1="${p[1] * 1000}" x2="${p[0] * 1000}" y2="${p[1] * 1000}" stroke="#e0260f" stroke-width="9" stroke-linecap="round" vector-effect="non-scaling-stroke"/>`).join('') : '';
  $('#cizim-alani').innerHTML = `<div class="sahne cizim" id="cizim">${C.kare ? `<img src="${h(C.kare)}" alt="" style="filter:none">` : '<div class="bosyazi">Kare yok. Kamerayı kaydedip <b>Bağlantıyı dene</b>\'ye basın ya da aşağıdan bir görüntü seçin.<br>Kare olmadan da köşelere tıklayarak bölge çizebilirsiniz.</div>'}
    <svg viewBox="0 0 1000 1000" preserveAspectRatio="none">${C.ayar.bolgeler.map(poli).join('')}${acik}</svg></div>`;
  $('#bolge-listesi').innerHTML = C.ayar.bolgeler.length ? `<table style="margin-top:8px">${C.ayar.bolgeler.map((b, i) => `<tr><td><b>${h(b.ad)}</b> <span class="not">${h(K.bolge_turleri[b.tur] || b.tur)}</span></td><td class="s"><button class="dug kucuk tehlike" data-is="bolge-sil" data-i="${i}">Sil</button></td></tr>`).join('')}</table>` : '';
}
function kameraFormu() {
  const C = S.cizim, v = id => $('#' + id)?.value.trim() ?? '';
  const tur = v('k-tur');
  const kamera = { tur };
  if (tur === 'rtsp') {
    if (v('k-adres')) Object.assign(kamera, { adres: v('k-adres') });
    else Object.assign(kamera, { marka: v('k-marka') || 'hikvision', ip: v('k-ip'), port: +v('k-port') || 554, kanal: +v('k-kanal') || 1, akis: v('k-akis') });
    kamera.kullanici = v('k-kullanici') || 'admin';
  } else if (tur === 'onvif') {
    Object.assign(kamera, { ip: v('o-ip'), port: +v('o-port') || 80, kullanici: v('o-kullanici') || 'admin', kanal: +v('o-kanal') || 1, akis: v('o-akis') });
    const secili = $('#o-profil').selectedOptions[0];
    if (secili?.value) Object.assign(kamera, { profil: secili.value, profil_ad: secili.dataset.ad || secili.textContent }, secili.dataset.kaynak ? { kaynak: secili.dataset.kaynak } : {});
  } else if (tur === 'http') Object.assign(kamera, { adres: v('k-adres'), kullanici: v('k-kullanici') || 'admin' });
  else { kamera.yol = v('k-yol'); if (v('k-baslangic')) kamera.baslangic = v('k-baslangic') + ':00'; }
  const kurallar = [];
  document.querySelectorAll('[data-kural]').forEach(e => {
    if (!e.checked) return;
    const r = { kod: e.dataset.kural };
    document.querySelectorAll(`[data-kural-alan^="${r.kod}:"]`).forEach(a => { const x = parseFloat(a.value); if (!isNaN(x)) r[a.dataset.kuralAlan.split(':')[1]] = x; });
    kurallar.push(r);
  });
  return { ...C.ayar, ad: v('k-ad') || v('k-kod'), kod: v('k-kod'), kamera, kurallar, hassasiyet: v('k-hassasiyet') };
}
function karePenceresi(sonuc) {
  // Bağlantı denemesinde alınan kare: gösterilir, istenirse üstüne bölge çizilir.
  $('#katman').innerHTML = `<div class="perde"><div class="pencere" style="width:min(820px,100%)"><h2 style="margin:0 0 10px">Bağlantı kuruldu</h2>
    <img src="${h(sonuc.kare)}" alt="" style="width:100%;border-radius:12px;display:block;background:#0f1115">
    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px"><button class="dug" data-is="katman-kapat">Kapat</button><a class="dug ana" href="#/kamera/${h(sonuc.kod)}">Bölge çiz</a></div></div></div>`;
}

/* ------------------------------------------------------------ olaylar (tıklama / değişiklik) */
const IS = {
  'studio-kurulum': async e => {
    const tur = e.dataset.tur;
    if (tur === 'kur' && !confirm('Resmî AugeLab Studio kurucusu indirilsin ve çalıştırılsın mı?')) return;
    await api('/api/studio/' + tur, {});
    await durumAl();
    await ciz();
  },
  'model-indir': async () => { await api('/api/model/indir', {}); await durumAl(); shCiz(); },
  'sihirbaz-ac': () => sihirbazAc(),
  'sihirbaz-kapat': () => sihirbazKapat(),
  'hesap-ac': () => {
    const url = S.durum?.hesap_url || 'https://account.augelab.com/';
    if (!window.open(url, 'augelab-hesap', 'width=560,height=820')) window.open(url, '_blank');
  },
  'ses': () => {
    SES.kapali = !SES.kapali;
    try { localStorage.setItem('yangin-siren', SES.kapali ? '0' : '1'); } catch (x) { /* depolama kapalı: seçim bu oturumda geçerli */ }
    rayCiz();
    if (SES.kapali) bildir('Siren kapalı.'); else { sirenCal(0.6); bildir('Siren açık: yeni kritik uyarıda çalar.'); }
  },
  'katman-kapat': () => { $('#katman').innerHTML = ''; const k = konum(); if (k.q.id) { delete k.q.id; history.replaceState(null, '', '#/' + k.yol + (Object.keys(k.q).length ? '?' + new URLSearchParams(k.q) : '')); } },
  'olay-ac': e => { const k = konum(); if (k.yol === 'uyarilar') { git('uyarilar', { ...k.q, id: e.dataset.id }); } else olayCekmecesi(S.olaylar[e.dataset.id]); },
  'olay-git': e => git('uyarilar', { id: e.dataset.id, gun: 90 }),
  'kamera-ac': e => git('analitik', { kamera: e.dataset.kod }),
  'olay-durum': async e => {
    await api('/api/olay/durum', { id: +e.dataset.id, durum: e.dataset.durum, ustlenen: $('#o-ustlenen')?.value || null, not: $('#o-not')?.value ?? null });
    bildir('Olay: ' + DURUM[e.dataset.durum].toLowerCase()); $('#katman').innerHTML = ''; await durumAl(); ciz();
  },
  'gorev-yeni': e => gorevPenceresi(null, e.dataset.olay),
  'gorev-duzenle': e => gorevPenceresi(S.gorevler[e.dataset.id]),
  'gorev-kaydet': async e => {
    const g = { id: e.dataset.id ? +e.dataset.id : undefined, baslik: $('#g-baslik').value, aciklama: $('#g-aciklama').value, sorumlu: $('#g-sorumlu').value, son_tarih: $('#g-tarih').value,
      kamera: $('#g-kamera').value, kural: $('#g-kural').value, bolge: e.dataset.bolge, durum: e.dataset.durum, olaylar: e.dataset.olay ? [+e.dataset.olay] : [] };
    await api('/api/gorev', g); $('#katman').innerHTML = ''; bildir('Görev kaydedildi.'); await durumAl();
    if (konum().yol === 'aksiyonlar') ciz(); else git('aksiyonlar');
  },
  'gorev-durum': async e => { const g = S.gorevler[e.dataset.id]; await api('/api/gorev', { ...g, olaylar: [], durum: e.dataset.durum }); ciz(); },
  'gorev-sil': async e => { if (confirm('Görev silinsin mi? Bağlı olaylar silinmez.')) { await api('/api/gorev/sil', { id: +e.dataset.id }); ciz(); } },
  'analitik-sec': e => { S.analitik[e.dataset.alan] = e.dataset.deger; ciz(); },
  'ornek': async () => { await api('/api/is/ornek', {}); await durumAl(); git('ayarlar'); },
  'is': async e => {
    const sifre = document.querySelector(`[data-sifre="${e.dataset.kod}"]`);
    await api('/api/is/' + e.dataset.tur, { kod: e.dataset.kod, sifre: sifre ? sifre.value : undefined });
    await durumAl(); ciz();
  },
  'is-durdur': async () => { await api('/api/is/durdur', {}); await durumAl(); ciz(); },
  'kamera-sil': async e => { if (confirm(`"${e.dataset.ad}" kamerası, bütün olayları ve klipleriyle silinsin mi? Bu geri alınamaz.`)) { await api('/api/ayar/sil', { kod: e.dataset.kod }); await durumAl(); ciz(); } },
  'klasor': () => api('/api/klasor', {}),
  'kapat': async () => { if (confirm('Program kapatılsın mı? İzleme sürüyorsa durur.')) { await api('/api/kapat', {}); document.body.innerHTML = '<div style="padding:40px;font:16px Segoe UI">Yangın Kamera kapatıldı. Bu sekmeyi kapatabilirsiniz.</div>'; } },
  'genel-kaydet': async () => {
    const vardiyalar = [...document.querySelectorAll('#vardiyalar .satir')].map(s => { const [a, b, c] = s.querySelectorAll('input'); return { ad: a.value, bas: b.value, bit: c.value }; });
    await api('/api/genel', { tesis: $('#tesis').value, vardiyalar }); bildir('Kaydedildi.'); await durumAl();
  },
  'baglanti-pencere': e => baglantiPenceresi(+e.dataset.i),
  'baglanti-kaydet': async e => {
    const liste = [...S.durum.genel.baglantilar], i = +e.dataset.i, b = baglantiFormu();
    if (i >= 0) liste[i] = b; else liste.push(b);
    await api('/api/genel', { baglantilar: liste }); $('#katman').innerHTML = ''; bildir('Çıkış kaydedildi.'); await durumAl(); ciz();
  },
  'baglanti-sil': async e => {
    const liste = [...S.durum.genel.baglantilar];
    if (!confirm(`"${liste[+e.dataset.i].ad}" çıkışı silinsin mi?`)) return;
    liste.splice(+e.dataset.i, 1); await api('/api/genel', { baglantilar: liste }); await durumAl(); ciz();
  },
  'baglanti-dene': async e => {
    const b = e.dataset.i === 'form' ? baglantiFormu() : S.durum.genel.baglantilar[+e.dataset.i];
    bildir('Deneme iletisi gönderiliyor…');
    const r = await api('/api/baglanti/dene', { baglanti: b });
    bildir(r.tamam ? `${b.ad || 'Çıkış'}: ${r.mesaj}` : `Gönderilemedi: ${r.mesaj}`);
  },
  'anahtar-yenile': async () => { if (confirm('Yeni anahtar üretilsin mi? Eski anahtarı kullanan sistemler okuyamaz.')) { await api('/api/genel', { anahtar_yenile: true }); await durumAl(); ciz(); } },
  'bolge-kapat': () => {
    const C = S.cizim;
    if (C.noktalar.length < 3) return bildir('Bölge için en az üç köşe gerekir.');
    const tur = $('#b-tur').value, ayni = C.ayar.bolgeler.filter(b => b.tur === tur).length;
    C.ayar.bolgeler.push({ ad: $('#b-ad').value.trim() || `${S.katalog.bolge_turleri[tur]} ${ayni + 1}`, tur, poly: C.noktalar.map(p => [+p[0].toFixed(4), +p[1].toFixed(4)]) });
    C.noktalar = []; $('#b-ad').value = ''; cizimCiz();
    // bu bölge türünü isteyen kural (kritik bölge) kendiliğinden açılır: bölge çizilip kural kapalı kalmasın
    S.katalog.kurallar.filter(r => r.bolge_turu === tur).forEach(r => { const e = document.querySelector(`[data-kural="${r.kod}"]`); if (e && !e.disabled) e.checked = true; });
  },
  'bolge-geri': () => { S.cizim.noktalar.pop(); cizimCiz(); },
  'bolge-sil': e => { S.cizim.ayar.bolgeler.splice(+e.dataset.i, 1); cizimCiz(); },
  'kamera-kaydet': async () => {
    const ayar = kameraFormu();
    if (!ayar.kod) return bildir('Kısa kod yazın (ör. depo2).');
    const r = await api('/api/ayar', { ayar });
    bildir(['Kamera kaydedildi.', ...(r.notlar || [])].join(' ')); await durumAl(); git('ayarlar');
  },
};
/* Kayıt cihazının kanalları: formdaki bağlantı, her kanal için ayrı bir kamera olarak kaydedilir (bölgeler sonradan çizilir). */
async function kanallariEkle(kanallar, profiller) {
  const taban = kameraFormu();
  if (!taban.kod) return bildir('Önce kısa kodu yazın (ör. nvr1): kanallar nvr1-k1, nvr1-k2… olarak eklenir.');
  if (!taban.kamera.ip) return bildir('Önce kayıt cihazının IP adresini yazın.');
  if (!kanallar.length || kanallar.length > 64) return bildir('Kanal sayısı 2 ile 64 arasında olmalı.');
  const kodlar = kanallar.map(n => `${taban.kod}-k${n}`);
  const varolan = kodlar.filter(k => (S.durum.kameralar || []).some(c => c.kod === k));
  if (varolan.length) return bildir(`Bu kodlarla kamera zaten var: ${varolan.join(', ')}. Üstlerine yazılmaz; başka bir kısa kod yazın.`);
  if (!confirm(`${kanallar.length} kanal ayrı kameralar olarak eklenecek: ${kodlar[0]} … ${kodlar[kodlar.length - 1]}. İşaretli kurallar her kanala kopyalanır; bölgeler her kamerada ayrıca çizilir. Devam edilsin mi?`)) return;
  try {  // sunucu kanalların ayarını üretir (ONVIF'te profil ve kaynak belirteçleriyle) ve hepsini tek işlemde oluşturur: ya hepsi eklenir ya hiçbiri
    const r = await api('/api/ayar/kanallar', { taban, kanallar, ...(profiller ? { profiller } : {}) });
    bildir(`${r.kodlar.length} kanal eklendi.`);
  } catch (x) { await durumAl(); return bildir(x.message); }
  await durumAl(); git('ayarlar');
}
Object.assign(IS, {
  'nvr-kanallari-ekle': () => { const n = +$('#k-kanal-sayisi').value; return kanallariEkle(n >= 2 && n <= 64 ? Array.from({ length: n }, (_, i) => i + 1) : []); },
  'onvif-kesfet': async () => {
    $('#o-sonuc').innerHTML = '<div class="not">Ağda ONVIF cihazı aranıyor (yaklaşık 3 saniye)…</div>';
    const d = await api('/api/onvif/kesfet', {}).catch(x => ({ hata: x.message }));
    $('#o-sonuc').innerHTML = d.hata ? `<div class="not">${h(d.hata)}</div>` : d.cihazlar.length
      ? `<table>${d.cihazlar.map(c => `<tr><td><b>${h(c.ip)}</b>:${c.port}<div class="not">${h([c.ad, c.model].filter(Boolean).join(' · ') || 'ONVIF cihazı')}</div></td><td style="text-align:right"><button class="dug kucuk" data-is="onvif-cihaz-sec" data-ip="${h(c.ip)}" data-port="${c.port}">Seç</button></td></tr>`).join('')}</table>`
      : '<div class="not">Bu ağda yanıt veren ONVIF cihazı bulunamadı. Cihaz başka bir ağdaysa ya da keşfe kapalıysa IP adresini elle yazın.</div>';
  },
  'onvif-cihaz-sec': e => { $('#o-ip').value = e.dataset.ip; $('#o-port').value = e.dataset.port; $('#o-sonuc').innerHTML = '<div class="not">Cihaz seçildi. Kullanıcı adını ve şifreyi yazıp kanalları listeleyin.</div>'; },
  'onvif-profiller': async () => {
    $('#o-sonuc').innerHTML = '<div class="not">Cihaza bağlanılıyor…</div>';
    const d = await api('/api/onvif/profiller', { ip: $('#o-ip').value.trim(), port: +$('#o-port').value || 80, kullanici: $('#o-kullanici').value.trim() || 'admin', sifre: $('#o-sifre').value }).catch(x => ({ hata: x.message }));
    if (d.hata) { $('#o-sonuc').innerHTML = `<div class="uyari-seridi" style="margin:0">${h(d.hata)}</div>`; return; }
    S.onvifProfiller = d.profiller;
    const kanallar = [...new Set(d.profiller.map(p => p.kanal))];
    const cihaz = [d.cihaz?.uretici, d.cihaz?.model].filter(Boolean).join(' ');
    $('#o-sonuc').innerHTML = `<div class="not" style="margin-bottom:4px">${h(cihaz || 'Cihaz')} · ${kanallar.length} kanal · ${d.profiller.length} profil</div>
      <table>${d.profiller.map(p => `<tr><td>Kanal ${p.kanal}</td><td><b>${h(p.ad || p.belirtec)}</b><div class="not">${h(p.kodlama)} ${p.en}×${p.boy}</div></td>
        <td style="text-align:right"><button class="dug kucuk" data-is="onvif-profil-sec" data-belirtec="${h(p.belirtec)}" data-kanal="${p.kanal}" data-kaynak="${h(p.kaynak)}" data-ad="${h(`Kanal ${p.kanal} · ${p.ad || p.belirtec} · ${p.kodlama} ${p.en}×${p.boy}`)}">Seç</button></td></tr>`).join('')}</table>
      ${kanallar.length > 1 ? `<p style="margin:8px 0 0"><button class="dug kucuk" data-is="onvif-kanallari-ekle" data-kanallar="${kanallar.join(',')}">${kanallar.length} kanalı ayrı kameralar olarak ekle</button></p>` : ''}`;
  },
  'onvif-profil-sec': e => {
    const s = $('#o-profil');
    [...s.options].filter(o => o.value).forEach(o => o.remove());
    const o = new Option(e.dataset.ad, e.dataset.belirtec, true, true);
    o.dataset.ad = e.dataset.ad;
    o.dataset.kaynak = e.dataset.kaynak || '';
    s.add(o);
    $('#o-kanal').value = e.dataset.kanal;
    bildir('Profil seçildi. Kaydet\'e basınca kamera bu profille bağlanır.');
  },
  'onvif-kanallari-ekle': e => kanallariEkle(e.dataset.kanallar.split(',').map(Number), S.onvifProfiller || []),
});
document.addEventListener('click', async ev => {
  const e = ev.target.closest('[data-is]');
  if (e) { ev.preventDefault(); try { await IS[e.dataset.is](e); } catch (x) { bildir(x.message); } return; }
  const c = ev.target.closest('#cizim');
  if (c && S.cizim) {
    const r = c.getBoundingClientRect();
    S.cizim.noktalar.push([Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height))]);
    cizimCiz();
  }
});
document.addEventListener('change', ev => {
  const e = ev.target, d = e.dataset.degis;
  if (d === 'donem') { S.gun = +e.value; ciz(); }
  else if (d === 'suzgec') { const k = konum(); if (e.value) k.q[e.dataset.alan] = e.value; else delete k.q[e.dataset.alan]; delete k.q.id; git('uyarilar', k.q); }
  else if (d === 'analitik-kamera') { S.analitik.kamera = e.value; history.replaceState(null, '', '#/analitik'); ciz(); }
  else if (d === 'analitik-kategori') { S.analitik.kategori = e.value; ciz(); }
  else if (d === 'analitik-karsilastir') { S.analitik.karsilastir = e.checked; ciz(); }
  else if (d === 'kamera-tur') kameraTuruGoster();
  else if (d === 'baglanti-tur') baglantiPenceresi(+e.dataset.i, e.value);
  else if (d === 'ag-erisimi') api('/api/genel', { ag_erisimi: e.checked }).then(durumAl).then(ciz).catch(x => bildir(x.message));
  else if (e.id === 'kare-dosya' && e.files[0]) { const o = new FileReader(); o.onload = () => { S.cizim.kare = o.result; cizimCiz(); }; o.readAsDataURL(e.files[0]); }
});
document.addEventListener('keydown', ev => { if (ev.key === 'Escape' && $('#katman').innerHTML) IS['katman-kapat'](); });

/* ------------------------------------------------------------ yönlendirme */
let durumIstegi = null;
function durumAl() {
  // Aynı anda tek durum isteği: süren bir istek varsa onu bekle (yoklamalar üst üste yığılmasın).
  if (!durumIstegi) durumIstegi = durumuYenile().finally(() => { durumIstegi = null; });
  return durumIstegi;
}
const acikImza = () => (S.durum?.kameralar || []).map(k => `${k.kod}:${k.acik}:${k.suruyor}`).join(',');
async function durumuYenile() {
  const modelEksikti = S.durum?.model_indirme?.eksik;
  S.durum = await api('/api/durum');
  rayCiz();
  studioOtoDene(S.durum);
  document.querySelectorAll('[data-studio-kurulum]').forEach(e => { e.outerHTML = studioUyarisi(); });
  document.querySelectorAll('[data-model-indirme]').forEach(e => { e.outerHTML = modelIndirmeSeridi(); });
  if (modelEksikti && !S.durum.model_indirme?.eksik) {  // model indirildi: kurallar artık "model yok" diye işaretlenmez
    S.katalog = await api('/api/katalog');
    bildir('Algılama modeli indirildi ve doğrulandı.');
  }
  sihirbazIzle();
}
async function ciz() {
  const { yol, q } = konum();
  rayCiz();
  S.acikImza = acikImza();
  if (!q.id) $('#katman').innerHTML = '';
  try {
    if (yol === '') await sayfaKontrol();
    else if (yol === 'uyarilar') await sayfaUyarilar(q);
    else if (yol === 'analitik') await sayfaAnalitik(q);
    else if (yol === 'aksiyonlar') await sayfaAksiyonlar();
    else if (yol === 'raporlar') await sayfaRaporlar();
    else if (yol === 'kurallar') await sayfaKurallar();
    else if (yol === 'ayarlar') await sayfaAyarlar();
    else if (yol.startsWith('kamera/')) await sayfaKamera(decodeURIComponent(yol.slice(7)));
    else git('');
  } catch (x) { $('#sayfa').innerHTML = `<div class="bos-durum"><h3>Sayfa açılamadı</h3><p>${h(x.message)}</p></div>`; }
}
async function nabiz() {
  try {
    const once = S.durum?.is;
    await durumAl();
    kritikIzle();
    const simdi = S.durum.is, yol = konum().yol, katmanAcik = !!document.querySelector('.cekmece, .perde');
    if (yol === 'ayarlar' && simdi) { const k = $('#is-karti'); if (k) { k.innerHTML = isKarti(); const y = $('#kayit'); if (y) y.scrollTop = y.scrollHeight; } }
    if (yol === '') karolariYenile();
    const bitti = once?.durum === 'calisiyor' && simdi?.durum !== 'calisiyor';
    if (bitti && !yol.startsWith('kamera/')) {
      bildir(`${simdi.baslik}: ${{ bitti: 'bitti', hata: 'hata verdi', durduruldu: 'durduruldu' }[simdi.durum] || simdi.durum}.`);
      if (!katmanAcik) await ciz();
      if (simdi.tur === 'test' && simdi.durum === 'bitti' && simdi.sonuc?.kare && !katmanAcik) karePenceresi(simdi.sonuc);
    } else if ((yol === '' || yol === 'uyarilar') && !katmanAcik && S.acikImza !== acikImza()) await ciz();  // yeni uyarı geldi ya da kapandı
  } catch (x) { /* program kapanmış olabilir */ }
}
window.addEventListener('hashchange', ciz);
(async () => {
  try {
    [S.durum, S.katalog] = await Promise.all([api('/api/durum'), api('/api/katalog')]);
    SES.son = S.durum.son_kritik || 0;
    await ciz();
    setInterval(nabiz, 2500);
  } catch (x) { $('#sayfa').innerHTML = `<div class="bos-durum"><h3>Program yanıt vermiyor</h3><p>${h(x.message)}</p></div>`; }
})();
