import telebot
from telebot.types import ReplyKeyboardRemove
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import logging

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройки Google Sheets
SHEET_NAME = "[SS] Saturn"
SERVICE_ACCOUNT_FILE = "service_account.json"

# Состояния диалога
GET_NICKNAME, GET_POINTS, GET_SQUAD_POWER = range(3)

# Глобальные переменные
current_sheet_name = "Лист1"
MODERATOR_CHAT_ID = 123456789  # Замените на ваш Telegram ID

# Инициализация бота
bot = telebot.TeleBot("YOUR_BOT_TOKEN")  # Замените на ваш токен

# Хранилище данных пользователей
user_data = {}


# Авторизация в Google Sheets
def get_google_client():
    try:
        scope = ["https://spreadsheets.google.com/feeds",
                 "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Ошибка при авторизации в Google Sheets: {e}")
        raise


def get_google_sheet(sheet_name=None):
    try:
        client = get_google_client()
        spreadsheet = client.open(SHEET_NAME)

        if sheet_name:
            try:
                return spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                worksheets = spreadsheet.worksheets()
                if worksheets:
                    last_sheet = worksheets[-1]
                    new_sheet = last_sheet.duplicate(new_sheet_name=sheet_name)
                    return new_sheet
                else:
                    return spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20)
        return spreadsheet.sheet1
    except Exception as e:
        logger.error(f"Ошибка при получении листа: {e}")
        raise


def find_nickname_row(sheet, nickname):
    try:
        nicknames = sheet.col_values(1)
        for idx, nick in enumerate(nicknames, start=1):
            if nick.lower() == nickname.lower():
                return idx
        return None
    except Exception as e:
        logger.error(f"Ошибка при поиске ника: {e}")
        return None


# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    user_data[user_id] = {'state': GET_NICKNAME}

    bot.send_message(
        message.chat.id,
        "Введи свой ник (регистр не важен):",
        reply_markup=ReplyKeyboardRemove()
    )


# Обработчик команды /set_sheet (только для модератора)
@bot.message_handler(commands=['set_sheet'])
def set_sheet(message):
    if message.from_user.id != MODERATOR_CHAT_ID:
        bot.reply_to(message, "❌ Эта команда только для модераторов!")
        return

    user_id = message.from_user.id
    user_data[user_id] = {'state': 'MODERATOR_SET_SHEET'}

    bot.send_message(
        message.chat.id,
        "Введи название листа (например, 'Лист2'):",
        reply_markup=ReplyKeyboardRemove()
    )


# Обработчик текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    state = user_data.get(user_id, {}).get('state')

    if state == GET_NICKNAME:
        process_nickname(message)
    elif state == GET_POINTS:
        process_points(message)
    elif state == GET_SQUAD_POWER:
        process_squad_power(message)
    elif state == 'MODERATOR_SET_SHEET':
        process_moderator_sheet(message)


def process_nickname(message):
    user_id = message.from_user.id
    nickname = message.text.strip()

    if not nickname:
        bot.send_message(message.chat.id, "Ник не может быть пустым. Попробуй ещё раз:")
        return

    sheet = get_google_sheet(current_sheet_name)
    row = find_nickname_row(sheet, nickname)

    if row:
        user_data[user_id] = {'state': GET_POINTS, 'row': row}
        bot.send_message(message.chat.id, "Ник найден! Теперь введи количество очков:")
    else:
        next_row = len(sheet.col_values(1)) + 1
        sheet.update_cell(next_row, 1, nickname)
        user_data[user_id] = {'state': GET_POINTS, 'row': next_row}
        bot.send_message(message.chat.id, "Ник добавлен! Теперь введи количество очков:")


def process_points(message):
    user_id = message.from_user.id
    points_text = message.text.strip()

    if not re.match(r"^\d+$", points_text):
        bot.send_message(message.chat.id, "Нужно ввести число! Попробуй ещё раз:")
        return

    points = int(points_text)
    row = user_data[user_id]['row']
    sheet = get_google_sheet(current_sheet_name)

    sheet.update_cell(row, 2, points)
    user_data[user_id]['state'] = GET_SQUAD_POWER
    bot.send_message(message.chat.id, "Теперь введи мощь отряда:")


def process_squad_power(message):
    user_id = message.from_user.id
    power_text = message.text.strip()

    if not re.match(r"^\d+$", power_text):
        bot.send_message(message.chat.id, "Нужно ввести число! Попробуй ещё раз:")
        return

    power = int(power_text)
    row = user_data[user_id]['row']
    sheet = get_google_sheet(current_sheet_name)

    sheet.update_cell(row, 5, power)
    bot.send_message(message.chat.id, "✅ Данные сохранены!")
    user_data.pop(user_id, None)  # Удаляем данные пользователя


def process_moderator_sheet(message):
    global current_sheet_name
    sheet_name = message.text.strip()

    try:
        sheet = get_google_sheet(sheet_name)
        current_sheet_name = sheet_name
        bot.send_message(message.chat.id, f"✅ Теперь данные будут сохраняться в лист '{sheet_name}'!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}. Попробуй ещё раз:")
        return

    user_data.pop(message.from_user.id, None)  # Удаляем данные модератора


if __name__ == "__main__":
    logger.info("Бот запущен")
    bot.infinity_polling()
