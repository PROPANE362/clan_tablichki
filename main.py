import telebot
from telebot.types import ReplyKeyboardRemove
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'  # Логи будут записываться в файл bot.log
)
logger = logging.getLogger(__name__)

# Настройки Google Sheets
SHEET_NAME = "YOUR_TABLE_NAME"
SERVICE_ACCOUNT_FILE = "service_account.json"

# Состояния диалога
GET_NICKNAME, GET_POINTS, GET_SQUAD_POWER = range(3)

# Глобальные переменные
current_sheet_name = "Лист1"
MODERATOR_CHAT_ID = 12345678  # Замените на ваш Telegram ID

# Инициализация бота
bot = telebot.TeleBot("YOUR_TG_API_KEY")  # Замените на ваш токен

# Хранилище данных пользователей
user_data = {}


def log_sheet_change(old_sheet, new_sheet):
    logger.info(f"Изменение текущего листа: с '{old_sheet}' на '{new_sheet}'")


def log_data_update(sheet_name, nickname, points=None, power=None):
    log_message = f"Данные обновлены в листе '{sheet_name}': НИК - {nickname}"
    if points is not None:
        log_message += f", СЧЕТ - {points}"
    if power is not None:
        log_message += f", МОЩЬ - {power}"
    logger.info(log_message)


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
                    logger.info(f"Создан новый лист: '{sheet_name}'")
                    return new_sheet
                else:
                    new_sheet = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20)
                    logger.info(f"Создан новый лист: '{sheet_name}' (первый лист в таблице)")
                    return new_sheet
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
    logger.info(f"Пользователь {user_id} начал взаимодействие")


# Обработчик команды /set_sheet (только для модератора)
@bot.message_handler(commands=['set_sheet'])
def set_sheet(message):
    if message.from_user.id != MODERATOR_CHAT_ID:
        bot.reply_to(message, "❌ Эта команда только для модераторов!")
        logger.warning(f"Пользователь {message.from_user.id} попытался использовать команду для модератора")
        return

    user_id = message.from_user.id
    user_data[user_id] = {'state': 'MODERATOR_SET_SHEET'}

    bot.send_message(
        message.chat.id,
        "Введи название листа (например, 'Лист2'):",
        reply_markup=ReplyKeyboardRemove()
    )
    logger.info(f"Модератор {user_id} начал смену листа")


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
        user_data[user_id] = {'state': GET_POINTS, 'row': row, 'nickname': nickname}
        bot.send_message(message.chat.id, "Ник найден! Теперь введи количество очков:")
        logger.info(f"Найден существующий ник '{nickname}' в строке {row}")
    else:
        next_row = len(sheet.col_values(1)) + 1
        sheet.update_cell(next_row, 1, nickname)
        user_data[user_id] = {'state': GET_POINTS, 'row': next_row, 'nickname': nickname}
        bot.send_message(message.chat.id, "Ник добавлен! Теперь введи количество очков:")
        logger.info(f"Добавлен новый ник '{nickname}' в строку {next_row}")


def process_points(message):
    user_id = message.from_user.id
    points_text = message.text.strip()

    if not re.match(r"^\d+$", points_text):
        bot.send_message(message.chat.id, "Нужно ввести число! Попробуй ещё раз:")
        return

    points = int(points_text)
    row = user_data[user_id]['row']
    nickname = user_data[user_id]['nickname']
    sheet = get_google_sheet(current_sheet_name)

    sheet.update_cell(row, 2, points)
    user_data[user_id]['state'] = GET_SQUAD_POWER
    user_data[user_id]['points'] = points
    bot.send_message(message.chat.id, "Теперь введи мощь отряда:")

    log_data_update(current_sheet_name, nickname, points=points)


def process_squad_power(message):
    user_id = message.from_user.id
    power_text = message.text.strip()

    if not re.match(r"^\d+$", power_text):
        bot.send_message(message.chat.id, "Нужно ввести число! Попробуй ещё раз:")
        return

    power = int(power_text)
    row = user_data[user_id]['row']
    nickname = user_data[user_id]['nickname']
    points = user_data[user_id]['points']
    sheet = get_google_sheet(current_sheet_name)

    sheet.update_cell(row, 5, power)
    bot.send_message(message.chat.id, "✅ Данные сохранены!")

    log_data_update(current_sheet_name, nickname, points=points, power=power)
    user_data.pop(user_id, None)  # Удаляем данные пользователя


def process_moderator_sheet(message):
    global current_sheet_name
    user_id = message.from_user.id
    sheet_name = message.text.strip()
    old_sheet_name = current_sheet_name

    try:
        sheet = get_google_sheet(sheet_name)
        current_sheet_name = sheet_name
        bot.send_message(message.chat.id, f"✅ Теперь данные будут сохраняться в лист '{sheet_name}'!")
        log_sheet_change(old_sheet_name, current_sheet_name)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}. Попробуй ещё раз:")
        logger.error(f"Ошибка при смене листа: {e}")
        return

    user_data.pop(user_id, None)  # Удаляем данные модератора


if __name__ == "__main__":
    logger.info("Бот запущен")
    bot.infinity_polling()
