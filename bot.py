#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Universal Downloader Bot - Updated & Working 100%

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

# ==================== إعدادات yt-dlp المحسنة ====================
YDL_OPTS = {
    'quiet': True,
    'no_warnings': False,
    'ignoreerrors': True,
    'no_check_certificate': True,
    'extract_flat': False,
    'force_generic_extractor': False,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'referer': 'https://www.youtube.com/',
    'geo_bypass': True,
    'geo_bypass_country': 'US',
    'retries': 10,
    'fragment_retries': 10,
    'sleep_interval': 1,
    'max_sleep_interval': 3,
    'extractor_args': {
        'youtube': {
            'skip': ['hls', 'dash', 'webpage'],
            'player_client': ['android', 'web'],
        }
    },
    'compat_opts': ['allow-unsafe-extract'],
}

# ==================== قاعدة البيانات ====================

def init_db():
    """تهيئة قاعدة البيانات"""
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    
    # جدول المستخدمين
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
              (chat_id, username or "user", first_name or "User", datetime.now().isoformat(), 1))
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
    """جلب معلومات الفيديو - 3 محاولات"""
    for attempt in range(3):
        try:
            with YoutubeDL(YDL_OPTS) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return info
        except Exception as e:
            logger.warning(f"محاولة {attempt+1} فشلت: {str(e)[:100]}")
            await asyncio.sleep(2)
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

أنا بوت تحميل الفيديوهات والصوت من أي منصة.
أرسل لي الرابط وسأحمله لك.

🔗 *المنصات المدعومة:*
YouTube - TikTok - Instagram - Twitter - Facebook - وغيرها

📌 *الأوامر:*
/help - المساعدة
/getid - معرفك

📤 فقط أرسل الرابط واختر الجودة.
"""
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    if not is_allowed(chat_id):
        await update.message.reply_text("⛔ غير مصرح لك")
        return
    
    help_msg = """
📖 *الأوامر المتاحة:*

/start - تشغيل البوت
/help - هذه الرسالة
/getid - معرفك في التلغرام

📤 *طريقة الاستخدام:*
1️⃣ أرسل رابط الفيديو
2️⃣ اختر (فيديو) أو (صوت MP3)
3️⃣ انتظر التحميل

⚡ *نصائح:*
• الروابط الطويلة تعمل بشكل أفضل
• إذا فشل رابط يوتيوب، جرب رابط TikTok أو Instagram
"""
    await update.message.reply_text(help_msg, parse_mode="Markdown")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"🆔 معرفك: `{user.id}`", parse_mode="Markdown")

async def adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذا الأمر للأدمن فقط")
        return
    
    if not context.args:
        await update.message.reply_text("📌 الاستخدام: `/adduser <chat_id>`", parse_mode="Markdown")
        return
    
    try:
        chat_id = int(context.args[0])
        add_user(chat_id, "user", "User")
        await update.message.reply_text(f"✅ تم إضافة المستخدم `{chat_id}`", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ خطأ: المعرف يجب أن يكون أرقام فقط")

async def removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ للأدمن فقط")
        return
    
    if not context.args:
        await update.message.reply_text("📌 `/removeuser <chat_id>`", parse_mode="Markdown")
        return
    
    try:
        chat_id = int(context.args[0])
        remove_user(chat_id)
        await update.message.reply_text(f"✅ تم حظر المستخدم `{chat_id}`", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ خطأ")

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ للأدمن فقط")
        return
    
    users_list = get_all_users()
    if not users_list:
        await update.message.reply_text("📭 لا يوجد مستخدمين")
        return
    
    msg = "📋 *قائمة المستخدمين:*\n\n"
    for user in users_list:
        status = "✅ نشط" if user[4] == 1 else "⛔ محظور"
        msg += f"• `{user[0]}` - {user[2]} - {status}\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ غير مصرح لك")
        return
    
    # التحقق من صحة الرابط
    url_pattern = re.compile(r'https?://[^\s]+')
    if not url_pattern.match(url):
        await update.message.reply_text("❌ رابط غير صحيح. تأكد من أن الرابط يبدأ بـ http:// أو https://")
        return
    
    log_usage(user_id, "download_request", url)
    
    processing_msg = await update.message.reply_text("🔄 جاري تحليل الرابط... (قد يستغرق 10-15 ثانية)")
    
    try:
        info = await asyncio.wait_for(get_video_info(url), timeout=45.0)
        
        if not info:
            await processing_msg.edit_text(
                "❌ فشل تحليل الرابط.\n\n"
                "الأسباب المحتملة:\n"
                "• الرابط محظور أو خاص\n"
                "• المنصة غير مدعومة\n"
                "• يرجى المحاولة لاحقاً\n\n"
                "💡 نصيحة: جرب رابط من منصة أخرى (TikTok, Instagram)"
            )
            return
        
        title = info.get('title', 'بدون عنوان')[:60]
        duration = info.get('duration', 0)
        duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "غير معروف"
        platform = info.get('extractor', 'YouTube')
        
        keyboard = [
            [InlineKeyboardButton("🎬 فيديو (أعلى جودة)", callback_data=f"video|{url}")],
            [InlineKeyboardButton("🎵 صوت MP3 فقط", callback_data=f"audio|{url}")],
        ]
        
        info_text = f"""
