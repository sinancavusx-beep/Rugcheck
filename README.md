# 🤖 Pump.fun Rug Checker Bot

Pump.fun token'larını analiz eden, rug yapan dev'leri tespit eden ve kara listeye alan Telegram botu.

## 🚀 Kurulum

### 1. Gereksinimler
- Python 3.10+
- Telegram Bot Token ([@BotFather](https://t.me/BotFather))
- Helius API Key ([helius.dev](https://helius.dev))

### 2. Dosyaları İndir
```bash
# Bu klasörü bir yere kopyala
cd rugchecker_bot
```

### 3. Kütüphaneleri Kur
```bash
pip install -r requirements.txt
```

### 4. .env Dosyası Oluştur
`.env.example` dosyasını kopyala, `.env` olarak yeniden adlandır:
```bash
cp .env.example .env
```

`.env` dosyasını aç ve tokenları gir:
```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
HELIUS_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### 5. Botu Başlat
**Windows:**
```bash
set TELEGRAM_BOT_TOKEN=tokenin
set HELIUS_API_KEY=keyın
python bot.py
```

**Mac/Linux:**
```bash
export TELEGRAM_BOT_TOKEN=tokenin
export HELIUS_API_KEY=keyın
python bot.py
```

**Veya .env dosyasıyla (python-dotenv kuruluysa):**
```bash
pip install python-dotenv
# bot.py'nin başına şunu ekle:
# from dotenv import load_dotenv; load_dotenv()
python bot.py
```

## 📊 Risk Skoru Sistemi

| Skor | Seviye | Anlamı |
|------|--------|--------|
| 0-30 | 🟢 Düşük | Nispeten güvenli |
| 31-60 | 🟡 Orta | Dikkatli ol |
| 61-100 | 🔴 Yüksek | Tehlikeli |
| Kara liste | ⛔ YASAK | Kesinlikle dokunma |

### Skor Bileşenleri
- **Rug Geçmişi** (0-40 puan): Dev'in önceki rug sayısı
- **Likidite Riski** (0-25 puan): Likidite çekme geçmişi
- **Sosyal Medya** (0-20 puan): Twitter/X ve website analizi
- **Pattern** (0-15 puan): Token açma sıklığı, etkileşim

### Kara Liste Kuralı
2 veya daha fazla rug yapan dev wallet'lar otomatik kara listeye girer.

## 🔧 Komutlar
- `/start` - Botu başlat
- `/help` - Yardım
- `/blacklist` - Kara listeyi gör
- `[CA gir]` - Token analizi yap

## ⚠️ Uyarı
Bu bot yatırım tavsiyesi vermez. DYOR (Do Your Own Research)!
