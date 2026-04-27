#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Universal Downloader Bot - Full Working Version

import os
import re
import sqlite3
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from yt_dlp import YoutubeDL

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# متغيرات البيئة
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# مجلد التحميلات
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# إعدادات yt-dlp المحسنة
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'no_check_certificate': True,
    'extract_flat': False,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'geo_bypass': True,
    'retries': 10,
}

# ==================== قاعدة البيانات ====================

def init_db():
    """تهيئة قاعدة البيانات"""
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    
    # جدول المستخدمين المصرح لهم
    c.execute('''
        CREATE TABLE IF NOT EXISTS allowed_users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            added_date TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # جدول سجل الاستخدامات
    c.execute('''
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            action TEXT,
            url TEXT,
            timestamp TEXT
        )
    ''')
    
    # إضافة الأدمن الأساسي
    c.execute('SELECT * FROM allowed_users WHERE chat_id = ?', (ADMIN_ID,))
    if not c.fetchone():
        c.execute('INSERT INTO allowed_users (chat_id, username, first_name, added_date, is_active) VALUES (?, ?, ?, ?, ?)',
                  (ADMIN_ID, 'admin', 'Admin', datetime.now().isoformat(), 1))
    
    conn.commit()
    conn.close()
    print("✅ قاعدة البيانات جاهزة")

def is_allowed(chat_id):
    """التحقق من صلاحية المستخدم"""
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('SELECT is_active FROM allowed_users WHERE chat_id = ?', (chat_id,))
    result = c.fetchone()
    conn.close()
    return result is not None and result[0] == 1

def is_admin(chat_id):
    return chat_id == ADMIN_ID

def add_user(chat_id, username, first_name):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO allowed_users (chat_id, username, first_name, added_date, is_active) VALUES (?, ?, ?, ?, ?)',
              (chat_id, username, first_name, datetime.now().isoformat(), 1))
    conn.commit()
    conn.close()

def remove_user(chat_id):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('UPDATE allowed_users SET is_active = 0 WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('SELECT chat_id, username, first_name, added_date, is_active FROM allowed_users')
    users = c.fetchall()
    conn.close()
    return users

def log_usage(chat_id, action, url=''):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('INSERT INTO usage_logs (chat_id, action, url, timestamp) VALUES (?, ?, ?, ?)',
              (chat_id, action, url, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# ==================== دوال التحميل ====================

async def get_video_info(url):
    """جلب معلومات الفيديو"""
    try:
        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error(f"Error getting info: {e}")
        return None

async def download_media(url, format_type='video'):
    """تحميل الوسائط"""
    try:
        ydl_opts = YDL_OPTS.copy()
        ydl_opts['paths'] = {'home': DOWNLOAD_DIR}
        ydl_opts['outtmpl'] = '%(title)s.%(ext)s'
        
        if format_type == 'audio':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            ydl_opts['format'] = 'best[height<=720]/best'
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                filename = ydl.prepare_filename(info)
                if format_type == 'audio':
                    filename = filename.rsplit('.', 1)[0] + '.mp3'
                if os.path.exists(filename):
                    return filename
    except Exception as e:
        logger.error(f"Download error: {e}")
    return None

# ==================== أوامر البوت ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = user.id
    
    if not is_allowed(chat_id):
        await update.message.reply_text(
            f"⛔ غير مصرح لك باستخدام هذا البوت.\n\nمعرفك: `{chat_id}`\nأرسله للأدمن لإضافتك.",
            parse_mode="Markdown"
        )
        return
    
    welcome_msg = f"""
🌟 مرحباً {user.first_name}! 🌟

أنا بوت تحميل الفيديوهات والصوت.
أرسل لي أي رابط وسأحمله لك.

🔗 يدعم: YouTube, TikTok, Instagram, Twitter, Facebook

/help - للمساعدة
/getid - لمعرفة معرفك
"""
    await update.message.reply_text(welcome_msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_msg = """
📖 الأوامر المتاحة:

/start - تشغيل البوت
/help - هذه الرسالة
/getid - معرفتك

📤 طريقة الاستخدام:
أرسل رابط الفيديو، اختر الجودة، انتظر التحميل.
"""
    await update.message.reply_text(help_msg)

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"🆔 معرفك: `{user.id}`", parse_mode="Markdown")

async def adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ للأدمن فقط")
        return
    
    if not context.args:
        await update.message.reply_text("الاستخدام: `/adduser <chat_id>`", parse_mode="Markdown")
        return
    
    try:
        chat_id = int(context.args[0])
        add_user(chat_id, "user", "User")
        await update.message.reply_text(f"✅ تم إضافة `{chat_id}`", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ خطأ في المعرف")

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ للأدمن فقط")
        return
    
    users_list = get_all_users()
    if not users_list:
        await update.message.reply_text("لا يوجد مستخدمين")
        return
    
    msg = "📋 المستخدمين:\n"
    for user in users_list:
        status = "✅" if user[4] == 1 else "⛔"
        msg += f"{status} `{user[0]}` - {user[2]}\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ غير مصرح لك")
        return
    
    if not re.match(r'https?://[^\s]+', url):
        await update.message.reply_text("❌ رابط غير صحيح")
        return
    
    log_usage(user_id, "download_request", url)
    
    processing_msg = await update.message.reply_text("🔄 جاري تحليل الرابط...")
    
    try:
        info = await asyncio.wait_for(get_video_info(url), timeout=30.0)
        
        if not info:
            await processing_msg.edit_text("❌ فشل التحليل. تأكد من الرابط")
            return
        
        title = info.get('title', 'بدون عنوان')[:50]
        
        keyboard = [
            [InlineKeyboardButton("🎬 فيديو", callback_data=f"video|{url}")],
            [InlineKeyboardButton("🎵 صوت MP3", callback_data=f"audio|{url}")],
        ]
        
        await processing_msg.edit_text(
            f"📌 {title}\n\nاختر نوع التحميل:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except asyncio.TimeoutError:
        await processing_msg.edit_text("❌ استغرق وقتاً طويلاً")
    except Exception as e:
        await processing_msg.edit_text(f"❌ خطأ: {str(e)[:100]}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split('|', 1)
    if len(parts) != 2:
        await query.edit_message_text("❌ خطأ")
        return
    
    action, url = parts
    user_id = query.from_user.id
    
    format_type = 'audio' if action == 'audio' else 'video'
    
    await query.edit_message_text("⬇️ جاري التحميل...")
    
    filename = await download_media(url, format_type)
    
    if not filename:
        await query.edit_message_text("❌ فشل التحميل")
        return
    
    try:
        with open(filename, 'rb') as f:
            if format_type == 'audio':
                await context.bot.send_audio(chat_id=user_id, audio=f)
            else:
                await context.bot.send_video(chat_id=user_id, video=f)
        
        await query.edit_message_text("✅ تم التحميل!")
        os.remove(filename)
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ: {str(e)[:100]}")

# ==================== التشغيل ====================

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN غير موجود")
        return
    
    if ADMIN_ID == 0:
        print("❌ ADMIN_ID غير موجود")
        return
    
    init_db()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # أوامر عامة
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("getid", get_id))
    
    # أوامر الأدمن
    app.add_handler(CommandHandler("adduser", adduser))
    app.add_handler(CommandHandler("users", users))
    
    # معالجة الروابط
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("=" * 50)
    print("🚀 البوت يعمل...")
    print(f"👑 الأدمن ID: {ADMIN_ID}")
    print("=" * 50)
    
    app.run_polling()

if __name__ == "__main__":
    main()
