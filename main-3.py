import os
import sys
import asyncio
import logging
import subprocess
import uuid
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, PreCheckoutQueryHandler
from deep_translator import GoogleTranslator
from pydub import AudioSegment
import whisper
import requests

# Windows uchun
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ======================================
# SHU YERGA O'Z TOKENLARINGIZNI YOZING
# ======================================
BOT_TOKEN = "8251116644:AAHG_von0pdx5zcytFCcFjxP3DcmFfwDPkA"
ELEVEN_API_KEY = "sk_bu_yerga_elevenlabs_api_keyingizni_yozing"

logging.basicConfig(level=logging.INFO)

# Foydalanuvchilar ma'lumotlari (faylda saqlanadi)
USERS_FILE = "users.json"

# Obuna rejalari (Telegram Stars bilan)
PLANS = {
    "boshlangich": {
        "name": "Boshlang'ich",
        "stars": 100,
        "videos": 10,
        "days": 30,
        "desc": "Oyiga 10 ta video dublyaj"
    },
    "standard": {
        "name": "Standard",
        "stars": 200,
        "videos": 30,
        "days": 30,
        "desc": "Oyiga 30 ta video dublyaj"
    },
    "premium": {
        "name": "Premium",
        "stars": 400,
        "videos": 9999,
        "days": 30,
        "desc": "Oyiga cheksiz video dublyaj"
    }
}

# 10 ta til
LANGUAGES = {
    "Uzbek": "uz",
    "Rus": "ru",
    "Ingliz": "en",
    "Nemis": "de",
    "Fransuz": "fr",
    "Arab": "ar",
    "Xitoy": "zh",
    "Yapon": "ja",
    "Koreys": "ko",
    "Ispan": "es",
}

# ElevenLabs ovoz ID lari (har til uchun)
ELEVEN_VOICES = {
    "uz": "pNInz6obpgDQGcFmaJgB",
    "ru": "pNInz6obpgDQGcFmaJgB",
    "en": "pNInz6obpgDQGcFmaJgB",
    "de": "pNInz6obpgDQGcFmaJgB",
    "fr": "pNInz6obpgDQGcFmaJgB",
    "ar": "pNInz6obpgDQGcFmaJgB",
    "zh": "pNInz6obpgDQGcFmaJgB",
    "ja": "pNInz6obpgDQGcFmaJgB",
    "ko": "pNInz6obpgDQGcFmaJgB",
    "es": "pNInz6obpgDQGcFmaJgB",
}

user_states = {}
whisper_model = None


# ─────────────────────────────
# FOYDALANUVCHI MA'LUMOTLARI
# ─────────────────────────────

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def get_user(uid):
    users = load_users()
    return users.get(str(uid))

def is_subscribed(uid):
    user = get_user(uid)
    if not user:
        return False
    expire = datetime.fromisoformat(user["expire"])
    if datetime.now() > expire:
        return False
    if user["videos_left"] <= 0 and user["plan"] != "premium":
        return False
    return True

def use_video(uid):
    users = load_users()
    u = users.get(str(uid))
    if u and u["videos_left"] > 0:
        u["videos_left"] -= 1
        save_users(users)

def activate_plan(uid, plan_key):
    users = load_users()
    plan = PLANS[plan_key]
    expire = datetime.now() + timedelta(days=plan["days"])
    users[str(uid)] = {
        "plan": plan_key,
        "plan_name": plan["name"],
        "expire": expire.isoformat(),
        "videos_left": plan["videos"]
    }
    save_users(users)


# ─────────────────────────────
# YORDAMCHI FUNKSIYALAR
# ─────────────────────────────

def get_whisper():
    global whisper_model
    if whisper_model is None:
        print("Whisper yuklanmoqda...")
        whisper_model = whisper.load_model("base")
    return whisper_model

def get_lang_name(code):
    for name, c in LANGUAGES.items():
        if c == code:
            return name
    return code

def secs_to_srt(s):
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    ms = int((s % 1) * 1000)
    return str(h).zfill(2) + ":" + str(m).zfill(2) + ":" + str(sec).zfill(2) + "," + str(ms).zfill(3)

def do_translate(text, target_lang):
    lang_map = {"uz": "uz", "ru": "ru", "en": "en", "de": "de", "fr": "fr",
                "ar": "ar", "zh": "zh-CN", "ja": "ja", "ko": "ko", "es": "es"}
    gl = lang_map.get(target_lang, "en")
    return GoogleTranslator(source="auto", target=gl).translate(text)

