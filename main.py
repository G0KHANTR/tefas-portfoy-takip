from datetime import datetime, timedelta
import calendar
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
from tefas import Crawler

app = Flask(__name__)
CORS(app)

crawler = Crawler()

def get_tefas_price_on_date(fon_kodu, hedef_tarih_str):
    try:
        hedef_tarih = datetime.strptime(hedef_tarih_str, "%Y-%m-%d")
        baslangic = hedef_tarih - timedelta(days=45)
        
        df = crawler.fetch(
            start=baslangic.strftime("%Y-%m-%d"),
            end=hedef_tarih.strftime("%Y-%m-%d"),
            name=fon_kodu.upper()
        )
        
        if df is not None and not df.empty:
            df['date'] = df['date'].astype(str)
            df = df.sort_values(by='date', ascending=False)
            
            gecmis_df = df[df['date'] <= hedef_tarih_str]
            if not gecmis_df.empty:
                bulunan_fiyat = float(gecmis_df.iloc[0]['price'])
                bulunan_tarih = gecmis_df.iloc[0]['date']
                return {"price": round(bulunan_fiyat, 6), "date": bulunan_tarih}
    except Exception as e:
        print(f"Tarihli Fiyat Çekme Hatası ({fon_kodu} - {hedef_tarih_str}): {e}")
    return None

