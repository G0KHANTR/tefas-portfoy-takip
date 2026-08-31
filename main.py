from flask import Flask, jsonify, request, render_template_string, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
from tefas import Crawler
from datetime import datetime, timedelta
import calendar
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gizli-anahtar-buraya-geleccek-12345'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tefas_portfoy.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
CORS(app)

tefas = Crawler()

# ==================== VERİTABANI MODELLERİ ====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tarih = db.Column(db.String(10), nullable=False)
    kod = db.Column(db.String(10), nullable=False)
    tip = db.Column(db.String(5), nullable=False) # AL / SAT
    adet = db.Column(db.Float, nullable=False)
    fiyat = db.Column(db.Float, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Veritabanını oluştur ve Varsayılan Admin Hesabı Ekle
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', is_admin=True)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

# ==================== TEFAS YARDIMCI FONKSİYONLARI ====================

def get_tefas_price_on_date(fon_kodu, hedef_tarih_str):
    try:
        hedef_tarih = datetime.strptime(hedef_tarih_str, "%Y-%m-%d")
        baslangic = hedef_tarih - timedelta(days=10)
        df = tefas.fetch(start=baslangic.strftime("%Y-%m-%d"), end=hedef_tarih_str, name=fon_kodu.upper())
        if df is not None and not df.empty:
            df['date'] = df['date'].astype(str)
            df = df.sort_values(by='date', ascending=False)
            gecmis_df = df[df['date'] <= hedef_tarih_str]
            if not gecmis_df.empty:
                return {"price": round(float(gecmis_df.iloc[0]['price']), 6), "date": gecmis_df.iloc[0]['date']}
    except Exception as e:
        print(f"Hata: {e}")
    return None

def get_tefas_data_crawler(fon_kodu):
    try:
        bugun = datetime.now()
        baslangic = bugun - timedelta(days=1850)
        df = tefas.fetch(start=baslangic.strftime("%Y-%m-%d"), end=bugun.strftime("%Y-%m-%d"), name=fon_kodu.upper())
        if df is not None and not df.empty:
            df['date'] = df['date'].astype(str)
            df = df.sort_values(by='date', ascending=False)
            guncel_fiyat = float(df.iloc[0]['price'])
            guncel_tarih_str = df.iloc[0]['date']
            guncel_tarih = datetime.strptime(guncel_tarih_str, "%Y-%m-%d")

            def get_price_for_target(year, month, day):
                max_days = calendar.monthrange(year, month)[1]
                tarih_str = f"{year:04d}-{month:02d}-{min(day, max_days):02d}"
                gecmis_df = df[df['date'] <= tarih_str]
                return float(gecmis_df.iloc[0]['price']) if not gecmis_df.empty else None

            def calc_return_by_months(m):
                year, month = guncel_tarih.year, guncel_tarih.month - m
                while month <= 0: month += 12; year -= 1
                old_p = get_price_for_target(year, month, guncel_tarih.day)
                return round(((guncel_fiyat - old_p) / old_p) * 100, 2) if old_p else None

            def calc_return_by_days(d):
                tarih_str = (guncel_tarih - timedelta(days=d)).strftime("%Y-%m-%d")
                gecmis_df = df[df['date'] <= tarih_str]
                if not gecmis_df.empty:
                    old_p = float(gecmis_df.iloc[0]['price'])
                    return round(((guncel_fiyat - old_p) / old_p) * 100, 2) if old_p > 0 else None
                return None

            return {
                "code": fon_kodu.upper(),
                "title": df.iloc[0].get('title', fon_kodu.upper()),
                "price": round(guncel_fiyat, 6),
                "date": guncel_tarih_str,
                "market_cap": df.iloc[0].get('market_cap', 0),
                "investors": df.iloc[0].get('number_of_investors', 0),
                "ret_1w": calc_return_by_days(7),
                "ret_1m": calc_return_by_months(1),
                "ret_3m": calc_return_by_months(3),
                "ret_6m": calc_return_by_months(6),
                "ret_ybd": calc_return_by_months((guncel_tarih.month - 1)),
                "ret_1y": calc_return_by_months(12),
                "ret_3y": calc_return_by_months(36),
                "ret_5y": calc_return_by_months(60)
            }
    except Exception as e:
        print(f"TEFAS Hata: {e}")
    return None

# ==================== HTML ŞABLONLARI ====================

AUTH_TEMPLATE = """<!DOCTYPE html>
<html lang="tr" class="dark">
<head>
  <meta charset="UTF-8"><title>{{ title }} - TEFAS Portföy</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&display=swap" rel="stylesheet">
</head>
<body class="bg-[#0b0f17] text-white font-['Plus_Jakarta_Sans'] min-h-screen flex items-center justify-center p-4">
  <div class="max-w-md w-full bg-[#151c28] border border-slate-800 rounded-2xl p-8 shadow-2xl">
    <h2 class="text-2xl font-extrabold text-center mb-6">{{ title }}</h2>
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        {% for msg in messages %}<div class="bg-rose-500/10 border border-rose-500/20 text-rose-400 p-3 rounded-xl mb-4 text-xs">{{ msg }}</div>{% endfor %}
      {% endif %}
    {% endwith %}
    <form method="POST" class="space-y-4">
      <div>
        <label class="block text-xs font-semibold text-slate-400 uppercase mb-2">Kullanıcı Adı</label>
        <input type="text" name="username" class="w-full bg-[#1a2332] border border-slate-700/60 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500" required>
      </div>
      <div>
        <label class="block text-xs font-semibold text-slate-400 uppercase mb-2">Parola</label>
        <input type="password" name="password" class="w-full bg-[#1a2332] border border-slate-700/60 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500" required>
      </div>
      <button type="submit" class="w-full py-3 bg-blue-600 hover:bg-blue-500 rounded-xl font-bold text-sm transition-all">{{ button_text }}</button>
    </form>
    <div class="mt-6 text-center text-xs text-slate-400">
      {% if is_login %} Hesabınız yok mu? <a href="/register" class="text-blue-400 hover:underline">Kayıt Ol</a>
      {% else %} Zaten hesabınız var mı? <a href="/login" class="text-blue-400 hover:underline">Giriş Yap</a> {% endif %}
    </div>
  </div>
</body>
</html>"""

MAIN_TEMPLATE = """<!DOCTYPE html>
<html lang="tr" class="dark">
<head>
  <meta charset="UTF-8"><title>TEFAS Portföy Takip</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&display=swap" rel="stylesheet">
  <style>
    body { background-color: #0b0f17; color: #f1f5f9; font-family: 'Plus Jakarta Sans', sans-serif; }
    .glass-card { background: rgba(21, 28, 40, 0.75); backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.08); }
    .pos { color: #10b981; font-weight: 700; } .neg { color: #f43f5e; font-weight: 700; }
  </style>
</head>
<body class="min-h-screen pb-12">
<div class="max-w-7xl mx-auto px-4 pt-8">
  <header class="flex justify-between items-center mb-8">
    <div class="flex items-center gap-3">
      <div class="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center font-extrabold text-xl">T</div>
      <div>
        <h1 class="text-2xl font-extrabold">TEFAS <span class="text-blue-400">Portföy Takip</span></h1>
        <p class="text-xs text-slate-400">Hoş geldin, <span class="text-white font-bold">{{ current_user.username }}</span></p>
      </div>
    </div>
    <div class="flex items-center gap-3">
      {% if current_user.is_admin %}
      <a href="/admin" class="px-4 py-2 bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/30 text-purple-400 rounded-xl text-xs font-bold transition-all">Admin Paneli</a>
      {% endif %}
      <a href="/logout" class="px-4 py-2 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 rounded-xl text-xs font-bold transition-all">Çıkış Yap</a>
    </div>
  </header>

  <!-- Özet Kartları -->
  <div class="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-8">
    <div class="glass-card rounded-2xl p-5"><span class="text-xs font-semibold text-slate-400 uppercase">Toplam Değer</span><h3 class="text-2xl font-bold" id="toplamDeger">0.00 ₺</h3></div>
    <div class="glass-card rounded-2xl p-5"><span class="text-xs font-semibold text-slate-400 uppercase">Anapara</span><h3 class="text-2xl font-bold" id="toplamMaliyet">0.00 ₺</h3></div>
    <div class="glass-card rounded-2xl p-5"><span class="text-xs font-semibold text-slate-400 uppercase">Net Kâr / Zarar</span><h3 class="text-2xl font-bold" id="toplamKar">0.00 ₺</h3></div>
    <div class="glass-card rounded-2xl p-5"><span class="text-xs font-semibold text-slate-400 uppercase">Kâr Oranı</span><h3 class="text-2xl font-bold" id="toplamKarYuzde">%0.00</h3></div>
  </div>

  <!-- İşlem Formu -->
  <div class="glass-card rounded-2xl p-6 mb-8">
    <h2 class="text-lg font-bold mb-4">Yeni İşlem Ekle</h2>
    <form id="islemForm" onsubmit="islemEkle(event)" class="grid grid-cols-1 sm:grid-cols-12 gap-4">
      <div class="sm:col-span-2"><label class="block text-xs text-slate-400 mb-1">Tarih</label><input type="date" id="islemTarih" class="w-full bg-[#1a2332] border border-slate-700/60 rounded-xl px-3 py-2 text-sm" required></div>
      <div class="sm:col-span-2"><label class="block text-xs text-slate-400 mb-1">Fon Kodu</label><input type="text" id="islemKod" class="w-full bg-[#1a2332] border border-slate-700/60 rounded-xl px-3 py-2 text-sm uppercase" placeholder="MAC" required></div>
      <div class="sm:col-span-2"><label class="block text-xs text-slate-400 mb-1">Tip</label><select id="islemTip" class="w-full bg-[#1a2332] border border-slate-700/60 rounded-xl px-3 py-2 text-sm"><option value="AL">Alım</option><option value="SAT">Satım</option></select></div>
      <div class="sm:col-span-2"><label class="block text-xs text-slate-400 mb-1">Adet</label><input type="number" step="0.000001" id="islemAdet" class="w-full bg-[#1a2332] border border-slate-700/60 rounded-xl px-3 py-2 text-sm" required></div>
      <div class="sm:col-span-2"><label class="block text-xs text-slate-400 mb-1">Birim Fiyat (₺)</label><input type="number" step="0.000001" id="islemFiyat" class="w-full bg-[#1a2332] border border-slate-700/60 rounded-xl px-3 py-2 text-sm" placeholder="Otomatik"></div>
      <div class="sm:col-span-2 flex items-end"><button type="submit" id="kaydetBtn" class="w-full py-2 bg-blue-600 hover:bg-blue-500 rounded-xl font-bold text-sm">Kaydet</button></div>
    </form>
  </div>

  <!-- Portföy Tablosu -->
  <div class="glass-card rounded-2xl p-6 mb-8 overflow-x-auto">
    <h2 class="text-lg font-bold mb-4">Fon Varlıkları</h2>
    <table class="w-full text-left text-sm">
      <thead>
        <tr class="border-b border-slate-700 text-xs text-slate-400 uppercase">
          <th class="pb-3">Fon Kodu</th><th class="pb-3">Adet</th><th class="pb-3">Ort. Maliyet</th><th class="pb-3">Anlık Fiyat</th><th class="pb-3">Toplam Değer</th><th class="pb-3">Kâr / Zarar</th><th class="pb-3">Kâr (%)</th>
        </tr>
      </thead>
      <tbody id="portfoyTablosu" class="divide-y divide-slate-800"></tbody>
    </table>
  </div>
</div>

<script>
  let dbIslemler = [];
  let tefasFiyatlar = {};

  document.getElementById('islemTarih').valueAsDate = new Date();
  function formatMoney(n) { return (Math.round(n * 100) / 100).toLocaleString('tr-TR', { minimumFractionDigits: 2 }); }

  async function verileriYukle() {
    const res = await fetch('/api/user_transactions');
    dbIslemler = await res.json();
    await portfoyuGuncelle();
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
      btn.innerText = "Fiyat Alınıyor...";
      btn.disabled = true;
      const res = await fetch(`/api/fon_tarihli_fiyat?kod=${kod}&tarih=${tarih}`);
      const data = await res.json();
      if (data.status === 'success') fiyat = data.data.price;
      else { alert("Fiyat bulunamadı."); btn.innerText = "Kaydet"; btn.disabled = false; return; }
    }

    await fetch('/api/add_transaction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tarih, kod, tip, adet, fiyat })
    });

    document.getElementById("islemForm").reset();
    document.getElementById('islemTarih').valueAsDate = new Date();
    btn.innerText = "Kaydet"; btn.disabled = false;
    verileriYukle();
  }

  async function portfoyuGuncelle() {
    const fonKodlari = [...new Set(dbIslemler.map(x => x.kod))];
    for (const kod of fonKodlari) {
      const res = await fetch(`/api/fon?kod=${kod}`);
      const data = await res.json();
      if (data.status === 'success') tefasFiyatlar[kod] = data.data;
    }
    tabloCiz();
  }

  function tabloCiz() {
    let portfoy = {};
    dbIslemler.forEach(i => {
      if (!portfoy[i.kod]) portfoy[i.kod] = { adet: 0, toplamMaliyet: 0 };
      if (i.tip === 'AL') {
        portfoy[i.kod].adet += i.adet;
        portfoy[i.kod].toplamMaliyet += (i.adet * i.fiyat);
      } else {
        const ort = portfoy[i.kod].toplamMaliyet / (portfoy[i.kod].adet || 1);
        portfoy[i.kod].adet -= i.adet;
        portfoy[i.kod].toplamMaliyet -= (i.adet * ort);
      }
    });

    let html = "", genMaliyet = 0, genDeger = 0;
    Object.keys(portfoy).forEach(kod => {
      const pos = portfoy[kod];
      if (pos.adet > 0.00001) {
        const ortMaliyet = pos.toplamMaliyet / pos.adet;
        const guncelFiyat = tefasFiyatlar[kod] ? tefasFiyatlar[kod].price : ortMaliyet;
        const guncelDeger = pos.adet * guncelFiyat;
        const karTL = guncelDeger - pos.toplamMaliyet;
        const karYuzde = ortMaliyet > 0 ? ((guncelFiyat - ortMaliyet) / ortMaliyet) * 100 : 0;

        genMaliyet += pos.toplamMaliyet; genDeger += guncelDeger;
        html += `<tr class="hover:bg-slate-800/40">
          <td class="py-3 font-bold text-blue-400">${kod}</td>
          <td class="py-3">${pos.adet}</td>
          <td class="py-3">${formatMoney(ortMaliyet)} ₺</td>
          <td class="py-3">${formatMoney(guncelFiyat)} ₺</td>
          <td class="py-3 font-bold">${formatMoney(guncelDeger)} ₺</td>
          <td class="py-3 ${karTL >= 0 ? 'pos':'neg'}">${formatMoney(karTL)} ₺</td>
          <td class="py-3 ${karYuzde >= 0 ? 'pos':'neg'}">%${karYuzde.toFixed(2)}</td>
        </tr>`;
      }
    });

    document.getElementById("portfoyTablosu").innerHTML = html || `<tr><td colspan="7" class="text-center py-4 text-slate-500">İşlem kaydı yok.</td></tr>`;
    document.getElementById("toplamDeger").innerText = formatMoney(genDeger) + " ₺";
    document.getElementById("toplamMaliyet").innerText = formatMoney(genMaliyet) + " ₺";
    const genKar = genDeger - genMaliyet;
    document.getElementById("toplamKar").innerText = formatMoney(genKar) + " ₺";
    document.getElementById("toplamKar").className = "text-2xl font-bold " + (genKar >= 0 ? "pos" : "neg");
  }

  verileriYukle();
</script>
</body>
</html>"""

ADMIN_TEMPLATE = """<!DOCTYPE html>
<html lang="tr" class="dark">
<head>
  <meta charset="UTF-8"><title>Admin Paneli</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&display=swap" rel="stylesheet">
</head>
<body class="bg-[#0b0f17] text-white font-['Plus_Jakarta_Sans'] p-8">
  <div class="max-w-6xl mx-auto">
    <div class="flex justify-between items-center mb-8">
      <h1 class="text-2xl font-extrabold">Admin Yönetim Paneli</h1>
      <a href="/" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-xl text-xs font-bold">Arayüze Dön</a>
    </div>
    
    <div class="bg-[#151c28] border border-slate-800 rounded-2xl p-6 shadow-xl">
      <h2 class="text-lg font-bold mb-4">Kayıtlı Kullanıcılar ({{ users|length }})</h2>
      <table class="w-full text-left text-sm">
        <thead>
          <tr class="border-b border-slate-700 text-xs text-slate-400 uppercase">
            <th class="pb-3">ID</th><th class="pb-3">Kullanıcı Adı</th><th class="pb-3">Rol</th><th class="pb-3">Kayıt Tarihi</th><th class="pb-3">İşlem</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-800">
          {% for u in users %}
          <tr>
            <td class="py-3 text-slate-400">#{{ u.id }}</td>
            <td class="py-3 font-bold">{{ u.username }}</td>
            <td class="py-3">{% if u.is_admin %}<span class="px-2 py-1 bg-purple-500/20 text-purple-400 rounded text-xs">Admin</span>{% else %}<span class="px-2 py-1 bg-slate-800 text-slate-400 rounded text-xs">Üye</span>{% endif %}</td>
            <td class="py-3 text-slate-400">{{ u.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
            <td class="py-3">
              {% if u.id != current_user.id %}
              <a href="/admin/delete_user/{{ u.id }}" onclick="return confirm('Silinsin mi?')" class="text-rose-400 hover:underline text-xs">Kullanıcıyı Sil</a>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>"""

# ==================== ROUTE 'LAR ====================

@app.route('/')
@login_required
def home():
    return render_template_string(MAIN_TEMPLATE)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user)
            return redirect(url_for('home'))
        flash('Hatalı kullanıcı adı veya parola!')
    return render_template_string(AUTH_TEMPLATE, title="Giriş Yap", button_text="Giriş Yap", is_login=True)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        if User.query.filter_by(username=username).first():
            flash('Bu kullanıcı adı zaten alınmış.')
        else:
            user = User(username=username)
            user.set_password(request.form.get('password'))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('home'))
    return render_template_string(AUTH_TEMPLATE, title="Hesap Oluştur", button_text="Kayıt Ol", is_login=False)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        return "Erişim Yetkiniz Yok!", 403
    users = User.query.all()
    return render_template_string(ADMIN_TEMPLATE, users=users)

