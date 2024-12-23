import os
import logging

from flask import Flask, request, jsonify
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Dispatcher
import openai

# Загрузка переменных окружения
load_dotenv()  # В локальной среде берем из .env, на Render - из Dashboard

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Инициализация
app = Flask(__name__)

# Логгер (чтобы видеть ошибки в консоли Render и локально)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настраиваем OpenAI
openai.api_key = OPENAI_API_KEY

# Создаем инстанс бота
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Dispatcher для обработки апдейтов
dispatcher = Dispatcher(bot, None, use_context=True)

# Хранилище истории диалогов (для простоты - в памяти)
# В реальном проекте можно хранить в Redis или базе
user_conversations = {}

# Заранее прописанный system_prompt (логика этапов, общие правила)
SYSTEM_PROMPT = """
Ты — умный чат-бот для туристического бизнеса. 
Твоя задача — общаться с клиентами, выяснять их интересы и продавать туры.

Вот краткий сценарий этапов:
1) Приветствие (спросить, чем можно помочь, можешь ли задать пару вопросов для понимания нужд).
2) Выявление потребностей (задавай вопросы, не переходи к презентации, пока не поймешь, чего хочет клиент).
3) Презентация тура (с фокусом на преимущества, цену, выгоду).
4) Доп. вопросы, закрытие сделки (способы оплаты).

Отвечай дружелюбно, четко, задавая по одному уточняющему вопросу за раз.
При этом будь креативен, но не отклоняйся от темы. 
Если клиент пропадает, при следующем сообщении можно кратко напомнить о туре.
"""

def generate_response(user_id, user_message):
    """
    Функция для обращения к OpenAI GPT-4 и генерации ответа.
    Храним весь контекст диалога в user_conversations[user_id].
    """

    # Если диалога еще нет, инициализируем
    if user_id not in user_conversations:
        user_conversations[user_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    # Добавляем сообщение пользователя в историю
    user_conversations[user_id].append({"role": "user", "content": user_message})

    try:
        # Запрос к ChatCompletion
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=user_conversations[user_id],
            temperature=0.7,
            max_tokens=2000
        )

        assistant_reply = response.choices[0].message["content"]

        # Добавляем ответ ассистента в историю
        user_conversations[user_id].append({"role": "assistant", "content": assistant_reply})

        return assistant_reply

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return "Извините, возникла ошибка при подключении к ИИ. Попробуйте позже."


@app.route("/")
def index():
    return "Hello, this is your new Telegram bot backend!"

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Точка входа для запросов от Telegram (webhook).
    """
    try:
        update_json = request.get_json(force=True)
        update = Update.de_json(update_json, bot)
        dispatcher.process_update(update)
    except Exception as e:
        logger.error(f"webhook error: {e}")
    return jsonify({"status": "ok"})

# Обработчик всех текстовых сообщений
# Вместо классических хендлеров, создаем callback, который вручную дергается
def process_telegram_update(update, context):
    try:
        message = update.message.text.strip()
        user_id = update.effective_user.id

        # Генерируем ответ через OpenAI
        bot_reply = generate_response(user_id, message)

        # Отправляем ответ
        context.bot.send_message(chat_id=update.effective_chat.id, text=bot_reply)

    except Exception as e:
        logger.error(f"Handler error: {e}")

# Регистрируем обработчик в Dispatcher (MessageHandler аналог)
dispatcher.add_handler_callback(process_telegram_update)

if __name__ == "__main__":
    # При локальном запуске
    app.run(host="0.0.0.0", port=5000, debug=True)
