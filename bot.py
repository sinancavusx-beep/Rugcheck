import asyncio
import json
import os
import re
from datetime import datetime

import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from analyzer import TokenAnalyzer
from blacklist import BlacklistManager

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

analyzer = TokenAnalyzer(HELIUS_API_KEY)
blacklist = BlacklistManager()

SOLANA_CA_PATTERN = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Pump.fun Rug Checker Botuna Hoş Geldin!*\n\n"
        "📋 *Kullanım:*\n"
        "• Bir token CA'sı gönder → Analiz başlar\n"
        "• `/blacklist` → Kara listeyi gör\n"
        "• `/help` → Yardım\n\n"
        "⚠️ *Uyarı:* Bu bot yatırım tavsiyesi vermez. DYOR!",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 *Nasıl Kullanılır?*\n\n"
        "1. Token contract adresini (CA) gönder\n"
        "2. Bot şunları analiz eder:\n"
        "   • Dev wallet geçmişi\n"
        "   • Önceki rug sayısı\n"
        "   • Likidite çekme geçmişi\n"
        "   • X/Twitter hesabı\n"
        "   • Token pattern analizi\n\n"
        "3. 0-100 arası risk skoru alırsın\n"
        "   • 🟢 0-30: Düşük risk\n"
        "   • 🟡 31-60: Orta risk\n"
        "   • 🔴 61-100: Yüksek risk\n"
        "   • ⛔ Kara listede: DOKUNMA!\n\n"
        "/blacklist → Kara listeyi görüntüle",
        parse_mode="Markdown"
    )


async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bl = blacklist.get_all()
    if not bl:
        await update.message.reply_text("✅ Kara liste şu an boş.")
        return

    text = "⛔ *Kara Listedeki Dev Wallet'lar:*\n\n"
    for i, (wallet, data) in enumerate(bl.items(), 1):
        text += f"{i}. `{wallet[:8]}...{wallet[-4:]}`\n"
        text += f"   Rug sayısı: {data['rug_count']} | Son: {data['last_rug']}\n\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def analyze_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ca = update.message.text.strip()

    if not SOLANA_CA_PATTERN.match(ca):
        await update.message.reply_text("❌ Geçersiz CA formatı. Solana contract adresi gönder.")
        return

    msg = await update.message.reply_text("🔍 Analiz yapılıyor, lütfen bekle...")

    try:
        result = await analyzer.analyze(ca)

        # Kara liste kontrolü
        if blacklist.is_blacklisted(result.get("dev_wallet", "")):
            bl_data = blacklist.get(result["dev_wallet"])
            text = (
                f"⛔ *KARA LİSTEDE!*\n\n"
                f"🪙 Token: `{ca[:8]}...{ca[-4:]}`\n"
                f"👤 Dev: `{result['dev_wallet'][:8]}...{result['dev_wallet'][-4:]}`\n"
                f"💀 Rug sayısı: {bl_data['rug_count']}\n"
                f"📅 Son rug: {bl_data['last_rug']}\n\n"
                f"🚨 *Bu dev'e DOKUNMA!*"
            )
            await msg.edit_text(text, parse_mode="Markdown")
            return

        # Risk skoru hesapla
        score = result["risk_score"]

        if score <= 30:
            emoji = "🟢"
            risk_text = "DÜŞÜK RİSK"
        elif score <= 60:
            emoji = "🟡"
            risk_text = "ORTA RİSK"
        else:
            emoji = "🔴"
            risk_text = "YÜKSEK RİSK"

        # Kara listeye ekle (2+ rug)
        if result.get("rug_count", 0) >= 2:
            blacklist.add(result["dev_wallet"], result["rug_count"])
            bl_note = "⛔ *Dev kara listeye eklendi!*\n"
        else:
            bl_note = ""

        text = (
            f"{emoji} *{risk_text}* — Skor: `{score}/100`\n\n"
            f"🪙 *Token Bilgisi*\n"
            f"CA: `{ca}`\n"
            f"İsim: {result.get('token_name', 'Bilinmiyor')}\n"
            f"Sembol: {result.get('token_symbol', '?')}\n\n"
            f"👤 *Dev Wallet Analizi*\n"
            f"Wallet: `{result['dev_wallet'][:8]}...{result['dev_wallet'][-4:]}`\n"
            f"Toplam token: {result.get('total_tokens_created', '?')}\n"
            f"Rug sayısı: {result.get('rug_count', 0)}\n"
            f"Likidite çekme: {result.get('liquidity_pulls', 0)}\n\n"
            f"📊 *Risk Faktörleri*\n"
            f"• Rug geçmişi: {result.get('rug_score', 0)}/40\n"
            f"• Likidite riski: {result.get('liquidity_score', 0)}/25\n"
            f"• Sosyal medya: {result.get('social_score', 0)}/20\n"
            f"• Pattern analizi: {result.get('pattern_score', 0)}/15\n\n"
        )

        if result.get("twitter_handle"):
            text += f"🐦 *Twitter:* @{result['twitter_handle']}\n"
            text += f"   • Hesap yaşı: {result.get('twitter_age', '?')}\n"
            text += f"   • Silinen gönderi: {result.get('deleted_posts', '?')}\n\n"

        text += bl_note
        text += "\n⚠️ _Bu analiz yatırım tavsiyesi değildir. DYOR!_"

        await msg.edit_text(text, parse_mode="Markdown")

    except Exception as e:
        await msg.edit_text(f"❌ Analiz sırasında hata oluştu: {str(e)}\n\nCA geçerli mi kontrol et.")


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN env variable eksik!")
    if not HELIUS_API_KEY:
        raise ValueError("HELIUS_API_KEY env variable eksik!")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("blacklist", blacklist_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_token))

    print("🤖 Bot başlatıldı...")
    app.run_polling()


if __name__ == "__main__":
    main()