def get_tefas_data_crawler(fon_kodu):
    try:
        bugun = datetime.now()
        baslangic = bugun - timedelta(days=1850)
        
        df = crawler.fetch(
            start=baslangic.strftime("%Y-%m-%d"),
            end=bugun.strftime("%Y-%m-%d"),
            name=fon_kodu.upper()
        )
        
        if df is not None and not df.empty:
            df['date'] = df['date'].astype(str)
            df = df.sort_values(by='date', ascending=False)
            
            guncel_fiyat = float(df.iloc[0]['price'])
            guncel_tarih_str = df.iloc[0]['date']
            guncel_tarih = datetime.strptime(guncel_tarih_str, "%Y-%m-%d")

            def get_price_for_target(year, month, day):
                max_days = calendar.monthrange(year, month)[1]
                target_day = min(day, max_days)
                tarih_str = f"{year:04d}-{month:02d}-{target_day:02d}"
                gecmis_df = df[df['date'] <= tarih_str]
                if not gecmis_df.empty:
                    return float(gecmis_df.iloc[0]['price'])
                return None

            def calc_return_by_months(months_back):
                year = guncel_tarih.year
                month = guncel_tarih.month - months_back
                while month <= 0:
                    month += 12
                    year -= 1
                old_p = get_price_for_target(year, month, guncel_tarih.day)
                if old_p and old_p > 0:
                    return round(((guncel_fiyat - old_p) / old_p) * 100, 2)
                return None

            def calc_return_by_days(days_back):
                tarih_str = (guncel_tarih - timedelta(days=days_back)).strftime("%Y-%m-%d")
                gecmis_df = df[df['date'] <= tarih_str]
                if not gecmis_df.empty:
                    old_p = float(gecmis_df.iloc[0]['price'])
                    if old_p > 0:
                        return round(((guncel_fiyat - old_p) / old_p) * 100, 2)
                return None

            def calc_ybd_return():
                tarih_str = f"{guncel_tarih.year - 1}-12-31"
                gecmis_df = df[df['date'] <= tarih_str]
                if not gecmis_df.empty:
                    old_p = float(gecmis_df.iloc[0]['price'])
                    if old_p > 0:
                        return round(((guncel_fiyat - old_p) / old_p) * 100, 2)
                return None

            title = df.iloc[0].get('title', fon_kodu.upper())

            return {
                "code": fon_kodu.upper(),
                "title": title,
                "price": round(guncel_fiyat, 6),
                "date": guncel_tarih_str,
                "ret_1w": calc_return_by_days(7),
                "ret_1m": calc_return_by_months(1),
                "ret_3m": calc_return_by_months(3),
                "ret_6m": calc_return_by_months(6),
                "ret_ybd": calc_ybd_return(),
                "ret_1y": calc_return_by_months(12),
                "ret_3y": calc_return_by_months(36),
                "ret_5y": calc_return_by_months(60)
            }
    except Exception as e:
        print(f"TEFAS Crawler Hatası ({fon_kodu}): {e}")
    return None

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TEFAS Portföy Takip & Analiz</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          fontFamily: {
            sans: ['"Plus Jakarta Sans"', 'sans-serif'],
          },
          colors: {
            dark: {
              bg: '#0b0f17',
              card: '#151c28',
              border: '#222d3d',
              input: '#1a2332'
            }
          }
        }
      }
    }
  </script>
  <style>
    body { background-color: #0b0f17; color: #f1f5f9; font-family: 'Plus Jakarta Sans', sans-serif; }
    .glass-card {
      background: rgba(21, 28, 40, 0.75);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .pos { color: #10b981; font-weight: 700; }
    .neg { color: #f43f5e; font-weight: 700; }
    .draggable-modal {
      position: fixed;
      z-index: 1000;
      top: 100px;
      left: calc(50% - 280px);
      width: 560px;
      max-width: 95vw;
    }
  </style>
</head>
<body class="min-h-screen pb-12 antialiased">

<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8">
  
  <!-- Header -->
  <header class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
    <div>
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/20 text-white font-extrabold text-xl">
          T
        </div>
        <div>
          <h1 class="text-2xl font-extrabold text-white tracking-tight">TEFAS <span class="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-400">Portföy Takip</span></h1>
          <p class="text-xs text-slate-400 font-medium">Canlı Piyasa ve Kişisel Varlık Analizi</p>
        </div>
      </div>
    </div>
    <button onclick="portfoyuGuncelle()" class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-blue-400 border border-slate-700/50 text-sm font-semibold transition-all shadow-sm active:scale-95">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
      Fiyatları Canlı Güncelle
    </button>
  </header>

  <!-- Özet Kartları -->
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
    <div class="glass-card rounded-2xl p-5 shadow-lg">
      <div class="flex justify-between items-center mb-2">
        <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Toplam Portföy Değeri</span>
        <div class="p-2 rounded-lg bg-blue-500/10 text-blue-400">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
        </div>
      </div>
      <h3 class="text-2xl font-bold text-white" id="toplamDeger">0.00 ₺</h3>
    </div>

    <div class="glass-card rounded-2xl p-5 shadow-lg">
      <div class="flex justify-between items-center mb-2">
        <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Yatırılan Anapara</span>
        <div class="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
        </div>
      </div>
      <h3 class="text-2xl font-bold text-white" id="toplamMaliyet">0.00 ₺</h3>
    </div>

    <div class="glass-card rounded-2xl p-5 shadow-lg">
      <div class="flex justify-between items-center mb-2">
        <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Toplam Kâr / Zarar</span>
        <div class="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg>
        </div>
      </div>
      <h3 class="text-2xl font-bold text-slate-300" id="toplamKar">0.00 ₺</h3>
    </div>

    <div class="glass-card rounded-2xl p-5 shadow-lg">
      <div class="flex justify-between items-center mb-2">
        <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Toplam Kâr Oranı</span>
        <div class="p-2 rounded-lg bg-purple-500/10 text-purple-400">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
        </div>
      </div>
      <h3 class="text-2xl font-bold text-slate-300" id="toplamKarYuzde">%0.00</h3>
    </div>
  </div>

  <!-- İşlem Formu -->
  <div class="glass-card rounded-2xl p-6 shadow-xl mb-8">
    <h2 class="text-lg font-bold text-white mb-4 flex items-center gap-2">
      <span class="w-2 h-2 rounded-full bg-blue-500"></span> Yeni İşlem Ekle
    </h2>
    <form id="islemForm" onsubmit="islemEkle(event)" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-4">
      <div class="lg:col-span-2">
        <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">İşlem Tarihi</label>
        <input type="date" id="islemTarih" class="w-full bg-dark-input border border-slate-700/60 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all" required>
      </div>

      <div class="lg:col-span-2">
        <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Fon Kodu</label>
        <input type="text" id="islemKod" class="w-full bg-dark-input border border-slate-700/60 rounded-xl px-3.5 py-2.5 text-sm text-white uppercase placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all" placeholder="Örn: MAC" required>
      </div>

      <div class="lg:col-span-2">
        <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">İşlem Tipi</label>
        <select id="islemTip" class="w-full bg-dark-input border border-slate-700/60 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all">
          <option value="AL">Alım</option>
          <option value="SAT">Satım</option>
        </select>
      </div>

      <div class="lg:col-span-2">
        <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Adet</label>
        <input type="number" step="0.000001" id="islemAdet" class="w-full bg-dark-input border border-slate-700/60 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all" placeholder="0.00" required>
      </div>

      <div class="lg:col-span-2">
        <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Birim Fiyat (₺)</label>
        <input type="number" step="0.000001" id="islemFiyat" class="w-full bg-dark-input border border-slate-700/60 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all" placeholder="Otomatik Fiyat">
      </div>

      <div class="lg:col-span-2 flex items-end">
        <button type="submit" id="kaydetBtn" class="w-full py-2.5 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-sm rounded-xl shadow-lg shadow-blue-600/25 transition-all active:scale-95">
          İşlemi Kaydet
        </button>
      </div>
    </form>
  </div>

  <!-- Portföy Tablosu -->
  <div class="glass-card rounded-2xl p-6 shadow-xl mb-8 overflow-hidden">
    <div class="flex justify-between items-center mb-6">
      <h2 class="text-lg font-bold text-white flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-indigo-500"></span> Mevcut Fon Varlıkları
      </h2>
      <span class="text-xs text-slate-400 font-medium">Fon koduna tıklayarak TEFAS detaylarını görebilirsiniz</span>
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-left text-sm border-collapse">
        <thead>
          <tr class="border-b border-slate-700/60 text-xs font-bold uppercase tracking-wider text-slate-400">
            <th class="pb-3 px-3">Fon Kodu</th>
            <th class="pb-3 px-3">Adet</th>
            <th class="pb-3 px-3">Ort. Maliyet</th>
            <th class="pb-3 px-3">Anlık Fiyat</th>
            <th class="pb-3 px-3">Toplam Değer</th>
            <th class="pb-3 px-3">Net Kâr / Zarar (₺)</th>
            <th class="pb-3 px-3">Maliyete Göre Kâr (%)</th>
            <th class="pb-3 px-3">Tutma Süresi</th>
          </tr>
        </thead>
        <tbody id="portfoyTablosu" class="divide-y divide-slate-800/60 text-slate-200">
        </tbody>
      </table>
    </div>
  </div>

  <!-- Geçmiş İşlem Kayıtları -->
  <div class="glass-card rounded-2xl p-6 shadow-xl">
    <h2 class="text-lg font-bold text-white mb-4 flex items-center gap-2">
      <span class="w-2 h-2 rounded-full bg-purple-500"></span> Geçmiş İşlem Kayıtları
    </h2>
    <div id="gecmisQuotes" class="space-y-3"></div>
  </div>

</div>

<!-- Sürüklenebilir TEFAS Modal -->
<div id="tefasModal" class="hidden draggable-modal glass-card rounded-2xl shadow-2xl border border-slate-700/80 overflow-hidden">
  <div id="modalHeader" class="bg-slate-800/90 px-6 py-4 flex justify-between items-center cursor-move border-b border-slate-700/60">
    <div class="flex items-center gap-2">
      <span class="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse"></span>
      <h3 class="font-bold text-white text-base" id="modalFonBaslik">Fon Detayları</h3>
    </div>
    <button onclick="tefasModalKapat()" class="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-700/50 transition-all">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
    </button>
  </div>
  <div class="p-6">
    <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">TEFAS Resmi Dönemsel Getirileri (%):</p>
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center mb-3">
      <div class="bg-dark-input p-3 rounded-xl border border-slate-700/50">
        <span class="block text-xs text-slate-400 font-medium mb-1">Son 1 Hafta</span>
        <div id="m_ret_1w" class="text-sm font-bold">-</div>
      </div>
      <div class="bg-dark-input p-3 rounded-xl border border-slate-700/50">
        <span class="block text-xs text-slate-400 font-medium mb-1">Son 1 Ay</span>
        <div id="m_ret_1m" class="text-sm font-bold">-</div>
      </div>
      <div class="bg-dark-input p-3 rounded-xl border border-slate-700/50">
        <span class="block text-xs text-slate-400 font-medium mb-1">Son 3 Ay</span>
        <div id="m_ret_3m" class="text-sm font-bold">-</div>
      </div>
      <div class="bg-dark-input p-3 rounded-xl border border-slate-700/50">
        <span class="block text-xs text-slate-400 font-medium mb-1">Son 6 Ay</span>
        <div id="m_ret_6m" class="text-sm font-bold">-</div>
      </div>
    </div>
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
      <div class="bg-dark-input p-3 rounded-xl border border-slate-700/50">
        <span class="block text-xs text-slate-400 font-medium mb-1">Yılbaşı (YBD)</span>
        <div id="m_ret_ybd" class="text-sm font-bold">-</div>
      </div>
      <div class="bg-dark-input p-3 rounded-xl border border-slate-700/50">
        <span class="block text-xs text-slate-400 font-medium mb-1">Son 1 Yıl</span>
        <div id="m_ret_1y" class="text-sm font-bold">-</div>
      </div>
      <div class="bg-dark-input p-3 rounded-xl border border-slate-700/50">
        <span class="block text-xs text-slate-400 font-medium mb-1">Son 3 Yıl</span>
        <div id="m_ret_3y" class="text-sm font-bold">-</div>
      </div>
      <div class="bg-dark-input p-3 rounded-xl border border-slate-700/50">
        <span class="block text-xs text-slate-400 font-medium mb-1">Son 5 Yıl</span>
        <div id="m_ret_5y" class="text-sm font-bold">-</div>
      </div>
    </div>
  </div>
</div>

<script>
  let islemler = JSON.parse(localStorage.getItem('tefas_islemler')) || [];
  let tefasFiyatlar = {};

  document.getElementById('islemTarih').valueAsDate = new Date();

  function formatMoney(num) {
    return (Math.round(num * 100) / 100).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function formatPercent(num) {
    return (Math.round(num * 100) / 100).toFixed(2);
  }

  async function islemEkle(e) {
    e.preventDefault();
    const btn = document.getElementById("kaydetBtn");
    const tarih = document.getElementById("islemTarih").value;
    const kod = document.getElementById("islemKod").value.toUpperCase().trim();
    const tip = document.getElementById("islemTip").value;
    const adet = parseFloat(document.getElementById("islemAdet").value);
    let fiyat = parseFloat(document.getElementById("islemFiyat").value);

    if (!fiyat || isNaN(fiyat)) {
      btn.innerText = "Fiyat Çekiliyor...";
      btn.disabled = true;
      try {
        const res = await fetch(`/api/fon_tarihli_fiyat?kod=${kod}&tarih=${tarih}`);
        const data = await res.json();
        if (data.status === 'success') {
          fiyat = data.data.price;
        } else {
          alert("Seçilen tarihe ait TEFAS fiyatı bulunamadı. Lütfen elle fiyat giriniz.");
          btn.innerText = "İşlemi Kaydet";
          btn.disabled = false;
          return;
        }
      } catch(err) {
        alert("Veri bağlantı hatası oluştu.");
        btn.innerText = "İşlemi Kaydet";
        btn.disabled = false;
        return;
      }
      btn.innerText = "İşlemi Kaydet";
      btn.disabled = false;
    }

    const yeniIslem = { id: Date.now(), tarih, kod, tip, adet, fiyat };
    islemler.push(yeniIslem);
    localStorage.setItem('tefas_islemler', JSON.stringify(islemler));
    document.getElementById("islemForm").reset();
    document.getElementById('islemTarih').valueAsDate = new Date();
    portfoyuGuncelle();
  }

  function islemSil(id) {
    islemler = islemler.filter(x => x.id !== id);
    localStorage.setItem('tefas_islemler', JSON.stringify(islemler));
    portfoyuGuncelle();
  }

  async function portfoyuGuncelle() {
    const fonKodlari = [...new Set(islemler.map(x => x.kod))];
    const tbody = document.getElementById("portfoyTablosu");
    
    if (fonKodlari.length > 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-slate-400 text-center py-6">TEFAS güncel verileri çekiliyor...</td></tr>`;
    }

    for (const kod of fonKodlari) {
      try {
        const res = await fetch(`/api/fon?kod=${kod}`);
        const data = await res.json();
        if (data.status === 'success') {
          tefasFiyatlar[kod] = data.data;
        }
      } catch(e) { console.error(e); }
    }

    tablolariCiz();
  }

  function tefasModalAc(kod) {
    const data = tefasFiyatlar[kod];
    if (data) {
      document.getElementById("modalFonBaslik").innerText = `${data.code} - ${data.title || ''}`;
      
      const fmt = (val) => {
        if (val === null || val === undefined) return `<span class="text-slate-500">-</span>`;
        return `<span class="${val >= 0 ? 'pos' : 'neg'}">%${val > 0 ? '+' : ''}${formatPercent(val)}</span>`;
      };
      
      document.getElementById("m_ret_1w").innerHTML = fmt(data.ret_1w);
      document.getElementById("m_ret_1m").innerHTML = fmt(data.ret_1m);
      document.getElementById("m_ret_3m").innerHTML = fmt(data.ret_3m);
      document.getElementById("m_ret_6m").innerHTML = fmt(data.ret_6m);
      document.getElementById("m_ret_ybd").innerHTML = fmt(data.ret_ybd);
      document.getElementById("m_ret_1y").innerHTML = fmt(data.ret_1y);
      document.getElementById("m_ret_3y").innerHTML = fmt(data.ret_3y);
      document.getElementById("m_ret_5y").innerHTML = fmt(data.ret_5y);
      
      document.getElementById('tefasModal').classList.remove('hidden');
    }
  }

  function tefasModalKapat() {
    document.getElementById('tefasModal').classList.add('hidden');
  }

  function tablolariCiz() {
    islemler.sort((a, b) => new Date(b.tarih) - new Date(a.tarih));

    const fonGruplari = {};
    islemler.forEach(i => {
      if (!fonGruplari[i.kod]) fonGruplari[i.kod] = [];
      fonGruplari[i.kod].push(i);
    });

    const quotesContainer = document.getElementById("gecmisQuotes");
    let quotesHtml = "";
    const fonKodlari = Object.keys(fonGruplari);

    if (fonKodlari.length === 0) {
      quotesContainer.innerHTML = `<div class="text-slate-500 text-center py-4">Henüz kayıtlı işlem bulunmuyor.</div>`;
    } else {
      fonKodlari.forEach((kod) => {
        const grupIslemler = fonGruplari[kod];
        const collapseId = `quoteCollapse_${kod}`;
        let tabloSatirlari = "";

        grupIslemler.forEach(i => {
          tabloSatirlari += `
            <tr class="hover:bg-slate-800/40 border-b border-slate-800/40">
              <td class="py-2 px-3 text-slate-300">${i.tarih}</td>
              <td class="py-2 px-3"><span class="px-2 py-0.5 rounded-md text-xs font-bold ${i.tip === 'AL' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}">${i.tip}</span></td>
              <td class="py-2 px-3 text-slate-300">${i.adet}</td>
              <td class="py-2 px-3 text-slate-300">${formatMoney(i.fiyat)} ₺</td>
              <td class="py-2 px-3 text-slate-300">${formatMoney(i.adet * i.fiyat)} ₺</td>
              <td class="py-2 px-3"><button onclick="islemSil(${i.id})" class="text-rose-400 hover:text-rose-300 text-xs hover:underline">Sil</button></td>
            </tr>`;
        });

        quotesHtml += `
          <div class="bg-dark-input border border-slate-800 rounded-xl overflow-hidden">
            <button onclick="document.getElementById('${collapseId}').classList.toggle('hidden')" class="w-full px-4 py-3 flex justify-between items-center text-left hover:bg-slate-800/50 transition-all">
              <div class="flex items-center gap-2">
                <span class="px-2.5 py-1 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 font-bold text-xs">${kod}</span>
                <span class="text-sm font-semibold text-slate-200">İşlem Kayıtları (${grupIslemler.length})</span>
              </div>
              <span class="text-xs text-slate-400">Göster / Gizle</span>
            </button>
            <div id="${collapseId}" class="hidden p-3 border-t border-slate-800/60 bg-slate-900/40">
              <div class="overflow-x-auto">
                <table class="w-full text-left text-xs">
                  <thead>
                    <tr class="text-slate-400 border-b border-slate-800">
                      <th class="pb-2 px-3">Tarih</th><th class="pb-2 px-3">Tip</th><th class="pb-2 px-3">Adet</th><th class="pb-2 px-3">Fiyat</th><th class="pb-2 px-3">Toplam</th><th class="pb-2 px-3">İşlem</th>
                    </tr>
                  </thead>
                  <tbody>${tabloSatirlari}</tbody>
                </table>
              </div>
            </div>
          </div>`;
      });
      quotesContainer.innerHTML = quotesHtml;
    }

    let portfoy = {};
    const kronolojikIslemler = [...islemler].sort((a, b) => new Date(a.tarih) - new Date(b.tarih));
    const bugunMs = new Date().getTime();

    kronolojikIslemler.forEach(i => {
      if (!portfoy[i.kod]) {
        portfoy[i.kod] = { adet: 0, toplamMaliyet: 0, zamanAgridikliGun: 0 };
      }
      
      const islemTarihiMs = new Date(i.tarih).getTime();
      const gecenGun = Math.max(0, Math.floor((bugunMs - islemTarihiMs) / (1000 * 60 * 60 * 24)));

      if (i.tip === 'AL') {
        const eskiAdet = portfoy[i.kod].adet;
        const yeniAdet = eskiAdet + i.adet;
        
        portfoy[i.kod].zamanAgridikliGun = ((eskiAdet * portfoy[i.kod].zamanAgridikliGun) + (i.adet * gecenGun)) / (yeniAdet || 1);
        portfoy[i.kod].adet = yeniAdet;
        portfoy[i.kod].toplamMaliyet += (i.adet * i.fiyat);
      } else if (i.tip === 'SAT') {
        const ortMaliyet = portfoy[i.kod].toplamMaliyet / (portfoy[i.kod].adet || 1);
        portfoy[i.kod].adet -= i.adet;
        portfoy[i.kod].toplamMaliyet -= (i.adet * ortMaliyet);
      }
    });

    let portfoyHtml = "";
    let genMaliyet = 0;
    let genDeger = 0;

    Object.keys(portfoy).forEach(kod => {
      const pos = portfoy[kod];
      if (pos.adet > 0.00001) {
        const ortMaliyet = pos.toplamMaliyet / pos.adet;
        const tefasData = tefasFiyatlar[kod] || { price: ortMaliyet };
        
        const guncelFiyat = tefasData.price;
        const guncelDeger = pos.adet * guncelFiyat;
        
        const karTL = guncelDeger - pos.toplamMaliyet;
        const karYuzde = ortMaliyet > 0 ? ((guncelFiyat - ortMaliyet) / ortMaliyet) * 100 : 0;

        genMaliyet += pos.toplamMaliyet;
        genDeger += guncelDeger;

        const gunSayisi = Math.round(pos.zamanAgridikliGun);

        portfoyHtml += `
          <tr class="hover:bg-slate-800/40 transition-colors">
            <td class="py-3 px-3">
              <button onclick="tefasModalAc('${kod}')" class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/30 text-blue-400 font-bold text-xs transition-all">
                🔍 ${kod}
              </button>
            </td>
            <td class="py-3 px-3">${pos.adet}</td>
            <td class="py-3 px-3">${formatMoney(ortMaliyet)} ₺</td>
            <td class="py-3 px-3">${formatMoney(guncelFiyat)} ₺</td>
            <td class="py-3 px-3 font-semibold text-white">${formatMoney(guncelDeger)} ₺</td>
            <td class="py-3 px-3 ${karTL >= 0 ? 'pos' : 'neg'}">${karTL > 0 ? '+' : ''}${formatMoney(karTL)} ₺</td>
            <td class="py-3 px-3 ${karYuzde >= 0 ? 'pos' : 'neg'}">%${karYuzde > 0 ? '+' : ''}${formatPercent(karYuzde)}</td>
            <td class="py-3 px-3"><span class="px-2.5 py-1 rounded-md text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700">${gunSayisi} Gün</span></td>
          </tr>`;
      }
    });

    document.getElementById("portfoyTablosu").innerHTML = portfoyHtml || `<tr><td colspan="8" class="text-slate-500 text-center py-6">Portföyünüzde henüz aktif fon bulunmuyor.</td></tr>`;

    const genKarTL = genDeger - genMaliyet;
    const genKarYuzde = genMaliyet > 0 ? (genKarTL / genMaliyet) * 100 : 0;

    document.getElementById("toplamDeger").innerText = formatMoney(genDeger) + " ₺";
    document.getElementById("toplamMaliyet").innerText = formatMoney(genMaliyet) + " ₺";

    const elKar = document.getElementById("toplamKar");
    elKar.innerText = (genKarTL > 0 ? "+" : "") + formatMoney(genKarTL) + " ₺";
    elKar.className = "text-2xl font-bold " + (genKarTL >= 0 ? "pos" : "neg");

    const elKarYuzde = document.getElementById("toplamKarYuzde");
    elKarYuzde.innerText = "%" + (genKarYuzde > 0 ? "+" : "") + formatPercent(genKarYuzde);
    elKarYuzde.className = "text-2xl font-bold " + (genKarYuzde >= 0 ? "pos" : "neg");
  }

  // Draggable Modal logic
  const modalDialog = document.getElementById('tefasModal');
  const modalHeader = document.getElementById('modalHeader');
  let isDragging = false, offsetRight = 0, offsetBottom = 0;

  modalHeader.addEventListener('mousedown', (e) => {
    isDragging = true;
    offsetRight = e.clientX - modalDialog.offsetLeft;
    offsetBottom = e.clientY - modalDialog.offsetTop;
  });

  document.addEventListener('mousemove', (e) => {
    if (isDragging) {
      modalDialog.style.left = (e.clientX - offsetRight) + 'px';
      modalDialog.style.top = (e.clientY - offsetBottom) + 'px';
    }
  });

  document.addEventListener('mouseup', () => { isDragging = false; });

  portfoyuGuncelle();
</script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/fon')
def api_fon():
    kod = request.args.get('kod', '').strip()
    result = get_tefas_data_crawler(kod)
    if result:
        return jsonify({"status": "success", "data": result})
    return jsonify({"status": "error", "message": "Fon verisi alınamadı"}), 404

@app.route('/api/fon_tarihli_fiyat')
def api_fon_tarihli_fiyat():
    kod = request.args.get('kod', '').strip()
    tarih = request.args.get('tarih', '').strip()
    result = get_tefas_price_on_date(kod, tarih)
    if result:
        return jsonify({"status": "success", "data": result})
    return jsonify({"status": "error", "message": "Tarihli fiyat verisi alınamadı"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)