@app.route('/admin/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return "Yetkisiz İşlem", 403
    user = User.query.get_or_404(user_id)
    if user.id != current_user.id:
        db.session.delete(user)
        db.session.commit()
    return redirect(url_for('admin_panel'))

# ==================== API ENDPOINT'LERİ ====================

@app.route('/api/user_transactions')
@login_required
def get_user_transactions():
    txs = Transaction.query.filter_by(user_id=current_user.id).all()
    return jsonify([{"id": t.id, "tarih": t.tarih, "kod": t.kod, "tip": t.tip, "adet": t.adet, "fiyat": t.fiyat} for t in txs])

@app.route('/api/add_transaction', methods=['POST'])
@login_required
def add_transaction():
    data = request.json
    tx = Transaction(
        user_id=current_user.id,
        tarih=data['tarih'],
        kod=data['kod'].upper(),
        tip=data['tip'],
        adet=float(data['adet']),
        fiyat=float(data['fiyat'])
    )
    db.session.add(tx)
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/fon')
def api_fon():
    kod = request.args.get('kod', '').strip()
    result = get_tefas_data_crawler(kod)
    return jsonify({"status": "success", "data": result}) if result else (jsonify({"status": "error"}), 404)

@app.route('/api/fon_tarihli_fiyat')
def api_fon_tarihli_fiyat():
    kod = request.args.get('kod', '').strip()
    tarih = request.args.get('tarih', '').strip()
    result = get_tefas_price_on_date(kod, tarih)
    return jsonify({"status": "success", "data": result}) if result else (jsonify({"status": "error"}), 404)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)