import os
import telebot
from googletrans import Translator
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

# DIQQAT: Qo'shtirnoq ichiga o'zingizning bot tokeningizni yozing!
BOT_TOKEN = "8251116644:AAHG_von0pdx5zcytFCcFjxP3DcmFfwDPkA" 

bot = telebot.TeleBot(BOT_TOKEN)
translator = Translator()

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Salom! Men matnlarni tarjima qiluvchi botman. Menga xabar yuboring!")

@bot.message_handler(func=lambda message: True)
def translate_message(message):
    try:
        text_to_translate = message.text
        detected = translator.detect(text_to_translate)
        target_lang = 'en' if detected.lang == 'uz' else 'uz'
        translated = translator.translate(text_to_translate, dest=target_lang)
        bot.reply_to(message, translated.text)
    except Exception as e:
        bot.reply_to(message, "Tarjimada xatolik bo'ldi.")

if __name__ == '__main__':
    bot.infinity_polling()
    