def elevenlabs_tts(text, lang, output_path):
    """ElevenLabs orqali tabiiy ovoz yaratadi"""
    voice_id = ELEVEN_VOICES.get(lang, ELEVEN_VOICES["en"])
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
        }
    }
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(response.content)
        return True
    return False

def do_dubbing(video_path, lang):
    """ElevenLabs bilan professional dublyaj"""
    lang_map = {"uz": "uz", "ru": "ru", "en": "en", "de": "de", "fr": "fr",
                "ar": "ar", "zh": "zh", "ja": "ja", "ko": "ko", "es": "es"}

    # 1. Ovoz ajrat
    audio = "audio_" + uuid.uuid4().hex + ".wav"
    subprocess.run(["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
                    "-ar", "16000", "-ac", "1", audio, "-y"],
                   check=True, capture_output=True)

    # 2. Whisper bilan matn ol
    model = get_whisper()
    result = model.transcribe(audio)
    segments = result["segments"]

    # 3. Video davomiyligini ol
    dur_res = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                               "format=duration", "-of",
                               "default=noprint_wrappers=1:nokey=1", video_path],
                              capture_output=True, text=True)
    duration = float(dur_res.stdout.strip())
    final = AudioSegment.silent(duration=int(duration * 1000))

    # 4. Har segment uchun ElevenLabs ovoz yarat
    for seg in segments:
        start_ms = int(seg["start"] * 1000)
        try:
            txt = do_translate(seg["text"].strip(), lang)
            if not txt.strip():
                continue
            mp3 = "seg_" + uuid.uuid4().hex + ".mp3"
            success = elevenlabs_tts(txt, lang, mp3)
            if success:
                seg_audio = AudioSegment.from_mp3(mp3)
                final = final.overlay(seg_audio, position=start_ms)
                os.remove(mp3)
        except Exception as e:
            print("Segment xato:", e)
            continue

    # 5. Yakuniy audio va video birlashtir
    dubbed = "dubbed_" + uuid.uuid4().hex + ".mp3"
    final.export(dubbed, format="mp3")
    out = "final_" + uuid.uuid4().hex + ".mp4"
    subprocess.run(["ffmpeg", "-i", video_path, "-i", dubbed,
                    "-c:v", "copy", "-c:a", "aac",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-shortest", out, "-y"],
                   check=True, capture_output=True)
    os.remove(audio)
    os.remove(dubbed)
    return out


# ─────────────────────────────
# KLAVIATURALAR
# ─────────────────────────────

def main_keyboard(uid):
    sub = is_subscribed(uid)
    keyboard = [
        [InlineKeyboardButton("🎬 Video Dublyaj", callback_data="mode_dub")],
        [InlineKeyboardButton("💳 Obuna", callback_data="show_plans")],
        [InlineKeyboardButton("👤 Mening obuna", callback_data="my_sub")],
    ]
    return InlineKeyboardMarkup(keyboard)

def lang_keyboard():
    keyboard = []
    row = []
    for name, code in LANGUAGES.items():
        row.append(InlineKeyboardButton(name, callback_data="dub_" + code))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back")])
    return InlineKeyboardMarkup(keyboard)

def plans_keyboard():
    keyboard = [
        [InlineKeyboardButton("⭐ Boshlang'ich — 100 Stars/oy", callback_data="buy_boshlangich")],
        [InlineKeyboardButton("⭐⭐ Standard — 200 Stars/oy", callback_data="buy_standard")],
        [InlineKeyboardButton("⭐⭐⭐ Premium — 400 Stars/oy", callback_data="buy_premium")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ─────────────────────────────
# HANDLERLAR
# ─────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    user = get_user(uid)
    if user and is_subscribed(uid):
        status = "✅ Faol obuna: " + user["plan_name"]
    else:
        status = "❌ Obuna yo'q"
    await update.message.reply_text(
        "🎬 *Dublyaj Bot*\n\n"
        "Professional video dublyaj — 10 tilda!\n\n"
        "Holat: " + status + "\n\n"
        "Rejim tanlang:",
        parse_mode="Markdown",
        reply_markup=main_keyboard(uid)
    )

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    d = q.data

    if d == "back":
        user_states.pop(uid, None)
        await q.edit_message_text("Rejim tanlang:", reply_markup=main_keyboard(uid))

    elif d == "show_plans":
        text = (
            "💳 *Obuna rejalari:*\n\n"
            "⭐ *Boshlang'ich* — 100 Stars/oy\n"
            "   10 ta video dublyaj\n\n"
            "⭐⭐ *Standard* — 200 Stars/oy\n"
            "   30 ta video dublyaj\n\n"
            "⭐⭐⭐ *Premium* — 400 Stars/oy\n"
            "   Cheksiz video dublyaj\n\n"
            "Tanlang:"
        )
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=plans_keyboard())

    elif d == "my_sub":
        user = get_user(uid)
        if user and is_subscribed(uid):
            expire = datetime.fromisoformat(user["expire"]).strftime("%d.%m.%Y")
            vl = "Cheksiz" if user["plan"] == "premium" else str(user["videos_left"])
            text = (
                "👤 *Sizning obunangiz:*\n\n"
                "Plan: " + user["plan_name"] + "\n"
                "Tugash sanasi: " + expire + "\n"
                "Qolgan videolar: " + vl
            )
        else:
            text = "❌ Sizda faol obuna yo'q.\n\nObuna olish uchun 💳 Obuna tugmasini bosing."
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=main_keyboard(uid))

    elif d == "mode_dub":
        if not is_subscribed(uid):
            await q.edit_message_text(
                "❌ Dublyaj qilish uchun obuna kerak!\n\nObuna olish uchun 💳 Obuna tugmasini bosing.",
                reply_markup=plans_keyboard()
            )
            return
        user_states[uid] = {"mode": "dub_lang"}
        await q.edit_message_text("🌍 Qaysi tilga dublyaj qilinsin?", reply_markup=lang_keyboard())

    elif d.startswith("dub_"):
        lang = d[4:]
        user_states[uid] = {"mode": "dubbing", "lang": lang}
        await q.edit_message_text(
            "✅ Til: " + get_lang_name(lang) + "\n\n"
            "Endi *video yuboring!*\n"
            "(MP4 format, max 50MB)",
            parse_mode="Markdown"
        )

    elif d.startswith("buy_"):
        plan_key = d[4:]
        plan = PLANS[plan_key]
        await q.message.reply_invoice(
            title=plan["name"] + " Obuna",
            description=plan["desc"],
            payload=plan_key,
            currency="XTR",
            prices=[LabeledPrice(plan["name"], plan["stars"])],
            provider_token=""
        )

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    plan_key = update.message.successful_payment.invoice_payload
    activate_plan(uid, plan_key)
    plan = PLANS[plan_key]
    await update.message.reply_text(
        "✅ *To'lov qabul qilindi!*\n\n"
        "Plan: " + plan["name"] + "\n"
        "Muddat: 30 kun\n"
        "Videolar: " + ("Cheksiz" if plan_key == "premium" else str(plan["videos"])) + "\n\n"
        "Endi video dublyaj qilishingiz mumkin! 🎬",
        parse_mode="Markdown",
        reply_markup=main_keyboard(uid)
    )

async def on_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    state = user_states.get(uid, {})
    mode = state.get("mode")
    lang = state.get("lang", "uz")

    if mode != "dubbing":
        await update.message.reply_text("Avval rejim tanlang. /start")
        return

    if not is_subscribed(uid):
        await update.message.reply_text(
            "❌ Obuna kerak! /start bosing."
        )
        return

    await update.message.reply_text("⏳ Video qayta ishlanmoqda... (bir necha daqiqa kuting)")

    file = await update.message.video.get_file()
    path = "video_" + str(uid) + ".mp4"
    await file.download_to_drive(path)

    try:
        out = do_dubbing(path, lang)
        use_video(uid)
        user = get_user(uid)
        vl = "Cheksiz" if user["plan"] == "premium" else str(user["videos_left"])
        with open(out, "rb") as f:
            await update.message.reply_video(
                video=f,
                caption="✅ Dublyaj tayyor! (" + get_lang_name(lang) + ")\nQolgan videolar: " + vl
            )
        os.remove(out)
    except Exception as e:
        await update.message.reply_text("❌ Xato: " + str(e))
    finally:
        if os.path.exists(path):
            os.remove(path)

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Video dublyaj uchun /start bosing.")


# ─────────────────────────────
# BOTNI ISHGA TUSHIRISH
# ─────────────────────────────

def main():
    print("Bot ishga tushmoqda...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.VIDEO, on_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    print("Bot tayyor! Telegramda /start bosing.")
    app.run_polling()

if __name__ == "__main__":
    main()