📌 *العنوان:* {title}
⏱️ *المدة:* {duration_str}
🌐 *المنصة:* {platform}

اختر نوع التحميل:
"""
        await processing_msg.edit_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    except asyncio.TimeoutError:
        await processing_msg.edit_text(
            "❌ استغرق التحليل وقتاً طويلاً.\n\n"
            "الرابط قد يكون معقداً أو المنصة تطلب تسجيل دخول.\n"
            "جرب رابطاً آخر أو منصة مختلفة."
        )
    except Exception as e:
        logger.error(f"Handle error: {e}")
        await processing_msg.edit_text(f"❌ حدث خطأ: {str(e)[:100]}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split('|', 1)
    if len(parts) != 2:
        await query.edit_message_text("❌ حدث خطأ في البيانات")
        return
    
    action, url = parts
    user_id = query.from_user.id
    
    format_type = 'audio' if action == 'audio' else 'video'
    type_name = "صوت MP3" if action == 'audio' else "فيديو"
    
    await query.edit_message_text(f"⬇️ جاري تحميل {type_name}... قد يستغرق دقيقة ⏳")
    
    filename = await download_media(url, format_type)
    
    if not filename or not os.path.exists(filename):
        await query.edit_message_text("❌ فشل التحميل. حاول مرة أخرى أو استخدم رابطاً آخر.")
        return
    
    try:
        with open(filename, 'rb') as file:
            if format_type == 'audio':
                await context.bot.send_audio(chat_id=user_id, audio=file, title=os.path.basename(filename))
            else:
                await context.bot.send_video(chat_id=user_id, video=file, supports_streaming=True)
        
        await query.edit_message_text(
            f"✅ تم التحميل بنجاح!\n"
            f"📁 {type_name}: {os.path.basename(filename)}\n\n"
            f"💡 أرسل رابطاً آخر للتحميل."
        )
        
        # حذف الملف المؤقت
        try:
            os.remove(filename)
        except:
            pass
        
    except Exception as e:
        logger.error(f"Send error: {e}")
        await query.edit_message_text(f"❌ خطأ في إرسال الملف: {str(e)[:100]}")

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ للأدمن فقط")
        return
    
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('SELECT chat_id, action, url, timestamp FROM usage_logs ORDER BY timestamp DESC LIMIT 20')
    logs_data = c.fetchall()
    conn.close()
    
    if not logs_data:
        await update.message.reply_text("📭 لا توجد سجلات")
        return
    
    msg = "📜 *آخر 20 سجل استخدام:*\n\n"
    for log in logs_data:
        chat_id, action, url, timestamp = log
        short_url = url[:30] + "..." if len(url) > 30 else url
        msg += f"• `{chat_id}` | {action} | {short_url}\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ للأدمن فقط")
        return
    
    help_msg = """
👑 *أوامر الأدمن:*

/adduser `<chat_id>` - إضافة مستخدم
/removeuser `<chat_id>` - حظر مستخدم
/users - عرض جميع المستخدمين
/logs - عرض سجل الاستخدامات
/adminhelp - هذه القائمة

📌 للحصول على معرف أي مستخدم:
اطلب منه إرسال /getid
"""
    await update.message.reply_text(help_msg, parse_mode="Markdown")

# ==================== التشغيل الرئيسي ====================

def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ يرجى تعيين BOT_TOKEN في متغيرات البيئة")
        print("💡 اذهب إلى @BotFather في تلغرام لإنشاء بوت جديد")
        return
    
    if ADMIN_ID == 0:
        print("❌ يرجى تعيين ADMIN_ID في متغيرات البيئة")
        print("💡 أرسل /getid لأي بوت لمعرفة معرفك")
        return
    
    # تهيئة قاعدة البيانات
    init_db()
    
    # إنشاء التطبيق
    app = Application.builder().token(BOT_TOKEN).build()
    
    # أوامر عامة
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("getid", get_id))
    
    # أوامر الأدمن
    app.add_handler(CommandHandler("adduser", adduser))
    app.add_handler(CommandHandler("removeuser", removeuser))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("logs", logs))
    app.add_handler(CommandHandler("adminhelp", admin_help))
    
    # معالجة الروابط والاستعلامات
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("=" * 50)
    print("🚀 Universal Downloader Bot يعمل الآن!")
    print(f"👑 معرف الأدمن: {ADMIN_ID}")
    print(f"📁 مجلد التحميلات: {DOWNLOAD_DIR}")
    print("=" * 50)
    print("✅ البوت جاهز لاستقبال الروابط")
    print("=" * 50)
    
    # تشغيل البوت
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
