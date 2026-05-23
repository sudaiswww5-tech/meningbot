import os
import telebot
from deep_translator import GoogleTranslator
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot ishlamoqda!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

Thread(target=run).start()

# DIQQAT: Bu yerga o'zingizning bot tokeningizni yozing!
BOT_TOKEN = "8251116644:AAHG_von0pdx5zcytFCcFjxP3DcmFfwDPkA
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Salom! Men matnlarni avtomatik tarjima qiluvchi botman. Menga matn yuboring!")

@bot.message_handler(func=lambda message: True)
def translate_message(message):
    try:
        text_to_translate = message.text
        
        # Birinchi tilni aniqlab olamiz (agar xatolik bo'lsa, inglizcha deb hisoblaydi)
        try:
            detected_lang = GoogleTranslator().detect(text_to_translate)
        except:
            detected_lang = 'en'
            
        # Agar yozilgan matn o'zbekcha bo'lsa -> inglizchaga, boshqa tilda bo'lsa -> o'zbekchaga tarjima qiladi
        target_lang = 'en' if detected_lang == 'uz' else 'uz'
        
        translated = GoogleTranslator(source='auto', target=target_lang).translate(text_to_translate)
        bot.reply_to(message, translated)
    except Exception as e:
        bot.reply_to(message, "Tarjimada kutilmagan xatolik bo'ldi.")

if __name__ == '__main__':
    bot.infinity_polling()
    
    
