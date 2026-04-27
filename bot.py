#!/usr/bin/env python3
import os
import re
import sqlite3
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from yt_dlp import YoutubeDL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==================== إعدادات yt-dlp المحسنة ====================
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
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
}

# ==================== دوال التحميل ====================
async def get_video_info(url):
    for attempt in range(3):
        try:
            with YoutubeDL(YDL_OPTS) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return info
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2)
    return None

async def download_media(url, format_type='video', quality='best'):
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
        elif format_type == 'video':
            ydl_opts['format'] = 'best[height<=720]/best' if quality == 'best' else 'worst'
        
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

# ==================== بقية الدوال (نفس الكود السابق) ====================
# ... (أضف هنا دوال قاعدة البيانات والأدمن كما هي من الكود السابق) ...

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return
    
    processing_msg = await update.message.reply_text("🔄 جاري تحليل الرابط... (قد يستغرق 15-20 ثانية)")
    
    try:
        info = await asyncio.wait_for(get_video_info(url), timeout=60.0)
        
        if not info:
            await processing_msg.edit_text("❌ فشل تحليل الرابط. جرب:\n1. رابط من منصة أخرى\n2. أعد المحاولة لاحقاً\n3. تأكد من أن الرابط صحيح")
            return
        
        title = info.get('title', 'بدون عنوان')[:50]
        duration = info.get('duration', 0)
        duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "غير معروف"
        
        keyboard = [
            [InlineKeyboardButton("🎬 فيديو (أعلى جودة)", callback_data=f"video_best|{url}")],
            [InlineKeyboardButton("🎵 صوت MP3 فقط", callback_data=f"audio|{url}")],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        info_text = f"""
📌 *العنوان:* {title}
⏱️ *المدة:* {duration_str}
🌐 *المنصة:* {info.get('extractor', 'غير معروف')}

*اختر جودة التحميل:*
"""
        await processing_msg.edit_text(info_text, reply_markup=reply_markup, parse_mode="Markdown")
        
    except asyncio.TimeoutError:
        await processing_msg.edit_text("❌ استغرق التحليل وقتاً طويلاً. الرابط قد يكون محظوراً أو المنصة تعطل.")
    except Exception as e:
        await processing_msg.edit_text(f"❌ خطأ: {str(e)[:100]}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split('|', 1)
    if len(parts) != 2:
        await query.edit_message_text("❌ حدث خطأ")
        return
    
    action, url = parts
    user_id = query.from_user.id
    
    await query.edit_message_text("⬇️ جاري التحميل... ⏳")
    
    if action == "video_best":
        filename = await download_media(url, 'video', 'best')
        file_type = "فيديو"
    elif action == "audio":
        filename = await download_media(url, 'audio')
        file_type = "صوت MP3"
    else:
        await query.edit_message_text("❌ خيار غير صالح")
        return
    
    if not filename:
        await query.edit_message_text("❌ فشل التحميل. حاول مرة أخرى أو استخدم رابطاً مختلفاً.")
        return
    
    try:
        with open(filename, 'rb') as file:
            if file_type == "صوت MP3":
                await context.bot.send_audio(chat_id=user_id, audio=file)
            else:
                await context.bot.send_video(chat_id=user_id, video=file, supports_streaming=True)
        
        await query.edit_message_text(f"✅ تم التحميل بنجاح!")
        os.remove(filename)
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ في الإرسال: {str(e)[:100]}")

# ... (أضاف دوال start, help, get_id, admin commands من الكود السابق) ...

def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ يرجى تعيين BOT_TOKEN")
        return
    
    init_db()
    
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
    
    # معالجة الروابط
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("🚀 البوت يعمل...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Universal Downloader Bot - Admin Edition with Full Fixes
# يدعم: تحميل فيديوهات/صور/صوت من أي منصة
# مع نظام إدارة المستخدمين وحظر/تفعيل الصلاحيات

import os
import re
import sqlite3
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from yt_dlp import YoutubeDL
import shutil

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# توكن البوت من BotFather
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# معرف الأدمن الأساسي (ضع معرفك هنا)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))

# مجلد التحميلات المؤقتة
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# إعدادات yt-dlp المحسنة
YDL_OPTS_BASE = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'no_check_certificate': True,
    'retries': 10,
    'fragment_retries': 10,
    'sleep_interval': 1,
    'max_sleep_interval': 3,
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
            last_name TEXT,
            added_by INTEGER,
            added_date TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # جدول سجل الاستخدامات
    c.execute('''
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            username TEXT,
            action TEXT,
            url TEXT,
            timestamp TEXT
        )
    ''')
    
    # إضافة الأدمن الأساسي إذا لم يكن موجوداً
    c.execute('SELECT * FROM allowed_users WHERE chat_id = ?', (ADMIN_ID,))
    if not c.fetchone():
        c.execute('''
            INSERT INTO allowed_users (chat_id, username, first_name, added_by, added_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ADMIN_ID, 'admin', 'Admin', ADMIN_ID, datetime.now().isoformat(), 1))
    
    conn.commit()
    conn.close()
    print("✅ قاعدة البيانات جاهزة")

def is_allowed(chat_id):
    """التحقق مما إذا كان المستخدم مصرحاً له ونشطاً"""
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('SELECT is_active FROM allowed_users WHERE chat_id = ?', (chat_id,))
    result = c.fetchone()
    conn.close()
    return result is not None and result[0] == 1

def is_admin(chat_id):
    """التحقق من صلاحيات الأدمن"""
    return chat_id == ADMIN_ID

def add_user(chat_id, username, first_name, last_name, added_by):
    """إضافة مستخدم جديد إلى قاعدة البيانات"""
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    try:
        c.execute('''
            INSERT OR REPLACE INTO allowed_users (chat_id, username, first_name, last_name, added_by, added_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (chat_id, username or "no_username", first_name or "Unknown", last_name or "", added_by, datetime.now().isoformat(), 1))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding user: {e}")
        return False
    finally:
        conn.close()

def remove_user(chat_id):
    """حظر مستخدم (إلغاء التفعيل)"""
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('UPDATE allowed_users SET is_active = 0 WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

def unblock_user(chat_id):
    """إعادة تفعيل مستخدم"""
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('UPDATE allowed_users SET is_active = 1 WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

def get_all_users():
    """الحصول على قائمة جميع المستخدمين"""
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('SELECT chat_id, username, first_name, last_name, added_date, is_active FROM allowed_users ORDER BY added_date DESC')
    users = c.fetchall()
    conn.close()
    return users

def log_usage(chat_id, username, action, url=''):
    """تسجيل استخدام البوت"""
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO usage_logs (chat_id, username, action, url, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (chat_id, username or "unknown", action, url, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_usage_logs(limit=50):
    """الحصول على سجل الاستخدامات"""
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('''
        SELECT chat_id, username, action, url, timestamp 
        FROM usage_logs 
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (limit,))
    logs = c.fetchall()
    conn.close()
    return logs

# ==================== أوامر الأدمن ====================

async def adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة مستخدم جديد (للأدمن فقط)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذا الأمر مخصص للأدمن فقط.")
        return
    
    if not context.args:
        await update.message.reply_text("📌 الاستخدام: `/adduser <chat_id>`\n\nمثال: `/adduser 123456789`", parse_mode="Markdown")
        return
    
    try:
        chat_id = int(context.args[0])
        try:
            chat = await context.bot.get_chat(chat_id)
            username = chat.username or "no_username"
            first_name = chat.first_name or "Unknown"
            last_name = chat.last_name or ""
        except:
            username = "unknown"
            first_name = "unknown"
            last_name = ""
        
        if add_user(chat_id, username, first_name, last_name, update.effective_user.id):
            await update.message.reply_text(f"✅ تم إضافة المستخدم `{chat_id}` بنجاح.", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ فشل إضافة المستخدم.")
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال Chat ID صحيح (أرقام فقط).")

async def removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حظر مستخدم (للأدمن فقط)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذا الأمر مخصص للأدمن فقط.")
        return
    
    if not context.args:
        await update.message.reply_text("📌 الاستخدام: `/removeuser <chat_id>`\n\nمثال: `/removeuser 123456789`", parse_mode="Markdown")
        return
    
    try:
        chat_id = int(context.args[0])
        remove_user(chat_id)
        await update.message.reply_text(f"✅ تم حظر المستخدم `{chat_id}`. لن يتمكن من استخدام البوت.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال Chat ID صحيح.")

async def unblockuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعادة تفعيل مستخدم محظور (للأدمن فقط)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذا الأمر مخصص للأدمن فقط.")
        return
    
    if not context.args:
        await update.message.reply_text("📌 الاستخدام: `/unblockuser <chat_id>`", parse_mode="Markdown")
        return
    
    try:
        chat_id = int(context.args[0])
        unblock_user(chat_id)
        await update.message.reply_text(f"✅ تم إعادة تفعيل المستخدم `{chat_id}`.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال Chat ID صحيح.")

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع المستخدمين المصرح لهم (للأدمن فقط)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذا الأمر مخصص للأدمن فقط.")
        return
    
    users_list = get_all_users()
    if not users_list:
        await update.message.reply_text("📭 لا يوجد مستخدمين مسجلين حتى الآن.")
        return
    
    msg = "📋 *قائمة المستخدمين المصرح لهم:*\n\n"
    for user in users_list:
        chat_id, username, first_name, last_name, added_date, is_active = user
        status = "✅ نشط" if is_active == 1 else "⛔ محظور"
        name = first_name or username or str(chat_id)
        msg += f"• `{chat_id}` - {name} - {status}\n"
    
    if len(msg) > 4000:
        msg = msg[:4000] + "\n...(مختصر)"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض سجل الاستخدامات (للأدمن فقط)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذا الأمر مخصص للأدمن فقط.")
        return
    
    logs_data = get_usage_logs(30)
    
    if not logs_data:
        await update.message.reply_text("📭 لا توجد سجلات استخدام حتى الآن.")
        return
    
    msg = "📜 *آخر سجلات الاستخدام:*\n\n"
    for log in logs_data:
        chat_id, username, action, url, timestamp = log
        short_url = url[:40] + "..." if len(url) > 40 else url
        msg += f"• [{timestamp[:16]}] `{chat_id}` → {action}"
        if short_url:
            msg += f": {short_url}"
        msg += "\n"
    
    if len(msg) > 4000:
        msg = msg[:4000] + "\n...(مختصر)"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الحصول على Chat ID الخاص بالمستخدم"""
    user = update.effective_user
    
    msg = f"""
🆔 *معلومات الحساب:*

• معرفك (Chat ID): `{user.id}`
• يوزرنيم: @{user.username if user.username else 'لا يوجد'}
• الاسم الأول: {user.first_name}
• الاسم الأخير: {user.last_name if user.last_name else ''}

📌 *للأدمن:* لإضافتي، استخدم الأمر:
`/adduser {user.id}`
"""
    await update.message.reply_text(msg, parse_mode="Markdown")

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أوامر الأدمن"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذا الأمر مخصص للأدمن فقط.")
        return
    
    help_msg = """
👑 *أوامر الأدمن:*

/adduser `<chat_id>` - إضافة مستخدم جديد
/removeuser `<chat_id>` - حظر مستخدم
/unblockuser `<chat_id>` - إعادة تفعيل مستخدم محظور
/users - عرض جميع المستخدمين
/logs - عرض سجل الاستخدامات
/adminhelp - عرض هذه الأوامر

📌 *لجلب أي Chat ID:*
اطلب من المستخدم إرسال الأمر `/getid`
"""
    await update.message.reply_text(help_msg, parse_mode="Markdown")

# ==================== وظائف التحميل والتشغيل ====================

async def get_video_info(url):
    """جلب معلومات الفيديو مع إعدادات صحيحة"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'no_check_certificate': True,
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
        return None

async def download_media(url, format_type='video', quality='best'):
    """تحميل الوسائط مع إعدادات محسنة"""
    filename = None
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'paths': {'home': DOWNLOAD_DIR},
            'outtmpl': '%(title)s.%(ext)s',
            'ignoreerrors': True,
            'no_check_certificate': True,
            'retries': 10,
            'fragment_retries': 10,
            'sleep_interval': 1,
            'max_sleep_interval': 3,
        }
        
        if format_type == 'audio':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        elif format_type == 'video':
            if quality == 'best':
                ydl_opts['format'] = 'best[height<=720]/best'
            else:
                ydl_opts['format'] = 'worst'
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                filename = ydl.prepare_filename(info)
                if format_type == 'audio':
                    filename = filename.rsplit('.', 1)[0] + '.mp3'
                
                if os.path.exists(filename):
                    return filename
                
                if format_type == 'audio':
                    mp3_file = filename.rsplit('.', 1)[0] + '.mp3'
                    if os.path.exists(mp3_file):
                        return mp3_file
            
            return None
            
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة الترحيب"""
    user = update.effective_user
    chat_id = user.id
    
    if not is_allowed(chat_id):
        await update.message.reply_text(
            f"⛔ *غير مصرح لك باستخدام هذا البوت.*\n\n"
            f"يرجى التواصل مع الأدمن لإضافتك.\n\n"
            f"🆔 معرفك: `{chat_id}`\n\n"
            f"أرسل هذا المعرف للأدمن ليضيفك.",
            parse_mode="Markdown"
        )
        return
    
    welcome_msg = f"""
🌟 اهلاً بك {user.first_name}! 🌟

أنا بوت التحميل الشامل 💾
أستطيع تحميل من أي منصة:
📹 فيديو | 🖼️ صورة | 🎵 صوت

📌 أرسل لي الرابط وسأعطيك خيارات التحميل.

🔗 يدعم: YouTube, TikTok, Instagram, Twitter, Facebook, Vimeo, Twitch, Reddit, و 1000+ منصة

💡 الأوامر المتاحة:
/start - تشغيل البوت
/help - المساعدة
/getid - الحصول على معرفك
"""
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")
    log_usage(chat_id, user.username, "start")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أوامر المساعدة"""
    chat_id = update.effective_user.id
    
    if not is_allowed(chat_id):
        await update.message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return
    
    help_msg = """
📖 *قائمة الأوامر:*

/start - تشغيل البوت والترحيب
/help - عرض هذه المساعدة
/getid - الحصول على معرفك (Chat ID)

📤 *كيفية الاستخدام:*
1. انسخ رابط الفيديو/الصورة من أي منصة
2. أرسل الرابط هنا
3. اختر جودة التحميل من القائمة

⚙️ *المنصات المدعومة:*
✅ YouTube, YouTube Shorts
✅ TikTok (بدون علامة مائية)
✅ Instagram (Reels, Posts, Stories)
✅ Twitter/X
✅ Facebook
✅ Vimeo, Dailymotion
✅ Twitch Clips, Reddit
"""
    await update.message.reply_text(help_msg, parse_mode="Markdown")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الروابط المرسلة"""
    url = update.message.text.strip()
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    if not is_allowed(user_id):
        await update.message.reply_text(
            f"⛔ غير مصرح لك باستخدام هذا البوت.\n\n🆔 معرفك: `{user_id}`\nأرسل هذا المعرف للأدمن لإضافتك.",
            parse_mode="Markdown"
        )
        return
    
    url_pattern = re.compile(r'https?://[^\s]+')
    if not url_pattern.match(url):
        await update.message.reply_text("❌ يرجى إرسال رابط صحيح (يبدأ بـ http:// أو https://)")
        return
    
    log_usage(user_id, username, "download_request", url)
    
    processing_msg = await update.message.reply_text("🔄 جاري تحليل الرابط... (قد يستغرق 10-15 ثانية)")
    
    try:
        info = await asyncio.wait_for(get_video_info(url), timeout=30.0)
        
        if not info:
            await processing_msg.edit_text("❌ فشل تحليل الرابط. تأكد من صحة الرابط أو حاول مرة أخرى.")
            return
        
        title = info.get('title', 'بدون عنوان')[:50]
        duration = info.get('duration', 0)
        duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "غير معروف"
        
        keyboard = [
            [InlineKeyboardButton("🎬 فيديو (أعلى جودة)", callback_data=f"video_best|{url}")],
            [InlineKeyboardButton("📱 فيديو (جودة منخفضة)", callback_data=f"video_worst|{url}")],
            [InlineKeyboardButton("🎵 صوت MP3 فقط", callback_data=f"audio|{url}")],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        info_text = f"""
📌 *العنوان:* {title}
⏱️ *المدة:* {duration_str}
🌐 *المنصة:* {info.get('extractor', 'غير معروف')}

*اختر جودة التحميل:*
"""
        await processing_msg.edit_text(info_text, reply_markup=reply_markup, parse_mode="Markdown")
        
    except asyncio.TimeoutError:
        await processing_msg.edit_text("❌ استغرق التحليل وقتاً طويلاً. الرابط قد يكون معقداً أو المنصة محمية.")
    except Exception as e:
        logger.error(f"Handle URL error: {e}")
        await processing_msg.edit_text(f"❌ حدث خطأ: {str(e)[:100]}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اختيار المستخدم"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split('|', 1)
    if len(parts) != 2:
        await query.edit_message_text("❌ حدث خطأ، حاول مرة أخرى")
        return
    
    action, url = parts
    user_id = query.from_user.id
    username = query.from_user.username
    
    if not is_allowed(user_id):
        await query.edit_message_text("⛔ صلاحياتك منتهية. تواصل مع الأدمن.")
        return
    
    log_usage(user_id, username, f"download_{action}", url)
    
    await query.edit_message_text("⬇️ جاري تحميل الملف... قد يستغرق هذا دقيقة أو اثنتين ⏳")
    
    if action == "video_best":
        filename = await download_media(url, 'video', 'best')
        file_type = "فيديو"
    elif action == "video_worst":
        filename = await download_media(url, 'video', 'worst')
        file_type = "فيديو"
    elif action == "audio":
        filename = await download_media(url, 'audio')
        file_type = "صوت MP3"
    else:
        await query.edit_message_text("❌ خيار غير صالح")
        return
    
    if not filename or not os.path.exists(filename):
        await query.edit_message_text("❌ فشل التحميل. تأكد من الرابط أو حاول مرة أخرى لاحقاً.")
        return
    
    try:
        with open(filename, 'rb') as file:
            if file_type == "صوت MP3":
                await context.bot.send_audio(chat_id=user_id, audio=file, title=os.path.basename(filename))
            else:
                await context.bot.send_video(chat_id=user_id, video=file, supports_streaming=True)
        
        await query.edit_message_text(f"✅ تم التحميل بنجاح!\n📁 {file_type}: {os.path.basename(filename)}")
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Error sending file: {e}")
        await query.edit_message_text(f"❌ حدث خطأ أثناء إرسال الملف: {str(e)[:100]}")

# ==================== التشغيل الرئيسي ====================

def main():
    """تشغيل البوت"""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ يرجى تعيين BOT_TOKEN في متغيرات البيئة")
        return
    
    init_db()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # أوامر الأدمن
    app.add_handler(CommandHandler("adduser", adduser))
    app.add_handler(CommandHandler("removeuser", removeuser))
    app.add_handler(CommandHandler("unblockuser", unblockuser))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("logs", logs))
    app.add_handler(CommandHandler("adminhelp", admin_help))
    
    # أوامر عامة
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("getid", get_id))
    
    # معالجة الروابط والاستعلامات
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print(f"{'='*50}")
    print("🚀 تشغيل البوت مع نظام الإدارة...")
    print(f"👑 الأدمن ID: {ADMIN_ID}")
    print(f"{'='*50}")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
